"""autoplan.py — какое по счёту сообщение переводится автоматически.

Счётчик серии (pos) двигают обычные сообщения И команды /to /lto /l /wt /s /st
(см. engine.is_counted_command). Остальные команды счётчик не двигают.
Слова-паразиты при этом переводятся в КАЖДОМ сообщении, вне зависимости
от номера в серии (см. engine.wrap_fillers)."""
import random


class AutoPlan:
    def __init__(self, cfg):
        self.cfg = cfg
        self.pos = 0              # сколько сообщений уже отправлено в текущей серии
        self.target = None        # номер (1..N) переводимого сообщения в серии
        self.seed = random.random()

    def n(self):
        try:
            return max(1, int(self.cfg.get("auto_every", 4)))
        except (TypeError, ValueError):
            return 4

    def mode(self):
        return str(self.cfg.get("auto_position", "last")).strip().lower()

    def is_random(self):
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

    def changed(self):
        """Настройки изменились — номер переводимого сообщения выбрать заново."""
        self.target = None

    def is_auto(self):
        """Будет ли автоматически переведено СЛЕДУЮЩЕЕ отправляемое сообщение."""
        if not self.cfg.get("auto_mode"):
            return False
        self._sync()
        return self.pos + 1 == self.target

    def advance(self):
        """Вызывается после отправки сообщения (обычного или /to /lto /l /wt /s /st)."""
        self._sync()
        self.pos += 1
        if self.pos >= self.n():
            self.pos, self.target = 0, None
        self.seed = random.random()

    def reroll(self):
        """Выбрать другой фрагмент в текущем сообщении."""
        self.seed = random.random()

    def label(self):
        if not self.cfg.get("auto_mode"):
            return ""
        self._sync()
        s = f"авто {self.pos + 1}/{self.n()}"
        if self.is_auto():
            return s + " · это сообщение переводится (Ctrl+R — другой фрагмент)"
        if not self.is_random():
            s += f", перевод на {self.target}-м"
        return s