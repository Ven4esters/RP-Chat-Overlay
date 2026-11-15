"""Какое по счёту сообщение переводится автоматически / auto-translation counter.

Счётчик серии (pos) двигают обычные сообщения И команды /to /lto /l /wt /s /st
(см. engine.is_counted_command). Остальные команды счётчик не двигают.
Слова-паразиты при этом переводятся в КАЖДОМ сообщении, вне зависимости
от номера в серии (см. engine.wrap_fillers).
The series counter is advanced by ordinary messages and by the counted commands
/to /lto /l /wt /s /st; other commands do not move it. Filler words are still
translated in every message, whatever the position in the series.
"""
from __future__ import annotations

import random
from typing import Any, Mapping


class AutoPlan:
    """Номер переводимого сообщения в серии / which message of the series is translated.

    Настройки читаются из конфигурации каждый раз, поэтому изменение частоты
    в окне настроек сразу действует на следующую серию.
    Settings are read from the configuration on every call, so a new frequency
    takes effect with the next series.
    """

    def __init__(self, cfg: Mapping[str, Any]) -> None:
        self.cfg = cfg
        self.pos = 0              # сколько сообщений уже отправлено в текущей серии
        self.target = None        # номер (1..N) переводимого сообщения в серии
        self.seed = random.random()

    def n(self) -> int:
        """Длина серии: каждое N-е сообщение / the series length."""
        try:
            return max(1, int(self.cfg.get("auto_every", 4)))
        except (TypeError, ValueError):
            return 4

    def mode(self) -> str:
        """Какое сообщение переводить: last / first / random / номер / position."""
        return str(self.cfg.get("auto_position", "last")).strip().lower()

    def is_random(self) -> bool:
        """Выбор случайный / is the position picked at random."""
        return self.mode() in ("random", "rand", "случайное")

    def _roll(self):
        n, p = self.n(), self.mode()
        if self.is_random():
            return random.randint(1, n)
        if p == "first":
            return 1
        if p.isdigit():
            return min(max(1, int(p)), n)
        return n

    def _sync(self):
        n = self.n()
        if self.pos >= n:
            self.pos, self.target = 0, None
        if self.target is None or self.target > n:
            self.target = self._roll()

    def changed(self) -> None:
        """Настройки изменились — номер переводимого сообщения выбрать заново.

        Settings changed: forget the current position and pick a new one.
        """
        self.target = None

    def is_auto(self) -> bool:
        """Будет ли автоматически переведено СЛЕДУЮЩЕЕ отправляемое сообщение.

        Will the NEXT message be translated automatically?
        """
        if not self.cfg.get("auto_mode"):
            return False
        self._sync()
        return self.pos + 1 == self.target

    def advance(self) -> None:
        """Вызывается после отправки сообщения (обычного или /to /lto /l /wt /s /st).

        Called after a message is sent, ordinary or counted.
        """
        self._sync()
        self.pos += 1
        if self.pos >= self.n():
            self.pos, self.target = 0, None
        self.seed = random.random()

    def reroll(self) -> None:
        """Выбрать другой фрагмент в текущем сообщении / pick another fragment."""
        self.seed = random.random()

    def label(self) -> str:
        """Подпись для строки состояния оверлея / overlay status line text."""
        if not self.cfg.get("auto_mode"):
            return ""
        self._sync()
        s = f"авто {self.pos + 1}/{self.n()}"
        if self.is_auto():
            return s + " · это сообщение переводится (Ctrl+R — другой фрагмент)"
        if not self.is_random():
            s += f", перевод на {self.target}-м"
        return s