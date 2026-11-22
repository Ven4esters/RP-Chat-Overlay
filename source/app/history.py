"""Отмена и повтор правок в окне настроек / undo and redo in the settings.

Зачем это нужно / why it exists
-------------------------------
В окне настроек правки делаются и запоминаются по разделам: словарь одного
языка, сокращения, правила анимаций, всё остальное. Один общий Ctrl+Z здесь
вреден: отмена, вернувшая три таблицы сразу, отправляет игрока искать, что
именно изменилось. Поэтому история своя у каждого раздела, и Ctrl+Z в разделе
отменяет только его шаги.

Edits in the settings window belong to sections: one language's glossary, the
abbreviations, the animation rules, everything else. One global Ctrl+Z would be
harmful here, because undoing three tables at once leaves the player hunting for
what actually changed. Each section therefore keeps its own history, and Ctrl+Z
takes back only that section's steps.

Как это работает / how it works
-------------------------------
История хранит не действия, а снимки состояния раздела: сравнение и откат
получаются тривиальными, а любая правка — от ввода буквы до перетаскивания
строки — попадает в историю одинаково.

The history keeps snapshots rather than actions: comparing and rolling back is
trivial, and every edit — a typed letter or a dragged row — lands in it the same
way.

Что важно / the important part
------------------------------
Отмена обязана снимать правку и с ДИСКА, а не только с экрана. Иначе игра
продолжит играть анимацию, которую игрок только что отменил. Поэтому снимок
несёт и то, что уже записано в config.json и в файлы словарей.

Undo must take the change off the DISK as well, not just off the screen.
Otherwise the game keeps playing the animation the player just undid. That is why
a snapshot carries what was already written to config.json and to the glossary
files.
"""

from __future__ import annotations

from typing import Any

# Сколько шагов помнит раздел. Десять — минимум из требований; сорок хватает,
# чтобы отменить целую правку таблицы, не задумываясь о счётчике.
# How many steps a section remembers. Ten is the required minimum; forty is
# enough to take back a whole table edit without watching the counter.
DEPTH = 40

# Правки одного и того же поля, разделённые паузой меньше этой, считаются одной.
# Edits of the same field closer than this are one step.
COALESCE_SEC = 1.0


class Section:
    """История одного раздела / the history of one section.

    Записи хранятся парой «снимок до» и «снимок после»: при отмене состояние
    возвращается к «до», при повторе — к «после». Так не нужно хранить одно
    состояние дважды, и повтор работает без повторных правок.

    Entries are pairs of "before" and "after": undo restores the former, redo the
    latter. Nothing is stored twice and redo needs no replaying of edits.
    """

    def __init__(self, key: str) -> None:
        self.key = key
        self._entries: list[tuple[Any, Any, str]] = []
        self._index = 0  # сколько записей применено / how many are applied
        self._stamp = ""  # подпись поля для склейки / field tag for coalescing
        self._when = -COALESCE_SEC

    # --- запись ---
    def record(self, before: Any, after: Any, tag: str = "") -> bool:
        """Запомнить шаг; повтор истории при этом сбрасывается.

        Remember a step; the redo part of the history is dropped, as in every
        editor: an edit after an undo starts a new branch.

        Возвращает True, если шаг добавлен / True when a step was added.
        """
        if before == after:
            return False  # ничего не изменилось — шага нет
        if self._index < len(self._entries):
            del self._entries[self._index :]
        self._entries.append((before, after, tag))
        if len(self._entries) > DEPTH:
            del self._entries[0]
        self._index = len(self._entries)
        self._stamp = tag
        return True

    def record_field(self, before: Any, after: Any, tag: str, now: float) -> bool:
        """Запомнить правку поля, склеивая быстрый ввод в один шаг.

        Remember a field edit, coalescing fast typing into one step.

        Возвращает True, если шаг действительно добавлен: по этому признаку окно
        понимает, что можно обновить подписи.

        Returns True when a step was really added, so the window knows whether
        to refresh the captions.
        """
        if before == after:
            return False
        continuing = (
            self._stamp == tag
            and self._entries
            and self._index == len(self._entries)
            and self._entries[-1][2] == tag
            and now - self._when < COALESCE_SEC
        )
        if continuing:
            # тот же ввод продолжается: обновляем «после» у последнего шага
            # the same typing continues: the last step's "after" is refreshed
            last_before = self._entries[-1][0]
            self._entries[-1] = (last_before, after, tag)
            self._when = now
            return False
        self.record(before, after, tag)
        self._when = now
        return True

    # --- чтение ---
    def can_undo(self) -> bool:
        """Есть ли что отменять / is there anything to undo."""
        return self._index > 0

    def can_redo(self) -> bool:
        """Есть ли что повторять / is there anything to redo."""
        return self._index < len(self._entries)

    def undo(self) -> Any:
        """Снимок «до» последнего шага или None / the previous state, or None."""
        if not self.can_undo():
            return None
        self._index -= 1
        self._stamp = ""
        return self._entries[self._index][0]

    def redo(self) -> Any:
        """Снимок «после» отменённого шага или None / the state to reapply."""
        if not self.can_redo():
            return None
        state = self._entries[self._index][1]
        self._index += 1
        self._stamp = ""
        return state

    def reset(self) -> None:
        """Забыть историю раздела / forget the section's history."""
        self._entries.clear()
        self._index = 0
        self._stamp = ""
        self._when = -COALESCE_SEC


class History:
    """Истории всех разделов окна / the histories of every section."""

    def __init__(self) -> None:
        self._sections: dict[str, Section] = {}

    def section(self, key: str) -> Section:
        """История раздела по имени; создаётся при первом обращении.

        The history of a section, created on first use.
        """
        if key not in self._sections:
            self._sections[key] = Section(key)
        return self._sections[key]

    def can_undo(self, key: str) -> bool:
        return self.section(key).can_undo()

    def can_redo(self, key: str) -> bool:
        return self.section(key).can_redo()

    def reset(self, key: str | None = None) -> None:
        """Забыть историю одного раздела или всех / forget one section or all."""
        if key is None:
            for section in self._sections.values():
                section.reset()
            return
        self.section(key).reset()
