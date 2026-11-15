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

Окно закрывается само / the window closes itself
-----------------------------------------------
Есть таймаут (по умолчанию 30 секунд): если игрок отошёл, очередь не стоит
вечно. Esc и кнопка «Отмена» означают «ничего не играть». Если игрок ничего не
выбрал, вариант не играет вовсе — молчаливая подмена одним из вариантов была бы
хуже, чем ничего.

There is a timeout (30 seconds by default), so the queue never waits forever if
the player walked away. Esc and the Cancel button mean "play nothing". When nothing
is chosen, no variant plays at all — silently substituting one would be worse than
nothing.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from app import i18n
from app.config import log

# сколько ждать выбора: игрок мог отойти / how long to wait for the player
CHOICE_TIMEOUT_S = 30.0
# сколько ждать показа окна, прежде чем счесть, что его нет
# how long to wait for the window to appear before deciding there is none
SHOW_TIMEOUT_S = 5.0

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
QLabel#choiceNum {
    color: #c9d4ff; background: #2a3350; border: 1px solid #3f4d78;
    border-radius: 6px; font-size: 13px; font-weight: 700;
}
QLabel#choiceLabel { color: #ffffff; font-size: 15px; font-weight: 600; }
QLabel#choiceDesc { color: #b9b9c8; font-size: 12px; }
QLabel#choiceNoDesc { color: #6a6a78; font-size: 12px; font-style: italic; }
QLabel#choiceName { color: #7b88b8; font-size: 11px; }

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

        title = QLabel(choice.label())
        title.setObjectName("choiceLabel")
        title.setWordWrap(True)
        text.addWidget(title)

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

    def mouseReleaseEvent(self, event):
        """Клик по карточке = выбор варианта / a click picks the variant."""
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
                event.position().toPoint()):
            self._on_pick(self.index)
            return
        super().mouseReleaseEvent(event)


class ChoiceWindow(QWidget):
    """Окно выбора: список вариантов поверх игры.

    The chooser window: a list of variants above the game.

    Показывается без рамки и поверх всех окон, но с фокусом — иначе клавиатура
    осталась бы у игры. Как только игрок выбрал, окно скрывается и возвращает
    ответ через ``done_callback``.

    Frameless and always on top, but focused — otherwise the keyboard would stay
    with the game. As soon as the player picks, the window hides and reports the
    answer through ``done_callback``.
    """

    def __init__(self, title, subtitle, variants, done_callback, parent=None):
        super().__init__(parent)
        self.done_callback = done_callback
        self._variants = list(variants)
        self._answered = False
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(STYLE)
        self.setWindowTitle(i18n.t("Выбор анимации"))

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

        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("choiceEmpty")
            sub.setWordWrap(True)
            lay.addWidget(sub)

        # список прокручивается: вариантов может быть много, а окно не должно
        # вырасти выше экрана
        # the list scrolls: there may be many variants, and the window must not
        # grow taller than the screen
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        holder_lay = QVBoxLayout(holder)
        holder_lay.setContentsMargins(0, 0, 0, 0)
        holder_lay.setSpacing(6)
        self.buttons = []
        for index, choice in enumerate(self._variants):
            holder_lay.addWidget(self._item(index, choice))
        holder_lay.addStretch(1)
        scroll.setWidget(holder)
        # хотя бы пара вариантов должна быть видна, даже на тесном экране:
        # остальное докручивается
        # a couple of variants must be visible even on a tight screen; the rest
        # scrolls
        scroll.setMinimumHeight(150)
        lay.addWidget(scroll, 1)
        self._scroll = scroll
        self._holder = holder

        bottom = QHBoxLayout()
        hint = QLabel(i18n.t("1–9 — выбрать · Enter — первый · Esc — ничего"))
        hint.setObjectName("choiceKeys")
        hint.setWordWrap(True)
        bottom.addWidget(hint, 1)
        cancel = QPushButton(i18n.t("Ничего"))
        cancel.setObjectName("choiceCancel")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(lambda: self._answer(None))
        bottom.addWidget(cancel)
        lay.addLayout(bottom)

        self._fit()

    def _item(self, index, choice) -> QWidget:
        """Карточка одного варианта / one variant card."""
        card = _Card(index, choice, self._choose)
        self.buttons.append(card)
        return card

    def _choose(self, index):
        if 0 <= index < len(self._variants):
            self._answer(self._variants[index])

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
        screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        # Ширину берём по содержимому: на 420 описания уже переносятся, на 620
        # строки становятся слишком длинными.
        # The width follows the content: below 420 the descriptions wrap early,
        # past 620 the lines get too long.
        width = max(420, min(self.sizeHint().width(), 620))
        if area:
            width = min(width, max(int(area.width() * 0.9), 320))
        self.setFixedWidth(width)

        needed = self._content_height(width)
        if area:
            needed = min(needed, int(area.height() * 0.85))
        self.resize(width, max(needed, 200))
        if area:
            self.move(area.left() + (area.width() - width) // 2,
                      area.top() + (area.height() - self.height()) // 2)

    def _content_height(self, width: int) -> int:
        """Сколько высоты просит содержимое при такой ширине.

        How much height the content asks for at this width.

        Список меряем по его содержимому: у ``QScrollArea`` собственная высота
        всегда маленькая, а вариантов может быть и три, и десять.
        The list is measured by its content: a ``QScrollArea`` always reports a
        small height of its own, while there may be three variants or ten.
        """
        scroll = getattr(self, "_scroll", None)
        holder = getattr(self, "_holder", None)
        if scroll is None or holder is None:
            return 260
        # список должен успеть переразложиться под новую ширину
        # the list has to re-flow for the new width first
        holder.setFixedWidth(max(width - 60, 200))
        holder.adjustSize()
        list_height = holder.sizeHint().height()
        hint = self.layout().sizeHint().height()
        without_list = max(hint - scroll.sizeHint().height(), 90)
        total = without_list + list_height
        # сплошная прокрутка вместо списка из одной строки
        # a solid scroll area instead of a list of a single line
        return min(max(total, without_list + 150), 900)

    # --- ответ ---
    def _answer(self, choice):
        """Закрыть окно и сообщить выбор / close the window and report the pick."""
        if self._answered:
            return
        self._answered = True
        self.hide()
        try:
            self.done_callback(choice)
        except Exception:
            log.exception("Выбор анимации: колбэк упал")

    def keyPressEvent(self, event):
        """Клавиатура: цифры, Enter и Esc / the keyboard: digits, Enter and Esc."""
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._answer(None)
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
        """Крестик или закрытие окна = «ничего не играть».

        The close button or a plain close means "play nothing".
        """
        if not self._answered:
            self._answered = True
            try:
                self.done_callback(None)
            except Exception:
                log.exception("Выбор анимации: колбэк падения окна упал")
        super().closeEvent(event)


class _Bridge(QObject):
    """Сигнал «показать окно» для перехода в главный поток Qt.

    The "show the window" signal, used to hop into the Qt main thread.
    """

    show = Signal(object)


class Chooser:
    """Связка «поток очереди -> главный поток -> ответ».

    The "queue thread -> main thread -> answer" link.

    Один экземпляр на программу: окно выборов не должно открываться дважды, и
    очередь анимаций одна.
    One instance per program: the chooser must not open twice, and the animation
    queue is a single one.
    """

    def __init__(self, timeout_s: float = CHOICE_TIMEOUT_S):
        self.timeout_s = timeout_s
        self._bridge = None
        self._window = None
        self._lock = threading.Lock()

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
        return True

    def ask(self, rule) -> "object | None":
        """Спросить игрока, какой вариант играть / ask which variant to play.

        Вызывается из потока очереди анимаций и блокируется до ответа, таймаута
        или отказа. Возвращает выбранный ``Choice`` или None.
        Called from the animation queue thread and blocks until an answer, the
        timeout or a refusal. Returns the chosen ``Choice`` or None.
        """
        variants = rule.variant_list()
        if not variants:
            return None
        with self._lock:
            if not self._ensure_bridge():
                log.warning("Выбор анимации: Qt не запущен — спросить некого")
                return None
            answer: dict[str, object] = {}
            answered = threading.Event()
            shown = threading.Event()

            def done(choice):
                answer["choice"] = choice
                answered.set()

            payload = {"rule": rule, "variants": variants, "done": done,
                       "shown": shown}
            self._bridge.show.emit(payload)
            # Сначала ждём появления окна, потом самого выбора: это два разных
            # события, и путать их нельзя — иначе ответ вернулся бы сразу, ещё
            # до того, как игрок что-то нажал.
            # The window appearing and the answer arriving are two different
            # events and must not be mixed up: otherwise the answer would come
            # back at once, before the player pressed anything.
            if not shown.wait(SHOW_TIMEOUT_S):
                log.warning("Выбор анимации: окно не показалось за %d с",
                            int(SHOW_TIMEOUT_S))
                return None
            if answered.wait(self.timeout_s):
                return answer.get("choice")
            log.info("Выбор анимации: игрок не выбрал за %d с — правило "
                     "пропущено", int(self.timeout_s))
            # окно закрываем сами: иначе оно висело бы поверх игры
            # the window is closed by us, otherwise it would hang over the game
            self._close_window()
            return None

    # --- главный поток ---
    def _show(self, payload):
        """Показать окно выбора (главный поток Qt) / show the chooser (Qt main)."""
        rule = payload["rule"]
        variants = payload["variants"]
        done = payload["done"]
        self._close_window()
        # Ключи в заголовке не перечисляем: их бывает три-четыре, и заголовок
        # растягивался на три строки, отжимая сам список. Достаточно вопроса.
        # The keywords are not listed in the title: there may be three or four,
        # and the title grew to three lines and squeezed the list itself. The
        # question alone is enough.
        window = ChoiceWindow(i18n.t("Какую анимацию вы собираетесь использовать?"),
                              i18n.t("Выбор отправится в чат игры как /anim."),
                              variants, done)
        self._window = window
        window.show()
        window.raise_()
        window.activateWindow()
        if window.buttons:
            window.buttons[0].setFocus()
        payload["shown"].set()

    def cancel(self):
        """Закрыть окно выбора, ничего не выбрав (остановка, выход).

        Close the chooser without choosing (a stop or a shutdown).
        Нужна, когда игрок нажал клавишу остановки, пока окно открыто: очередь
        снимается, и окно не должно остаться висеть поверх игры.
        Needed when the stop key is pressed while the window is open: the queue is
        dropped and the window must not stay above the game.
        """
        window = self._window
        if window is not None:
            log.info("Выбор анимации: закрыт остановкой")
            window._answer(None)

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
