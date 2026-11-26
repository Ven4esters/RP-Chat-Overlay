"""Reusable Qt widgets used by Settings pages."""

from PySide6.QtCore import QEasingCurve, QPoint, QRect, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QDrag, QPainter, QPixmap, QPolygon
from PySide6.QtWidgets import QAbstractButton, QAbstractItemView, QTableWidget


class ToggleSwitch(QAbstractButton):
    """Тумблер: дорожка и бегунок, состояние — «включён / выключен».

    A switch: a track and a knob; the state is on or off.

    Зачем свой, а не QCheckBox: у галочки два вида, и на тёмной теме она читается
    как «пункт списка», а не как выключатель сервиса. Тумблер рисуется сам —
    значит, его вид не зависит от стиля Windows и одинаков на всех системах.
    A switch is drawn here rather than taken from QCheckBox: a checkbox reads as a
    list item on a dark theme, not as a service switch. Drawing it by hand also
    keeps the look the same on every system instead of following the Windows
    style.
    """

    WIDTH = 46  # ширина дорожки / the track width
    HEIGHT = 24  # высота дорожки / the track height
    KNOB = 18  # диаметр бегунка / the knob diameter
    ON_COLOR = QColor("#2e7d55")  # зелёная дорожка: включено / on
    ON_EDGE = QColor("#3d9a6b")
    OFF_COLOR = QColor("#2b2b36")  # серая дорожка: выключено / off
    OFF_EDGE = QColor("#3c3c4a")
    KNOB_COLOR = QColor("#eef6f1")
    KNOB_DIM = QColor("#9a9aa6")
    DISABLED_COLOR = QColor("#20202a")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self._pos = 0.0  # 0 — выключен, 1 — включён / 0 off, 1 on
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._animate_to)
        self.toggled.connect(self._slide)

    def sizeHint(self):
        return QSize(self.WIDTH, self.HEIGHT)

    def _slide(self, on):
        """Плавно сдвинуть бегунок / slide the knob to the new side."""
        start = float(self._pos)
        end = 1.0 if on else 0.0
        self._anim.stop()
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.start()

    def _animate_to(self, value):
        self._pos = float(value)
        self.update()

    def set_on(self, on, animate=False):
        """Поставить состояние без сигнала / set the state without a signal.

        Нужно, когда состояние пришло извне (сервис упал или поднялся сам):
        переключать тумблер и запускать от этого остановку нельзя.
        It is used when the state comes from outside (the service died or came up
        on its own): the switch must follow without starting a stop.
        """
        on = bool(on)
        if self.isChecked() != on:
            self.blockSignals(True)
            self.setChecked(on)
            self.blockSignals(False)
            if animate:
                self._slide(on)
            else:
                self._pos = 1.0 if on else 0.0
                self.update()

    def paintEvent(self, event):  # noqa: N802 — имя из Qt / a Qt name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0.5, 0.5, self.WIDTH - 1, self.HEIGHT - 1)
        radius = rect.height() / 2
        enabled = self.isEnabled()
        on = self._pos > 0.5
        if not enabled:
            track = self.DISABLED_COLOR
            edge = self.OFF_EDGE
        elif on:
            track = self.ON_COLOR
            edge = self.ON_EDGE
        else:
            track = self.OFF_COLOR
            edge = self.OFF_EDGE
        painter.setPen(edge)
        painter.setBrush(track)
        painter.drawRoundedRect(rect, radius, radius)
        # бегунок едет между краями по значению анимации
        # the knob travels between the edges with the animation value
        margin = (self.HEIGHT - self.KNOB) / 2
        left = margin
        right = self.WIDTH - margin - self.KNOB
        x = left + (right - left) * self._pos
        knob = QRectF(x, margin, self.KNOB, self.KNOB)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.KNOB_COLOR if enabled else self.KNOB_DIM)
        painter.drawEllipse(knob)
        if self.hasFocus():
            # рамка фокуса — снаружи дорожки, чтобы бегунок её не перекрывал
            # the focus ring sits outside the track so the knob cannot hide it
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor("#7ea6ff"))
            painter.drawRoundedRect(
                QRectF(-2.5, -2.5, self.WIDTH + 4, self.HEIGHT + 4), radius + 2, radius + 2
            )
        painter.end()


class DragTable(QTableWidget):
    """Таблица, в которой строки меняются местами перетаскиванием мышью.

    A table whose rows can be reordered by dragging them with the mouse.

    Qt умеет «внутренний перенос» строк, но переставляет только ячейки: галочки
    и выпадающие списки остаются на старых местах. Поэтому строку двигает не Qt,
    а сама таблица через ``on_move(откуда, куда)`` — она заново собирает строки
    из данных, и всё содержимое переезжает вместе с ними.
    Qt has an "internal move", but it moves the cells only: checkboxes and combo
    boxes stay behind. So the row is moved by the table itself through
    ``on_move(from_row, to_row)``, which rebuilds the rows from the data, and
    everything moves along.

    Почему не штатный перенос / why not Qt's own move
    ------------------------------------------------
    ``QAbstractItemView.startDrag`` после ``QDrag.exec()`` вызывает
    ``clearOrRemove``: при ``MoveAction`` Qt **удаляет** исходную строку сам. У
    нас строку уже пересобрал ``on_move``, поэтому удаление приходилось на новую
    таблицу — строка исчезала. Здесь ``QDrag.exec()`` вызывается напрямую, без
    ``clearOrRemove``, и строку двигает только ``on_move``.
    ``QAbstractItemView.startDrag`` calls ``clearOrRemove`` after ``QDrag.exec()``:
    with ``MoveAction`` Qt deletes the source row itself. Our ``on_move`` has
    already rebuilt the rows, so that deletion hit the fresh table and the row
    vanished. Here ``QDrag.exec()`` is called directly, without
    ``clearOrRemove``, and only ``on_move`` moves anything.

    Куда встанет строка / where the row will land
    ---------------------------------------------
    Штатный индикатор Qt рисуется по краю ячейки и почти не виден, поэтому
    таблица рисует свою линию вставки — толстую, акцентного цвета, во всю
    ширину, — и дополнительно подсвечивает строку, которую тянут.
    The stock Qt indicator is drawn on the cell edge and is barely visible, so
    the table paints its own drop line — thick, accent-coloured, full width — and
    also highlights the row being dragged.
    """

    # цвета линии вставки и «призрака» перетаскиваемой строки
    # the drop line and the dragged row colours
    LINE_COLOR = QColor("#5b8cff")
    DRAG_BG = QColor(91, 140, 255, 46)  # подсветка исходной строки / dragged row
    TARGET_BG = QColor(91, 140, 255, 22)  # цель перетаскивания / the drop target
    LINE_WIDTH = 3

    def __init__(self, on_move=None, rows=0, columns=0, parent=None):
        super().__init__(rows, columns, parent)
        self.on_move = on_move
        self._drag_row = -1
        self._drop_at = -1  # перед какой строкой встанет / the row it lands before
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        # штатный индикатор выключен: рисуем свой, заметный
        # the stock indicator is off: ours is the visible one
        self.setDropIndicatorShown(False)
        self.setDragDropOverwriteMode(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setMouseTracking(True)

    # --- перетаскивание ---
    def startDrag(self, _actions):
        """Свой перенос: без ``clearOrRemove``, который удаляет строку.

        Our own drag: no ``clearOrRemove``, which is what deleted the row.

        Данные для Qt готовятся вручную (``mimeData`` + ``QDrag``), поэтому
        исходная строка остаётся на месте, пока её не переставит ``on_move``.
        The data for Qt is prepared by hand (``mimeData`` + ``QDrag``), so the
        source row stays where it is until ``on_move`` moves it.
        """
        source = self.currentRow()
        if source < 0 or source >= self.rowCount():
            return
        self._drag_row = source
        indexes = self.selectedIndexes() or [self.model().index(source, 0)]
        mime = self.model().mimeData(indexes)
        if mime is None:
            self._drag_row = -1
            return
        drag = QDrag(self)
        drag.setMimeData(mime)
        # «призрак» строки под курсором: видно, что именно тащат
        # a ghost of the row under the cursor: it shows what is being dragged
        pixmap = self._row_pixmap(source)
        if pixmap is not None:
            drag.setPixmap(pixmap)
            drag.setHotSpot(QPoint(12, pixmap.height() // 2))
        self.viewport().update()
        drag.exec(Qt.DropAction.MoveAction)
        # после переноса разметка сбрасывается: линия вставки не должна висеть
        # after the drag the marks are cleared so the drop line does not linger
        self._drag_row = -1
        self._drop_at = -1
        self.viewport().update()

    def _row_pixmap(self, row: int) -> QPixmap | None:
        """Снимок строки для «призрака» под курсором / a snapshot of the row."""
        top = self.rowViewportPosition(row)
        height = self.rowHeight(row)
        if height <= 0:
            return None
        pixmap = QPixmap(self.viewport().width(), min(height, self.viewport().height()))
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setOpacity(0.85)
        # рисуем область таблицы как есть, но только одну строку
        # the table area is drawn as is, one row only
        painter.fillRect(pixmap.rect(), QColor("#1c1c24"))
        painter.end()
        self.viewport().render(
            pixmap, QPoint(0, 0), QRect(0, top, self.viewport().width(), pixmap.height())
        )
        return pixmap

    def dragEnterEvent(self, event):
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()
        self._mark_drop(event.position().toPoint())

    def dragLeaveEvent(self, event):
        self._drop_at = -1
        self.viewport().update()
        event.accept()

    def dragMoveEvent(self, event):
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()
        self._mark_drop(event.position().toPoint())

    def dropEvent(self, event):
        """Отдать перенос в on_move: Qt сам строки не двигает.

        Hand the move over to on_move: Qt does not move the rows itself.
        """
        source = self._drag_row
        target = self._drop_row(event.position().toPoint())
        self._drag_row = -1
        self._drop_at = -1
        self.viewport().update()
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()
        if source < 0 or self.on_move is None:
            return
        if target in (source, source + 1):  # на то же место / same place
            return
        self.on_move(source, target)

    def _mark_drop(self, pos) -> None:
        """Запомнить, где встанет строка, и перерисовать линию вставки.

        Remember where the row will land and repaint the drop line.
        """
        self._drop_at = self._drop_row(pos)
        self.viewport().update()

    def _drop_row(self, pos) -> int:
        """Перед какой строкой встанет перетаскиваемая / the row it lands before.

        За краем последней строки — значит, в самый конец списка.
        Past the last row means the very end of the list.
        """
        index = self.indexAt(pos)
        if not index.isValid():
            if self.rowCount() == 0:
                return 0
            last = self.visualRect(self.model().index(self.rowCount() - 1, 0))
            # ниже последней строки — в конец; выше первой — в начало
            # below the last row lands at the end, above the first at the start
            return self.rowCount() if pos.y() > last.center().y() else 0
        row = index.row()
        rect = self.visualRect(index)
        return row + 1 if pos.y() > rect.center().y() else row

    # --- отрисовка подсказок перетаскивания / drag hints ---
    def paintEvent(self, event):
        """Обычная отрисовка плюс линия вставки и подсветка строк.

        The usual painting plus the drop line and the row highlights.
        """
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        width = self.viewport().width()

        # строка, которую тянут: подсвечиваем, чтобы не потерять её из виду
        # the row being dragged is tinted, so it is not lost from sight
        if 0 <= self._drag_row < self.rowCount():
            top = self.rowViewportPosition(self._drag_row)
            painter.fillRect(0, top, width, self.rowHeight(self._drag_row), self.DRAG_BG)

        # строка, на которую сейчас упадёт переносимая: лёгкая подсветка
        # the row the dragged one will land on: a light tint
        if 0 <= self._drop_at < self.rowCount():
            top = self.rowViewportPosition(self._drop_at)
            painter.fillRect(0, top, width, self.rowHeight(self._drop_at), self.TARGET_BG)

        # сама линия вставки: место, куда строка встанет
        # the drop line itself: exactly where the row will land
        if self._drop_at >= 0:
            y = self._line_y(self._drop_at)
            if y is not None:
                painter.fillRect(
                    0, y - self.LINE_WIDTH // 2, width, self.LINE_WIDTH, self.LINE_COLOR
                )
                # треугольник-указатель слева: видно даже на светлой строке
                # an arrow on the left: visible even on a light row
                painter.setBrush(self.LINE_COLOR)
                painter.setPen(Qt.PenStyle.NoPen)
                size = 7
                painter.drawPolygon(
                    QPolygon([QPoint(0, y - size), QPoint(size, y), QPoint(0, y + size)])
                )
        painter.end()

    def _line_y(self, row: int) -> int | None:
        """Y линии вставки перед строкой ``row`` / the y of the line before a row.

        ``row == rowCount()`` — линия под последней строкой: тогда это конец
        списка. Возвращается координата в области прокрутки.
        ``row == rowCount()`` means below the last row, that is the end of the
        list. The value is a viewport coordinate.
        """
        count = self.rowCount()
        if count == 0:
            return 0
        if row >= count:
            top = self.rowViewportPosition(count - 1)
            y = top + self.rowHeight(count - 1)
            if y < 0 or y > self.viewport().height():
                return None
            return min(y, self.viewport().height() - self.LINE_WIDTH)
        top = self.rowViewportPosition(row)
        if top < 0 or top > self.viewport().height():
            return None
        return max(self.LINE_WIDTH // 2, top)

    # --- общий перенос готовых ячеек ---
    @staticmethod
    def move_cells(table, source: int, target: int) -> None:
        """Переставить строку с её ячейками / move a row together with its cells.

        Годится для таблиц без встроенных виджетов: ячейки берутся как есть, со
        всеми флажками и подсказками.
        Good for tables without cell widgets: the cells are taken as they are,
        with their check states and tooltips.
        """
        if source < 0 or source >= table.rowCount():
            return
        rows = [
            [table.takeItem(row, col) for col in range(table.columnCount())]
            for row in range(table.rowCount())
        ]
        moved = rows.pop(source)
        if target > source:
            target -= 1
        rows.insert(max(0, min(target, len(rows))), moved)
        table.blockSignals(True)
        table.setRowCount(0)
        table.setRowCount(len(rows))
        for row, cells in enumerate(rows):
            for col, cell in enumerate(cells):
                if cell is not None:
                    table.setItem(row, col, cell)
        table.blockSignals(False)
        table.selectRow(max(0, min(target, len(rows) - 1)))
