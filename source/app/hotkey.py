"""Глобальная горячая клавиша / the global hotkey (RegisterHotKey).

Клавиша занята только пока в фокусе игра (или игра не найдена); в остальных
программах сочетание остаётся свободным и работает как обычно.
The key is grabbed only while the game has focus (or when the game is not
found); everywhere else the combination stays free for other programs.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import re
import threading
import time

from app.config import log
from app.gamesend import user32

WM_HOTKEY, MOD_NOREPEAT = 0x0312, 0x4000
MODS = {"alt": 1, "ctrl": 2, "control": 2, "shift": 4, "win": 8}
NAMED = {"insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23, "pageup": 0x21,
         "pagedown": 0x22, "pause": 0x13, "tab": 0x09, "space": 0x20, "`": 0xC0}

user32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]
user32.RegisterHotKey.restype = wt.BOOL
user32.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]
user32.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
user32.PeekMessageW.restype = wt.BOOL


def parse_hotkey(spec: str) -> tuple[int, int]:
    """Строка вида "ctrl+shift+f6" -> (модификаторы, виртуальный код клавиши).

    A string like "ctrl+shift+f6" to (modifier mask, virtual key code).
    Raises ValueError for an unknown key name.
    """
    mods, vk = 0, 0
    for p in (x.strip().lower() for x in spec.split("+") if x.strip()):
        m = re.fullmatch(r"f(\d{1,2})", p)
        if p in MODS:
            mods |= MODS[p]
        elif p in NAMED:
            vk = NAMED[p]
        elif m and 1 <= int(m.group(1)) <= 24:
            vk = 0x70 + int(m.group(1)) - 1
        elif len(p) == 1 and p.isascii() and p.isalnum():
            vk = ord(p.upper())
        else:
            raise ValueError(f"неизвестная клавиша «{p}»")
    if not vk:
        raise ValueError("не указана клавиша")
    return mods, vk


class HotkeyThread(threading.Thread):
    """Поток горячей клавиши / the hotkey thread.

    Регистрирует сочетание, пока активна игра, и снимает регистрацию, когда
    игрок переключился в другое окно. Registers the combination while the game
    is active and releases it as soon as another window comes to the front.
    """

    def __init__(self, spec: str, callback, active_fn, on_fail) -> None:
        super().__init__(daemon=True, name="hotkey")
        self.spec, self.callback, self.active_fn, self.on_fail = spec, callback, active_fn, on_fail
        self.stop_ev = threading.Event()

    def stop(self) -> None:
        """Попросить поток завершиться / ask the thread to stop."""
        self.stop_ev.set()

    def run(self) -> None:
        """Основной цикл: регистрация клавиши и ожидание нажатия.

        The main loop: register the key, then poll the message queue for presses.
        """
        try:
            mods, vk = parse_hotkey(self.spec)
        except ValueError as e:
            log.error("hotkey %r: %s", self.spec, e)
            self.on_fail(f"Неверное значение hotkey «{self.spec}»: {e}.")
            return
        reg, last, msg = False, 0.0, wt.MSG()
        try:
            while not self.stop_ev.is_set():
                if time.time() - last > 0.3:
                    last = time.time()
                    try:
                        want = bool(self.active_fn())
                    except Exception:
                        want = True
                    if want and not reg:
                        reg = bool(user32.RegisterHotKey(None, 1, mods | MOD_NOREPEAT, vk))
                        if not reg:
                            log.error("RegisterHotKey(%s) не удалось, код %s",
                                      self.spec, ctypes.get_last_error())
                            self.on_fail(f"Сочетание {self.spec} занято другой программой. "
                                         f"Измените «hotkey» в data\\config.json.")
                            return
                        log.info("Горячая клавиша %s включена", self.spec)
                    elif reg and not want:
                        user32.UnregisterHotKey(None, 1)
                        reg = False
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == WM_HOTKEY:
                        self.callback()
                time.sleep(0.02)
        finally:
            if reg:
                user32.UnregisterHotKey(None, 1)
