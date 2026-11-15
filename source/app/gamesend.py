"""Окно игры: поиск, фокус, ввод в чат (Windows, ctypes) / game window input.

Модуль отвечает за всё, что происходит за пределами оверлея: находит окно
GTA V или FiveM, выводит его вперёд, открывает чат клавишей T, вставляет текст
и отправляет его. Работает только на Windows: используется Win32 API.
This module owns everything outside the overlay: it finds the GTA V or FiveM
window, brings it to the front, opens the chat with the T key, pastes the text
and submits it. Windows only, it talks to the Win32 API.

Правила / rules
---------------
  * фокус чужому процессу Windows просто так не отдаёт — используется
    AttachThreadInput и несколько попыток; Windows does not hand focus to
    another process directly, so AttachThreadInput and retries are used;
  * все задержки берутся из конфигурации: медленный сервер не теряет текст;
    every delay comes from the configuration, so a slow server is not an issue;
  * при ошибке текст остаётся в буфере обмена — игрок вставит его сам;
    on failure the text stays in the clipboard for a manual paste.
"""
import ctypes
import ctypes.wintypes as wt
import os
import time
from collections import namedtuple

from app.config import log

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _IU(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _IU)]


ENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
user32.GetForegroundWindow.restype = wt.HWND
for _n in ("SetForegroundWindow", "BringWindowToTop", "IsWindow", "IsIconic", "IsWindowVisible"):
    getattr(user32, _n).argtypes = [wt.HWND]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.EnumWindows.argtypes = [ENUMPROC, wt.LPARAM]
user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wt.UINT
user32.MapVirtualKeyW.argtypes = [wt.UINT, wt.UINT]
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.GetCurrentThreadId.restype = wt.DWORD

VK_RETURN, VK_CONTROL, VK_MENU, VK_V, VK_ESCAPE = 0x0D, 0x11, 0x12, 0x56, 0x1B
Win = namedtuple("Win", "hwnd title cls exe w h")


# ---------- поиск окна ----------
def _exe(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        n = wt.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return os.path.basename(buf.value).lower()
    finally:
        kernel32.CloseHandle(h)
    return ""


def list_windows() -> list[Win]:
    """Все видимые окна Windows с их процессами / every visible window and its process.

    Нужен для поиска окна игры и для ключа --find-game.
    Used to find the game window and by the --find-game flag.
    """
    out = []

    def cb(hwnd, _):
        try:
            if user32.IsWindowVisible(hwnd):
                r = wt.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                cls = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls, 256)
                title = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, title, 256)
                pid = wt.DWORD(0)
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                out.append(Win(hwnd, title.value, cls.value, _exe(pid.value),
                               r.right - r.left, r.bottom - r.top))
        except Exception:
            pass
        return True

    proc = ENUMPROC(cb)
    user32.EnumWindows(proc, 0)
    return out


def is_game(w: Win, cfg) -> bool:
    """Похоже ли окно на игру / does this window look like the game.

    Проверяются класс окна (grcWindow), имя процесса (gta5.exe, FiveM) и
    список исключений из настроек.
    The window class, the process name and the extra processes from the
    settings are all taken into account.
    """
    exes = {"gta5.exe", "gta5_enhanced.exe"} | {str(e).lower() for e in cfg.get("game_extra_exes", [])}
    if w.cls == cfg.get("game_window_class", "grcWindow") or w.exe in exes:
        return True
    return w.exe.startswith(("fivem", "cfx")) and "gtaprocess" in w.exe


def find_game(cfg) -> int | None:
    """Окно игры с самой большой площадью или None / the largest game window."""
    c = [w for w in list_windows() if w.w > 200 and w.h > 200 and is_game(w, cfg)]
    return max(c, key=lambda w: w.w * w.h).hwnd if c else None


class GameTracker:
    """Кэширует окно игры, повторный поиск не чаще раза в 2 секунды.

    Caches the game window and looks for it at most once every two seconds, so
    the overlay does not enumerate windows on every keystroke.
    """

    def __init__(self, cfg):
        self.cfg, self._h, self._t = cfg, None, 0.0

    def get(self, force: bool = False) -> int | None:
        """Дескриптор окна игры / the game window handle (or None)."""
        if self._h and not force and user32.IsWindow(self._h):
            return self._h
        if force or time.time() - self._t > 2.0:
            self._t = time.time()
            self._h = find_game(self.cfg)
        elif self._h and not user32.IsWindow(self._h):
            self._h = None
        return self._h


def window_rect(hwnd) -> tuple[int, int, int, int] | None:
    """Прямоугольник окна в пикселях экрана / the window rectangle in screen pixels."""

    r = wt.RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return r.left, r.top, r.right, r.bottom
    return None


# ---------- фокус и ввод ----------
def is_fg(hwnd) -> bool:
    """Окно в фокусе? / is the window in the foreground?"""
    return user32.GetForegroundWindow() == hwnd


def _kb(vk=0, scan=0, flags=0):
    i = INPUT()
    i.type = 1
    i.ki.wVk, i.ki.wScan, i.ki.dwFlags = vk, scan, flags
    return i


def _send(*items):
    arr = (INPUT * len(items))(*items)
    if user32.SendInput(len(items), arr, ctypes.sizeof(INPUT)) != len(items):
        log.warning("SendInput отправил не всё: %s", ctypes.get_last_error())


def _vk_event(vk, up=False):
    return _kb(0, user32.MapVirtualKeyW(vk, 0), 0x8 | (0x2 if up else 0))   # SCANCODE


def tap(vk: int, hold: float = 0.05) -> None:
    """Нажать и отпустить клавишу с короткой паузой / press and release a key."""

    _send(_vk_event(vk))
    time.sleep(hold)
    _send(_vk_event(vk, True))


def paste() -> None:
    """Ctrl+V в активное окно / send Ctrl+V to the focused window."""

    _send(_vk_event(VK_CONTROL))
    time.sleep(0.05)
    tap(VK_V)
    time.sleep(0.05)
    _send(_vk_event(VK_CONTROL, True))


def type_text(text: str) -> None:
    """Посимвольный ввод Unicode-текста / type the text character by character."""

    data = text.encode("utf-16-le")
    for k in range(0, len(data), 2):
        u = int.from_bytes(data[k:k + 2], "little")
        _send(_kb(0, u, 0x4), _kb(0, u, 0x4 | 0x2))                          # UNICODE
        time.sleep(0.008)


def focus(hwnd, tries: int = 3) -> bool:
    """Вывести окно игры на передний план / bring the game window to the front.

    Windows не отдаёт фокус чужому процессу напрямую, поэтому используется
    AttachThreadInput и несколько попыток.
    Windows does not hand focus to another process directly, so AttachThreadInput
    and a few retries are used.
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
    for n in range(tries):
        if is_fg(hwnd):
            return True
        cur = kernel32.GetCurrentThreadId()
        tids = {user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None),
                user32.GetWindowThreadProcessId(hwnd, None)} - {0, cur}
        att = [t for t in tids if user32.AttachThreadInput(cur, t, True)]
        try:
            if n:                                   # запасной приём: «тап» Alt
                _send(_kb(VK_MENU, 0, 0), _kb(VK_MENU, 0, 0x2))
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            for t in att:
                user32.AttachThreadInput(cur, t, False)
        time.sleep(0.08)
    return is_fg(hwnd)


def _ms(cfg, key, default):
    time.sleep(max(0, int(cfg.get(key, default))) / 1000)


def chat_key_vk(cfg):
    """Виртуальный код клавиши чата (по умолчанию T)."""
    key = (str(cfg.get("game_chat_key", "t")).strip().upper() or "T")[0]
    return ord(key)


def open_chat(cfg, hwnd) -> bool:
    """Открыть чат игры клавишей T / open the in-game chat with the chat key.

    Сначала открыть чат игры (T), чтобы окружающие видели, что вы пишете:
    игра в фокус → T → пауза. Чат остаётся открытым, пока пользователь печатает
    в оверлее. Возвращает True, если чат, скорее всего, открыт.
    Opens the game chat with the chat key, so other players see that you are
    typing: focus the game, press the key and wait a little. Returns True when
    the chat is most likely open.
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    if not focus(hwnd):
        log.warning("Не удалось переключиться в игру для открытия чата")
        return False
    _ms(cfg, "game_focus_delay_ms", 150)
    vk = chat_key_vk(cfg)
    log.info("Открываю чат игры клавишей %s", chr(vk))
    tap(vk)
    _ms(cfg, "game_open_delay_ms", 300)
    return is_fg(hwnd)


def close_chat(cfg, hwnd):
    """Закрыть уже открытый чат игры (Esc) — отмена без отправки."""
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    if not focus(hwnd):
        return False
    _ms(cfg, "game_focus_delay_ms", 150)
    tap(VK_ESCAPE)
    _ms(cfg, "game_open_delay_ms", 300)
    return True


def send_to_open_chat(cfg, hwnd, text):
    """Вставить текст в УЖЕ открытый чат игры и отправить (Enter).

    Клавиша чата (T) НЕ нажимается — чат был открыт заранее при открытии
    оверлея, поэтому он не мигает и не закрывается повторно.
    """
    lost = (False, "Игра потеряла фокус во время ввода.")
    if not hwnd or not user32.IsWindow(hwnd):
        return False, "Окно игры не найдено."
    if not focus(hwnd):
        return False, "Не удалось переключиться в игру (она запущена от администратора?)."
    _ms(cfg, "game_focus_delay_ms", 150)
    log.info("Вставка в открытый чат игры, режим %s, %r", cfg.get("game_input_mode"), text)
    if cfg.get("game_input_mode", "paste") == "type":
        type_text(text)
    else:
        paste()
    _ms(cfg, "game_paste_delay_ms", 150)
    if cfg.get("game_submit", True):
        if not is_fg(hwnd):
            return lost
        tap(VK_RETURN)
    return True, ""


def send_chat(cfg, hwnd, text, chat_open=False):
    """Отправка в игру. Возвращает (успех, сообщение).

    chat_open=True  — чат уже открыт (оверлей открыл его заранее):
                      только вставка + Enter, без повторного T.
    chat_open=False — старый путь: фокус → T → вставка → Enter (запасной).
    """
    if chat_open:
        return send_to_open_chat(cfg, hwnd, text)
    lost = (False, "Игра потеряла фокус во время ввода.")
    if not hwnd or not user32.IsWindow(hwnd):
        return False, "Окно игры не найдено."
    if not focus(hwnd):
        return False, "Не удалось переключиться в игру (она запущена от администратора?)."
    _ms(cfg, "game_focus_delay_ms", 150)
    vk = chat_key_vk(cfg)
    log.info("Отправка в игру: клавиша %s, режим %s, %r", chr(vk), cfg.get("game_input_mode"), text)
    tap(vk)
    _ms(cfg, "game_open_delay_ms", 300)
    if not is_fg(hwnd):
        return lost
    if cfg.get("game_input_mode", "paste") == "type":
        type_text(text)
    else:
        paste()
    _ms(cfg, "game_paste_delay_ms", 150)
    if cfg.get("game_submit", True):
        if not is_fg(hwnd):
            return lost
        tap(VK_RETURN)
    return True, ""