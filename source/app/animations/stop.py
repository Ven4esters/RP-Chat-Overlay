"""Stop-key validation and polling for animation playback.

The watcher reads key state without capturing it from the game. Win32 imports
remain lazy so the animation rule and settings modules stay importable elsewhere.
"""

from __future__ import annotations

import sys
import threading
from typing import Callable

from app.config import log


# ------------------------------------------------------- клавиша остановки
class StopWatcher(threading.Thread):
    """Следит за клавишей остановки, не забирая её у игры.

    Watches the stop key without taking it away from the game.

    RegisterHotKey перехватил бы клавишу целиком, а остановка анимации в игре —
    это обычная игровая клавиша (по умолчанию F). Поэтому состояние клавиши
    читается через GetAsyncKeyState: игра получает нажатие как обычно, а модуль
    узнаёт о нём со стороны.
    RegisterHotKey would swallow the key, while the in-game animation stop is an
    ordinary game key (F by default). So the key state is read through
    GetAsyncKeyState: the game gets the press as usual and the module notices it
    from the side.
    """

    POLL = 0.04  # 25 раз в секунду / 25 times a second

    def __init__(
        self, spec: str, callback: Callable[[], None], active_fn: Callable[[], bool] | None = None
    ) -> None:
        super().__init__(name="anims-stop", daemon=True)
        self.spec = spec or ""
        self.callback = callback
        self.active_fn = active_fn
        self._stop_flag = threading.Event()
        self._pressed = False
        self._vk = 0
        self._mods = 0
        self._ok = self._prepare()

    # --- подготовка ---
    def _prepare(self) -> bool:
        """Разобрать клавишу и взять функции Windows / parse the key, load Win32."""
        if sys.platform != "win32" or not self.spec.strip():
            return False
        try:
            from app.hotkey import parse_hotkey

            self._mods, self._vk = parse_hotkey(self.spec)
        except Exception as error:
            log.warning("Анимации: клавиша остановки «%s» не разобрана (%s)", self.spec, error)
            return False
        return self._vk > 0

    def _down(self, vk: int) -> bool:
        """Нажата ли клавиша прямо сейчас / is the key down right now."""
        try:
            import ctypes

            return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
        except Exception:
            return False

    def _mods_down(self) -> bool:
        from app.hotkey import MODS

        if not self._mods:
            return True
        pairs = (
            (MODS["alt"], 0x12),
            (MODS["ctrl"], 0x11),
            (MODS["shift"], 0x10),
            (MODS["win"], 0x5B),
        )
        return all(self._down(vk) for mask, vk in pairs if self._mods & mask)

    # --- работа ---
    def stop(self) -> None:
        self._stop_flag.set()

    def run(self) -> None:
        """Опрос клавиши; колбэк — на передний фронт нажатия.

        Poll the key; the callback fires on the rising edge only, so holding the
        key does not repeat the stop over and over.
        """
        if not self._ok:
            return
        while not self._stop_flag.wait(self.POLL):
            try:
                down = self._down(self._vk) and self._mods_down()
                if down and not self._pressed:
                    if self.active_fn is None or self.active_fn():
                        self.callback()
                self._pressed = down
            except Exception:
                log.exception("Анимации: сбой опроса клавиши остановки")
                return


# клавиша остановки: одна клавиша и, при желании, модификаторы
# the stop key: one key and, optionally, modifiers
STOP_KEY_MODS = ("ctrl", "alt", "shift", "win")
STOP_KEY_NAMED = (
    "space",
    "tab",
    "insert",
    "delete",
    "home",
    "end",
    "pageup",
    "pagedown",
    "pause",
    "`",
)
VAL_EMPTY_STOP_KEY = "клавиша остановки не задана"
VAL_BAD_STOP_KEY = "нужна ровно одна клавиша: буква, цифра, F1–F24 или Space"
VAL_UNKNOWN_STOP_KEY = "такая клавиша не поддерживается"


def stop_key_problem(spec: str) -> str:
    """Проверка клавиши остановки; пустая строка — всё в порядке.

    Validation of the stop key; an empty string means it is fine.

    Одиночная буква здесь разрешена: в игре анимацию прекращает обычная клавиша
    (по умолчанию F), и забирать её у игры нельзя.
    A single letter is allowed here: in the game an ordinary key (F by default)
    stops the animation, and the module must not take it away from the game.
    """
    parts = [part.strip().lower() for part in str(spec or "").split("+") if part.strip()]
    if not parts:
        return VAL_EMPTY_STOP_KEY
    keys = [part for part in parts if part not in STOP_KEY_MODS]
    if len(keys) != 1:
        return VAL_BAD_STOP_KEY
    key = keys[0]
    letter = len(key) == 1 and key.isascii() and key.isalnum()
    function = key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24
    if not (letter or function or key in STOP_KEY_NAMED):
        return VAL_UNKNOWN_STOP_KEY
    return ""
