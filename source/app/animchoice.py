"""Оверлей выбора анимации / the animation chooser overlay.

Зачем / why
-----------
Один ключ часто подходит к нескольким анимациям: «Опёрся руками» — это и
``anim_counterleanbar`` (локти на стойке), и ``anim_leanrail`` (опёрся на
перила). Раньше играла только первая, и игрок не мог выбрать.

Модуль показывает поверх игры небольшое окно со списком вариантов: название,
описание и имя команды. Игрок выбирает мышью или с клавиатуры, и в чат игры
уходит нужный ``/anim``.

One keyword often fits several animations: «Опёрся руками» is both
``anim_counterleanbar`` (elbows on the bar) and ``anim_leanrail`` (leaning on a
railing). Before this, only the first one played and the player had no choice.

This module shows a small window above the game with the variants: title,
description and command name. The player picks with the mouse or the keyboard and
the chosen ``/anim`` goes into the game chat.

Как это вызывается / how it is called
-------------------------------------
Очередь анимаций вызывает :func:`ask` из своего потока и ждёт ответа. Окно
живёт в главном потоке Qt, поэтому :func:`ask` перебрасывает показ в него через
сигнал и блокируется на ``threading.Event`` с таймаутом — игра не зависает,
если окно почему-то не показалось.

The animation queue calls :func:`ask` from its own thread and waits for the
answer. The window lives in the Qt main thread, so :func:`ask` hands the display
over through a signal and blocks on a ``threading.Event`` with a timeout — the
game never hangs if the window could not be shown for some reason.

Окно закрывается только вручную / the window closes only by hand
---------------------------------------------------------------
Таймаута нет: окно висит справа, пока игрок сам его не закроет. Так можно
спокойно рассмотреть варианты, передумать и нажать другой — окно остаётся на
месте. Esc и «Ничего» означают «ничего не играть»: игрок нажал именно это, и
подставлять вариант за него нельзя.

There is no timeout: the window sits on the right until the player closes it.
That leaves time to read the variants, change your mind and pick another one —
the window stays where it is. Esc and "Nothing" mean "play nothing": that is what
was pressed, and substituting a variant would be putting words in the player's
mouth.
"""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import i18n
from app.config import log

# таймаута нет: окно закрывает сам игрок / no timeout: the player closes the window
CHOICE_TIMEOUT_S = 0.0
# сколько ждать показа окна, прежде чем счесть, что его нет
# how long to wait for the window to appear before deciding there is none
SHOW_TIMEOUT_S = 5.0

# сколько ждать ввода, прежде чем показать следующее меню. Игрок уже набирает
# цифру или тянется мышью, и подменить список под курсором — худшее, что можно
# сделать: он выберет не то, что хотел.
# how long to wait for input before showing the next menu. The player may already
# be typing a digit or reaching for the mouse, and swapping the list under the
# pointer is the worst thing to do: he would pick something he did not mean.
SETTLE_S = 0.6

STYLE = """
#choiceBox { background: rgba(16,16,22,250); border: 1px solid #3a3a4a;
             border-radius: 12px; }
#choiceTitle { color: #ffffff; font-size: 17px; font-weight: 600; }
#choiceKeys { color: #8a8a96; font-size: 11px; }
#choiceEmpty { color: #8a8a96; font-size: 12px; }

/* карточка варианта: рамка, номер, название, описание, команда
   a variant card: frame, number, title, description, command */
QFrame#choiceCard {
    background: #1e1e28; border: 1px solid #33333f; border-radius: 9px;
}
QFrame#choiceCard:hover { background: #262636; border-color: #5b8cff; }
QFrame#choiceCard:focus { background: #2a2a3c; border: 2px solid #5b8cff; }
QFrame#choiceCard[chosen="true"] { background: #1b2b1f; border: 2px solid #4ad07a; }
QLabel#choiceMark { color: #4ad07a; font-size: 11px; font-weight: 700; }
QLabel#choiceNum {
    color: #c9d4ff; background: #2a3350; border: 1px solid #3f4d78;
    border-radius: 6px; font-size: 13px; font-weight: 700;
}
QLabel#choiceLabel { color: #ffffff; font-size: 15px; font-weight: 600; }
QLabel#choiceDesc { color: #b9b9c8; font-size: 12px; }
QLabel#choiceNoDesc { color: #6a6a78; font-size: 12px; font-style: italic; }
QLabel#choiceName { color: #7b88b8; font-size: 11px; }

/* заголовок группы вариантов и черта между группами
   a variants group title and the rule between groups */
QLabel#choiceGroup {
    color: #9fb0ff; font-size: 11px; font-weight: 700; padding-top: 4px;
}
QFrame#choiceSep { background: #3a3a4c; border: none;
                   min-height: 1px; max-height: 1px; }

QPushButton#choiceCancel {
    background: #24242e; border: 1px solid #3a3a46; border-radius: 6px;
    padding: 7px 16px; color: #c8c8d2; font-size: 12px;
}
QPushButton#choiceCancel:hover { background: #2e2e3a; border-color: #5b8cff; }

/* список внутри окна: без этой строки QScrollArea рисует свой белый фон и
   окно выглядит как белая дыра в тёмной рамке
   the list inside the window: without this QScrollArea paints its own white
   background and the window looks like a white hole in a dark frame */
QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #3a3a4a; border-radius: 4px;
                              min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #5b8cff; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent; }
"""


class _Card(QFrame):
    """Один вариант анимации: номер, название, описание и имя команды.

    One animation variant: number, title, description and command name.

    Раньше вариантом была ``QPushButton`` с раскладкой внутри. Кнопка считает
    высоту по своему тексту (а он пустой — текста у неё нет), поэтому весь
    вариант схлопывался в тонкую полоску и строки наезжали друг на друга.
    ``QFrame`` раскладку уважает: у карточки честная высота по содержимому.
    The variant used to be a ``QPushButton`` with a layout inside. A button sizes
    itself from its own text (which is empty), so the whole variant collapsed into
    a thin strip and the lines overlapped. A ``QFrame`` honours the layout, so the
    card gets an honest height from its content.
    """

    def __init__(self, index, choice, on_pick, parent=None):
        super().__init__(parent)
        self.index = index
        self.choice = choice
        self._on_pick = on_pick
        self.setObjectName("choiceCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setProperty("chosen", False)
        self.mark = None

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 14, 10)
        row.setSpacing(12)

        # номер — то, что нажимать на клавиатуре; у 10+ вариантов номера нет
        # the number is what the player types; variants past 9 get no number
        badge = QLabel(str(index + 1) if index < 9 else "")
        badge.setObjectName("choiceNum")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(26, 26)
        row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title = QLabel(choice.label())
        title.setObjectName("choiceLabel")
        title.setWordWrap(True)
        title_row.addWidget(title, 1)
        # метка «играет» появляется на выбранной карточке
        # the "playing" mark appears on the chosen card
        self.mark = QLabel("")
        self.mark.setObjectName("choiceMark")
        self.mark.setVisible(False)
        title_row.addWidget(self.mark, 0)
        text.addLayout(title_row)

        # описание пустым не оставляем: пустая строка выглядит как ошибка
        # the description is never empty: a blank line looks like a bug
        description = (choice.description or "").strip()
        desc = QLabel(description or i18n.t("Без описания"))
        desc.setObjectName("choiceDesc" if description else "choiceNoDesc")
        desc.setWordWrap(True)
        text.addWidget(desc)

        command = QLabel(f"/anim {choice.name}")
        command.setObjectName("choiceName")
        command.setWordWrap(True)
        text.addWidget(command)

        row.addLayout(text, 1)

    def set_mark(self, playing: bool) -> None:
        """Поставить или снять метку «играет» / set or clear the "playing" mark."""
        if self.mark is None:
            return
        self.mark.setText(i18n.t("играет") if playing else "")
        self.mark.setVisible(bool(playing))

    def mouseReleaseEvent(self, event):
        """Клик по карточке = выбор варианта / a click picks the variant."""
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._on_pick(self.index)
            return
        super().mouseReleaseEvent(event)


class ChoiceWindow(QWidget):
    """Окно выбора: список вариантов поверх игры.

    The chooser window: a list of variants above the game.

    Показывается без рамки справа поверх игры, но с фокусом — иначе клавиатура
    осталась бы у игры. После выбора окно **не закрывается**: анимация играет, а
    окно висит рядом, и другой вариант можно нажать в любой момент — он и
    заменит играющую анимацию. Закрывает окно только сам игрок (Esc или
    «Ничего»).

    Frameless and always on top on the right, but focused — otherwise the keyboard
    would stay with the game. After a pick the window does **not** close: the
    animation plays and the window stays beside it, so another variant can be
    pressed at any moment and it replaces the playing animation. Only the player
    closes it (Esc or "Nothing").

    ``done_callback`` зовётся на каждый выбор и получает ``Choice`` или None.
    ``done_callback`` is called on every pick with a ``Choice`` or None.
    """

    def __init__(self, title, subtitle, variants, done_callback, parent=None, on_closed=None):
        super().__init__(parent)
        self.done_callback = done_callback
        # меню, которое сейчас показано: выбор уходит в него, а не в глобальное
        # состояние — иначе второй ключ в сообщении крал бы ответ первого
        # the menu on screen: a pick goes into it, not into global state —
        # otherwise the second keyword in a message would steal the first's answer
        self.entry = None
        # кого позвать после выбора: очередь меню решает, показывать ли следующее
        # who to call after a pick: the menu queue decides whether to move on
        self.on_pick = None
        # кого известить, когда окно закроют: сам игрок, а не таймер
        # who to tell when the window is closed: the player, not a timer
        self.on_closed = on_closed
        self._variants = list(variants)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(STYLE)
        self.setWindowTitle(i18n.t("Выбор анимации"))
        # Esc закрывает окно штатно: closeEvent снимает меню с очереди
        # Esc closes the window properly: closeEvent takes the menu off the queue

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        box = QFrame()
        box.setObjectName("choiceBox")
        outer.addWidget(box)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(8)

        head = QLabel(title or i18n.t("Какую анимацию играть?"))
        head.setObjectName("choiceTitle")
        head.setWordWrap(True)
        lay.addWidget(head)
        self._head = head

        self._sub = None
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("choiceEmpty")
            sub.setWordWrap(True)
            lay.addWidget(sub)
            self._sub = sub

        # список прокручивается: вариантов может быть много, а окно не должно
        # вырасти выше экрана
        # the list scrolls: there may be many variants, and the window must not
        # grow taller than the screen
        scroll = QScrollArea()
        self._scroll = scroll
        scroll.setWidgetResizable(False)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        holder_lay = QVBoxLayout(holder)
        holder_lay.setContentsMargins(0, 0, 0, 0)
        holder_lay.setSpacing(6)
        self.buttons = []
        # Группы: варианты одной группы идут подряд под её названием, разные
        # группы разделены чертой. Одного названия мало — подпись без черты
        # читается как ещё один вариант, и список сливается в кашу.
        # Groups: the variants of one group sit together under its title and
        # different groups are separated by a rule. A bare heading is not enough —
        # without the rule it reads as just another variant and the list blurs.
        self._groups = []  # (название, [карточки]) / (title, [cards])
        previous = None
        for index, choice in enumerate(self._variants):
            group = (choice.group or "").strip()
            if index == 0 or group != previous:
                if index > 0:
                    holder_lay.addWidget(self._separator())
                if group:
                    holder_lay.addWidget(self._group_head(group))
                    self._groups.append((group, []))
                else:
                    self._groups.append(("", []))
            card = self._item(index, choice)
            holder_lay.addWidget(card)
            self._groups[-1][1].append(card)
            previous = group
        holder_lay.addStretch(1)
        scroll.setWidget(holder)
        # хотя бы пара вариантов должна быть видна, даже на тесном экране:
        # остальное докручивается
        # a couple of variants must be visible even on a tight screen; the rest
        # scrolls
        scroll.setMinimumHeight(0)
        lay.addWidget(scroll, 1)
        self._holder = holder

        bottom = QHBoxLayout()
        hint = QLabel(
            i18n.t(
                "Окно не закроется само: другой вариант можно "
                "выбрать в любой момент · Esc — закрыть"
            )
        )
        hint.setObjectName("choiceKeys")
        hint.setWordWrap(True)
        bottom.addWidget(hint, 1)
        cancel = QPushButton(i18n.t("Закрыть"))
        cancel.setObjectName("choiceCancel")
        cancel.setAutoDefault(False)
        # Кнопка ЗАКРЫВАЕТ окно. Раньше она звала `_answer(None)`, а тот только
        # сообщал «ничего не выбрано» и окно не трогал: нажатие выглядело так,
        # будто ничего не произошло, и выйти можно было только по Esc.
        # The button CLOSES the window. It used to call `_answer(None)`, which only
        # reported "nothing picked" and left the window alone: the click looked
        # like nothing happened, and Esc was the only way out.
        cancel.clicked.connect(self._close_clicked)
        bottom.addWidget(cancel)
        lay.addLayout(bottom)
        # Нижнюю строку держим отдельно: её высота резервируется при расчёте
        # размера первой. Иначе на тесном экране окно ужимается и «Закрыть»
        # уезжает за нижний край — выглядит так, будто кнопки нет совсем.
        # The bottom row is kept apart: its height is reserved first when the size
        # is worked out. Otherwise on a tight screen the window shrinks and
        # "Закрыть" goes past the bottom edge — it looks like there is no button.
        self._hint = hint
        self._cancel = cancel
        self._lay = lay

        self._fit()

    @staticmethod
    def _group_head(title: str) -> QWidget:
        """Название группы над её вариантами / the group title above its variants."""
        label = QLabel(title.upper())
        label.setObjectName("choiceGroup")
        label.setWordWrap(True)
        return label

    @staticmethod
    def _separator() -> QWidget:
        """Черта между группами / the rule between groups.

        Именно ``QFrame``, а не голый ``QWidget``: у обычного виджета фон из
        таблицы стилей не рисуется без WA_StyledBackground, и черта просто
        исчезла бы — разделения групп не было бы видно.
        A ``QFrame`` and not a bare ``QWidget``: a plain widget does not paint a
        stylesheet background without WA_StyledBackground, and the rule would
        simply vanish — the group split would be invisible.
        """
        line = QFrame()
        line.setObjectName("choiceSep")
        line.setFrameShape(QFrame.Shape.NoFrame)
        line.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        line.setFixedHeight(1)
        return line

    def _item(self, index, choice) -> QWidget:
        """Карточка одного варианта / one variant card."""
        card = _Card(index, choice, self._choose)
        self.buttons.append(card)
        return card

    def _choose(self, index):
        """Выбрать вариант, не закрывая окно / pick a variant without closing."""
        if not (0 <= index < len(self._variants)):
            return
        self._mark_chosen(index)
        self._answer(self._variants[index])

    def clear_marks(self):
        """Снять пометки «играет»: правило доиграло.

        Clear the "playing" marks: the rule has finished.
        Окно при этом остаётся открытым — игрок закроет его сам.
        The window stays open — the player closes it himself.
        """
        for card in self.buttons:
            card.setProperty("chosen", False)
            card.style().unpolish(card)
            card.style().polish(card)
            card.set_mark(False)

    def _mark_chosen(self, index):
        """Подсветить выбранный вариант: видно, что сейчас играет.

        Highlight the chosen variant, so it is clear what is playing now.

        Окно больше не закрывается после выбора, поэтому «какой сейчас» надо
        показывать: рамка и метка «играет» на выбранной карточке.
        The window no longer closes after a pick, so "which one is playing" has to
        be shown: a frame and a "playing" mark on the chosen card.
        """
        for position, card in enumerate(self.buttons):
            card.setProperty("chosen", position == index)
            card.style().unpolish(card)
            card.style().polish(card)
            card.set_mark(position == index)

    def _fit(self):
        """Размер и место окна: по центру экрана, не выше рабочей области.

        The window size and place: centred on screen, no taller than the work
        area.

        Высота считается по содержимому вручную. ``adjustSize()`` для окна
        ограничен экраном (две трети высоты), поэтому на мониторе 1080p список
        из пяти вариантов обрезался до двух с половиной. Считаем так: всё, кроме
        списка, плюс настоящая высота списка, и уже это ограничиваем экраном.
        The height is measured from the content by hand. ``adjustSize()`` on a
        window is capped by the screen (two thirds of its height), so on a 1080p
        monitor a list of five variants was cut to two and a half. The sum is:
        everything but the list, plus the list's real height, and that is what
        gets clamped to the screen.
        """
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        # Ширину берём по содержимому: на 420 описания уже переносятся, на 620
        # строки становятся слишком длинными.
        # The width follows the content: below 420 the descriptions wrap early,
        # past 620 the lines get too long.
        width = max(420, min(self.sizeHint().width(), 620))
        if area:
            width = min(width, max(int(area.width() * 0.9), 320))
        self.setFixedWidth(width)

        needed = max(self._content_height(width), self.minimumSizeHint().height())
        if area:
            # Keep the chooser inside the working area. The list is the flexible
            # region, so it scrolls before the title or close action is clipped.
            max_height = max(1, area.height() - 24)
            needed = min(max(needed, min(200, max_height)), max_height)
        else:
            needed = max(needed, 200)
        self.resize(width, needed)
        if area:
            # справа по центру: игра слева, окно не закрывает то, что играет
            # on the right, centred: the game is on the left, and the window does
            # not cover what is being played
            margin = 24
            self.move(
                area.right() - width - margin, area.top() + (area.height() - self.height()) // 2
            )

    def _content_height(self, width: int) -> int:
        """Сколько высоты просит содержимое при такой ширине.

        How much height the content asks for at this width.

        Считаем по частям, а не через ``layout().sizeHint()``: подсказка
        раскладки считается для уже назначенной ширины и на узком окне врёт —
        заголовок и подсказка переносятся на лишние строки, а окно выходит
        короче содержимого. Тогда нижняя строка с «Закрыть» уезжает за край.
        Parts are summed instead of trusting ``layout().sizeHint()``: the layout
        hint is computed for the width already set and lies on a narrow window —
        the title and the hint wrap into extra lines while the window ends up
        shorter than its content. Then the bottom row with "Закрыть" falls past
        the edge.
        """
        margins = self._lay.contentsMargins()
        spacing = self._lay.spacing()
        inner = max(width - margins.left() - margins.right(), 200)

        # Заголовок, подзаголовок и подсказка переносятся: меряем на своей
        # ширине, а не гадаем по одной строке.
        # The title, subtitle and hint wrap: they are measured at their own width
        # instead of guessed as a single line.
        def wrapped_height(label, extra=0):
            if label is None:
                return 0
            label.setFixedWidth(inner - (extra or 0))
            label.adjustSize()
            return label.sizeHint().height()

        head_h = wrapped_height(self._head)
        sub_h = wrapped_height(self._sub)
        # подсказка делит строку с кнопкой, поэтому её ширина меньше на кнопку
        # the hint shares the row with the button, so its width is smaller
        hint_h = wrapped_height(self._hint, extra=self._cancel.sizeHint().width() + 8)
        button_h = max(self._cancel.sizeHint().height(), 28)
        bottom_h = max(hint_h, button_h)
        self._cancel.setFixedHeight(button_h)

        holder = getattr(self, "_holder", None)
        if holder is not None:
            holder.setFixedWidth(inner)
            holder_lay = holder.layout()
            if holder_lay is not None:
                holder_lay.invalidate()
                holder_lay.activate()
            holder.adjustSize()
            list_h = max(holder.sizeHint().height(), holder.minimumSizeHint().height())
        else:
            list_h = 150
        # список не меньше двух карточек и не больше половины экрана
        # the list is at least two cards and at most half the screen
        list_h = max(min(list_h, 520), 150)

        return (
            margins.top() + margins.bottom() + head_h + sub_h + list_h + bottom_h + spacing * 4 + 8
        )

    # --- ответ ---
    def _answer(self, choice):
        """Сообщить выбор, оставив окно открытым.

        Report the pick and keep the window open.

        Вариант можно менять сколько угодно раз, пока окно открыто: повторный
        выбор того же варианта ничего не ломает — очередь просто заменит
        анимацию на ту же.
        The variant may change any number of times while the window is open:
        picking the same variant again breaks nothing — the queue just replaces
        the animation with the same one.
        """
        try:
            self.done_callback(choice)
        except Exception:
            log.exception("Выбор анимации: колбэк упал")
        if choice is not None and self.on_pick is not None:
            # первый выбор отвечает ожидающей очереди анимаций; каждый выбор
            # заодно откладывает показ следующего меню — игрок ещё выбирает
            # the first pick answers the waiting animation queue; every pick also
            # postpones the next menu — the player is still choosing
            try:
                self.on_pick()
            except Exception:
                log.exception("Выбор анимации: очередь меню не обновилась")

    def _close_clicked(self):
        """Нажата «Закрыть»: сообщить отказ и убрать окно.

        "Закрыть" was clicked: report the refusal and take the window down.

        Окно закрывается по-настоящему (``close()`` -> ``closeEvent``), а не
        просто скрывается: очередь меню должна узнать, что это меню больше не
        показывается.
        The window is really closed (``close()`` -> ``closeEvent``) rather than just
        hidden: the menu queue has to learn this menu is on screen no more.
        """
        self.close()

    def keyPressEvent(self, event):
        """Клавиатура: цифры, Enter и Esc / the keyboard: digits, Enter and Esc."""
        key = event.key()
        if key == Qt.Key.Key_Escape:
            # Esc — это «закрыть окно», а не «ничего не играть»: если анимация
            # уже выбрана и играет, окно просто убирается, ничего не меняя
            # Esc means "close the window", not "play nothing": if an animation
            # is already picked and playing, the window just goes away
            self.close()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._choose(0)
            return
        if Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
            index = key - Qt.Key.Key_1
            if index < len(self._variants):
                self._choose(index)
                return
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            # стрелки водят фокус по вариантам: мышью не обязательно
            # the arrows walk the focus over the variants: the mouse is optional
            self.focusNextPrevChild(key == Qt.Key.Key_Down)
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        """Закрытие окна игроком: если ничего не выбрано — правило пропускается.

        The player closes the window: if nothing was picked, the rule is skipped.

        Когда вариант уже выбран и играет, закрытие окна ничего не меняет —
        анимация продолжается. Если не выбрано ничего, ответ None означает
        «ничего не играть»: молчаливая подмена вариантом была бы хуже.
        When a variant is already picked and playing, closing the window changes
        nothing — the animation goes on. When nothing was picked, the None answer
        means "play nothing": silently substituting a variant would be worse.
        """
        # Закрытие окна всегда доносит до меню «дальше ничего»: если варианта не
        # выбирали, это отказ, а если выбирали — просто «меню закрыто».
        # Closing the window always carries "nothing further" to the menu: a refusal
        # when nothing was picked, and plain "the menu is closed" otherwise.
        try:
            self.done_callback(None)
        except Exception:
            log.exception("Выбор анимации: колбэк падения окна упал")
        if self.on_closed is not None:
            try:
                self.on_closed()
            except Exception:
                log.exception("Выбор анимации: колбэк закрытия окна упал")
        super().closeEvent(event)


class _Bridge(QObject):
    """Сигнал «показать окно» для перехода в главный поток Qt.

    The "show the window" signal, used to hop into the Qt main thread.
    """

    show = Signal(object)
    wake = Signal()  # пересобрать очередь меню / rebuild the menu queue
    hide = Signal()  # убрать окно / take the window away


def _key(rule):
    """Ключ правила для привязок / the rule's key for links."""
    return (getattr(rule, "id", None), getattr(rule, "keywords", ""))


def _grouped_order(variants) -> list:
    """Разложить варианты по группам, сохранив порядок внутри группы.

    Lay the variants out by group, keeping the order inside each group.

    Группы идут в порядке первого появления, варианты без группы — как были.
    Без этого одинаковые названия групп повторялись бы в списке, если в таблице
    строки одной группы стоят вразбивку: «А, Б, А» вместо «А, А, Б». Сортировка
    устойчивая — внутри группы ничего не переставляется.
    Groups follow their first appearance and ungrouped variants stay where they
    were. Without it the same group name would repeat in the list whenever the
    table has that group's rows split apart: "A, B, A" instead of "A, A, B". The
    sort is stable — nothing is reordered inside a group.
    """
    order = []
    buckets = {}
    for variant in variants:
        group = (getattr(variant, "group", "") or "").strip()
        if group not in buckets:
            buckets[group] = []
            order.append(group)
        buckets[group].append(variant)
    out = []
    for group in order:
        out.extend(buckets[group])
    return out


class _Menu:
    """Одно меню выбора: правило, варианты и всё, что о нём надо помнить.

    One choice menu: the rule, the variants and everything to remember about it.

    Меню живёт дольше своего окна: пока окно показывает другое меню, это ждёт в
    очереди и помнит уже сделанный выбор. Поэтому «нажал 2» по первому ключу
    меняет именно его анимацию, даже если на экране давно другое меню.
    A menu outlives its window: while the window shows another menu, this one
    waits in the queue and keeps the pick already made. That is why "pressed 2"
    for the first keyword changes exactly its animation, even when another menu
    has long been on screen.
    """

    def __init__(self, rule, variants, on_change=None):
        self.rule = rule
        self.variants = _grouped_order(variants)
        self.on_change = on_change
        self.first = threading.Event()  # первый ответ / the first answer
        self.shown = threading.Event()  # окно показано / the window is up
        self.picks = []  # [(Choice|None)] по порядку
        self.finished = False  # правило доиграло
        self.focused = False  # меню подняли повторно
        self.window = None  # окно, где оно сейчас
        self.settle_timer = None  # пауза перед следующим меню
        # сейчас ли это меню на экране: по этому признаку снимаются пометки
        # whether this menu is the one on screen: that decides the marks
        self.on_screen = False
        self.settle_until = 0.0  # до какого времени ждать паузу
        # чем сыграть выбор, если правило уже доиграло (ставит Runner)
        # what to play the pick with when the rule has already finished (set by
        # Runner)
        self.replay = None

    def matches(self, rule) -> bool:
        """Это меню того же правила / is this the menu of the same rule."""
        return _key(rule) == _key(self.rule)

    def current_index(self) -> int:
        """Какой вариант выбран сейчас, -1 если ещё нет.

        Which variant is picked right now, -1 when none is.
        """
        if not self.picks or self.picks[-1] is None:
            return -1
        last = self.picks[-1]
        for position, variant in enumerate(self.variants):
            if variant.name == last.name:
                return position
        return -1

    def pick(self, choice):
        """Игрок выбрал вариант в этом меню (главный поток Qt).

        The player picked a variant in this menu (Qt main thread).

        Первый выбор отвечает ожидающей очереди анимаций, следующие — меняют уже
        играющую анимацию.
        The first pick answers the waiting animation queue, the later ones change
        the animation already playing.
        """
        first = not self.picks
        self.picks.append(choice)
        if first:
            self.first.set()
        else:
            change = self.on_change
            if change is not None:
                try:
                    change(choice)
                except Exception:
                    log.exception("Выбор анимации: смена варианта не удалась")
                return
            # Правило доиграло (или доиграет раньше, чем очередь дойдёт) —
            # тогда выбор играет заново через `replay`.
            # The rule has finished (or will before the queue gets to it) — then
            # the pick plays again through `replay`.
            replay = self.replay
            if replay is not None:
                try:
                    replay(choice)
                except Exception:
                    log.exception("Выбор анимации: повторный запуск не удался")


class Chooser:
    """Связка «поток очереди -> главный поток -> ответ».

    The "queue thread -> main thread -> answer" link.

    Один экземпляр на программу: окно выборов не должно открываться дважды, и
    очередь анимаций одна.
    One instance per program: the chooser must not open twice, and the animation
    queue is a single one.
    """

    def __init__(self, timeout_s: float = CHOICE_TIMEOUT_S):
        # С asyncio-ожиданием не путать: timeout_s больше не используется, окно
        # закрывает сам игрок. Параметр оставлен, чтобы не ломать вызовы.
        # Not to be confused with an async wait: timeout_s is unused now, the
        # player closes the window. The parameter stays so calls do not break.
        self.timeout_s = timeout_s
        self._bridge = None
        self._window = None
        self._lock = threading.Lock()
        # Кто ждёт первого ответа; после него окно живёт само и сообщает о
        # смене варианта в `_on_change`.
        # Who waits for the first answer; after it the window lives on its own and
        # reports a variant change through `_on_change`.
        # Очередь меню: `_menus` — те, что ждут или показываются, `_order` — все
        # меню этой сессии, чтобы повторный ключ вернул своё меню, а не открыл
        # второе такое же.
        # The menu queue: `_menus` wait or show, `_order` keeps every menu of this
        # session so a repeated keyword brings back its own menu instead of opening
        # a second identical one.
        self._menus = []
        self._order = []
        self._timer_parent = None
        # один таймер паузы и один таймер повторного показа на всю программу
        # one settle timer and one re-show timer for the whole program
        self._settle_q: QTimer | None = None
        self._wake_q: QTimer | None = None
        # чем сыграть выбор заново, по правилу: очередь зовёт attach до создания
        # меню, поэтому привязка живёт здесь
        # what to replay a pick with, per rule: the queue calls attach before the
        # menu exists, so the link lives here
        self._replay_hooks = {}
        self.open = False

    def __call__(self, rule, on_change=None):
        """Экземпляр сам и есть функция выбора: ``chooser(rule)``.

        The instance is the chooser function itself: ``chooser(rule)``.

        Так очередь получает объект, а не обёртку: у него есть ``cancel`` и
        ``rule_finished``, которые обёртка бы спрятала.
        That way the queue gets an object rather than a wrapper: it has ``cancel``
        and ``rule_finished``, which a wrapper would hide.
        """
        return self.ask(rule, on_change=on_change)

    def rule_finished(self, rule=None):
        """Правило доиграло или его анимацию остановили: снять «играет».

        The rule has finished or its animation was stopped: clear "playing".

        Снимаем только у меню ЭТОГО правила: пометки соседнего меню к нему не
        относятся. Раньше снимались у любого видимого меню — из-за этого
        останавливал одно правило, а гасла пометка у другого.
        The marks are cleared only on THIS rule's menu: a neighbouring menu's marks
        are none of its business. Clearance used to hit whatever menu was visible,
        so stopping one rule blanked another one's mark.
        """
        window = self._window
        entry = getattr(window, "entry", None) if window is not None else None
        if entry is None:
            return
        if rule is not None and not entry.matches(rule):
            return
        try:
            window.clear_marks()
        except Exception:
            log.exception("Выбор анимации: не удалось снять пометки")

    def rule_stopped(self, rule=None):
        """Анимацию остановили (F или /sa): меню правила больше не живое.

        The animation was stopped (F or /sa): this rule's menu is no longer live.

        Останавливает игрок — значит и спрашивать по этому правилу больше нечего:
        меню уходит из очереди, и следующий тот же ключ открывает СВЕЖЕЕ меню, а
        не возвращает старое с уже отмеченным вариантом. Окно не закрываем: игрок
        может нажать другой вариант и сыграть заново — но пометку «играет» снимаем,
        в игре ведь ничего не идёт.
        The player stopped it, so there is nothing left to ask about this rule: the
        menu leaves the queue and the next hit of the same keyword opens a FRESH
        menu instead of bringing back the old one with a variant already marked.
        The window is not closed: the player may pick another variant and replay —
        but the "playing" mark is cleared, because nothing is playing any more.
        """
        with self._lock:
            dead = [entry for entry in self._order if rule is None or entry.matches(rule)]
            for entry in dead:
                if entry.settle_timer is not None:
                    entry.settle_timer.stop()
                    entry.settle_timer = None
                if entry in self._menus:
                    self._menus.remove(entry)
                if entry in self._order:
                    self._order.remove(entry)
                if not entry.picks:
                    entry.picks.append(None)
                entry.first.set()
                entry.finished = True
                entry.on_screen = False
        self.open = bool(self._menus)
        window = self._window
        entry = getattr(window, "entry", None) if window is not None else None
        if entry is not None and any(entry is gone for gone in dead):
            if not entry.picks or entry.picks[-1] is None:
                # по этому меню ничего не выбрано — спрашивать некого, окно
                # убираем: иначе на нём остаются кнопки, которые уже ничего не
                # делают
                # nothing was picked in this menu, so there is nobody to ask: the
                # window goes away, otherwise its buttons stay and do nothing
                if self._bridge is not None:
                    self._bridge.hide.emit()
                else:
                    self._close_window()
            else:
                # вариант уже играл — окно оставляем: игрок может выбрать
                # другой, и он сыграет заново; пометку «играет» снимаем
                # a variant was already playing — the window stays: the player may
                # pick another one and it replays; the "playing" mark is cleared
                try:
                    window.clear_marks()
                except Exception:
                    log.exception("Выбор анимации: не удалось снять пометки")
        log.info("Выбор анимации: анимацию остановили, меню правила снято")

    def _settle_timer(self) -> QTimer:
        """Один таймер паузы перед следующим меню / the single settle timer.

        Создаётся один раз в главном потоке. Раньше на каждое нажатие варианта
        заводился новый ``QTimer``, и они копились до закрытия программы: у
        каждого был родитель, живущий столько же, сколько приложение.
        Created once on the main thread. A new ``QTimer`` used to be made on every
        pick and they piled up until the program closed: each one had a parent
        that lives as long as the application.
        """
        if self._settle_q is None:
            if self._timer_parent is None:
                self._timer_parent = QObject()
            timer = QTimer(self._timer_parent)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self._settle_fired(timer))
            self._settle_q = timer
        return self._settle_q

    def _settle_fired(self, timer: QTimer) -> None:
        """Пауза вышла: решить, показывать ли следующее меню / the pause is over."""
        entry = getattr(timer, "entry", None)
        if entry is not None:
            self._advance(entry, timer)

    def _wake_timer(self) -> QTimer:
        """Один таймер «показать окно заново» / the single re-show timer.

        После закрытия окна новый показ откладывается на ``SETTLE_S``, чтобы окно
        не мигало на одном месте. Один таймер на все такие паузы, по той же
        причине, что и у ``_settle_timer``.
        After the window closes the next display waits ``SETTLE_S`` so the window
        does not blink in place. One timer for all such pauses, for the same
        reason as ``_settle_timer``.
        """
        if self._wake_q is None:
            if self._timer_parent is None:
                self._timer_parent = QObject()
            timer = QTimer(self._timer_parent)
            timer.setSingleShot(True)
            timer.timeout.connect(self._wake_fired)
            self._wake_q = timer
        return self._wake_q

    def _wake_fired(self) -> None:
        """Пауза после закрытия вышла: показать, что накопилось.

        The pause after closing is over: show whatever has piled up.
        """
        if self._bridge is not None:
            self._bridge.wake.emit()

    def _ensure_bridge(self) -> bool:
        """Создать мост и привязать его к главному потоку; False — Qt нет.

        Create the bridge and attach it to the main thread; False means Qt is not
        running.

        ``ask`` вызывается из потока очереди анимаций, а сигнал должен попасть в
        главный поток Qt — иначе окно не появится: у рабочего потока нет цикла
        событий, и объект, созданный в нём, свои сигналы не доставит. Поэтому
        мост сразу переезжает в поток приложения.
        ``ask`` runs on the animation queue thread, but the signal must reach the
        Qt main thread — otherwise the window never appears: the worker thread has
        no event loop, and an object created there does not deliver its signals. So
        the bridge immediately moves to the application thread.
        """
        if self._bridge is not None:
            return True
        application = QApplication.instance()
        if application is None:
            return False
        self._bridge = _Bridge()
        self._bridge.moveToThread(application.thread())
        self._bridge.show.connect(self._show, Qt.ConnectionType.QueuedConnection)
        # Очередь меню живёт в главном потоке: будить её сигналом обязательно,
        # иначе окно не появится, а ожидание в `ask` упрётся в SHOW_TIMEOUT_S.
        # The menu queue lives on the main thread: it must be woken by a signal,
        # otherwise no window appears and `ask` waits out SHOW_TIMEOUT_S.
        self._bridge.wake.connect(self._render, Qt.ConnectionType.QueuedConnection)
        self._bridge.hide.connect(self._close_window, Qt.ConnectionType.QueuedConnection)
        return True

    def ask(self, rule, on_change=None) -> "object | None":
        """Спросить игрока, какой вариант играть / ask which variant to play.

        Вызывается из потока очереди анимаций и блокируется до первого ответа
        или закрытия окна. Возвращает выбранный ``Choice`` или None.

        ``on_change`` зовётся на каждый следующий выбор, пока окно открыто:
        игрок меняет анимацию, не закрывая окно.

        В одном сообщении может сработать несколько ключей с выбором. Тогда окна
        не наслаиваются: у программы одно окно, а меню ждут своей очереди в
        ``self._menus``. Пока игрок не выбрал по текущему меню, следующее не
        открывается, поэтому «нажал 2» всегда попадает туда, что он видит.
        Several keywords with a choice may fire in one message. The windows never
        stack: the program has one window, and the menus wait their turn in
        ``self._menus``. The next one does not open until the player has picked in
        the current one, so "pressed 2" always lands where he is looking.

        Пока меню ждёт в очереди, оно помнит уже сделанный по нему выбор: если
        игрок вернётся к первому ключу и нажмёт другой вариант, заменится именно
        та анимация, а не последняя.
        While a menu waits in the queue it keeps the pick already made through it:
        when the player returns to the first keyword and presses another variant,
        that is the animation which changes, not the last one.
        Called from the animation queue thread and blocks until the first answer
        or the window's close. Returns the chosen ``Choice`` or None.
        ``on_change`` is called on every later pick while the window is open: the
        player swaps the animation without closing it.
        """
        variants = rule.variant_list()
        if not variants:
            return None
        with self._lock:
            if not self._ensure_bridge() and self._bridge is None:
                log.warning("Выбор анимации: Qt не запущен — спросить некого")
                return None
        entry = _Menu(rule, variants, on_change)
        with self._lock:
            entry.replay = self._replay_hooks.get(_key(rule))
        # вход в очередь: сразу поднимаем мост, чтобы окно показалось сразу,
        # если очереди нет
        # joining the queue: the bridge is raised at once so the window appears
        # immediately when nothing else is open
        with self._lock:
            self._menus.append(entry)
            self._order.append(entry)
        self._bridge.wake.emit()
        # Сначала ждём появления: это отдельное событие от ответа, иначе ответ
        # вернулся бы мгновенно, ещё до нажатия.
        # The appearance is a separate event from the answer, otherwise the answer
        # would come back at once, before anything was pressed.
        if not entry.shown.wait(SHOW_TIMEOUT_S):
            log.warning("Выбор анимации: окно не показалось за %d с", int(SHOW_TIMEOUT_S))
            with self._lock:
                if entry in self._menus:
                    self._menus.remove(entry)
                if entry in self._order:
                    self._order.remove(entry)
            return None
        if self.timeout_s:
            entry.first.wait(self.timeout_s)
        else:
            entry.first.wait()
        return entry.picks[0] if entry.picks else None

    # --- главный поток ---
    def _show(self, payload):
        """Показать окно с меню (главный поток Qt).

        Show the window with a menu (Qt main thread).
        """
        self._close_window()
        self._render()

    def _render(self):
        """Показать меню, до которого дошла очередь (главный поток Qt).

        Show the menu whose turn it is (Qt main thread).

        Одно окно переиспользуется: при переходе к следующему меню меняется
        только содержимое. Так игрок не видит, как окно мигает и прыгает.
        One window is reused: moving to the next menu only swaps the contents, so
        the player never sees the window blink and jump.
        """
        with self._lock:
            entry = self._menus[0] if self._menus else None
            waiting = len(self._menus) - 1 if entry is not None else 0
        if entry is None:
            # Очередь пуста. Если в окне уже отвеченное меню — оставляем его:
            # игрок может передумать и выбрать другой вариант. Новое меню,
            # пришедшее позже, просто займёт окно (это другая ветка).
            # The queue is empty. If the window shows an answered menu, keep it: the
            # player may change his mind and pick another variant. A menu arriving
            # later simply takes the window over (that is the other branch).
            if self._window is not None and self._window.entry is not None:
                return
            self._close_window()
            return
        if self._window is not None and self._window.entry is entry:
            return
        self._close_window()
        subtitle = i18n.t("Выбор отправится в чат игры как /anim.")
        if waiting > 0:
            subtitle += " " + i18n.tf("Ещё меню в очереди: %d — после этого.", waiting)
        window = ChoiceWindow(
            i18n.t("Какую анимацию вы собираетесь использовать?"),
            subtitle,
            entry.variants,
            entry.pick,
            on_closed=lambda: self._window_closed(entry),
        )
        window.entry = entry
        window.on_pick = lambda: self._settle(entry)
        self._window = window
        entry.window = window
        with self._lock:
            for item in self._order:
                item.on_screen = item is entry
        window.show()
        window.raise_()
        window.activateWindow()
        # останавливаемся на уже выбранном варианте: игрок мог вернуться к этому
        # ключу, чтобы поменять анимацию
        # the focus lands on the variant already picked: the player may have come
        # back to this keyword to change the animation
        index = entry.current_index()
        if 0 <= index < len(window.buttons):
            window.buttons[index].setFocus()
        if index >= 0:
            window._mark_chosen(index)
        entry.shown.set()

    def _window_closed(self, entry):
        """Окно закрыл игрок: меню снято с очереди.

        The player closed the window: the menu leaves the queue.

        Всё, что не выбрано, — не играет: и текущее меню, и те, что ждали. Но
        уже сыгранные и выбранные варианты остаются: закрытие окна не отменяет
        то, что игрок выбрал раньше.
        Whatever is unpicked does not play: the current menu and the ones waiting.
        What was already picked stays: closing the window does not undo the
        player's earlier choices.
        """
        with self._lock:
            was_first = bool(self._menus) and self._menus[0] is entry
            if entry in self._menus:
                self._menus.remove(entry)
            if entry in self._order:
                self._order.remove(entry)
        if self._window is not None and self._window.entry is entry:
            self._window = None
        if not entry.picks:
            entry.picks.append(None)
            # ничего не выбрано, и анимацию этого правила запускать незачем
            # nothing was picked, and this rule's animation need not start
            self._tell_replay(entry, None)
        entry.first.set()
        entry.finished = True
        self.open = bool(self._menus)
        log.info("Выбор анимации: окно закрыто игроком, в очереди меню: %d", len(self._menus))
        if was_first:
            # Следующее меню (если оно придёт) покажется не мгновенно: между
            # закрытием окна и новым показом должна быть пауза, иначе окно
            # мигает на одном месте.
            # The next menu, when it comes, is not shown instantly: a pause is
            # needed between closing and showing again, otherwise the window blinks
            # in place.
            self._wake_timer().start(int(SETTLE_S * 1000))

    @staticmethod
    def _tell_replay(entry, choice):
        """Сказать очереди анимаций «сыграть заново» или «снять».

        Tell the animation queue to replay or to drop.
        """
        replay = entry.replay
        if replay is None:
            return
        try:
            replay(choice)
        except Exception:
            log.exception("Выбор анимации: очередь анимаций не ответила")

    def _settle(self, entry) -> None:
        """Ответ по меню получен: решить, показывать ли следующее.

        An answer for the menu has arrived: decide whether to move on.

        Следующее меню показывается не сразу, а через ``SETTLE_S``: игрок может
        набирать цифру или уже вести мышь к другой строке. Если он нажмёт цифру
        ещё раз, ожидание сбрасывается и показ откладывается — значит, он ещё
        разбирается с этим меню, а не ждёт следующего.
        The next menu is shown after ``SETTLE_S`` rather than at once: the player
        may be typing a digit or already moving the pointer to another row. If he
        presses another digit, the wait is reset and the display postponed — he is
        still busy with this menu, not waiting for the next one.
        """
        if entry.settle_timer is not None:
            entry.settle_timer.stop()
            entry.settle_timer = None
        # Новый выбор продлевает паузу: пока игрок нажимает, следующее меню ждёт
        # a new pick extends the pause: while the player keeps pressing, the next
        # menu waits
        entry.settle_until = time.monotonic() + SETTLE_S
        # Таймеру нужен родитель из главного потока: сам Chooser живёт и в
        # рабочем потоке, поэтому родитель — маленький объект, созданный в
        # главном. Таймер тот же самый на все меню: раньше на каждое нажатие
        # заводился новый QTimer, и они копились до конца работы программы.
        # The timer needs a parent from the main thread: Chooser itself lives on
        # the worker thread too, so the parent is a small object made on main.
        # One timer serves every menu: a new QTimer used to be created on every
        # pick, and they piled up until the program exited.
        timer = self._settle_timer()
        timer.entry = entry
        entry.settle_timer = timer
        timer.start(int(SETTLE_S * 1000))

    def _advance(self, entry, timer):
        """Пора показать следующее меню / time to show the next menu.

        Пауза соблюдается не формально: если игрок только что нажал другую
        цифру, показ откладывается ещё раз. Он ещё выбирает — подменять список
        под его рукой нельзя.
        The pause is not merely nominal: if the player pressed another digit just
        now, the display is postponed again. He is still choosing, and swapping the
        list under his hand is not allowed.
        """
        if entry.settle_timer is timer:
            entry.settle_timer = None
        # Пауза отсчитывается от выбора, но продлевается только НОВЫМИ выборами.
        # Раньше здесь каждый раз сравнивалось «прошло ли SETTLE_S» с последним
        # выбором, и таймер перезапускался бесконечно: `time.monotonic()` при
        # перезапуске отставал на микросекунды от нужной точки, `left` всё время
        # был чуть больше нуля, и меню никогда не уходило из очереди. Следующее
        # меню из-за этого не показывалось вовсе.
        # The pause counts from the pick but is extended only by NEW picks. The old
        # code re-compared "has SETTLE_S passed" against the last pick and restarted
        # the timer forever: on each restart `time.monotonic()` was microseconds
        # short of the mark, `left` stayed just above zero, and the menu never left
        # the queue. That is why the next menu was never shown at all.
        if entry.settle_until and time.monotonic() < entry.settle_until - 0.01:
            left = entry.settle_until - time.monotonic()
            timer.entry = entry
            entry.settle_timer = timer
            timer.start(max(int(left * 1000), 10))
            return
        entry.settle_until = 0.0
        with self._lock:
            # Отвеченное меню уходит из очереди ВСЕГДА. Раньше последнее меню
            # здесь оставалось, чтобы окно не закрывалось, — и это ломало второе
            # меню: следующее срабатывание добавляло своё меню в хвост очереди,
            # `_render` продолжал показывать первое (оно ведь ещё «в очереди»), а
            # новое ждало своего показа до таймаута и пропускалось. Окно и так
            # не закрывается: его держит не очередь, а сам список меню.
            # An answered menu ALWAYS leaves the queue. The last one used to stay
            # here to keep the window open, and that broke the second menu: the
            # next hit appended its menu to the tail, `_render` kept showing the
            # first one (still "queued") and the new one waited for its display
            # until the timeout and was dropped. The window does not need the queue
            # to stay open: the menu list itself keeps it.
            if entry in self._menus:
                self._menus.remove(entry)
        self._render()

    def select(self, index: int = 0) -> bool:
        """Ответить по открытому меню (цифры, Enter).

        Answer the open menu (digits, Enter).
        Отвечаем именно по тому меню, которое игрок видит.
        The answer goes to the menu the player is looking at.
        """
        window = self._window
        if window is None:
            return False
        window._choose(index)
        return True

    def type_digit(self, digit: int) -> bool:
        """Нажата цифра в игре: ответить по видимому меню.

        A digit was pressed in the game: answer the menu on screen.
        ``digit`` — 1..9, как в окне / ``digit`` is 1..9, as in the window.
        """
        if self._window is None:
            return False
        return self.select(digit - 1)

    def confirm(self) -> bool:
        """Enter в игре: первый вариант видимого меню.

        Enter in the game: the first variant of the menu on screen.
        """
        if self._window is None:
            return False
        return self.select(0)

    def close_window(self) -> bool:
        """Esc в игре: закрыть окно выбора / Esc in the game: close the chooser."""
        window = self._window
        if window is None:
            return False
        window.close()
        return True

    def busy(self) -> bool:
        """Окно выбора что-то показывает / the chooser is showing something."""
        return self._window is not None

    def attach(self, rule, replay) -> bool:
        """Связать меню правила с очередью анимаций / link a rule menu to the queue.

        ``replay(choice)`` вызывается, когда правило уже доиграло, а игрок
        выбрал по его меню: выбор играет заново. ``replay(None)`` снимает
        поставленное в очередь.
        ``replay(choice)`` is called when the rule has already finished and the
        player picks in its menu: the pick plays again. ``replay(None)`` drops
        what was queued.
        """
        with self._lock:
            for entry in reversed(self._order):
                if entry.matches(rule):
                    entry.replay = replay
                    self._replay_hooks[_key(rule)] = replay
                    return True
            # меню ещё не создано: очередь зовёт attach раньше, чем ask заводит
            # меню, и без этого выбор по «старому» ключу не сыграл бы заново
            # the menu does not exist yet: the queue calls attach before ask makes
            # it, and without this a pick for an "old" keyword would not replay
            self._replay_hooks[_key(rule)] = replay
        return False

    def focus_menu_for(self, rule) -> bool:
        """Вернуть окно к меню этого правила / bring the menu of this rule back.

        Нужна, когда игрок снова написал ключ, меню которого ещё ждёт в очереди:
        лучше вернуть его меню с уже выбранным вариантом, чем открыть второе
        такое же.
        Needed when the player writes a keyword again while its menu is still
        waiting: better to bring that menu back, with its pick, than to open a
        second one like it.
        """
        with self._lock:
            entry = None
            for candidate in reversed(self._order):
                if not candidate.finished and candidate.matches(rule):
                    entry = candidate
                    break
            if entry is None:
                return False
            # Меню могло уже уйти с экрана, когда доиграло правило. Возвращаем его
            # в начало очереди: игрок думает именно о нём.
            # The menu may have left the screen when its rule finished. It goes
            # back to the front of the queue: that is the one on his mind.
            if entry in self._menus:
                self._menus.remove(entry)
            self._menus.insert(0, entry)
            entry.focused = True
            entry.shown.set()
        self._bridge.wake.emit()
        return True

    def close_all(self):
        """Закрыть окно и снять очередь меню (полная остановка, выход).

        Close the window and drop the menu queue (a full stop, an exit).
        """
        with self._lock:
            entries = list(self._menus)
            self._menus.clear()
            self._order.clear()
        for entry in entries:
            if entry.settle_timer is not None:
                entry.settle_timer.stop()
                entry.settle_timer = None
            if not entry.picks:
                entry.picks.append(None)
            entry.first.set()
            entry.finished = True
        # Окно снимаем сигналом в главный поток — он для того и есть. Ссылку
        # забываем сразу: очередь меню пуста, и следующий показ начнётся с чистого
        # листа. Если Qt ещё не запущен, убираем напрямую.
        # The window is taken down through the signal into the main thread — that
        # is what it is for. The reference is dropped at once: the menu queue is
        # empty and the next display starts from scratch. With Qt not running yet,
        # it is removed directly.
        if self._bridge is not None:
            self._bridge.hide.emit()
        else:
            self._close_window()
        self._window = None
        self.open = False

    def cancel(self, close: bool = False):
        """Отпустить ожидающую очередь, ничего не выбрав.

        Release the waiting queue without choosing.

        ``close=False`` (клавиша остановки) — окно остаётся: игрок нажал
        «остановить», но может тут же выбрать другой вариант.
        ``close=True`` (полная остановка, выход) — окно и вся очередь меню
        закрываются совсем.
        ``close=False`` (the stop key) keeps the window: the player asked to stop,
        but may pick another variant right away. ``close=True`` (a full stop, an
        exit) closes the window and the whole menu queue for good.
        """
        if close:
            log.info("Выбор анимации: закрыт остановкой")
            self.close_all()
            return
        # остановка снимает меню, по которому ещё ничего не выбрано: анимация
        # остановлена, и спрашивать «какую играть» уже поздно
        # a stop drops the menus nothing was picked in yet: the animation was
        # stopped, and asking "which one" is too late
        with self._lock:
            pending = [entry for entry in self._menus if not entry.picks]
            for entry in pending:
                if entry.settle_timer is not None:
                    entry.settle_timer.stop()
                    entry.settle_timer = None
                entry.picks.append(None)
                entry.first.set()
                entry.finished = True
                self._menus.remove(entry)
                if entry in self._order:
                    self._order.remove(entry)
        if pending:
            log.info("Выбор анимации: остановка сняла меню без выбора: %d", len(pending))
            # Окно показывало именно такое меню, и спрашивать больше некого:
            # убираем его с экрана. Иначе на нём остаются кнопки, которые уже
            # ничего не делают, — игрок жмёт вариант, а в игру ничего не уходит.
            # The window was showing exactly such a menu and there is nobody left
            # to ask: it leaves the screen. Otherwise its buttons stay and do
            # nothing — the player presses a variant and nothing reaches the game.
            window = self._window
            if window is not None and any(window.entry is entry for entry in pending):
                if self._bridge is not None:
                    self._bridge.hide.emit()
                else:
                    self._close_window()
        # Анимацию остановили — значит «играет» больше не правда, даже если
        # вариант уже выбран и меню осталось на экране.
        # The animation was stopped, so "playing" is no longer true, even when a
        # variant was already picked and the menu stayed on screen.
        self.rule_finished()
        self.open = bool(self._menus)
        self._bridge.wake.emit() if self._bridge is not None else None

    def _close_window(self):
        window, self._window = self._window, None
        if window is not None:
            try:
                window.hide()
                window.deleteLater()
            except Exception:
                log.exception("Выбор анимации: не удалось закрыть окно")


# один выбор на программу / one chooser per program
_chooser: Chooser | None = None


def chooser() -> Chooser:
    """Общий экземпляр выбора / the shared chooser instance."""
    global _chooser
    if _chooser is None:
        _chooser = Chooser()
    return _chooser


def ask(rule) -> "object | None":
    """Спросить игрока о варианте правила / ask the player about the rule variant."""
    return chooser().ask(rule)
