"""Окно настроек / the settings window.

Как устроено / how it works
---------------------------
Диалог из семи разделов, каждый — отдельная страница в прокрутке: «Основные»,
«Автоперевод», «Чат игры», «Словарь», «Сокращения», «Проверка», «Модули».
A dialog with seven sections, each one a separate scrollable page: General,
Auto-translation, Game chat, Glossary, Abbreviations, Test and Modules.

Правила / rules
---------------
  * «Сохранить» — единственная точка записи: словари и сокращения пишутся
    на диск только здесь; Save is the only place that writes files;
  * размер окна подстраивается под экран, содержимое прокручивается,
    ничего не выходит за пределы рабочей области; the window fits the screen
    and scrolls instead of overflowing;
  * модули, выключенные на странице «Модули», не мешают остальным страницам.
    Modules switched off on their page do not break the other pages.
"""
import csv
import io
import json
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QDrag, QGuiApplication, QKeySequence, QPainter,
                           QPixmap, QPolygon)
import urllib.parse

from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox,
                               QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QSpinBox, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QToolButton,
                               QVBoxLayout, QWidget)

from app import dlx as dlx_mod
from app import anims, i18n, langs, modules, morph, slang
from app.config import DATA, DEFAULT_CONFIG, log, save_config
from app.engine import (Engine, Glossary, glossary_path, load_glossary_data,
                        reset_glossary, save_glossary_data)
from app.translator import TranslateError, Translator

STYLE = """
QDialog, QWidget#page { background: #14141a; color: #f2f2f2; }
QWidget { color: #f2f2f2; font-size: 13px; }
QLabel#h1 { font-size: 19px; font-weight: 600; }
QLabel#sub { color: #8a8a96; font-size: 12px; }
QLabel#hint { color: #8a8a96; font-size: 11px; }
QLabel#warn { color: #ffb45b; font-size: 11px; }
QLabel#err { color: #ff6b6b; font-size: 12px; }
QLabel#ok { color: #66d18b; font-size: 12px; }
QFrame#card { background: #1c1c24; border: 1px solid #2e2e3a; border-radius: 10px; }
QFrame#sep { background: #2a2a36; max-height: 1px; border: none; }
QListWidget#nav { background: #17171e; border: none; border-right: 1px solid #26262f;
                  padding: 8px 6px; outline: 0; }
QListWidget#nav::item { padding: 10px 12px; border-radius: 8px; margin: 2px 4px; color: #c8c8d2; }
QListWidget#nav::item:selected { background: #26263a; color: #ffffff; }
QListWidget#nav::item:hover { background: #20202b; }
QLineEdit, QSpinBox, QComboBox { background: #0e0e12; border: 1px solid #3a3a48;
                                 border-radius: 6px; padding: 6px 8px; min-height: 18px; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border: 1px solid #5b8cff; }
QLineEdit:read-only { color: #b9c4ff; }
/* у счётчиков свои кнопки «−» и «+», штатные стрелки убираем совсем, иначе
   они отнимают у поля почти всю ширину. Spin boxes draw their − and + as real
   buttons, so the built-in arrows are given zero width instead of a hidden one. */
QSpinBox::up-button, QSpinBox::down-button { width: 0px; height: 0px;
                                            border: none; background: transparent; }
QComboBox QAbstractItemView { background: #1c1c24; selection-background-color: #2e3f6b;
                              border: 1px solid #3a3a48; }
/* Кнопки: заметная рамка, отдельные состояния и видимый фокус для клавиатуры.
   Buttons carry a visible outline, distinct hover/pressed states and a focus ring
   for keyboard users. */
QPushButton { background: #22222c; border: 1px solid #3c3c4a; border-radius: 8px;
              padding: 8px 16px; color: #e9e9f2; min-height: 20px; }
QPushButton:hover { background: #2c2c39; border: 1px solid #4d4d60; }
QPushButton:pressed { background: #1c1c25; border: 1px solid #5b8cff; }
QPushButton:focus { border: 1px solid #4d4d60; }
QPushButton:disabled { background: #1a1a21; border: 1px solid #2b2b36; color: #6b6b78; }
/* главная кнопка: ровная заливка без светлой рамки — рамка того же цвета,
   что и фон, поэтому кнопка не выглядит постоянно нажатой / the main button is
   a flat fill: its border matches the fill, so it never looks stuck in focus */
QPushButton#primary { background: #3d6fd8; border: 1px solid #3d6fd8; color: #ffffff;
                      font-weight: 600; }
QPushButton#primary:hover { background: #4a7ce8; border: 1px solid #4a7ce8; }
QPushButton#primary:pressed { background: #345fbd; border: 1px solid #345fbd; }
QPushButton#primary:focus { background: #4174e2; border: 1px solid #4174e2; }
QPushButton#primary:disabled { background: #2b3a5c; border: 1px solid #35486e; color: #9aa6bd; }
QPushButton#danger { color: #ff9c9c; border: 1px solid #4a3238; }
QPushButton#danger:hover { background: #2a1e22; border: 1px solid #7a4a52; color: #ffbcbc; }
QPushButton#soft { color: #ffcf9c; border: 1px solid #33333f; background: transparent; }
QPushButton#soft:hover { background: #2a2418; border: 1px solid #7a6444; color: #ffd9ae; }
QToolButton#step { background: #22222c; border: 1px solid #3c3c4a; border-radius: 8px;
                   color: #e9e9f2; font-weight: 600; }
QToolButton#step:hover { background: #2f2f3d; border: 1px solid #5b8cff; }
QToolButton#step:pressed { background: #1c1c25; border: 1px solid #5b8cff; }
QToolButton#step:disabled { color: #6b6b78; border: 1px solid #2b2b36; background: #1a1a21; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px;
                       border: 1px solid #4a4a58; background: #0e0e12; }
QCheckBox::indicator:checked { background: #3d6fd8; border: 1px solid #4f7ee6; }
QTableWidget { background: #0e0e12; border: 1px solid #3a3a48; border-radius: 8px;
               gridline-color: #26262f; selection-background-color: #2e3f6b; }
QHeaderView::section { background: #1c1c24; color: #b9b9c6; border: none;
                       border-bottom: 1px solid #3a3a48; padding: 6px; }
QTableWidget::item { padding: 4px; }
/* галочки в таблице словаря: свой индикатор, иначе Qt рисует тонкую «птичку»
   без рамки, которую на тёмном фоне почти не видно. Table check indicators are
   drawn explicitly: the default is a thin tick with no box, nearly invisible here. */
QTableWidget::indicator, QTableView::indicator { width: 18px; height: 18px; }
QTableWidget::indicator:unchecked, QTableView::indicator:unchecked {
    border: 1px solid #5a5a6a; border-radius: 4px; background: #16161d; }
QTableWidget::indicator:unchecked:hover, QTableView::indicator:unchecked:hover {
    border: 1px solid #7ea6ff; }
QTableWidget::indicator:checked, QTableView::indicator:checked {
    border: 1px solid #7ea6ff; border-radius: 4px; background: #3d6fd8; }
QScrollBar:vertical { background: #14141a; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #33333f; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QToolTip { background: #23232e; color: #f2f2f2; border: 1px solid #3a3a48; padding: 4px; }
QScrollArea#scroll { background: transparent; border: none; }
QScrollArea#scroll > QWidget > QWidget { background: #14141a; }
QScrollBar:horizontal { background: #14141a; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #33333f; border-radius: 5px; min-width: 30px; }
"""


def style_sheet(scale=1.0):
    """Таблица стилей с масштабом шрифта.

    Один и тот же набор правил работает и на 1366×768, и на 4K: меняется
    только базовый размер шрифта, остальное подстраивает компоновка.
    """
    try:
        k = float(scale or 1.0)
    except (TypeError, ValueError):
        k = 1.0
    k = min(max(k, 0.8), 1.8)
    size = int(round(13 * k))
    out = STYLE.replace("font-size: 13px", "font-size: %dpx" % size)
    out = out.replace("font-size: 19px", "font-size: %dpx" % int(round(19 * k)))
    out = out.replace("font-size: 12px", "font-size: %dpx" % int(round(12 * k)))
    out = out.replace("font-size: 11px", "font-size: %dpx" % int(round(11 * k)))
    # размеры кнопок считаются от того же масштаба: на 150 % палец и мышь
    # попадают в кнопку так же уверенно, как на 100 %
    extra = (
        "QPushButton { min-height: %dpx; padding: %dpx %dpx; }\n"
        "QToolButton#step { min-width: %dpx; min-height: %dpx; font-size: %dpx; }\n"
        "QCheckBox::indicator { width: %dpx; height: %dpx; }\n"
        "QTableWidget::indicator, QTableView::indicator { width: %dpx; height: %dpx; }\n"
        % (int(round(20 * k)), int(round(8 * k)), int(round(16 * k)),
           int(round(26 * k)), int(round(24 * k)), int(round(15 * k)),
           int(round(16 * k)), int(round(16 * k)), int(round(18 * k)), int(round(18 * k)))
    )
    return out + extra


def _scroll_page(page):
    """Обёртка с прокруткой: содержимое раздела не наезжает само на себя.

    Без неё на невысоком экране (или при масштабе Windows 125–150 %) карточки
    сжимались и поля уезжали под соседние — именно это было видно у «Скобок
    перевода». Теперь страница прокручивается, а не сжимается.
    """
    area = QScrollArea()
    area.setObjectName("scroll")
    area.setWidget(page)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    area.viewport().setAutoFillBackground(False)
    page.setAutoFillBackground(False)
    return area

# строка подвала, когда всё сохранено / the footer line in its idle state
_FOOTER_IDLE = "Изменения применятся после «Сохранить»."


MODIFIER_KEYS = {Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift,
                 Qt.Key.Key_Meta, Qt.Key.Key_AltGr}
NAMED_KEYS = {
    Qt.Key.Key_Insert: "insert", Qt.Key.Key_Delete: "delete", Qt.Key.Key_Home: "home",
    Qt.Key.Key_End: "end", Qt.Key.Key_PageUp: "pageup", Qt.Key.Key_PageDown: "pagedown",
    Qt.Key.Key_Pause: "pause", Qt.Key.Key_Tab: "tab", Qt.Key.Key_Space: "space",
    Qt.Key.Key_QuoteLeft: "`",
}

ALLOWED_PLAIN = {"insert", "delete", "home", "end", "pageup", "pagedown", "pause",
                 "tab", "space", "`"}
ALLOWED_MODS = {"ctrl", "alt", "shift", "win"}


def check_hotkey(spec):
    """Проверка строки горячей клавиши без импорта Windows-модулей.

    Возвращает (ок, текст_предупреждения).
    """
    parts = [p.strip().lower() for p in str(spec or "").split("+") if p.strip()]
    if not parts:
        return False, "Укажите клавишу."
    mods = [p for p in parts if p in ALLOWED_MODS]
    keys = [p for p in parts if p not in ALLOWED_MODS]
    if len(keys) != 1:
        return False, "Нужна ровно одна клавиша (например, F6 или Ctrl+Alt+T)."
    k = keys[0]
    ok_key = (k in ALLOWED_PLAIN or (len(k) == 1 and k.isascii() and k.isalnum())
              or (k.startswith("f") and k[1:].isdigit() and 1 <= int(k[1:]) <= 24))
    if not ok_key:
        return False, f"Клавиша «{k}» не поддерживается."
    if not mods and not (k.startswith("f") or k in ALLOWED_PLAIN):
        return False, "Одиночная буква/цифра будет мешать печати — добавьте Ctrl/Alt или выберите F-клавишу."
    return True, ""


class KeyCapture(QLineEdit):
    """Поле горячей клавиши: нажмите сочетание — оно запишется."""

    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("нажмите сочетание клавиш…")
        self.setToolTip("Кликните по полю и нажмите нужное сочетание, например F6 или Ctrl+Alt+T")

    def keyPressEvent(self, e):
        if e.key() in MODIFIER_KEYS:
            return
        mods = e.modifiers()
        parts = []
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("shift")
        if mods & Qt.KeyboardModifier.MetaModifier:
            parts.append("win")
        name = self._key_name(e.key())
        if not name:
            return
        self.setText("+".join(parts + [name]))
        self.changed.emit(self.text())

    @staticmethod
    def _key_name(key):
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
            return "f%d" % (key - Qt.Key.Key_F1 + 1)
        if key in NAMED_KEYS:
            return NAMED_KEYS[key]
        if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            return chr(key).lower()
        if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            return chr(key)
        return ""


def _card():
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(10)
    return f, lay


def _title(text, size=None):
    lab = QLabel(text)
    lab.setObjectName("h1" if size == "h1" else "")
    if size == "h1":
        lab.setStyleSheet("font-size:18px;font-weight:600;")
    elif size == "sec":
        lab.setStyleSheet("font-size:14px;font-weight:600;color:#dfe3ff;")
    return lab


def _hint(text):
    lab = QLabel(text)
    lab.setObjectName("hint")
    lab.setWordWrap(True)
    return lab


def _small_spin(spin, lo, hi, suffix="", width=170, step=None, prefix=None):
    """Компактный счётчик: не растягивается на всю карточку."""
    spin.setRange(lo, hi)
    if suffix:
        spin.setSuffix(suffix)
    if prefix:
        spin.setPrefix(prefix)
    if step:
        spin.setSingleStep(step)
    spin.setMaximumWidth(width)
    spin.setMinimumWidth(min(width, 62))
    return spin


def _num_row(spin, width=None):
    """Счётчик с крупными кнопками «−» и «+» / counter with big − and + buttons.

    Штатные стрелки Qt на тёмной теме почти не видны, а попасть в них мышью
    трудно. Поэтому рядом стоят две обычные кнопки: размер задаётся стилем и
    растёт вместе с масштабом интерфейса, нажатие повторяется при удержании.
    Qt's own spin arrows are tiny and almost invisible on a dark theme, so two
    real buttons sit next to the field. Their size follows the interface scale
    and a held button repeats its step.
    """
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    # штатные стрелки убираются стилем (QSpinBox::up-button, width: 0), а не
    # NoButtons: при NoButtons Qt отдаёт полю ввода 1 px и текст исчезает
    # the built-in arrows are removed by the style sheet (zero width), not by
    # NoButtons: with NoButtons Qt shrinks the line edit to 1 px and the text
    # disappears
    minus = QToolButton()
    minus.setText("−")
    minus.setToolTip(i18n.t("Уменьшить значение"))
    minus.clicked.connect(spin.stepDown)
    plus = QToolButton()
    plus.setText("+")
    plus.setToolTip(i18n.t("Увеличить значение"))
    plus.clicked.connect(spin.stepUp)
    for b in (minus, plus):
        b.setObjectName("step")
        b.setAutoRepeat(True)
        b.setAutoRepeatDelay(400)
        b.setAutoRepeatInterval(70)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        b.setAccessibleName(b.text())
        b.setAccessibleDescription(b.toolTip())
    row.addWidget(minus)
    row.addWidget(spin, 1)
    row.addWidget(plus)
    row.addStretch(1)
    if width:
        spin.setMaximumWidth(width)
    return box


def _sep():
    s = QFrame()
    s.setObjectName("sep")
    s.setFrameShape(QFrame.Shape.HLine)
    return s


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
    DRAG_BG = QColor(91, 140, 255, 46)     # подсветка исходной строки / dragged row
    TARGET_BG = QColor(91, 140, 255, 22)   # цель перетаскивания / the drop target
    LINE_WIDTH = 3

    def __init__(self, on_move=None, rows=0, columns=0, parent=None):
        super().__init__(rows, columns, parent)
        self.on_move = on_move
        self._drag_row = -1
        self._drop_at = -1        # перед какой строкой встанет / the row it lands before
        self._drop_rect = None    # та же точка, но в координатах области / in viewport coords
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
    def startDrag(self, actions):
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
        self._drop_rect = None
        self.viewport().update()

    def _row_pixmap(self, row: int) -> QPixmap | None:
        """Снимок строки для «призрака» под курсором / a snapshot of the row."""
        top = self.rowViewportPosition(row)
        height = self.rowHeight(row)
        if height <= 0:
            return None
        pixmap = QPixmap(self.viewport().width(),
                         min(height, self.viewport().height()))
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setOpacity(0.85)
        # рисуем область таблицы как есть, но только одну строку
        # the table area is drawn as is, one row only
        painter.fillRect(pixmap.rect(), QColor("#1c1c24"))
        painter.end()
        self.viewport().render(pixmap, QPoint(0, 0),
                               QRect(0, top, self.viewport().width(), pixmap.height()))
        return pixmap

    def dragEnterEvent(self, event):
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()
        self._mark_drop(event.position().toPoint())

    def dragLeaveEvent(self, event):
        self._drop_at = -1
        self._drop_rect = None
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
        self._drop_rect = None
        self.viewport().update()
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()
        if source < 0 or self.on_move is None:
            return
        if target in (source, source + 1):        # на то же место / same place
            return
        self.on_move(source, target)

    def _mark_drop(self, pos) -> None:
        """Запомнить, где встанет строка, и перерисовать линию вставки.

        Remember where the row will land and repaint the drop line.
        """
        row = self._drop_row(pos)
        rect = None
        if 0 <= row < self.rowCount():
            rect = self.visualRect(self.model().index(row, 0))
        self._drop_at = row
        self._drop_rect = rect
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
            painter.fillRect(0, top, width, self.rowHeight(self._drag_row),
                             self.DRAG_BG)

        # строка, на которую сейчас упадёт переносимая: лёгкая подсветка
        # the row the dragged one will land on: a light tint
        if 0 <= self._drop_at < self.rowCount():
            top = self.rowViewportPosition(self._drop_at)
            painter.fillRect(0, top, width, self.rowHeight(self._drop_at),
                             self.TARGET_BG)

        # сама линия вставки: место, куда строка встанет
        # the drop line itself: exactly where the row will land
        if self._drop_at >= 0:
            y = self._line_y(self._drop_at)
            if y is not None:
                painter.fillRect(0, y - self.LINE_WIDTH // 2, width,
                                 self.LINE_WIDTH, self.LINE_COLOR)
                # треугольник-указатель слева: видно даже на светлой строке
                # an arrow on the left: visible even on a light row
                painter.setBrush(self.LINE_COLOR)
                painter.setPen(Qt.PenStyle.NoPen)
                size = 7
                painter.drawPolygon(QPolygon([
                    QPoint(0, y - size), QPoint(size, y), QPoint(0, y + size)]))
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
        rows = [[table.takeItem(row, col) for col in range(table.columnCount())]
                for row in range(table.rowCount())]
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


class DlxJob(QObject):
    """Фоновое действие над сервисом DLX / a background action on the DLX service.

    Сеть и запуск процесса могут занять секунды, поэтому они уходят в поток, а
    окно получает только результат — сигналом, то есть в главном потоке.
    Network calls and process start can take seconds, so they run in a thread and
    the window only receives the result, through a signal, on the main thread.
    """

    finished = Signal(bool, str)        # получилось?, причина / ok?, reason

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def start(self) -> None:
        """Запускает действие в отдельном потоке / starts the action in a thread."""
        def run():
            ok, reason = False, ""
            try:
                ok = bool(self.fn())
            except Exception as error:      # noqa: BLE001 — причину покажем игроку
                log.exception("DLX: фоновое действие не удалось")
                reason = str(error) or type(error).__name__
            self.finished.emit(ok, reason)
        threading.Thread(target=run, daemon=True, name="dlx-job").start()


class SettingsWindow(QDialog):
    """Окно настроек. signal saved(cfg) — после сохранения."""

    saved = Signal(dict)
    anim_test_done = Signal(bool, str)     # ручная отправка /anim: успех и ответ игры
                                          # manual /anim send: success and reply

    def __init__(self, cfg, parent=None, first_run=False, dlx=None, anims_api=None):
        """Окно настроек; dlx — сервис DeepL, если он уже создан программой.

        The settings window; dlx is the DeepL service when the program created one.

        anims_api — работающий модуль «Анимации»: состояние, ручная отправка и
        остановка. Без него страница «Анимации» только настраивает правила.
        anims_api is the running Animations module: its state, a manual send and
        a stop. Without it the Animations page only edits the rules.
        """
        super().__init__(parent)
        self.dlx = dlx
        self.anims_api = anims_api
        self.cfg = dict(cfg)
        self.docs = {}            # код языка -> данные словаря
        self.dirty = set()        # языки с несохранёнными правками словаря
        # свой порядок строк в таблице сокращений: встроенные идут
        # по алфавиту, а перетаскивание мышью его меняет
        # the user's row order in the slang table: built-ins come
        # alphabetically and dragging changes that
        self._slang_order = list(cfg.get("slang_order") or [])
        self.glang = langs.code_of(self.cfg.get("target_lang", "it"))
        self.glossary_changed = False
        self.first_run = first_run
        self._busy = False

        self.setWindowTitle("Настройки — RP Chat Overlay")
        self.setStyleSheet(style_sheet(self._ui_scale()))
        if parent is None:
            self.setWindowFlags(Qt.WindowType.Window)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(210)
        self.stack = QStackedWidget()
        self.stack.setObjectName("page")
        self._views = []                 # страницы в прокрутке, по порядку
        self._anims_row = 0               # номер строки «Анимации» в списке разделов
        pages = (("Основные", "page_main", self._page_main),
                 ("Автоперевод", "page_auto", self._page_auto),
                 ("Чат игры", "page_game", self._page_game),
                 ("Словарь", "page_glossary", self._page_glossary),
                 ("Сокращения", "page_slang", self._page_slang),
                 ("Проверка", "page_test", self._page_test),
                 ("DeepL", "page_dlx", self._page_dlx),
                 ("Анимации", "page_anims", self._page_anims),
                 ("Модули", "page_modules", self._page_modules))
        for page_index, (name, attr, maker) in enumerate(pages):
            item = QListWidgetItem(name)
            item.setSizeHint(item.sizeHint().expandedTo(item.sizeHint() + _sz(0, 10)))
            self.nav.addItem(item)
            if attr == "page_anims":
                self._anims_row = page_index
            page = maker()
            setattr(self, attr, page)
            view = _scroll_page(page)
            if attr == "page_anims":
                self._anim_view = view
            self._views.append(view)
            self.stack.addWidget(view)
        self.nav.currentRowChanged.connect(self._nav_changed)
        self.nav.setCurrentRow(0)
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)
        root.addWidget(self._build_footer())

        self._load_language(self.glang, reload_table=True)
        self.setWindowTitle(i18n.t("Настройки — RP Chat Overlay"))
        i18n.retranslate(self)
        self._slang_pending = False
        self._fill_slang()
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._do_preview)
        # живое состояние модуля «Анимации»: что играет и что не отправилось
        # live state of the Animations module: what plays and what failed
        self._anim_note = ("", 0.0)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(1000)
        self._anim_timer.timeout.connect(self._anim_live_tick)
        self._anim_timer.start()
        self._apply_adaptive_size(center=True)
        # фокус — на список разделов: кнопка «Сохранить» не должна встречать
        # игрока подсветкой / focus goes to the section list, so the Save button
        # does not greet the player with a highlight
        QTimer.singleShot(0, self.nav.setFocus)

    # ------------------------------------------------------------ каркас
    def _build_header(self):
        w = QWidget()
        w.setObjectName("header")
        w.setStyleSheet("QWidget#header { background:#17171e; }")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 14, 20, 12)
        lay.setSpacing(2)
        self.header_title = _title(
            "Настройки" if not self.first_run else "Добро пожаловать в RP Chat Overlay",
            "h1")
        lay.addWidget(self.header_title)
        self.header_sub = QLabel()
        self.header_sub.setProperty("no_i18n", True)
        self.header_sub.setObjectName("sub")
        lay.addWidget(self.header_sub)
        return w

    def _build_footer(self):
        w = QWidget()
        w.setObjectName("footer")
        w.setStyleSheet("QWidget#footer { background:#17171e;"
                        "border-top:1px solid #26262f; }")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(20, 12, 20, 12)
        lay.setSpacing(10)
        # слева — редкое и опасное действие, справа — обычный порядок окон:
        # «Закрыть», затем главная кнопка. Left holds the rare destructive
        # action, right follows the usual window order: Close, then the main one.
        self.footer_hint = _hint(_FOOTER_IDLE)
        self.btn_reset = QPushButton("Сбросить всё")
        self.btn_reset.setObjectName("soft")
        self.btn_reset.setToolTip("Вернуть заводские настройки (словари не затрагиваются)")
        self.btn_reset.clicked.connect(self._reset_all)
        self.btn_cancel = QPushButton("Закрыть")
        self.btn_cancel.setToolTip("Закрыть окно: сохранять для этого не нужно")
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_save = QPushButton("Сохранить")
        self.btn_save.setObjectName("primary")
        # setDefault(True) заставляет Qt рисовать кнопку «нажатой по умолчанию»
        # всё время, поэтому Enter обрабатывается в keyPressEvent окна
        # setDefault(True) makes Qt draw a permanent default-button highlight, so
        # Enter is handled in the window keyPressEvent instead
        self.btn_save.setAutoDefault(False)
        self.btn_save.setToolTip("Применить настройки (Ctrl+S); окно остаётся открытым")
        self.btn_save.setShortcut(QKeySequence.StandardKey.Save)
        self.btn_save.clicked.connect(self._save)
        for b in (self.btn_reset, self.btn_cancel, self.btn_save):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setAutoDefault(False)
        lay.addWidget(self.btn_reset)
        lay.addWidget(self.footer_hint, 1)
        lay.addWidget(self.btn_cancel)
        lay.addWidget(self.btn_save)
        return w

    # ------------------------------------------------ размер под экран
    def _ui_scale(self):
        """Масштаб интерфейса из настроек: 0.8…1.8 (в окне — проценты)."""
        try:
            k = float(self.cfg.get("ui_scale", 1.0) or 1.0)
        except (TypeError, ValueError):
            k = 1.0
        return min(max(k, 0.8), 1.8)

    @staticmethod
    def _available():
        scr = QGuiApplication.primaryScreen()
        if scr is None:
            return None
        return scr.availableGeometry()

    def _apply_adaptive_size(self, center=True):
        """Подгоняет окно под экран: не больше 94 % рабочей области.

        На маленьком ноутбуке окно становится меньше, на большом мониторе —
        таким же, как раньше; всё, что не влезло по высоте, прокручивается.
        """
        avail = self._available()
        k = self._ui_scale()
        want_w, want_h = int(1020 * k), int(700 * k)
        if avail is None:
            w, h = want_w, want_h
        else:
            w = max(720, min(want_w, int(avail.width() * 0.94)))
            h = max(460, min(want_h, int(avail.height() * 0.94)))
        self.setMinimumSize(min(760, w), min(500, h))
        self.resize(w, h)
        self.nav.setFixedWidth(max(140, min(int(210 * k), int(w * 0.26))))
        if center and avail is not None:
            self.move(avail.x() + max(0, (avail.width() - w) // 2),
                      avail.y() + max(0, (avail.height() - h) // 2))

    def resizeEvent(self, e):
        """Меню разделов подстраивается под ширину окна, а не режет подписи."""
        super().resizeEvent(e)
        if hasattr(self, "nav"):
            self.nav.setFixedWidth(max(132, min(int(210 * self._ui_scale()),
                                                int(self.width() * 0.28))))

    def _ui_scale_changed(self, value=None):
        """Ползунок масштаба: сразу меняет шрифт и размер окна."""
        pct = int(value if value is not None else self.sp_ui_scale.value())
        k = min(max(pct / 100.0, 0.8), 1.8)
        self.cfg["ui_scale"] = round(k, 2)
        self.setStyleSheet(style_sheet(k))
        self._apply_adaptive_size(center=False)
        self.lb_ui_scale.setText(i18n.tf(
            "Шрифт и отступы окна: %d %%. На маленьком экране поставьте меньше.", pct))

    def _nav_changed(self, row):
        self._sync_glossary()
        self.stack.setCurrentIndex(row)
        cur = self.stack.currentWidget()
        if cur is not None and cur.widget() is getattr(self, "page_test", None):
            self._do_preview()

    # ------------------------------------------------------------ Основные
    def _page_main(self):
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(14)

        # язык перевода
        card, cl = _card()
        cl.addWidget(_title("Язык перевода", "sec"))
        cl.addWidget(_hint("Печатаете по-русски — в чат игры уходит текст на выбранном языке."))
        row = QHBoxLayout()
        self.cb_lang = QComboBox()
        self.cb_lang.setMinimumWidth(220)
        for code, name in langs.choices():
            self.cb_lang.addItem(name, code)
        self.cb_lang.setToolTip("Язык, на который переводится ваш текст")
        self.cb_lang.currentIndexChanged.connect(self._lang_changed_ui)
        row.addWidget(self.cb_lang)
        self.lb_lang_about = _hint("")
        self.lb_lang_about.setProperty("no_i18n", True)
        row.addWidget(self.lb_lang_about, 1)
        cl.addLayout(row)
        self.lb_lang_note = QLabel("")
        self.lb_lang_note.setProperty("no_i18n", True)
        self.lb_lang_note.setObjectName("warn")
        self.lb_lang_note.setWordWrap(True)
        cl.addWidget(self.lb_lang_note)
        row = QHBoxLayout()
        row.addWidget(QLabel("Что уходит в чат:"))
        self.cb_send_mode = QComboBox()
        self.cb_send_mode.addItem("Русская запись — как это читается", "reading")
        self.cb_send_mode.addItem("Текст на языке — для международных серверов", "native")
        self.cb_send_mode.setMinimumWidth(220)
        self.cb_send_mode.setToolTip(
            "«Русская запись» — в чат уходит «Чао» (кириллицей), как в исходной версии.\n"
            "«Текст на языке» — в чат уходит «Ciao» (для серверов, где читают латиницу).")
        self.cb_send_mode.currentIndexChanged.connect(lambda *_: self._do_preview())
        row.addWidget(self.cb_send_mode)
        row.addStretch(1)
        cl.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Язык интерфейса"))
        self.cb_ui_lang = QComboBox()
        self.cb_ui_lang.addItem("Русский", "ru")
        self.cb_ui_lang.addItem("English", "en")
        self.cb_ui_lang.setMinimumWidth(200)
        self.cb_ui_lang.setToolTip("Язык кнопок, подсказок и меню. Применяется сразу.")
        self.cb_ui_lang.currentIndexChanged.connect(self._ui_lang_changed)
        row.addWidget(self.cb_ui_lang)
        row.addStretch(1)
        cl.addLayout(row)
        cl.addWidget(_hint("Язык кнопок, подсказок и меню. Применяется сразу."))
        lay.addWidget(card)

        # режим переводчика: входящий текст → русский
        card, cl = _card()
        cl.addWidget(_title("Перевод входящего текста", "sec"))
        cl.addWidget(_hint("Режим для иностранного игрока на русскоязычном сервере: пишете "
                           "в оверлее на своём языке — в чат уходит перевод на русский. "
                           "Переводится каждое сообщение целиком, включая действия *...*; "
                           "служебные команды (/me, /to и другие) остаются без перевода."))
        self.chk_reverse = QCheckBox("Переводить на русский (режим переводчика)")
        self.chk_reverse.setToolTip("Ваш язык → русский. Enter отправляет перевод в чат игры.\n"
                                    "Служебные команды через / не переводятся.")
        self.chk_reverse.stateChanged.connect(self._reverse_changed)
        cl.addWidget(self.chk_reverse)
        self.lb_reverse = QLabel("")
        self.lb_reverse.setProperty("no_i18n", True)
        self.lb_reverse.setObjectName("warn")
        self.lb_reverse.setWordWrap(True)
        cl.addWidget(self.lb_reverse)
        lay.addWidget(card)

        # сленг и сокращения
        card, cl = _card()
        cl.addWidget(_title("Сленг и сокращения", "sec"))
        cl.addWidget(_hint("Сокращения из живого чата раскрываются до перевода, поэтому "
                           "в русском тексте сразу верные падеж, род и время: "
                           "«brb» → «я скоро вернусь», «afk» → «я не за клавиатурой», "
                           "«ty» → «спасибо». Если сервис всё же вернёт «afk» или «gg» "
                           "латиницей, подставляется короткий русский вариант. "
                           "В обратную сторону так же раскрываются русские сокращения: "
                           "«спс» → «спасибо», «мб» → «может быть»."))
        self.chk_slang = QCheckBox("Разворачивать сленг и сокращения")
        self.chk_slang.setToolTip(
            "lol, brb, afk, idk, idc, omw, gtg, gg, wp, ez, ty, thx, np, pls, sry,\n"
            "btw, imo, tbh, ngl, rn, asap, wdym, wbu, sup, cya, gn, gm, tmrw, cuz,\n"
            "ppl, rp, ooc, ic и растянутый смех (looool, lmaooo, xD).\n"
            "Обратное направление: спс, пж, нз, мб, крч, ща, оч, тож, збс, норм, прив.")
        cl.addWidget(self.chk_slang)
        lay.addWidget(card)

        # горячая клавиша
        card, cl = _card()
        cl.addWidget(_title("Горячая клавиша", "sec"))
        cl.addWidget(_hint("Клавиша ловит открытие оверлея. Работает только когда активна игра."))
        row = QHBoxLayout()
        self.ed_hotkey = KeyCapture()
        self.ed_hotkey.setFixedWidth(240)
        self.ed_hotkey.changed.connect(self._hotkey_changed)
        btn_hk = QPushButton("F6")
        btn_hk.setToolTip("Вернуть F6")
        btn_hk.clicked.connect(lambda: (self.ed_hotkey.setText("F6"), self._hotkey_changed("F6")))
        row.addWidget(self.ed_hotkey)
        row.addWidget(btn_hk)
        row.addStretch(1)
        cl.addLayout(row)
        self.lb_hotkey = QLabel("")
        self.lb_hotkey.setProperty("no_i18n", True)
        self.lb_hotkey.setObjectName("warn")
        self.lb_hotkey.setWordWrap(True)
        cl.addWidget(self.lb_hotkey)
        self.chk_show_settings = QCheckBox("Открывать это окно при запуске программы")
        cl.addWidget(self.chk_show_settings)

        # масштаб окна: адаптивность под маленькие и большие экраны
        row_scale = QHBoxLayout()
        row_scale.addWidget(QLabel("Масштаб интерфейса"))
        self.sp_ui_scale = QSpinBox()
        self.sp_ui_scale.setRange(80, 180)
        self.sp_ui_scale.setSingleStep(10)
        self.sp_ui_scale.setSuffix(" %")
        self.sp_ui_scale.setValue(int(round(self._ui_scale() * 100)))
        self.sp_ui_scale.setToolTip(
            "Размер шрифта и окна настроек. 100 % — обычный; на экране 1366×768 "

            "или при масштабе Windows 150 % удобнее 120–130 %.")
        self.sp_ui_scale.valueChanged.connect(self._ui_scale_changed)
        row_scale.addWidget(_num_row(self.sp_ui_scale))
        row_scale.addStretch(1)
        cl.addLayout(row_scale)
        self.lb_ui_scale = _hint("")
        self.lb_ui_scale.setProperty("no_i18n", True)
        cl.addWidget(self.lb_ui_scale)
        lay.addWidget(card)

        # оформление текста
        card, cl = _card()
        cl.addWidget(_title("Текст и маркеры", "sec"))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.ed_open = QLineEdit()
        self.ed_open.setMaxLength(2)
        self.ed_open.setMinimumWidth(64)
        self.ed_open.setMaximumWidth(84)
        self.ed_open.setMinimumHeight(30)
        self.ed_open.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.ed_close = QLineEdit()
        self.ed_close.setMaxLength(2)
        self.ed_close.setMinimumWidth(64)
        self.ed_close.setMaximumWidth(84)
        self.ed_close.setMinimumHeight(30)
        self.ed_close.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        dot = QLabel("…")
        dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.ed_open)
        row.addWidget(dot)
        row.addWidget(self.ed_close)
        row.addStretch(1)
        # QFormLayout получает сам слой, а не обёртку-виджет: у обёртки
        # не было своей высоты, и поля уезжали под соседнюю карточку
        form.addRow("Скобки перевода", row)
        self.sp_max = _small_spin(QSpinBox(), 20, 512, " символов", 170)
        form.addRow("Максимум в сообщении", _num_row(self.sp_max))
        self.sp_debounce = _small_spin(QSpinBox(), 100, 2000, " мс", 170, step=50)
        self.sp_debounce.setToolTip("Пауза после последнего символа, перед переводом")
        form.addRow("Задержка перевода", _num_row(self.sp_debounce))
        cl.addLayout(form)
        cl.addWidget(_hint("Внутри таких скобок текст переводится принудительно: "
                           "«+привет+» → «Ciao»."))
        lay.addWidget(card)
        lay.addStretch(1)
        return page

    def _ui_lang_changed(self, *_):
        """Переключение языка интерфейса прямо в окне настроек."""
        i18n.set_lang(self.cb_ui_lang.currentData() or "ru")
        i18n.retranslate(self)
        # названия и пояснения модулей берутся из реестра, а не из таблицы
        # переводов, поэтому обновляем их отдельно
        # module titles and descriptions come from the registry rather than the
        # translation table, so they are updated separately
        if hasattr(self, "cb_lang"):
            current = self.cb_lang.currentData()
            self.cb_lang.blockSignals(True)
            for index, (code, name) in enumerate(langs.choices()):
                if index < self.cb_lang.count():
                    self.cb_lang.setItemText(index, name)
            self.cb_lang.blockSignals(False)
            if current is not None:
                self.cb_lang.setCurrentIndex(max(0, self.cb_lang.findData(current)))
        for box, desc, module in getattr(self, "_module_rows", []):
            box.setText(module.title_en if i18n.is_en() else module.title_ru)
            desc.setText(module.desc_en if i18n.is_en() else module.desc_ru)
        for label, module in getattr(self, "_module_deps", []):
            if not module.requires:
                continue
            names = ", ".join(
                (modules.get(dep).title_en if i18n.is_en() else modules.get(dep).title_ru)
                for dep in module.requires if modules.get(dep))
            label.setText(i18n.t("Зависит от модуля: ") + names)
        self._refresh_dynamic()

    def _refresh_dynamic(self):
        """Обновляет подписи, которые собираются в коде (счётчики, подсказки)."""
        try:
            self._update_header()
            self._reverse_changed()
            self._load_language(self.glang, reload_table=False)
            self._update_glossary_ui()
            self._update_slang_ui()
            if hasattr(self, "chk_anims"):
                self._anim_stop_changed()
                self._update_anims_ui()
                if self.lb_anims_test.text():
                    self._anims_test()
            self._test_dir_changed(silent=True)
            if hasattr(self, "lb_ui_scale"):
                self.lb_ui_scale.setText(i18n.tf(
                    "Шрифт и отступы окна: %d %%. На маленьком экране "
                    "поставьте меньше.", int(self.sp_ui_scale.value())))
            if hasattr(self, "_dlx_refresh"):
                self._dlx_refresh()
        except Exception:
            log.exception("Не удалось обновить подписи после смены языка")

    def _reverse_changed(self, *_):
        """Подсказка под галочкой обратного режима."""
        if not hasattr(self, "lb_reverse"):
            return
        if self.chk_reverse.isChecked():
            self.lb_reverse.setText(i18n.t(
                "Включено: пишете на своём языке — Enter отправляет перевод на русский "
                "в чат игры. Команды /… не переводятся."))
        else:
            self.lb_reverse.setText(i18n.t(
                "Выключено: обычный режим — русский текст переводится на выбранный "
                "язык перевода."))

    def _hotkey_changed(self, text=None):
        ok, warn = check_hotkey(self.ed_hotkey.text())
        self.lb_hotkey.setText("" if ok else warn)
        self.lb_hotkey.setObjectName("warn")
        return ok

    def _lang_changed_ui(self, *_):
        code = self.cb_lang.currentData()
        self._sync_glossary()
        self._load_language(code, reload_table=True)
        self._update_header()
        self._do_preview()

    def _update_header(self):
        self.header_sub.setText(i18n.tf(
            "Язык: %s · горячая клавиша: %s · частота автоперевода: каждое %d-е",
            langs.label(langs.code_of(self.cb_lang.currentData() or "it")),
            _pretty_hotkey(self.ed_hotkey.text()),
            int(self.sp_every.value())))

    def _load_language(self, code, reload_table=False):
        """Показывает описание языка и (при необходимости) словарь этого языка."""
        code = langs.code_of(code)
        meta = langs.get(code)
        about = i18n.t(meta["about_en"]) if (i18n.is_en()
                                             and meta.get("about_en")) else meta["about"]
        self.lb_lang_about.setText(about)
        note = ""
        if not langs.reading(code):
            note = i18n.t("Для этого языка русская запись по звучанию не делается — "
                          "в оверлее показывается сам текст. Чтение есть только "
                          "у фраз из словаря.")
        self.lb_lang_note.setText(note)
        self.lb_lang_note.setVisible(bool(note))
        self.glang = code
        if hasattr(self, "lb_glang"):
            # название языка зависит от языка интерфейса, поэтому обновляется
            # и без перезагрузки таблицы
            # the language name depends on the interface language, so it is
            # refreshed even when the table is not reloaded
            self.lb_glang.setText(i18n.tf("Язык: %s", langs.label(code, native=True)))
        if reload_table and hasattr(self, "tbl"):
            self._fill_table(self._doc(code))
            self._update_glossary_ui()

    def _doc(self, code):
        """Данные словаря языка (из памяти или с диска)."""
        code = langs.code_of(code)
        if code not in self.docs:
            try:
                self.docs[code] = load_glossary_data(code)
            except Exception:
                log.exception("Не удалось прочитать словарь %s", code)
                self.docs[code] = {"_version": 1, "phrases": {}, "_fillers": []}
        return self.docs[code]

    # ------------------------------------------------------------ Автоперевод
    def _page_auto(self):
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(14)

        card, cl = _card()
        cl.addWidget(_title("Автоперевод", "sec"))
        cl.addWidget(_hint("Перевод вставляется в обычную русскую речь, чтобы она выглядела живой. "
                           "Например: «мне срочно нужна помощь» → «мне срочно нужна Aiutami»."))
        self.chk_auto = QCheckBox("Включить автоперевод")
        cl.addWidget(self.chk_auto)
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.sp_every = _small_spin(QSpinBox(), 2, 20, "-е сообщение", 230, prefix="каждое ")
        self.sp_every.setToolTip("Как часто переводить: одно сообщение из N")
        form.addRow("Частота", _num_row(self.sp_every))
        self.cb_pos = QComboBox()
        self.cb_pos.setMaximumWidth(340)
        for val, text in (("last", "последнее в серии (каждое N-е)"),
                          ("first", "первое в серии"),
                          ("random", "случайное в серии")):
            self.cb_pos.addItem(text, val)
        form.addRow("Какое сообщение", self.cb_pos)
        self.sp_frag = _small_spin(QSpinBox(), 1, 3, " фрагм.", 170)
        form.addRow("Фрагментов в сообщении", _num_row(self.sp_frag))
        row = QHBoxLayout()
        self.sp_min = _small_spin(QSpinBox(), 1, 6, "", 62)
        self.sp_maxw = _small_spin(QSpinBox(), 1, 8, "", 62)
        row.addWidget(QLabel(i18n.t("от")))
        row.addWidget(_num_row(self.sp_min, 56))
        row.addWidget(QLabel(i18n.t("до")))
        row.addWidget(_num_row(self.sp_maxw, 56))
        row.addWidget(QLabel(i18n.t("слов")))
        row.addStretch(1)
        w = QWidget()
        w.setLayout(row)
        form.addRow("Длина фрагмента", w)
        cl.addLayout(form)
        self.chk_prefer = QCheckBox("Сначала брать фразы из словаря")
        cl.addWidget(self.chk_prefer)
        lay.addWidget(card)

        card, cl = _card()
        cl.addWidget(_title("Слова-паразиты", "sec"))
        self.chk_filler = QCheckBox("Переводить всегда, вне зависимости от частоты")
        self.chk_filler.setToolTip("Слова-паразиты из PDF переводятся в каждом сообщении")
        cl.addWidget(self.chk_filler)
        self.lb_fillers = _hint("")
        self.lb_fillers.setProperty("no_i18n", True)
        cl.addWidget(self.lb_fillers)
        lay.addWidget(card)
        lay.addStretch(1)
        return page

    # ------------------------------------------------------------ Чат игры
    def _page_game(self):
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(14)

        card, cl = _card()
        cl.addWidget(_title("Отправка в игру", "sec"))
        self.chk_send = QCheckBox("Вставлять текст в чат игры")
        cl.addWidget(self.chk_send)
        self.chk_chat_first = QCheckBox("Сначала открывать чат игры (клавиша T), потом оверлей")
        self.chk_chat_first.setToolTip("Окружающие видят, что вы печатаете, а не стоите без действия")
        cl.addWidget(self.chk_chat_first)
        self.chk_submit = QCheckBox("Отправлять сразу (Enter в игре)")
        cl.addWidget(self.chk_submit)
        lay.addWidget(card)

        card, cl = _card()
        cl.addWidget(_title("Клавиша чата и задержки", "sec"))
        cl.addWidget(_hint("Задержки нужны, чтобы игра успевала открыть чат и вставить текст. "
                           "Если сообщения пропадают — увеличьте «после чата»."))
        cl.addWidget(_hint("Перед вставкой поле ввода чата полностью очищается (Ctrl+A, "
                           "Backspace): остаток прошлой строки не приклеится к команде."))
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.ed_chatkey = QLineEdit()
        self.ed_chatkey.setMaxLength(1)
        self.ed_chatkey.setFixedWidth(56)
        form.addRow("Клавиша чата", self.ed_chatkey)
        self.sp_focus = _small_spin(QSpinBox(), 0, 2000, " мс", 170, step=10)
        form.addRow("После переключения в игру", _num_row(self.sp_focus))
        self.sp_opendelay = _small_spin(QSpinBox(), 0, 2000, " мс", 170, step=10)
        form.addRow("После открытия чата", _num_row(self.sp_opendelay))
        self.sp_paste = _small_spin(QSpinBox(), 0, 2000, " мс", 170, step=10)
        form.addRow("После вставки текста", _num_row(self.sp_paste))
        cl.addLayout(form)
        lay.addWidget(card)
        lay.addStretch(1)
        return page

    # ------------------------------------------------------------ Словарь
    def _page_glossary(self):
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)

        head = QHBoxLayout()
        self.lb_glang = QLabel("Язык: —")
        self.lb_glang.setProperty("no_i18n", True)
        self.lb_glang.setStyleSheet("font-size:14px;font-weight:600;color:#dfe3ff;")
        head.addWidget(self.lb_glang)
        head.addStretch(1)
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Поиск по фразе или русскому значению…")
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.setMinimumWidth(180)
        self.ed_search.setMaximumWidth(320)
        self.ed_search.textChanged.connect(self._filter_table)
        head.addWidget(self.ed_search)
        lay.addLayout(head)
        self.lb_gcount = _hint("")
        self.lb_gcount.setProperty("no_i18n", True)
        head.insertWidget(1, self.lb_gcount)

        self.tbl = DragTable(self._move_glossary_row, 0, 4)
        self.tbl.setHorizontalHeaderLabels(["Паразит", "Фраза", "Русская запись",
                                            "Русские значения (через ;)"])
        head = self.tbl.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.tbl.setColumnWidth(0, 78)
        for c in (1, 2, 3):
            head.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setAlternatingRowColors(False)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.itemChanged.connect(self._table_edited)
        lay.addWidget(self.tbl, 1)
        lay.addWidget(_hint(
            "Строки перетаскиваются мышью — порядок сохраняется вместе со "
            "словарём. Он важен: если у двух фраз одинаковое русское значение, "
            "срабатывает та, что ниже в таблице."))

        btns = QHBoxLayout()
        b_add = QPushButton("Добавить фразу")
        b_add.clicked.connect(self._add_phrase)
        b_del = QPushButton("Удалить")
        b_del.setObjectName("danger")
        b_del.clicked.connect(self._del_phrase)
        b_imp = QPushButton("Импорт…")
        b_imp.setToolTip("JSON или CSV: фраза ; русская запись ; значения через ;")
        b_imp.clicked.connect(self._import)
        b_exp = QPushButton("Экспорт…")
        b_exp.clicked.connect(self._export)
        b_reset = QPushButton("Вернуть встроенный словарь")
        b_reset.clicked.connect(self._reset_glossary)
        for b in (b_add, b_del, b_imp, b_exp, b_reset):
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)
        lay.addWidget(_hint("Галочка в первой колонке — слово-паразит: фраза переводится в каждом "
                            "сообщении, даже когда автоперевод ещё не сработал. Выбор сохраняется "
                            "вместе со словарём. Значения — это то, что вы печатаете по-русски; "
                            "«е/ё» и «и/й» считаются одной буквой."))
        return page

    def _fill_table(self, data):
        self.tbl.blockSignals(True)
        phrases = data.get("phrases") or {}
        fillers = {self._norm_key(f.get("target")) for f in (data.get("_fillers") or [])
                   if isinstance(f, dict)}
        self.tbl.setRowCount(0)
        for phrase, val in phrases.items():
            ru, _, meanings = str(val).partition("|")
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            # галочка вместо звёздочки: видно, что это переключатель, и его
            # можно снять мышью или пробелом с клавиатуры
            # a checkbox instead of a star: it looks switchable and can be
            # toggled by mouse or by the space key
            mark = QTableWidgetItem("")
            mark.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
                          | Qt.ItemFlag.ItemIsSelectable)
            mark.setCheckState(Qt.CheckState.Checked if self._norm_key(phrase) in fillers
                               else Qt.CheckState.Unchecked)
            mark.setToolTip(i18n.t("Переводить эту фразу в каждом сообщении"))
            items = [mark,
                     QTableWidgetItem(str(phrase)),
                     QTableWidgetItem(ru.strip()),
                     QTableWidgetItem(meanings.strip().lstrip(";").strip())]
            for c, it in enumerate(items):
                it.setData(Qt.ItemDataRole.UserRole, str(phrase))
                if c:
                    it.setToolTip(it.text())
                self.tbl.setItem(r, c, it)
        self.tbl.blockSignals(False)
        self._filter_table()
        self._update_glossary_ui()

    @staticmethod
    def _norm_key(s):
        return " ".join(str(s or "").lower().replace("ё", "е").split())

    def _filter_table(self, *_):
        needle = self.ed_search.text().strip().lower().replace("ё", "е")
        shown = 0
        for r in range(self.tbl.rowCount()):
            texts = []
            for c in range(self.tbl.columnCount()):
                item = self.tbl.item(r, c)
                texts.append(item.text().lower() if item else "")
            match = (not needle) or any(needle in t.replace("ё", "е") for t in texts)
            self.tbl.setRowHidden(r, not match)
            shown += 1 if match else 0
        total = self.tbl.rowCount()
        self.lb_gcount.setText(i18n.tf("показано %d из %d", shown, total) if needle
                               else i18n.tf("всего фраз: %d", total))

    def _table_edited(self, item):
        self.glossary_changed = True
        self._collect_glossary()

    def _collect_glossary(self):
        """Переносит таблицу в данные словаря текущего языка.

        Галочка в первой колонке делает фразу словом-паразитом: движок берёт
        список из ключа «_fillers», а флаг «_fillers_user» говорит, что список
        выбран человеком и встроенный словарь его больше не перезаписывает.
        The checkbox in the first column makes a phrase a filler word: the engine
        reads «_fillers», and «_fillers_user» marks the list as the user's own so
        a built-in glossary update never overwrites it.
        """
        if not self.glossary_changed:
            return
        data = self._doc(self.glang)
        phrases = {}
        fillers = []
        for r in range(self.tbl.rowCount()):
            cells = []
            for c in range(1, 4):
                it = self.tbl.item(r, c)
                cells.append(it.text().strip() if it else "")
            phrase = cells[0]
            if not phrase:
                continue
            reading = cells[1] or phrase
            meanings = "; ".join(x.strip() for x in cells[2].split(";") if x.strip())
            phrases[phrase] = reading + " | " + meanings if meanings else reading + " | "
            mark = self.tbl.item(r, 0)
            if mark is not None and mark.checkState() == Qt.CheckState.Checked:
                forms = [x.strip() for x in cells[2].split(";") if x.strip()] or [reading]
                fillers.append({"target": phrase, "ru": forms})
        data["phrases"] = phrases
        data["_fillers"] = fillers
        data["_fillers_user"] = True
        self.docs[self.glang] = data
        self.dirty.add(self.glang)
        self.glossary_changed = False

    def _move_glossary_row(self, source, target):
        """Перетащили строку словаря / a glossary row was dragged.

        Порядок фраз сохраняется вместе со словарём и значит больше, чем кажется:
        если у двух фраз одинаковое русское значение, побеждает та, что ниже.
        The phrase order is saved with the glossary and matters more than it
        looks: when two phrases share a Russian meaning, the lower one wins.
        """
        DragTable.move_cells(self.tbl, source, target)
        self.glossary_changed = True
        self._collect_glossary()
        self._filter_table()
        log.info("Словарь: фраза переставлена (%d -> %d)", source, target)

    def _sync_glossary(self):
        self._collect_glossary()

    def _update_glossary_ui(self):
        data = self.docs.get(self.glang) or {}
        names = [f.get("target") for f in (data.get("_fillers") or []) if f.get("target")]
        self.lb_fillers.setText(
            i18n.tf("Для этого языка: %s",
                    ", ".join(names) if names else i18n.t("список не задан")))
        has_pack = langs.get(self.glang).get("pack")
        self.lb_gcount.setText(i18n.tf("всего фраз: %d",
                                       len(data.get("phrases") or {}))
                               + ("" if has_pack else i18n.t(" · встроенного словаря нет")))

    def _add_phrase(self):
        self.tbl.blockSignals(True)
        r = self.tbl.rowCount()
        self.tbl.insertRow(r)
        mark = QTableWidgetItem("")
        mark.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
                      | Qt.ItemFlag.ItemIsSelectable)
        mark.setCheckState(Qt.CheckState.Unchecked)
        self.tbl.setItem(r, 0, mark)
        for c in (1, 2, 3):
            self.tbl.setItem(r, c, QTableWidgetItem(""))
        self.tbl.blockSignals(False)
        self.glossary_changed = True
        self._filter_table()
        self.tbl.editItem(self.tbl.item(r, 1))

    def _del_phrase(self):
        rows = sorted({i.row() for i in self.tbl.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, i18n.t("Словарь"),
                                    i18n.t("Сначала выберите строку (строки)."))
            return
        for r in rows:
            self.tbl.removeRow(r)
        self.glossary_changed = True
        self._collect_glossary()
        self._update_glossary_ui()

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, i18n.t("Загрузить словарь"), str(DATA),
            i18n.t("Словари (*.json *.csv *.txt);;Все файлы (*)"))
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except OSError as e:
            QMessageBox.warning(self, i18n.t("Импорт"),
                                i18n.t("Не удалось прочитать файл:\n") + str(e))
            return
        phrases = {}
        try:
            if path.lower().endswith(".json"):
                obj = json.loads(text)
                src = obj.get("phrases") if isinstance(obj, dict) and "phrases" in obj else obj
                if not isinstance(src, dict):
                    raise ValueError(i18n.t("в JSON нужен объект «фраза: перевод»"))
                for k, v in src.items():
                    if isinstance(v, str) and not str(k).startswith("_"):
                        phrases[str(k)] = v
            else:
                for row in csv.reader(io.StringIO(text), delimiter=";"):
                    if len(row) < 2 or not row[0].strip():
                        continue
                    if row[0].strip().lower() in ("фраза", "phrase", "target"):
                        continue
                    phrase = row[0].strip()
                    reading = row[1].strip()
                    meanings = "; ".join(x.strip() for x in row[2:] if x.strip())
                    phrases[phrase] = reading + " | " + meanings if meanings else reading + " | "
        except Exception as e:
            QMessageBox.warning(self, i18n.t("Импорт"),
                                i18n.t("Файл не подошёл:\n") + str(e))
            return
        if not phrases:
            QMessageBox.information(self, i18n.t("Импорт"),
                                    i18n.t("В файле не нашлось фраз."))
            return
        data = self._doc(self.glang)
        cur = dict(data.get("phrases") or {})
        added = replaced = 0
        for k, v in phrases.items():
            if k in cur:
                replaced += 1
            else:
                added += 1
            cur[k] = v
        data["phrases"] = cur
        self.docs[self.glang] = data
        self.dirty.add(self.glang)
        self.glossary_changed = False
        self._fill_table(data)
        QMessageBox.information(
            self, i18n.t("Импорт"),
            i18n.tf("Загружено в «%s»: новых %d, обновлено %d.\n"
                    "Нажмите «Сохранить», чтобы применить.",
                    langs.label(self.glang), added, replaced))

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, i18n.t("Сохранить словарь"), str(glossary_path(self.glang)),
            "JSON (*.json);;CSV (*.csv)")
        if not path:
            return
        data = self._doc(self.glang)
        try:
            if path.lower().endswith(".csv"):
                with open(path, "w", encoding="utf-8-sig", newline="") as f:
                    w = csv.writer(f, delimiter=";")
                    w.writerow(["Фраза", "Русская запись", "Русские значения"])
                    for phrase, val in (data.get("phrases") or {}).items():
                        ru, _, mean = str(val).partition("|")
                        w.writerow([phrase, ru.strip(), mean.strip()])
            else:
                Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, i18n.t("Экспорт"),
                                i18n.t("Не удалось записать файл:\n") + str(e))
            return
        QMessageBox.information(self, i18n.t("Экспорт"),
                                i18n.t("Словарь сохранён:\n") + str(path))

    def _reset_glossary(self):
        ans = QMessageBox.question(
            self, i18n.t("Сбросить словарь"),
            i18n.tf("Вернуть встроенный словарь для «%s»?\nВаши добавленные фразы "
                    "этого языка будут потеряны.", langs.label(self.glang)))
        if ans != QMessageBox.StandardButton.Yes:
            return
        data = reset_glossary(self.glang)
        self.docs[self.glang] = data
        self.dirty.discard(self.glang)
        self.glossary_changed = False
        self._fill_table(data)

    # ---------------------------------------------------------- Сокращения
    def _page_slang(self):
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)

        head = QHBoxLayout()
        self.lb_slang_count = _hint("")
        self.lb_slang_count.setProperty("no_i18n", True)
        # две короткие строки вместо одной длинной: переносить нечего, поэтому
        # подпись не разъезжается на три строки в узком окне
        # two short lines instead of one long one: nothing to wrap, so the label
        # never breaks into three lines in a narrow window
        self.lb_slang_count.setWordWrap(False)
        self.lb_slang_count.setMinimumWidth(150)
        head.addWidget(self.lb_slang_count)
        head.addStretch(1)
        self.ed_slang_search = QLineEdit()
        self.ed_slang_search.setPlaceholderText("Поиск по сокращению или развороту…")
        self.ed_slang_search.setClearButtonEnabled(True)
        self.ed_slang_search.setMinimumWidth(180)
        self.ed_slang_search.setMaximumWidth(320)
        self.ed_slang_search.textChanged.connect(self._filter_slang)
        head.addWidget(self.ed_slang_search)
        lay.addLayout(head)

        self.tbl_slang = DragTable(self._move_slang_row, 0, 3)
        self.tbl_slang.setHorizontalHeaderLabels(
            ["Сокращение", "Разворот (полная фраза)", "Русский вариант"])
        for c in range(3):
            self.tbl_slang.horizontalHeader().setSectionResizeMode(
                c, QHeaderView.ResizeMode.Stretch)
        self.tbl_slang.verticalHeader().setVisible(False)
        self.tbl_slang.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_slang.itemChanged.connect(self._slang_edited)
        lay.addWidget(self.tbl_slang, 1)
        lay.addWidget(_hint(
            "Строки перетаскиваются мышью — порядок запоминается в настройках "
            "и остаётся таким при следующем открытии окна."))

        btns = QHBoxLayout()
        b_add = QPushButton("Добавить сокращение")
        b_add.clicked.connect(self._add_slang)
        b_del = QPushButton("Удалить")
        b_del.setObjectName("danger")
        b_del.clicked.connect(self._del_slang)
        b_imp = QPushButton("Импорт…")
        b_imp.setToolTip("JSON или CSV: сокращение ; разворот ; русский вариант")
        b_imp.clicked.connect(self._import_slang)
        b_exp = QPushButton("Экспорт…")
        b_exp.clicked.connect(self._export_slang)
        b_reset = QPushButton("Вернуть встроенные")
        b_reset.clicked.connect(self._reset_slang)
        for b in (b_add, b_del, b_imp, b_exp, b_reset):
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)

        lay.addWidget(_hint(
            "Свои сокращения работают так же, как встроенные, и перекрывают их: «afaik» → "
            "«as far as I know» → «насколько знаю». Во второй колонке — полная фраза на языке "
            "собеседника: её получает переводчик, поэтому падеж и род выходят верными. "
            "В третьей — короткая подстановка, если сервис вернул латиницу. Кириллическое "
            "сокращение («мнепох») идёт в обратную сторону, в текст на языке сервера. "
            "Пустые колонки выключают сокращение."))
        return page

    # заполнение и сбор таблицы сокращений
    def _fill_slang(self):
        if not hasattr(self, "tbl_slang"):
            return
        self.tbl_slang.blockSignals(True)
        self.tbl_slang.setRowCount(0)
        # порядок из настроек: перетащенные строки остаются на своих местах,
        # новые и незнакомые идут в конце / the saved order comes first
        order = {token: index for index, token in enumerate(self._slang_order)}
        rows = sorted(slang.entries(),
                      key=lambda row: order.get(row[0], len(order)))
        for token, expand, ru, own in rows:
            r = self.tbl_slang.rowCount()
            self.tbl_slang.insertRow(r)
            items = [QTableWidgetItem(("★ " if own else "") + token),
                     QTableWidgetItem(expand),
                     QTableWidgetItem(ru)]
            for c, it in enumerate(items):
                it.setData(Qt.ItemDataRole.UserRole, token)
                it.setToolTip(it.text())
                self.tbl_slang.setItem(r, c, it)
        self.tbl_slang.blockSignals(False)
        self._filter_slang()
        self._update_slang_ui()

    def _filter_slang(self, *_):
        if not hasattr(self, "tbl_slang"):
            return
        needle = self.ed_slang_search.text().strip().lower()
        shown = 0
        for r in range(self.tbl_slang.rowCount()):
            texts = []
            for c in range(self.tbl_slang.columnCount()):
                item = self.tbl_slang.item(r, c)
                texts.append(item.text().lower() if item else "")
            match = (not needle) or any(needle in t for t in texts)
            self.tbl_slang.setRowHidden(r, not match)
            shown += 1 if match else 0
        total = self.tbl_slang.rowCount()
        own = len(slang.user_entries())
        self.lb_slang_count.setText(
            i18n.tf("Показано: %d из %d\nСвоих: %d", shown, total, own) if needle
            else i18n.tf("Всего: %d\nСвоих: %d", total, own))

    def _update_slang_ui(self):
        if hasattr(self, "lb_slang_count"):
            own = len(slang.user_entries())
            total = len(slang.entries())
            self.lb_slang_count.setText(i18n.tf("Всего: %d\nСвоих: %d", total, own))

    def _slang_edited(self, item):
        self._slang_pending = True
        self._collect_slang()

    def _collect_slang(self):
        """Переносит таблицу в набор своих сокращений (в памяти)."""
        if not hasattr(self, "tbl_slang"):
            return {}
        rows = {}
        for r in range(self.tbl_slang.rowCount()):
            cells = []
            for c in range(3):
                it = self.tbl_slang.item(r, c)
                cells.append(it.text().strip() if it else "")
            token = cells[0].lstrip("★ ").strip()
            if not token:
                continue
            expand, ru = cells[1], cells[2]
            if token in slang.FOREIGN:
                if (expand, ru) == tuple(slang.FOREIGN[token]):
                    continue                     # встроенное не тронуто
            elif token in slang.RUSSIAN:
                if expand == slang.RUSSIAN[token] and not ru:
                    continue
            rows[token] = [expand, ru]
        # встроенные, которых в таблице нет, игрок убрал — значит, выключаем
        for token in list(slang.FOREIGN) + list(slang.RUSSIAN):
            if token not in rows and not self._slang_row_exists(token):
                rows[token] = ["", ""]
        slang.set_user(rows)
        self._slang_pending = True
        return rows

    def _move_slang_row(self, source, target):
        """Перетащили строку сокращений / a slang row was dragged.

        Порядок запоминается в настройках (``slang_order``): без этого таблица
        снова сортировалась бы по алфавиту при следующем открытии окна.
        The order is kept in the settings (``slang_order``): without it the table
        would be sorted alphabetically again the next time the window opens.
        """
        DragTable.move_cells(self.tbl_slang, source, target)
        self._slang_order = [
            (self.tbl_slang.item(row, 0).text().lstrip("★ ").strip()
             if self.tbl_slang.item(row, 0) else "")
            for row in range(self.tbl_slang.rowCount())]
        self._slang_pending = True
        self._collect_slang()
        self._filter_slang()

    def _slang_row_exists(self, token):
        for r in range(self.tbl_slang.rowCount()):
            it = self.tbl_slang.item(r, 0)
            if it and it.text().lstrip("★ ").strip().lower() == token.lower():
                return True
        return False

    def _sync_slang(self):
        """Сохранить свои сокращения на диск (вызывается по «Сохранить»)."""
        if not hasattr(self, "tbl_slang"):
            return
        slang.save_user(self._collect_slang())
        self._slang_pending = False

    def _add_slang(self):
        self.tbl_slang.blockSignals(True)
        r = self.tbl_slang.rowCount()
        self.tbl_slang.insertRow(r)
        for c in range(3):
            self.tbl_slang.setItem(r, c, QTableWidgetItem(""))
        self.tbl_slang.blockSignals(False)
        self._filter_slang()
        self.tbl_slang.editItem(self.tbl_slang.item(r, 0))

    def _del_slang(self):
        rows = sorted({i.row() for i in self.tbl_slang.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, i18n.t("Сокращения"),
                                    i18n.t("Сначала выберите строку (строки)."))
            return
        for r in rows:
            self.tbl_slang.removeRow(r)
        self._collect_slang()
        self._update_slang_ui()

    def _import_slang(self):
        path, _ = QFileDialog.getOpenFileName(
            self, i18n.t("Загрузить сокращения"), str(DATA),
            i18n.t("Сокращения (*.json *.csv *.txt);;Все файлы (*)"))
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except OSError as e:
            QMessageBox.warning(self, i18n.t("Импорт"),
                                i18n.t("Не удалось прочитать файл:\n") + str(e))
            return
        loaded = {}
        try:
            if path.lower().endswith(".json"):
                obj = json.loads(text)
                src = obj.get("custom") if isinstance(obj, dict) and "custom" in obj else obj
                if not isinstance(src, dict):
                    raise ValueError(i18n.t("в JSON нужен объект «сокращение: разворот»"))
                for k, v in src.items():
                    if isinstance(v, dict):
                        loaded[str(k)] = [str(v.get("expand", "")), str(v.get("ru", ""))]
                    elif isinstance(v, str):
                        loaded[str(k)] = [v, ""]
                    elif isinstance(v, (list, tuple)):
                        pair = list(v) + ["", ""]
                        loaded[str(k)] = [str(pair[0] or ""), str(pair[1] or "")]
            else:
                for row in csv.reader(io.StringIO(text), delimiter=";"):
                    if len(row) < 2 or not row[0].strip():
                        continue
                    if row[0].strip().lower() in ("сокращение", "abbr", "token"):
                        continue
                    loaded[row[0].strip()] = [row[1].strip(),
                                              row[2].strip() if len(row) > 2 else ""]
        except Exception as e:
            QMessageBox.warning(self, i18n.t("Импорт"),
                                i18n.t("Файл не подошёл:\n") + str(e))
            return
        if not loaded:
            QMessageBox.information(self, i18n.t("Импорт"),
                                    i18n.t("В файле не нашлось сокращений."))
            return
        cur = {k: list(v) for k, v in slang.user_entries().items()}
        added = sum(1 for k in loaded if k not in cur)
        cur.update(loaded)
        slang.set_user(cur)
        self._fill_slang()
        QMessageBox.information(
            self, i18n.t("Импорт"),
            i18n.tf("Загружено сокращений: %d (новых %d).\n"
                    "Нажмите «Сохранить», чтобы применить.", len(loaded), added))

    def _export_slang(self):
        path, _ = QFileDialog.getSaveFileName(
            self, i18n.t("Сохранить сокращения"), str(DATA / "slang-export.json"),
            "JSON (*.json);;CSV (*.csv)")
        if not path:
            return
        data = slang.entries()
        try:
            if path.lower().endswith(".csv"):
                with open(path, "w", encoding="utf-8-sig", newline="") as f:
                    w = csv.writer(f, delimiter=";")
                    w.writerow(["Сокращение", "Разворот", "Русский вариант"])
                    for token, expand, ru, _own in data:
                        w.writerow([token, expand, ru])
            else:
                payload = {"custom": slang.user_entries() or {
                    token: [expand, ru] for token, expand, ru, _o in data}}
                Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, i18n.t("Экспорт"),
                                i18n.t("Не удалось записать файл:\n") + str(e))
            return
        QMessageBox.information(self, i18n.t("Экспорт"),
                                i18n.t("Сокращения сохранены:\n") + str(path))

    def _reset_slang(self):
        ans = QMessageBox.question(
            self, i18n.t("Сбросить сокращения"),
            i18n.t("Вернуть встроенный список сокращений?\nВаши добавления будут "
                   "потеряны."))
        if ans != QMessageBox.StandardButton.Yes:
            return
        slang.save_user({})
        self._fill_slang()

    # ------------------------------------------------------------ DeepL
    def _page_dlx(self):
        """Локальный сервис DeepL: согласие, состояние, доступ, установка."""
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(14)

        # первый вопрос любого игрока: «а мне это надо?» — отвечаем до настроек
        # the first question any player has: "do I need this?" — answered first
        card, cl = _card()
        cl.addWidget(_title("Кому это нужно", "sec"))
        cl.addWidget(_hint(
            "Никому не обязательно. Без DeepL программа переводит через Google и "
            "остальные сервисы — так она работает сразу после установки, и "
            "большинству игроков этого достаточно. DeepL — это шаг в качестве для "
            "тех, кто готов потратить пять минут: либо включите VPN с зарубежным "
            "выходом, либо разверните свой сервис и впишите его адрес ниже (как "
            "это сделать — VERCEL.md в папке source/tools/deeplx-local). Общий "
            "адрес у всех быть не может: DeepL быстро упирается в лимиты частоты, "
            "и один перегруженный сервис отказывает всем сразу."))
        lay.addWidget(card)

        card, cl = _card()
        cl.addWidget(_title("DeepL рядом (DLX)", "sec"))
        cl.addWidget(_hint(
            "DLX — отдельная бесплатная программа с открытым кодом (лицензия MIT), "
            "которая работает на вашем компьютере и переводит через движок DeepL. "
            "Она занимает около 15 МБ и запускается вместе с программой. Текст при "
            "этом уходит на серверы DeepL — так же, как сейчас уходит в Google. "
            "Сервис неофициальный: DeepL может ограничить запросы, и тогда перевод "
            "автоматически вернётся к стандартным сервисам."))
        self.chk_dlx = QCheckBox("Переводить через DeepL в первую очередь")
        self.chk_dlx.setToolTip("Без этого флажка работает обычная цепочка сервисов")
        cl.addWidget(self.chk_dlx)
        self.chk_dlx_autostart = QCheckBox("Запускать сервис вместе с программой")
        cl.addWidget(self.chk_dlx_autostart)
        self.chk_dlx_update = QCheckBox("Проверять обновления сервиса при запуске")
        cl.addWidget(self.chk_dlx_update)
        lay.addWidget(card)

        card, cl = _card()
        cl.addWidget(_title("Состояние", "sec"))
        self.lb_dlx_state = _hint("")
        self.lb_dlx_state.setProperty("no_i18n", True)
        self.lb_dlx_state.setWordWrap(True)
        cl.addWidget(self.lb_dlx_state)
        row = QHBoxLayout()
        self.b_dlx_check = QPushButton("Проверить")
        self.b_dlx_check.setToolTip("Короткий запрос к сервису: отвечает ли он")
        self.b_dlx_check.clicked.connect(self._dlx_check)
        self.b_dlx_start = QPushButton("Запустить")
        self.b_dlx_start.clicked.connect(self._dlx_start)
        self.b_dlx_stop = QPushButton("Остановить")
        self.b_dlx_stop.clicked.connect(self._dlx_stop)
        self.b_dlx_install = QPushButton("Установить")
        self.b_dlx_install.setObjectName("primary")
        self.b_dlx_install.setToolTip("Скачать сервис с GitHub (около 15 МБ)")
        self.b_dlx_install.clicked.connect(self._dlx_install)
        self.b_dlx_remove = QPushButton("Удалить сервис")
        self.b_dlx_remove.setObjectName("danger")
        self.b_dlx_remove.clicked.connect(self._dlx_remove)
        for button in (self.b_dlx_check, self.b_dlx_start, self.b_dlx_stop,
                       self.b_dlx_install, self.b_dlx_remove):
            button.setAutoDefault(False)
            row.addWidget(button)
        row.addStretch(1)
        cl.addLayout(row)
        self.lb_dlx_path = _hint("")
        self.lb_dlx_path.setProperty("no_i18n", True)
        cl.addWidget(self.lb_dlx_path)
        lay.addWidget(card)

        card, cl = _card()
        cl.addWidget(_title("Доступ к сервису", "sec"))
        cl.addWidget(_hint(
            "Сервис слушает только ваш компьютер. Порт выбирается свободный, а "
            "запросы подписываются токеном, чтобы чужие программы не могли гонять "
            "трафик через ваш DeepL."))
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.sp_dlx_port = _small_spin(QSpinBox(), 0, 65535, "", 170)
        self.sp_dlx_port.setToolTip("0 — выбирать свободный порт автоматически")
        form.addRow("Порт (0 — автоматически)", _num_row(self.sp_dlx_port))
        self.ed_dlx_token = QLineEdit()
        self.ed_dlx_token.setReadOnly(True)
        self.ed_dlx_token.setToolTip("Токен знает только программа; в сеть он не уходит")
        form.addRow("Токен", self.ed_dlx_token)
        # свой сервис вместо бинарника: локальный сервер на Node.js или
        # развёрнутый DeepLX / a service of your own instead of the binary
        self.ed_dlx_url = QLineEdit()
        self.ed_dlx_url.setPlaceholderText("http://127.0.0.1:1188")
        self.ed_dlx_url.setToolTip(
            "Пусто — работать через dlx.exe. Адрес своего сервиса — и файл "
            "скачивать не нужно")
        form.addRow("Свой адрес сервиса", self.ed_dlx_url)
        self.ed_dlx_url_token = QLineEdit()
        self.ed_dlx_url_token.setPlaceholderText("необязательно")
        self.ed_dlx_url_token.setToolTip(
            "Токен, с которым запущен ваш сервис (TOKEN=…); если он не задан — пусто")
        form.addRow("Токен своего сервиса", self.ed_dlx_url_token)
        cl.addLayout(form)
        # пояснение под полем адреса: откуда взяться своему сервису
        # a remark under the address field: where such a service comes from
        self.lb_dlx_url_note = QLabel(
            "Свой адрес нужен, когда dlx.exe не скачивается или не запускается: "
            "сервер из source/tools/deeplx-local (npm start) слушает 1188 и "
            "говорит на том же языке, что и DLX. Адрес можно вставить целиком, "
            "вместе с /translate — лишний хвост программа отрежет сама.")
        self.lb_dlx_url_note.setWordWrap(True)
        self.lb_dlx_url_note.setStyleSheet("color:#8a8fa3;font-size:11px;")
        cl.addWidget(self.lb_dlx_url_note)
        row = QHBoxLayout()
        self.b_dlx_token = QPushButton("Выпустить новый токен")
        self.b_dlx_token.setAutoDefault(False)
        self.b_dlx_token.clicked.connect(self._dlx_token)
        row.addWidget(self.b_dlx_token)
        row.addStretch(1)
        cl.addLayout(row)
        lay.addWidget(card)

        card, cl = _card()
        cl.addWidget(_title("Если DeepL не отвечает", "sec"))
        cl.addWidget(_hint(
            "С июня 2025 года DeepL закрыт для российских адресов: сервис DLX "
            "работает, а DeepL отвечает отказом. Своего прокси DLX не поднимает — "
            "он только ходит через тот, что вы укажете, и этот прокси должен "
            "выходить не из России: адрес российского сервера DeepL так же не "
            "примет. Cloudflare WARP и One Client тут не помогут: они не меняют "
            "страну, ближайший узел у них в России. DNS-сервисы вроде NextDNS — "
            "тоже: они только находят адрес по имени, а DeepL смотрит на адрес. "
            "Годится VPN или клиент с "
            "зарубежным выходом, поднявший локальный порт: v2rayN 10809, "
            "Clash 7890, Hiddify 2080, Nekoray 2080. Порт 1080 — обычно SOCKS5, "
            "и программа сама подставит socks5://, если вы написали http://. "
            "Токен DeepL Pro региональную блокировку не снимает — он только для "
            "владельцев подписки и снимает лимиты."))
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.ed_dlx_proxy = QLineEdit()
        self.ed_dlx_proxy.setPlaceholderText("http://127.0.0.1:10809")
        self.ed_dlx_proxy.setToolTip("Пусто — идти напрямую; http, https или socks5")
        form.addRow("HTTP-прокси", self.ed_dlx_proxy)
        self.ed_dlx_pro = QLineEdit()
        self.ed_dlx_pro.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_dlx_pro.setPlaceholderText("необязательно")
        self.ed_dlx_pro.setToolTip("OAuth-токен DeepL Pro; без него работает "
                                   "бесплатный путь")
        form.addRow("Токен DeepL Pro", self.ed_dlx_pro)
        cl.addLayout(form)
        # замечание к адресу прокси: опечатку видно сразу, до запуска сервиса
        # a remark about the proxy address: a typo shows up before the service runs
        self.chk_dlx_sysproxy = QCheckBox(
            "Брать прокси из настроек Windows, если свой не задан")
        self.chk_dlx_sysproxy.setToolTip(
            "VPN в режиме «системный прокси» прописывает адрес в Windows — "
            "сервис будет ходить через него")
        cl.addWidget(self.chk_dlx_sysproxy)
        row = QHBoxLayout()
        self.b_dlx_proxy_check = QPushButton("Проверить выход")
        self.b_dlx_proxy_check.setAutoDefault(False)
        self.b_dlx_proxy_check.setToolTip(
            "Покажет адрес и страну, из которой выходит прокси (запрос идёт через него)")
        self.b_dlx_proxy_check.clicked.connect(self._dlx_proxy_exit)
        row.addWidget(self.b_dlx_proxy_check)
        row.addStretch(1)
        cl.addLayout(row)
        self.lb_dlx_proxy_note = QLabel("")
        self.lb_dlx_proxy_note.setWordWrap(True)
        self.lb_dlx_proxy_note.setProperty("no_i18n", True)
        self.lb_dlx_proxy_note.setStyleSheet("color:#8a8fa3;font-size:11px;")
        cl.addWidget(self.lb_dlx_proxy_note)
        self.ed_dlx_proxy.textChanged.connect(self._dlx_proxy_note)
        lay.addWidget(card)
        lay.addStretch(1)
        # прогресс скачивания приходит из потока строкой; окно читает её таймером
        # download progress arrives from a thread as plain text; a timer reads it
        self._dlx_progress = ""
        self._dlx_timer = QTimer(self)
        self._dlx_timer.setInterval(300)
        self._dlx_timer.timeout.connect(lambda: self.lb_dlx_state.setText(
            self._dlx_progress) if self._dlx_progress else None)
        self._dlx_refresh()
        return page

    # ------------------------------------------------ работа с сервисом
    def _dlx_state_text(self):
        """Текст состояния сервиса / the service state as text."""
        if self.dlx is None:
            return i18n.t("Сервис не подключён к этому окну — перезапустите программу.")
        status = self.dlx.status()
        state = status.get("state")
        words = {
            "ready": i18n.tf("Работает · порт %d", status.get("port") or 0),
            "starting": i18n.t("Запускается…"),
            "off": i18n.t("Остановлен"),
            "missing": i18n.t("Не установлен"),
            "upstream": i18n.t("Работает, но DeepL не отвечает (503)"),
            "error": i18n.tf("Ошибка: %s", status.get("reason") or ""),
        }
        text = words.get(state, str(state))
        version = status.get("version")
        if version:
            text += i18n.tf(" · версия %s", version)
        note = status.get("note")
        if note:
            text += i18n.tf(" · %s", note)
        return text

    def _dlx_refresh(self):
        """Обновляет подписи страницы по текущему состоянию / refresh the page."""
        if not hasattr(self, "lb_dlx_state"):
            return
        self.lb_dlx_state.setText(self._dlx_state_text())
        if self.dlx is not None:
            token = self.dlx.token
            self.ed_dlx_token.setText(token[:8] + "…" if token else "")
            self.lb_dlx_path.setText(i18n.tf("Файлы сервиса: %s", str(self.dlx.dir)))
            self.b_dlx_install.setText(i18n.t("Обновить") if self.dlx.installed()
                                       else i18n.t("Установить"))
        for button in (self.b_dlx_start, self.b_dlx_stop, self.b_dlx_install,
                       self.b_dlx_remove, self.b_dlx_check, self.b_dlx_token):
            button.setEnabled(self.dlx is not None)

    def _dlx_proxy_note(self):
        """Проверяет адрес прокси на вид и подсказывает решение.

        Checks the proxy address by its looks and suggests the fix: a typo in the
        scheme or a SOCKS5 port written as http:// both end with a silent service.
        """
        if not hasattr(self, "lb_dlx_proxy_note"):
            return
        text = self.ed_dlx_proxy.text().strip()
        if not text:
            self.lb_dlx_proxy_note.setText("")
            return
        normalized = dlx_mod.normalize_proxy(text)
        if not normalized:
            self.lb_dlx_proxy_note.setStyleSheet("color:#ff8f8f;font-size:11px;")
            self.lb_dlx_proxy_note.setText(i18n.t(
                "Адрес не подходит: нужен http://, https:// или socks5:// с портом."))
            return
        self.lb_dlx_proxy_note.setStyleSheet("color:#8a8fa3;font-size:11px;")
        parsed = urllib.parse.urlparse(normalized)
        if parsed.scheme == "http" and parsed.port in (1080, 1081, 9050):
            self.lb_dlx_proxy_note.setText(i18n.tf(
                "Порт %d — обычно у SOCKS5; сервис сам подставит socks5://.",
                parsed.port))
        else:
            self.lb_dlx_proxy_note.setText("")

    def _dlx_proxy_exit(self):
        """Проверяет, из какой страны выходит прокси / where the proxy exits.

        Единственный способ убедиться, что прокси годится для DeepL: он смотрит
        на адрес источника, поэтому смотрим и мы — через сам прокси.
        The only way to be sure a proxy suits DeepL: it looks at the source
        address, so we look through that very proxy.
        """
        text = self.ed_dlx_proxy.text().strip()
        if not text:
            QMessageBox.information(self, i18n.t("DeepL рядом"),
                                    i18n.t("Прокси не задан — сервис ходит напрямую."))
            return
        proxy = dlx_mod.normalize_proxy(text)
        if not proxy:
            QMessageBox.warning(self, i18n.t("DeepL рядом"), i18n.t(
                "Адрес не подходит: нужен http://, https:// или socks5:// с портом."))
            return
        verdict = {}

        def job():
            ok, line = dlx_mod.proxy_exit(proxy)
            verdict["text"] = line
            return ok

        def done(ok, reason):
            line = verdict.get("text") or reason or i18n.t("неизвестно")
            self.lb_dlx_proxy_note.setStyleSheet(
                "color:#66d18b;font-size:11px;" if ok else "color:#ff8f8f;font-size:11px;")
            self.lb_dlx_proxy_note.setText(line)
            if ok:
                QMessageBox.information(self, i18n.t("DeepL рядом"),
                                        i18n.tf("Прокси работает. Выход: %s", line))
            else:
                QMessageBox.warning(self, i18n.t("DeepL рядом"),
                                    i18n.tf("Прокси не годится: %s", line))
        self._dlx_busy(True, i18n.t("Проверяю прокси…"))
        job_runner = DlxJob(job, self)
        self._dlx_job = job_runner

        def finish(ok, reason):
            self._dlx_busy(False)
            self._dlx_refresh()
            done(ok, reason)
        job_runner.finished.connect(finish)
        job_runner.start()

    def _dlx_guard(self):
        """Предупреждение, если сервис не подключён / warn when there is no service."""
        if self.dlx is None:
            QMessageBox.warning(self, i18n.t("DeepL рядом"),
                                i18n.t("Сервис не подключён — перезапустите программу."))
            return False
        return True

    def _dlx_busy(self, busy, text=""):
        """Блокирует кнопки на время работы / locks the buttons while working."""
        if text:
            self.lb_dlx_state.setText(text)
        for button in (self.b_dlx_check, self.b_dlx_start, self.b_dlx_stop,
                       self.b_dlx_install, self.b_dlx_remove, self.b_dlx_token,
                       self.b_dlx_proxy_check):
            button.setEnabled(not busy)
        if busy:
            self._dlx_progress = text
            self._dlx_timer.start()
        else:
            self._dlx_timer.stop()

    def _dlx_run(self, fn, busy_text, done):
        """Выполняет действие в фоне и возвращается к окну с результатом.

        Runs an action in the background and comes back to the window with the
        result; the callback runs on the main thread.
        """
        self._dlx_busy(True, busy_text)
        job = DlxJob(fn, self)
        self._dlx_job = job          # ссылка, иначе объект соберёт сборщик мусора
        def finish(ok, reason):
            self._dlx_busy(False)
            self._dlx_refresh()
            done(ok, reason)
        job.finished.connect(finish)
        job.start()

    def _dlx_check(self):
        """Короткая проверка: отвечает ли сервис / a short health check."""
        if not self._dlx_guard():
            return
        def done(ok, reason):
            QMessageBox.information(
                self, i18n.t("DeepL рядом"),
                i18n.t("Сервис отвечает нормально.") if ok
                else i18n.t("Сервис не отвечает. Нажмите «Запустить» или «Установить»."))
        self._dlx_run(self.dlx.health, i18n.t("Проверяю…"), done)

    def _dlx_start(self):
        """Запуск сервиса вручную / start the service by hand."""
        if not self._dlx_guard():
            return
        def done(ok, reason):
            if not ok:
                QMessageBox.warning(
                    self, i18n.t("DeepL рядом"),
                    i18n.t("Запустить не удалось: %s")
                    % (self.dlx.status().get("reason") or reason
                       or i18n.t("неизвестно")))
        self._dlx_run(self.dlx.ensure, i18n.t("Запускается…"), done)

    def _dlx_stop(self):
        """Остановка сервиса / stop the service."""
        if not self._dlx_guard():
            return
        self.dlx.stop()
        self._dlx_refresh()

    def _dlx_install(self):
        """Скачивание и установка сервиса / download and install the service."""
        if not self._dlx_guard():
            return
        answer = QMessageBox.question(
            self, i18n.t("Установка сервиса"),
            i18n.t("Скачать локальный сервис DeepL с GitHub?\n\n"
                   "Около 15 МБ, лицензия MIT, файл кладётся рядом с программой.\n"
                   "Текст перевода будет уходить на серверы DeepL."))
        if answer != QMessageBox.StandardButton.Yes:
            return
        def job():
            return self.dlx.install(lambda text: setattr(self, "_dlx_progress", text))
        def done(ok, reason):
            if not ok:
                QMessageBox.warning(
                    self, i18n.t("DeepL рядом"),
                    i18n.t("Установить не удалось: %s")
                    % (self.dlx.status().get("reason") or reason
                       or i18n.t("неизвестно")))
                return
            self._dlx_refresh()
            QMessageBox.information(self, i18n.t("DeepL рядом"),
                                    i18n.t("Сервис установлен и готов к работе."))
            if self.chk_dlx.isChecked():
                # запуск тоже в фоне: ожидание готовности занимает секунды
                # the start also runs in the background: waiting for readiness
                # takes seconds
                self._dlx_run(self.dlx.ensure, i18n.t("Запускается…"),
                              lambda ok, reason: None)
        self._dlx_run(job, i18n.t("Скачиваю…"), done)

    def _dlx_remove(self):
        """Удаление сервиса с диска / remove the service from disk."""
        if not self._dlx_guard():
            return
        answer = QMessageBox.question(
            self, i18n.t("Удаление сервиса"),
            i18n.t("Удалить сервис DeepL с диска?\nПрограмма вернётся к обычным "
                   "сервисам перевода, настройки останутся."))
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.dlx.uninstall()
        self.chk_dlx.setChecked(False)
        self._dlx_refresh()

    def _dlx_token(self):
        """Новый токен доступа / a new access token."""
        if not self._dlx_guard():
            return
        try:
            self.dlx.rotate_token()
        except dlx_mod.DlxError as error:
            QMessageBox.warning(self, i18n.t("DeepL рядом"), str(error))
            return
        self._dlx_refresh()

    # ------------------------------------------------------------ Анимации
    def _page_anims(self):
        """Раздел «Анимации»: правила «слово → /anim» и клавиша остановки.

        The Animations page: keyword → /anim rules and the stop key.

        Таблица — единственный источник правил, пока окно открыто: строки
        собираются в объекты anims.Rule и попадают в config.json только по
        кнопке «Сохранить».
        The table is the only source of rules while the window is open: rows are
        collected into anims.Rule objects and reach config.json only on Save.
        """
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)

        card, cl = _card()
        self.chk_anims = QCheckBox("Включить модуль «Анимации»")
        self.chk_anims.setChecked(bool(self.cfg.get("anims_enabled", False)))
        self.chk_anims.toggled.connect(self._anims_toggled)
        cl.addWidget(self.chk_anims)
        cl.addWidget(_hint(
            "Ключевое слово в вашем сообщении запускает анимацию: в чат игры уходит "
            "/anim «название», а через заданное время она останавливается — командой "
            "/sa, нажатием клавиши или обоими способами, как выбрано ниже. При "
            "зацикливании остановки нет: по истечении того же времени анимация "
            "просто запускается снова, пока не нажать клавишу остановки. "
            "Длительность 0 мс означает «не останавливать вовсе». Работает только "
            "вместе с модулем «Отправка в игру»."))

        key_row = QHBoxLayout()
        key_label = _title("Клавиша остановки зацикливания", "sec")
        key_row.addWidget(key_label)
        self.ed_anim_stop = KeyCapture()
        self.ed_anim_stop.setMaximumWidth(180)
        self.ed_anim_stop.setMinimumWidth(120)
        self.ed_anim_stop.setText(str(self.cfg.get("anim_stop_key", "f") or "f"))
        self.ed_anim_stop.setToolTip(
            "Клавиша, которая прекращает зацикленную анимацию. Нажатие получает и "
            "игра, поэтому подойдёт обычная игровая клавиша вроде F.")
        self.ed_anim_stop.changed.connect(self._anim_stop_changed)
        key_row.addWidget(self.ed_anim_stop)
        key_row.addStretch(1)
        cl.addLayout(key_row)
        self.lb_anim_stop = QLabel("")
        self.lb_anim_stop.setProperty("no_i18n", True)
        self.lb_anim_stop.setWordWrap(True)
        cl.addWidget(self.lb_anim_stop)

        # чем именно гасить анимацию по истечении времени
        # what exactly puts the animation out when the time is up
        self.chk_anim_stop_sa = QCheckBox("Останавливать анимацию командой /sa")
        self.chk_anim_stop_sa.setChecked(bool(self.cfg.get("anim_stop_by_sa", True)))
        self.chk_anim_stop_sa.setToolTip(
            "В чат игры уходит /sa — так анимацию гасит сама игра.")
        self.chk_anim_stop_sa.toggled.connect(self._anim_stop_changed)
        cl.addWidget(self.chk_anim_stop_sa)

        self.chk_anim_stop_key = QCheckBox(
            "Останавливать анимацию нажатием клавиши F (симуляция)")
        self.chk_anim_stop_key.setProperty("no_i18n", True)
        self.chk_anim_stop_key.setChecked(bool(self.cfg.get("anim_stop_by_key", False)))
        self.chk_anim_stop_key.setToolTip(
            "Программа нажимает клавишу остановки в игре, как если бы её нажали вы. "
            "Клавиша берётся из поля выше.")
        self.chk_anim_stop_key.toggled.connect(self._anim_stop_changed)
        cl.addWidget(self.chk_anim_stop_key)

        # отрицание: «открыл зонт» срабатывает, «не открыл зонт» — нет
        # negation: «открыл зонт» fires, «не открыл зонт» stays silent
        self.chk_anim_negation = QCheckBox("Не срабатывать на отрицание")
        self.chk_anim_negation.setChecked(bool(self.cfg.get("anim_skip_negation", True)))
        self.chk_anim_negation.setToolTip(
            "Правило молчит, если перед найденным словом стоит «не», «ни», "
            "«никогда» и подобное: «открыл зонт» сработает, «не открыл зонт» — "
            "нет. Если отрицание есть в самом ключе, проверка для него "
            "выключается.")
        self.chk_anim_negation.toggled.connect(self._anims_changed)
        cl.addWidget(self.chk_anim_negation)

        # хвост после анимации: к её длительности добавляется столько, и только
        # потом запускается следующая — игра успевает закрыть чат, сервер
        # принять остановку, и вторая анимация из того же сообщения не теряется
        # the tail after an animation: it is added to the animation's own length
        # and only then does the next one start, so the game closes its chat and
        # the server takes the stop — the second animation is not lost
        gap_row = QHBoxLayout()
        gap_row.addWidget(_title("Пауза после анимации, мс", "sec"))
        self.sp_anim_gap = QSpinBox()
        self.sp_anim_gap.setRange(0, 10000)
        self.sp_anim_gap.setSingleStep(10)
        self.sp_anim_gap.setValue(self._anim_extra())
        self.sp_anim_gap.setMaximumWidth(120)
        self.sp_anim_gap.setToolTip(
            "Добавляется к длительности самой анимации, и только потом "
            "запускается следующая из того же сообщения: 1500 мс + 50 мс. "
            "Если из двух ключевых слов играет только первое, увеличьте — "
            "серверу нужно время принять /sa и следующую /anim. "
            "0 — запускать сразу после анимации.")
        self.sp_anim_gap.valueChanged.connect(self._anims_changed)
        gap_row.addWidget(self.sp_anim_gap)
        gap_row.addStretch(1)
        cl.addLayout(gap_row)
        lay.addWidget(card)

        self.lb_anims_count = _hint("")
        self.lb_anims_count.setProperty("no_i18n", True)
        lay.addWidget(self.lb_anims_count)

        self.tbl_anims = DragTable(self._move_anims_row, 0, 7)
        # короткие заголовки: длинные подписи не влезали в столбцы на узком окне
        # short headers: the long ones did not fit the columns in a narrow window
        self.tbl_anims.setHorizontalHeaderLabels(
            ["Вкл", "Ключевые слова", "/anim", "Режим", "Формы", "мс",
             "Зацикливать"])
        head = self.tbl_anims.horizontalHeader()
        head.setMinimumSectionSize(38)
        for column, policy in ((0, QHeaderView.ResizeMode.ResizeToContents),
                               (1, QHeaderView.ResizeMode.Stretch),
                               (2, QHeaderView.ResizeMode.Stretch),
                               (3, QHeaderView.ResizeMode.Fixed),
                               (4, QHeaderView.ResizeMode.Fixed),
                               (5, QHeaderView.ResizeMode.ResizeToContents),
                               (6, QHeaderView.ResizeMode.ResizeToContents)):
            head.setSectionResizeMode(column, policy)
        # «Режим» и «Формы» — фиксированной ширины: иначе длинный список режимов
        # распирал столбец и сжимал соседние до нечитаемых
        # the mode and forms columns keep a fixed width: otherwise the long list
        # of modes inflated it and squeezed its neighbours into slivers
        self.tbl_anims.setColumnWidth(3, 124)
        self.tbl_anims.setColumnWidth(4, 92)
        self.tbl_anims.setMinimumWidth(600)
        self.tbl_anims.verticalHeader().setVisible(False)
        self.tbl_anims.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_anims.setWordWrap(False)
        self.tbl_anims.itemChanged.connect(self._anims_edited)
        self.tbl_anims.itemSelectionChanged.connect(self._update_anims_ui)
        # ПКМ по правилу — свойства анимации: варианты, названия и описания.
        # Это же меню умеет добавить второй вариант к обычному правилу.
        # right-click a rule opens its properties: variants, titles and
        # descriptions. The same menu adds a second variant to a plain rule.
        self.tbl_anims.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tbl_anims.customContextMenuRequested.connect(self._anims_menu)
        lay.addWidget(self.tbl_anims, 1)

        btns = QHBoxLayout()
        self.bt_anim_add = QPushButton("Добавить правило")
        self.bt_anim_add.clicked.connect(self._add_anim)
        self.bt_anim_del = QPushButton("Удалить")
        self.bt_anim_del.setObjectName("danger")
        self.bt_anim_del.clicked.connect(self._del_anim)
        self.bt_anim_up = QPushButton("Выше")
        self.bt_anim_up.clicked.connect(lambda: self._move_anim(-1))
        self.bt_anim_down = QPushButton("Ниже")
        self.bt_anim_down.clicked.connect(lambda: self._move_anim(1))
        b_imp = QPushButton("Импорт…")
        b_imp.setToolTip("Загрузить правила из JSON, созданного кнопкой «Экспорт…»")
        b_imp.clicked.connect(self._import_anims)
        b_exp = QPushButton("Экспорт…")
        b_exp.clicked.connect(self._export_anims)
        for button in (self.bt_anim_add, self.bt_anim_del, self.bt_anim_up,
                       self.bt_anim_down, b_imp, b_exp):
            btns.addWidget(button)
        btns.addStretch(1)
        lay.addLayout(btns)

        self.lb_anims_problem = QLabel("")
        self.lb_anims_problem.setProperty("no_i18n", True)
        self.lb_anims_problem.setWordWrap(True)
        self.lb_anims_problem.setStyleSheet("color:#ffb45b;")
        lay.addWidget(self.lb_anims_problem)

        live_card, ll = _card()
        ll.addWidget(_title("Проверка в игре", "sec"))
        ll.addWidget(_hint(
            "Слова проверяются в окне настроек, а отправку видит только игра. "
            "Кнопка «Отправить /anim в игру» запускает выбранное правило прямо "
            "сейчас — так видно, доходит ли команда: если игра не ответила, "
            "причина появится здесь же."))
        live_row = QHBoxLayout()
        self.bt_anim_send = QPushButton("Отправить /anim в игру")
        self.bt_anim_send.clicked.connect(self._anim_send_now)
        self.bt_anim_halt = QPushButton("Остановить анимацию")
        self.bt_anim_halt.clicked.connect(self._anim_halt_now)
        if getattr(self, "anims_api", None) is None:
            for button in (self.bt_anim_send, self.bt_anim_halt):
                button.setEnabled(False)
                button.setToolTip("Доступно, когда настройки открыты из программы")
        live_row.addWidget(self.bt_anim_send)
        live_row.addWidget(self.bt_anim_halt)
        live_row.addStretch(1)
        ll.addLayout(live_row)
        self.lb_anim_live = QLabel("")
        self.lb_anim_live.setProperty("no_i18n", True)
        self.lb_anim_live.setWordWrap(True)
        ll.addWidget(self.lb_anim_live)
        lay.addWidget(live_card)
        self.anim_test_done.connect(self._anim_send_result)

        test_card, tl = _card()
        tl.addWidget(_title("Проверка правила", "sec"))
        tl.addWidget(_hint(
            "Напишите фразу так, как отправили бы её в игру, и посмотрите, какие "
            "правила на неё сработают. Здесь проверяются только слова: отправку "
            "команд проверяет блок «Проверка в игре» выше."))
        test_row = QHBoxLayout()
        self.ed_anims_test = QLineEdit()
        self.ed_anims_test.setPlaceholderText("Например: /me привет")
        self.ed_anims_test.returnPressed.connect(self._anims_test)
        test_row.addWidget(self.ed_anims_test, 1)
        b_test = QPushButton("Проверить")
        b_test.clicked.connect(self._anims_test)
        test_row.addWidget(b_test)
        tl.addLayout(test_row)
        self.lb_anims_test = QLabel("")
        self.lb_anims_test.setProperty("no_i18n", True)
        self.lb_anims_test.setWordWrap(True)
        tl.addWidget(self.lb_anims_test)
        lay.addWidget(test_card)

        lay.addWidget(_hint(
            "Несколько ключевых слов в одном правиле разделяются запятой: «привет, "
            "здравствуй». Совпадение ищется целым словом и без учёта регистра, «ё» "
            "и «е» считаются одной буквой. Столбец «Формы» решает, как сравнивать "
            "слово: «Точно» — ровно написанное, «Основы» — любые падежи и "
            "спряжения («открыл» = «открывает»), «Леммы» — по словарю pymorphy3. "
            "Одно и то же слово правило запускает один раз, сколько бы раз оно "
            "ни повторилось, а каждое своё ключевое слово — отдельным выходом: "
            "«да ну, да брось» на «Да ну да брось» сыграет анимацию дважды. "
            "Если в одном сообщении совпало несколько правил, "
            "анимации играют по очереди, по одной: пока одна на экране, следующая "
            "ждёт. Порядок — как в самом сообщении: «Чёрт, я устал *кашляет*» "
            "сначала запустит анимацию на «чёрт», потом на «кашляет», даже если в "
            "таблице эти правила стоят наоборот. Если один ключ целиком входит в "
            "другой, играет только длинный: на «Сел откинувшись» сработает «сел "
            "откинувшись», а «сел» промолчит — иначе короткая анимация сразу же "
            "погасила бы длинную. Отдельные упоминания в том же сообщении "
            "считаются: «Сел откинувшись, а потом сел прямо» запустит обе."))
        lay.addWidget(_hint(
            "Строки таблицы перетаскиваются мышью — вместе с правилом едут его "
            "режим, формы, длительность и галочки. Пока строку тянут, она "
            "подсвечена, а синяя линия показывает, куда она встанет. Порядок в "
            "таблице нужен для удобства: в игре анимации играют по порядку слов "
            "в сообщении."))
        lay.addWidget(_hint(
            "ПКМ по строке — «Свойства анимации…»: там задаются варианты, если "
            "одному ключу подходят несколько анимаций. Например, ключ «оперся "
            "руками» с вариантами anim_counterleanbar и anim_leanrail: в игре "
            "откроется оверлей выбора с названием и описанием каждого. Один "
            "вариант — обычное правило, оно играет сразу."))
        self._fill_anims()
        self._update_anims_ui()
        return page

    # ------------------------------------------------ состояние и проверка
    def _anim_combo_hint(self, combo):
        """Подсказка поля «Режим»: полное объяснение выбранного режима."""
        mode = combo.currentData()
        if mode is None:
            return
        combo.setToolTip(i18n.t(anims.describe_mode_hint(int(mode), False)))

    def _anim_forms_hint(self, combo):
        """Подсказка поля «Формы»: что именно сравнивается со словом."""
        forms = combo.currentData()
        if forms is None:
            return
        combo.setToolTip(i18n.t(morph.describe_forms_hint(int(forms), False)))

    def _anim_say(self, text, seconds=8.0):
        """Заметка под кнопками проверки: живёт несколько секунд."""
        self._anim_note = (text, time.monotonic() + seconds)
        self.lb_anim_live.setText(text)

    def _anim_live_tick(self):
        """Раз в секунду: что играет и что не отправилось / live module state."""
        api = getattr(self, "anims_api", None)
        if api is None or getattr(self, "_anim_view", None) is None:
            return
        if self.stack.currentWidget() is not self._anim_view:
            return
        note, until = getattr(self, "_anim_note", ("", 0.0))
        if time.monotonic() < until:
            self.lb_anim_live.setText(note)
            return
        try:
            state = api["state"]()
        except Exception:
            log.exception("Не удалось прочитать состояние анимаций")
            return
        parts = []
        if state.get("current"):
            playing = i18n.tf("Сейчас играет: %s", state["current"])
            if state.get("loop"):
                playing += i18n.t(", зациклено")
            parts.append(playing)
        else:
            parts.append(i18n.t("Сейчас ничего не играет"))
        if state.get("queued"):
            parts.append(i18n.tf("в очереди: %d", int(state["queued"])))
        if state.get("error"):
            parts.append(i18n.tf("последняя ошибка: %s", state["error"]))
        if not state.get("enabled"):
            parts.append(i18n.t("модуль выключен"))
        self.lb_anim_live.setText(" · ".join(parts))

    def _anim_send_now(self):
        """Отправить /anim выбранного правила в игру — проверить весь путь."""
        api = getattr(self, "anims_api", None)
        if api is None:
            self._anim_say(i18n.t(
                "Проверка в игре работает, когда настройки открыты из программы."))
            return
        rows = self.tbl_anims.selectionModel().selectedRows()
        name = ""
        variants = []
        if rows:
            rules = self._collect_anims()
            row = rows[0].row()
            if 0 <= row < len(rules):
                rule = rules[row]
                # у правила с вариантами имени нет: проверяем первый, чтобы
                # кнопка работала и для выбора из двух
                # a rule with variants has no single name: the first one is sent,
                # so the button works for a choice of two as well
                variants = [choice.name for choice in rule.variant_list()]
                name = rule.name.strip() or (variants[0] if variants else "")
        if not name:
            self._anim_say(i18n.t(
                "Сначала выберите правило с названием анимации."))
            return
        problem = anims.Rule(keywords="слово", name=name).problem()
        if problem:
            self._anim_say(i18n.t("Название не подойдёт: ") + i18n.t(problem))
            return
        if len(variants) > 1:
            # честно: проверяется только один из вариантов
            # honest: only one of the variants is being checked
            self._anim_say(i18n.tf("У правила %d варианта(ов) — отправляю "
                                   "первый: /anim %s", len(variants), name),
                           seconds=25.0)
        else:
            self._anim_say(i18n.tf("Отправляю /anim %s в игру…", name), seconds=25.0)
        threading.Thread(
            target=lambda: self.anim_test_done.emit(*api["send"](name)),
            name="anim-test", daemon=True).start()

    def _anim_send_result(self, ok, message):
        """Ответ игры на ручную отправку /anim."""
        if ok:
            self._anim_say(i18n.t("Игра приняла /anim — анимация должна играть."))
            self.lb_anim_live.setStyleSheet("color:#66d18b;")
        else:
            self._anim_say(i18n.tf("Не получилось: %s", message))
            self.lb_anim_live.setStyleSheet("color:#ff6b6b;")

    def _anim_halt_now(self):
        """Остановить текущую зацикленную анимацию из настроек."""
        api = getattr(self, "anims_api", None)
        if api is None:
            self._anim_say(i18n.t(
                "Остановка доступна, когда настройки открыты из программы."))
            return
        api["stop"]()
        self._anim_say(i18n.t("Остановил: отправлен /sa."))
        self.lb_anim_live.setStyleSheet("color:#8a8a96;")

    # заполнение и сбор таблицы анимаций
    def _fill_anims(self, rules=None):
        """Переносит правила в таблицу / rules into the table.

        ``rules`` — готовый список (после перетаскивания); без него правила
        берутся из настроек.
        ``rules`` is a ready list (after a drag); without it the rules come from
        the settings.
        """
        if not hasattr(self, "tbl_anims"):
            return
        if rules is None:
            rules = anims.rules_from_cfg(self.cfg)
        self.tbl_anims.blockSignals(True)
        self.tbl_anims.setRowCount(0)
        for rule in rules:
            self._add_anim_row(rule)
        self.tbl_anims.blockSignals(False)
        self._update_anims_ui()

    def _move_anims_row(self, source, target):
        """Перетащили строку правил: собираем правила, меняем порядок, рисуем.

        A rule row was dragged: collect the rules, reorder them, draw again.
        Строку двигает не таблица, а пересборка: вместе с правилом переезжают
        выпадающие списки режима и форм, галочки и поле длительности.
        The table does not move the row, the rebuild does: the mode and forms
        combos, the checkboxes and the duration field move with the rule.
        """
        rules = self._collect_anims()
        if source < 0 or source >= len(rules):
            return
        rule = rules.pop(source)
        if target > source:
            target -= 1
        rules.insert(max(0, min(target, len(rules))), rule)
        self._fill_anims(rules)
        if hasattr(self, "tbl_anims"):
            self.tbl_anims.selectRow(max(0, min(target, len(rules) - 1)))
        self._anims_changed()
        log.info("Анимации: правило «%s» переставлено (%d -> %d)",
                 rule.keywords[:30], source, target)

    def _anims_menu(self, pos):
        """ПКМ по таблице правил: свойства анимации и быстрые действия.

        Right-click on the rules table: the animation properties and quick
        actions. Пункт «Свойства анимации…» — единственный вход в варианты,
        названия и описания.
        The Animation properties item is the one way into the variants, titles
        and descriptions.
        """
        index = self.tbl_anims.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        self.tbl_anims.selectRow(row)
        menu = QMenu(self.tbl_anims)
        act_props = menu.addAction(i18n.t("Свойства анимации…"))
        act_variant = None
        rules = self._collect_anims()
        current = rules[row] if 0 <= row < len(rules) else None
        if current is not None:
            act_variant = menu.addAction(i18n.t("Добавить ещё один вариант…"))
        menu.addSeparator()
        act_dup = menu.addAction(i18n.t("Дублировать правило"))
        act_del = menu.addAction(i18n.t("Удалить правило"))
        chosen = menu.exec(self.tbl_anims.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is act_props:
            self._anim_props(row, force_variants=False)
        elif act_variant is not None and chosen is act_variant:
            self._anim_props(row, force_variants=True)
        elif chosen is act_dup:
            self._duplicate_anim(row)
        elif chosen is act_del:
            self._del_anim()

    def _anim_props(self, row, force_variants=False):
        """Окно свойств анимации для строки таблицы.

        The animation properties dialog for a table row.

        ``force_variants`` — «Добавить ещё один вариант»: у обычного правила имя
        превращается в первый вариант, и сразу открывается второй — так из
        одного ``/anim`` получается выбор из двух.
        ``force_variants`` is "Add one more variant": a plain rule's name becomes
        its first variant and a second row is added at once, turning a single
        ``/anim`` into a choice of two.
        """
        rules = self._collect_anims()
        if not 0 <= row < len(rules):
            return
        rule = rules[row]
        if force_variants and not rule.choices:
            # имя из столбца «/anim» становится первым вариантом
            # the name from the /anim column becomes the first variant
            rule.choices = [anims.Choice(name=rule.name.strip())]
        if not rule.choices and not rule.name.strip():
            self._anim_say(i18n.t("Сначала задайте название анимации в таблице."))
            return
        if not ask_anim_props(rule, self):
            return
        # правило заменяется целиком: имя, варианты, всё остальное как было
        # the rule is replaced as a whole: the name, the variants, the rest as is
        rules[row] = rule
        self._fill_anims(rules)
        self.tbl_anims.selectRow(row)
        self._anims_changed()
        log.info("Анимации: свойства правила «%s» сохранены (вариантов: %d)",
                 rule.keywords[:30], len(rule.variant_list()))

    def _duplicate_anim(self, row):
        """Скопировать правило в новую строку под ним / copy a rule below itself."""
        rules = self._collect_anims()
        if not 0 <= row < len(rules):
            return
        copy = anims.Rule.from_dict(rules[row].to_dict())
        copy.id = anims.Rule().id          # новый id, чтобы строки не путались
        rules.insert(row + 1, copy)
        self._fill_anims(rules)
        self.tbl_anims.selectRow(row + 1)
        self._anims_changed()

    def _add_anim_row(self, rule):
        """Одна строка таблицы по правилу / one table row for a rule."""
        row = self.tbl_anims.rowCount()
        self.tbl_anims.insertRow(row)

        def checkable(checked):
            item = QTableWidgetItem("")
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                          | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if checked
                               else Qt.CheckState.Unchecked)
            return item

        item_on = checkable(rule.enabled)
        # id едет в первой ячейке вместе с галочкой — по нему правило находится
        # после пересборки таблицы
        # the id travels in the first cell next to the checkbox, so the rule can
        # be found again after the table is rebuilt
        item_on.setData(Qt.ItemDataRole.UserRole, rule.id)
        item_loop = checkable(rule.loop)
        cells = [item_on,
                 QTableWidgetItem(rule.keywords),
                 QTableWidgetItem(self._anim_name_cell(rule)),
                 None,                       # режим — выпадающий список,
                 None,                       # формы — тоже список,
                 QTableWidgetItem(str(rule.duration_ms)),
                 item_loop]
        for column, item in enumerate(cells):
            if item is None:
                continue
            item.setToolTip(item.text())
            self.tbl_anims.setItem(row, column, item)
        # варианты хранятся в ячейке имени: таблица — единственный источник правил,
        # пока окно открыто, и пересборка не должна их терять
        # the variants live in the name cell: the table is the only source of
        # rules while the window is open, and a rebuild must not lose them
        name_item = self.tbl_anims.item(row, 2)
        if name_item is not None:
            name_item.setToolTip(self._anim_name_hint(rule))
            if rule.choices:
                name_item.setData(Qt.ItemDataRole.UserRole + 1,
                                  [choice.to_dict() for choice in rule.choices])
        combo = QComboBox()
        # названия режимов хранятся по-русски: так i18n.retranslate может
        # переводить их в любую сторону сколько угодно раз
        # mode titles are stored in Russian, so i18n.retranslate can translate
        # them either way as many times as needed
        titles = [anims.describe_mode(mode, False) for mode in anims.MODES]
        for mode, title in zip(anims.MODES, titles):
            combo.addItem(i18n.t(title), mode)
        combo.setProperty("_ru_items", titles)
        # поле не должно требовать ширины под самую длинную строку: текст
        # обрезается, а полное объяснение висит подсказкой
        # the field must not demand the width of its longest item: the text is
        # elided and the full explanation sits in the tooltip
        combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(6)
        combo.setMinimumWidth(110)
        combo.setCurrentIndex(max(0, int(combo.findData(int(rule.mode)))))
        combo.currentIndexChanged.connect(self._anims_combo_changed)
        self._anim_combo_hint(combo)
        self.tbl_anims.setCellWidget(row, 3, combo)

        forms_combo = QComboBox()
        forms_titles = [morph.describe_forms(forms, False) for forms in morph.FORMS]
        for forms, title in zip(morph.FORMS, forms_titles):
            forms_combo.addItem(i18n.t(title), forms)
        forms_combo.setProperty("_ru_items", forms_titles)
        forms_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        forms_combo.setMinimumContentsLength(6)
        forms_combo.setMinimumWidth(88)
        forms_combo.setCurrentIndex(
            max(0, int(forms_combo.findData(int(rule.forms)))))
        forms_combo.currentIndexChanged.connect(self._anims_combo_changed)
        self._anim_forms_hint(forms_combo)
        self.tbl_anims.setCellWidget(row, 4, forms_combo)
        return row

    def _anim_name_cell(self, rule) -> str:
        """Что написать в столбце «/anim», когда вариантов несколько.

        What the /anim column shows when there are several variants.
        Один вариант или обычное правило — просто имя. Несколько — имя первого
        и «+N», а полный список с названиями виден в подсказке ячейки: строка
        таблицы остаётся узкой, но ничего не теряется.
        One variant or a plain rule is just the name. Several show the first name
        and «+N», with the full titled list in the cell tooltip: the row stays
        narrow and nothing is lost.
        """
        if not rule.choices:
            return rule.name
        if len(rule.choices) == 1:
            return rule.choices[0].name
        return f"{rule.choices[0].name}  +{len(rule.choices) - 1}"

    def _anim_name_hint(self, rule) -> str:
        """Подсказка столбца «/anim»: все варианты с названиями.

        The /anim column tooltip: every variant with its title.
        """
        if not rule.choices:
            return rule.name
        lines = []
        for choice in rule.choices:
            line = choice.name
            if choice.title:
                line += " — " + choice.title
            if choice.description:
                line += ": " + choice.description
            lines.append(line)
        return "\n".join(lines)

    def _anims_combo_changed(self, *_):
        """Сменили режим чтения в строке / the read mode of a row changed."""
        self._anims_changed()

    def _anims_edited(self, item=None):
        """Правка ячейки: проверяем длительность и обновляем подсказки."""
        if item is not None and item.column() == 5:
            text = (item.text() or "").strip()
            if text and not text.lstrip("-").isdigit():
                # в поле длительности ждём число; буквы не чиним молча, а
                # подсвечиваем строку и говорим об этом подсказкой
                # the duration field wants a number; letters are not fixed
                # silently, the row is highlighted and the hint explains why
                self._anims_changed()
                return
        self._anims_changed()

    def _anims_changed(self):
        self._update_anims_ui()

    def _collect_anims(self):
        """Собирает правила из таблицы (в памяти) / rules from the table."""
        if not hasattr(self, "tbl_anims"):
            return []
        rules = []
        for row in range(self.tbl_anims.rowCount()):
            item_on = self.tbl_anims.item(row, 0)
            if item_on is None:
                continue

            def text(column):
                item = self.tbl_anims.item(row, column)
                return item.text().strip() if item is not None else ""

            combo = self.tbl_anims.cellWidget(row, 3)
            mode = anims.MODE_ALWAYS
            if isinstance(combo, QComboBox) and combo.currentData() is not None:
                mode = int(combo.currentData())
            forms_combo = self.tbl_anims.cellWidget(row, 4)
            forms = morph.FORMS_DEFAULT
            if (isinstance(forms_combo, QComboBox)
                    and forms_combo.currentData() is not None):
                forms = int(forms_combo.currentData())
            raw_ms = text(5).replace(" ", "")
            try:
                duration = int(raw_ms)
            except ValueError:
                duration = -1        # problem() скажет «длительность должна быть…»
            item_loop = self.tbl_anims.item(row, 6)
            # варианты из ячейки имени: обычное правило их не имеет, и тогда
            # остаётся только name, как раньше
            # the variants come from the name cell; a plain rule has none, and
            # then only name remains, exactly as before
            name_item = self.tbl_anims.item(row, 2)
            raw_choices = (name_item.data(Qt.ItemDataRole.UserRole + 1)
                           if name_item is not None else None)
            choices = []
            if isinstance(raw_choices, list):
                for entry in raw_choices:
                    choice = anims.Choice.from_dict(entry)
                    if choice is not None:
                        choices.append(choice)
            rule = anims.Rule(
                keywords=text(1),
                name=text(2) if not choices else "",
                mode=mode,
                forms=forms,
                duration_ms=duration,
                loop=bool(item_loop and item_loop.checkState() == Qt.CheckState.Checked),
                enabled=bool(item_on.checkState() == Qt.CheckState.Checked),
                choices=choices,
            )
            ident = str(item_on.data(Qt.ItemDataRole.UserRole) or "").strip()
            if ident:
                rule.id = ident
            rules.append(rule)
        self._anim_rules = rules
        return rules

    def _anims_problems(self):
        """Список «строка — что не так» для всех правил / problems per row."""
        out = []
        for index, rule in enumerate(self._collect_anims()):
            problem = rule.problem()
            if problem:
                out.append((index, problem))
        return out

    def _update_anims_ui(self):
        """Счётчик, подсказки и доступность кнопок / counters and button state."""
        if not hasattr(self, "tbl_anims"):
            return
        total = self.tbl_anims.rowCount()
        rules = getattr(self, "_anim_rules", []) or []
        active = sum(1 for rule in rules if rule.ready())
        loops = sum(1 for rule in rules if rule.ready() and rule.loop)
        self.lb_anims_count.setText(i18n.tf(
            "Правил: %d, готовы к работе: %d, с зацикливанием: %d", total, active, loops))
        for row in range(total):
            combo = self.tbl_anims.cellWidget(row, 3)
            if isinstance(combo, QComboBox):
                self._anim_combo_hint(combo)
            forms_combo = self.tbl_anims.cellWidget(row, 4)
            if isinstance(forms_combo, QComboBox):
                self._anim_forms_hint(forms_combo)
        problems = self._anims_problems()
        notes = []
        if problems:
            lines = [i18n.tf("Строка %d: ", index + 1) + i18n.t(problem)
                     for index, problem in problems]
            notes.append(i18n.t("Проверьте правила: ") + "; ".join(lines))
        if not morph.lemmas_available() and any(
                rule.forms == morph.FORMS_LEMMA for rule in rules):
            # честно: без пакета pymorphy3 уровень «Леммы» работает как «Основы»
            # honest: without pymorphy3 the "Lemmas" level behaves like "Stems"
            notes.append(i18n.t("Пакет pymorphy3 не найден: уровень «Леммы» "
                                "сравнивает по основе."))
        self.lb_anims_problem.setText(" ".join(notes))
        enabled = bool(self.chk_anims.isChecked()) if hasattr(self, "chk_anims") else True
        self.tbl_anims.setEnabled(True)
        self.bt_anim_add.setEnabled(True)
        rows = self.tbl_anims.selectionModel().selectedRows() if total else []
        has_row = bool(rows)
        self.bt_anim_del.setEnabled(has_row)
        current = rows[0].row() if has_row else -1
        self.bt_anim_up.setEnabled(has_row and current > 0)
        self.bt_anim_down.setEnabled(has_row and 0 <= current < total - 1)
        if not enabled:
            self.lb_anims_count.setText(
                self.lb_anims_count.text() + i18n.t(" · модуль выключен"))

    def _anims_toggled(self, *_):
        """Галочка модуля: сразу видно, будет ли что-то работать."""
        self._update_anims_ui()

    def _anim_stop_changed(self, *_):
        """Проверка клавиши остановки и сводка способов остановки.

        Check the stop key and summarise how the animation is stopped.
        """
        problem = anims.stop_key_problem(self.ed_anim_stop.text())
        pretty = _pretty_hotkey(self.ed_anim_stop.text() or "f")
        if hasattr(self, "chk_anim_stop_key"):
            self.chk_anim_stop_key.setText(i18n.tf(
                "Останавливать анимацию нажатием клавиши %s (симуляция)", pretty))
        by_sa = bool(self.chk_anim_stop_sa.isChecked()) if hasattr(
            self, "chk_anim_stop_sa") else True
        by_key = bool(self.chk_anim_stop_key.isChecked()) if hasattr(
            self, "chk_anim_stop_key") else False
        if problem:
            self.lb_anim_stop.setText(i18n.t(problem))
            self.lb_anim_stop.setStyleSheet("color:#ff6b6b;")
            return False
        if by_sa and by_key:
            note = i18n.tf("Анимация останавливается командой /sa и нажатием «%s».",
                           pretty)
        elif by_sa:
            note = i18n.t("Анимация останавливается командой /sa.")
        elif by_key:
            note = i18n.tf("Анимация останавливается нажатием «%s» (симуляция).",
                           pretty)
        else:
            note = i18n.t("Остановка выключена: анимация играет, пока её не сменит "
                          "другая или пока её не остановит игра.")
        self.lb_anim_stop.setText(
            note + " " + i18n.t("Клавишу остановки получает и игра, поэтому "
                                "подойдёт обычная игровая клавиша."))
        self.lb_anim_stop.setStyleSheet("color:#8a8a96;")
        return True

    def _add_anim(self):
        """Новое правило с разумными значениями по умолчанию."""
        rule = anims.Rule(keywords="", name="", mode=anims.MODE_ALWAYS,
                          duration_ms=anims.DEFAULT_MS)
        self.tbl_anims.blockSignals(True)
        row = self._add_anim_row(rule)
        self.tbl_anims.blockSignals(False)
        self.tbl_anims.selectRow(row)
        item = self.tbl_anims.item(row, 1)
        if item is not None:
            self.tbl_anims.setCurrentCell(row, 1)
            self.tbl_anims.editItem(item)
        self._anims_changed()

    def _del_anim(self):
        """Удаляет выбранные правила / remove the selected rules."""
        rows = sorted({index.row() for index in
                       self.tbl_anims.selectionModel().selectedRows()}, reverse=True)
        if not rows:
            return
        for row in rows:
            self.tbl_anims.removeRow(row)
        self._anims_changed()

    def _move_anim(self, delta):
        """Правило выше или ниже: порядок = порядок срабатывания."""
        rows = self.tbl_anims.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        target = row + delta
        if not 0 <= target < self.tbl_anims.rowCount():
            return
        rules = self._collect_anims()
        rules[row], rules[target] = rules[target], rules[row]
        self.tbl_anims.blockSignals(True)
        self.tbl_anims.setRowCount(0)
        for rule in rules:
            self._add_anim_row(rule)
        self.tbl_anims.blockSignals(False)
        self.tbl_anims.selectRow(target)
        self._anims_changed()

    def _anim_context(self):
        """Контекст проверки: словарь и порядок слов — те же, что в работе.

        The check context: the same glossary and negation flag the running module
        uses, so the check shows exactly what the game will really do.
        """
        code = langs.code_of(self.cb_lang.currentData()
                             if hasattr(self, "cb_lang") and self.cb_lang.currentData()
                             else self.cfg.get("target_lang", "it"))
        cached = getattr(self, "_anim_glossary", (None, None))
        if cached[0] != code:
            try:
                cached = (code, Glossary(self._doc(code), code))
            except Exception:
                log.exception("Не удалось прочитать словарь для проверки анимаций")
                cached = (code, None)
            self._anim_glossary = cached
        glossary = cached[1]
        negation = (bool(self.chk_anim_negation.isChecked())
                    if hasattr(self, "chk_anim_negation") else True)
        if glossary is None:
            return anims.Context(negation=negation)
        return anims.Context(equivalent=lambda phrase: glossary.find_meaning(phrase) or "",
                             text_keys=glossary.phrase_keys,
                             negation=negation)

    def _anim_blockers(self):
        """Почему правила не дойдут до игры / why the rules never reach the game.

        Проверка слов работает и при выключенных модулях, поэтому список
        выключенного показывается рядом с результатом.
        The word check works even with the modules off, so the disabled ones are
        listed right next to the result.
        """
        why = []
        if hasattr(self, "chk_anims") and not self.chk_anims.isChecked():
            why.append(i18n.t("выключен модуль «Анимации»"))
        if not bool(self.cfg.get("game_send", True)):
            why.append(i18n.t("выключен модуль «Отправка в игру»"))
        return why

    def _anim_extra(self, cfg=None):
        """Пауза после анимации из настроек, мс / the tail from the settings.

        Новое поле — ``anim_extra_ms``, старое ``anim_gap_ms`` читается как оно
        же, чтобы значение из прошлой версии не потерялось.
        The new key is ``anim_extra_ms``; the old ``anim_gap_ms`` is read as the
        same, so a value from a previous version is not lost.
        """
        source = self.cfg if cfg is None else cfg
        raw = source.get("anim_extra_ms")
        if raw is None:
            raw = source.get("anim_gap_ms", 50)
        try:
            return max(0, min(10000, int(raw)))
        except (TypeError, ValueError):
            return 50

    def _anims_test(self):
        """Проверка фразы: какие правила на неё сработают / a dry run of a phrase."""
        text = self.ed_anims_test.text()
        if not text.strip():
            self.lb_anims_test.setText(i18n.t("Напишите фразу для проверки."))
            self.lb_anims_test.setStyleSheet("color:#8a8a96;")
            return
        # тот же порядок, что и в работе: по месту слова в сообщении, каждое
        # ключевое слово правила — своим выходом, слова-синонимы — по ключу
        # the same order as in real use: by the place of the word in the message,
        # every keyword of a rule fires on its own, synonyms by their key
        ctx = self._anim_context()
        # тот же разбор, что и в работе: вложенные ключи («сел» внутри «сел
        # откинувшись») показывает именно так, как они сыграют
        # the same resolution as at run time: nested keywords («сел» inside «сел
        # откинувшись») are shown exactly the way they will play
        rules = [rule for rule in self._collect_anims() if rule.ready()]
        hits = [(position, self._anim_hit_label(rule), form)
                for position, _index, rule, form in anims.plan(rules, text, ctx)]
        if hits:
            # видно не только правило, но и какая именно форма его задела
            # shows the rule and the exact form that fired it
            parts = ["/anim " + name + (f" ← «{form}»" if form else "")
                     for _, name, form in hits]
            text_out = i18n.t("Сработают: ") + ", ".join(parts)
            # правило может сработать и при этом не дойти до игры: проверка
            # слов не равна работе модуля, о выключенных модулях говорим прямо
            # a rule may fire and still never reach the game: this check is about
            # the words, so the disabled modules are called out
            why = self._anim_blockers()
            if why:
                text_out += " " + i18n.t("Но в игру ничего не уйдёт: ") + ", ".join(why) + "."
            self.lb_anims_test.setText(text_out)
            self.lb_anims_test.setStyleSheet(
                "color:#ffb45b;" if why else "color:#66d18b;")
        else:
            self.lb_anims_test.setText(i18n.t(
                "Ни одно правило не сработает: в этом режиме ключевого слова в "
                "сообщении нет."))
            self.lb_anims_test.setStyleSheet("color:#ffb45b;")

    def _anim_hit_label(self, rule) -> str:
        """Что написать в проверке фразы: правило или его варианты.

        What the phrase check prints: the rule or its variants.
        У правила с вариантами имени команды нет — вместо него видно, сколько
        их и что откроется: «выбор из 2: anim_counterleanbar, anim_leanrail».
        A rule with variants has no single command name, so the check shows how
        many there are and what the chooser will offer.
        """
        if not rule.choices:
            return rule.name.strip() or i18n.t("без названия")
        names = [choice.name for choice in rule.choices]
        if len(names) == 1:
            return names[0]
        return (i18n.tf("выбор из %d: ", len(names)) + ", ".join(names))

    def _export_anims(self):
        """Правила в JSON — их можно перенести на другой компьютер."""
        path, _ = QFileDialog.getSaveFileName(
            self, i18n.t("Экспорт правил анимаций"), str(DATA / "animations.json"),
            i18n.t("Правила анимаций (*.json);;Все файлы (*)"))
        if not path:
            return
        payload = {"format": "rpchatoverlay-animations", "version": 1,
                   "rules": anims.rules_to_cfg(self._collect_anims()),
                   "stop_key": self.ed_anim_stop.text().strip().lower()}
        try:
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, i18n.t("Экспорт"),
                                i18n.t("Не удалось записать файл:\n") + str(e))
            return
        QMessageBox.information(self, i18n.t("Экспорт"),
                                i18n.t("Правила сохранены в файл ") + str(path))

    def _import_anims(self):
        """Правила из JSON, созданного кнопкой «Экспорт…»."""
        path, _ = QFileDialog.getOpenFileName(
            self, i18n.t("Импорт правил анимаций"), str(DATA),
            i18n.t("Правила анимаций (*.json);;Все файлы (*)"))
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
            data = json.loads(text)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, i18n.t("Импорт"),
                                i18n.t("Файл не подошёл:\n") + str(e))
            return
        raw = data.get("rules") if isinstance(data, dict) and "rules" in data else data
        if not isinstance(raw, list):
            QMessageBox.warning(self, i18n.t("Импорт"), i18n.t(
                "В файле нужен список правил: {\"rules\": [ … ]}."))
            return
        imported = 0
        self.tbl_anims.blockSignals(True)
        for item in raw:
            if not isinstance(item, dict):
                continue
            rule = anims.Rule.from_dict(item)
            self._add_anim_row(rule)
            imported += 1
        self.tbl_anims.blockSignals(False)
        if isinstance(data, dict) and str(data.get("stop_key") or "").strip():
            stop_key = str(data["stop_key"]).strip().lower()
            if not anims.stop_key_problem(stop_key):
                self.ed_anim_stop.setText(stop_key)
                self._anim_stop_changed()
        if not imported:
            QMessageBox.information(self, i18n.t("Импорт"),
                                    i18n.t("В файле не нашлось правил."))
        self._anims_changed()
    # ------------------------------------------------------------ Модули
    def _page_modules(self):
        """Страница «Модули»: что можно выключить и что от чего зависит.

        The Modules page: which parts can be switched off and what depends on
        what. Modules that already have their own switch elsewhere are shown
        read-only, with the section where they live.
        """
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(14)

        card, cl = _card()
        cl.addWidget(_title("Модули", "sec"))
        cl.addWidget(_hint("Каждую часть программы можно выключить. Данные при этом "
                           "не теряются: словари, сокращения и настройки остаются "
                           "на месте, а программу можно вернуть к полному набору "
                           "в любой момент."))

        self.chk_modules = {}
        # подписи модулей собираются из реестра, а не из таблицы переводов:
        # при смене языка их нужно обновить вручную
        # module titles come from the registry, not from the translation table, so
        # they are refreshed by hand when the language changes
        self._module_rows = []
        self._module_deps = []
        for module in modules.MODULES:
            row = QWidget()
            rl = QVBoxLayout(row)
            rl.setContentsMargins(0, 6, 0, 6)
            rl.setSpacing(2)
            title = module.title_en if i18n.is_en() else module.title_ru
            box = QCheckBox(title)
            if module.settings_page is None:
                box.setChecked(bool(self.cfg.get(module.config_key, module.default)))
                self.chk_modules[module.config_key] = box
            else:
                # включается на своей странице — здесь только показываем
                # switched on its own page, shown here for reference only
                box.setChecked(bool(self.cfg.get(module.config_key, module.default)))
                box.setEnabled(False)
                box.setToolTip(i18n.t("Включается на странице «%s»")
                               % self.nav.item(module.settings_page).text()
                               if hasattr(self, "nav") and self.nav.count()
                               else i18n.t("Включается на своей странице"))
            rl.addWidget(box)
            desc = QLabel(module.desc_en if i18n.is_en() else module.desc_ru)
            desc.setWordWrap(True)
            desc.setProperty("no_i18n", True)
            desc.setStyleSheet("color:#9aa0b4;font-size:12px;")
            rl.addWidget(desc)
            self._module_rows.append((box, desc, module))
            if module.requires:
                names = ", ".join(
                    (modules.get(dep).title_en if i18n.is_en() else modules.get(dep).title_ru)
                    for dep in module.requires if modules.get(dep)
                )
                dep_label = QLabel(i18n.t("Зависит от модуля: ") + names)
                dep_label.setProperty("no_i18n", True)
                self._module_deps.append((dep_label, module))
                dep_label.setWordWrap(True)
                dep_label.setStyleSheet("color:#8a8fa3;font-size:11px;")
                rl.addWidget(dep_label)
            cl.addWidget(row)
            line = _sep()
            cl.addWidget(line)
        lay.addWidget(card)
        lay.addStretch(1)
        return page

    def _page_test(self):
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)
        lay.addWidget(_title("Проверка перевода", "sec"))
        self.lb_test_hint = _hint("")          # текст зависит от направления (см. ниже)
        self.lb_test_hint.setProperty("no_i18n", True)
        lay.addWidget(self.lb_test_hint)
        row_dir = QHBoxLayout()
        row_dir.addWidget(QLabel("Направление:"))
        self.cb_test_dir = QComboBox()
        self.cb_test_dir.addItem("Русский → выбранный язык перевода", "out")
        self.cb_test_dir.addItem("Ваш язык → русский", "in")
        self.cb_test_dir.setMinimumWidth(200)
        self.cb_test_dir.setToolTip(
            "Проверить можно оба направления. «Ваш язык → русский» показывает, что "
            "уйдёт в чат игры в режиме для иностранного игрока: сокращения "
            "раскрываются, служебные команды остаются как есть.")
        self.cb_test_dir.currentIndexChanged.connect(self._test_dir_changed)
        row_dir.addWidget(self.cb_test_dir)
        row_dir.addStretch(1)
        lay.addLayout(row_dir)

        self.ed_test = QLineEdit()
        self.ed_test.setClearButtonEnabled(True)
        self.ed_test.textChanged.connect(lambda: self._preview_timer.start(400))
        lay.addWidget(self.ed_test)

        card, cl = _card()
        self.lb_test_out = QLabel("—")
        self.lb_test_out.setProperty("no_i18n", True)
        self.lb_test_out.setWordWrap(True)
        self.lb_test_out.setStyleSheet("font-size:15px;")
        self.lb_test_read = QLabel("")
        self.lb_test_read.setProperty("no_i18n", True)
        self.lb_test_read.setWordWrap(True)
        self.lb_test_read.setObjectName("sub")
        self.lb_test_dir = QLabel("")
        self.lb_test_dir.setProperty("no_i18n", True)
        self.lb_test_dir.setObjectName("hint")
        self.lb_test_dir.setWordWrap(True)
        self.lb_test_mode = QLabel("")
        self.lb_test_mode.setProperty("no_i18n", True)
        self.lb_test_mode.setObjectName("hint")
        for w in (self.lb_test_out, self.lb_test_read, self.lb_test_dir, self.lb_test_mode):
            cl.addWidget(w)
        lay.addWidget(card)

        row = QHBoxLayout()
        b_filler = QPushButton("Слова-паразиты текущего языка")
        b_filler.clicked.connect(self._show_fillers)
        b_sample = QPushButton("Вставить пример")
        b_sample.clicked.connect(self._insert_sample)
        row.addWidget(b_sample)
        row.addWidget(b_filler)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        return page

    def _show_fillers(self):
        data = self._doc(self.glang)
        rows = []
        for f in data.get("_fillers") or []:
            rows.append(f"• {f.get('target')} ← " + ", ".join(f.get("ru") or []))
        QMessageBox.information(self, i18n.tf("Слова-паразиты — %s",
                                              langs.label(self.glang)),
                                "\n".join(rows) or i18n.t("Для этого языка список не задан."))

    # --- направление проверки ---
    def _test_reverse(self):
        return str(self.cb_test_dir.currentData() or "out") == "in"

    def _test_dir_changed(self, *_args, silent=False):
        """Подсказки и пример под выбранное направление."""
        if self._test_reverse():
            if hasattr(self, "lb_test_hint"):
                self.lb_test_hint.setText(i18n.t(
                    "Введите фразу на языке сервера — увидите, что именно уйдёт в чат "
                    "игры на русском. Работает по текущим настройкам окна (до сохранения)."))
            self.ed_test.setPlaceholderText(i18n.t("например: brb, I'm afk, ty"))
            self.lb_test_dir.setText(i18n.t(
                "Проверяем режим для иностранного игрока: в чат уйдёт перевод на русский."))
        else:
            if hasattr(self, "lb_test_hint"):
                self.lb_test_hint.setText(i18n.t(
                    "Введите фразу по-русски — увидите, что именно уйдёт в игру и как это "
                    "читать вслух. Работает по текущим настройкам окна (до сохранения)."))
            self.ed_test.setPlaceholderText(
                i18n.t("например: Слушай, брат, мне срочно нужна помощь"))
            self.lb_test_dir.setText(i18n.t(
                "Проверяем обычный режим: в чат уйдёт текст на выбранном языке перевода."))
        if not silent:
            self._do_preview()

    def _insert_sample(self):
        if self._test_reverse():
            self.ed_test.setText("brb, I'm afk, ty, gg")
        else:
            self.ed_test.setText("Слушай, ну что ты, я же говорил, что приду позже")

    def _preview_cfg(self):
        """Конфиг из текущих полей (без сохранения)."""
        cfg = dict(self.cfg)
        self._write_widgets(cfg)
        return cfg

    def _do_preview(self):
        text = self.ed_test.text().strip() if hasattr(self, "ed_test") else ""
        if not text:
            self.lb_test_out.setText("—")
            self.lb_test_read.setText("")
            self.lb_test_mode.setText("")
            return
        if self._busy:
            return
        self._busy = True
        cfg = self._preview_cfg()
        code = langs.code_of(cfg.get("target_lang"))
        self._collect_slang()                 # проверка учитывает свои сокращения
        self.lb_test_mode.setStyleSheet("")
        self.lb_test_mode.setText(i18n.t("перевожу…"))
        # если сервисы отвечают долго — честно об этом пишем, а не молчим
        if not hasattr(self, "_slow_timer"):
            self._slow_timer = QTimer(self)
            self._slow_timer.setSingleShot(True)
            self._slow_timer.timeout.connect(
                lambda: self.lb_test_mode.setText(i18n.t("перевожу… (сервисы заняты)")))
        self._slow_timer.start(5000)
        threading.Thread(target=self._preview_job,
                         args=(cfg, code, text, self._test_reverse()),
                         daemon=True).start()

    def _preview_job(self, cfg, code, text, reverse=False):
        """Прогон через движок: обычное направление или «язык → русский»."""
        try:
            data = self._doc(code)
            gl = Glossary(data, code)
            tr = Translator(code)
            # ключевое: проверка должна идти в том же направлении, что выбрано
            tr.set_direction("in" if reverse else "out")
            engine = Engine(cfg, gl, tr)
            if reverse:
                res = engine.process_in(text)
                payload = {"out": res.text or "—",
                           "sub": (i18n.t("Исходное сообщение: ") + res.native)
                                  if res.native and res.native != res.text else "",
                           "note": i18n.t("Способ: переведено в чат игры") if res.translated
                                   else i18n.t("Способ: без перевода (одна команда)")}
            else:
                res = engine.process(text, auto=bool(cfg.get("auto_mode")), seed=1.0)
                native = str(cfg.get("send_mode") or "reading") in (
                    "native", "lang", "text", "target")
                sent = (res.native or res.text) if native else (res.text or res.native)
                other = res.text if native else res.native
                payload = {"out": sent or "—",
                           "sub": (i18n.t("На языке: ") + other)
                                  if other and other != sent else "",
                           "note": i18n.t("Способ: ") + (
                               i18n.t("переведено") if res.translated
                               else i18n.t("без перевода (только маркеры/команды)"))}
            ok, msg = True, ""
        except TranslateError as e:
            payload, ok, msg = None, False, i18n.tf(
                "Перевод не удался: %s. Повторите через минуту — проверка попробует "
                "другой сервис, а в чате перевод пойдёт по словарю.", str(e)[:140])
        except Exception as e:
            payload, ok, msg = None, False, str(e)[:160]
        self._preview_done(payload, ok, msg)

    def _preview_done(self, payload, ok, msg):
        self._busy = False
        if hasattr(self, "_slow_timer"):
            self._slow_timer.stop()
        if not ok:
            self.lb_test_out.setText("—")
            self.lb_test_read.setText("")
            self.lb_test_mode.setObjectName("err")
            self.lb_test_mode.setText(msg)
            self.lb_test_mode.setStyleSheet("color:#ff6b6b;")
            return
        self.lb_test_mode.setStyleSheet("")
        self.lb_test_out.setText(payload.get("out") or "—")
        self.lb_test_read.setText(payload.get("sub") or "")
        self.lb_test_mode.setText(payload.get("note") or "")

    # ------------------------------------------------------------ данные
    def _write_widgets(self, cfg):
        cfg["target_lang"] = self.cb_lang.currentData() or "it"
        cfg["send_mode"] = self.cb_send_mode.currentData() or "reading"
        cfg["direction"] = "in" if self.chk_reverse.isChecked() else "out"
        cfg["slang"] = bool(self.chk_slang.isChecked())
        if hasattr(self, "cb_ui_lang"):
            cfg["ui_lang"] = self.cb_ui_lang.currentData() or "ru"
            cfg["ui_lang_chosen"] = True
        cfg["hotkey"] = self.ed_hotkey.text().strip().lower() or "f6"
        cfg["show_settings_on_start"] = bool(self.chk_show_settings.isChecked())
        if hasattr(self, "chk_dlx"):
            cfg["dlx_enabled"] = bool(self.chk_dlx.isChecked())
            # «уже спрашивали» — только когда игрок сам включил DeepL галочкой:
            # иначе согласие с предупреждениями так и не покажется
            # "already asked" is set only when the player ticks DeepL here;
            # otherwise the warning dialog would never be shown at all
            cfg["dlx_asked"] = bool(cfg.get("dlx_asked")) or bool(cfg["dlx_enabled"])
            cfg["dlx_autostart"] = bool(self.chk_dlx_autostart.isChecked())
            cfg["dlx_auto_update"] = bool(self.chk_dlx_update.isChecked())
            cfg["dlx_port"] = int(self.sp_dlx_port.value())
            cfg["dlx_proxy"] = dlx_mod.normalize_proxy(self.ed_dlx_proxy.text())
            cfg["dlx_use_system_proxy"] = bool(self.chk_dlx_sysproxy.isChecked())
            cfg["dlx_url"] = self.ed_dlx_url.text().strip().rstrip("/")
            cfg["dlx_url_token"] = self.ed_dlx_url_token.text().strip()
            cfg["dlx_pro_token"] = self.ed_dlx_pro.text().strip()
        if hasattr(self, "sp_ui_scale"):
            cfg["ui_scale"] = round(self.sp_ui_scale.value() / 100.0, 2)
        cfg["marker_open"] = (self.ed_open.text().strip() or "+")[0]
        cfg["marker_close"] = (self.ed_close.text().strip() or "+")[0]
        cfg["max_chars"] = int(self.sp_max.value())
        cfg["debounce_ms"] = int(self.sp_debounce.value())
        cfg["auto_mode"] = bool(self.chk_auto.isChecked())
        cfg["auto_every"] = int(self.sp_every.value())
        cfg["auto_position"] = self.cb_pos.currentData() or "last"
        cfg["auto_fragments"] = int(self.sp_frag.value())
        cfg["auto_min_words"] = int(self.sp_min.value())
        cfg["auto_max_words"] = max(int(self.sp_min.value()), int(self.sp_maxw.value()))
        cfg["auto_prefer_glossary"] = bool(self.chk_prefer.isChecked())
        cfg["filler_always"] = bool(self.chk_filler.isChecked())
        cfg["game_send"] = bool(self.chk_send.isChecked())
        cfg["game_open_chat_first"] = bool(self.chk_chat_first.isChecked())
        cfg["game_submit"] = bool(self.chk_submit.isChecked())
        cfg["game_chat_key"] = (self.ed_chatkey.text().strip() or "t")[:1]
        cfg["game_focus_delay_ms"] = int(self.sp_focus.value())
        cfg["game_open_delay_ms"] = int(self.sp_opendelay.value())
        cfg["game_paste_delay_ms"] = int(self.sp_paste.value())
        for key, box in getattr(self, "chk_modules", {}).items():
            cfg[key] = bool(box.isChecked())
        if hasattr(self, "chk_anims"):
            cfg["anims_enabled"] = bool(self.chk_anims.isChecked())
            cfg["anim_rules"] = anims.rules_to_cfg(self._collect_anims())
            cfg["anim_stop_key"] = self.ed_anim_stop.text().strip().lower() or "f"
            cfg["anim_stop_by_sa"] = bool(self.chk_anim_stop_sa.isChecked())
            cfg["anim_stop_by_key"] = bool(self.chk_anim_stop_key.isChecked())
            cfg["anim_extra_ms"] = int(self.sp_anim_gap.value())
            cfg["anim_skip_negation"] = bool(self.chk_anim_negation.isChecked())
        cfg["slang_order"] = list(self._slang_order)
        return modules.apply_defaults(cfg)

    def _load_widgets(self):
        cfg = self.cfg
        idx = self.cb_lang.findData(langs.code_of(cfg.get("target_lang", "it")))
        self.cb_lang.setCurrentIndex(max(0, idx))
        self.ed_hotkey.setText(_pretty_hotkey(cfg.get("hotkey", "F6")))
        self.chk_show_settings.setChecked(bool(cfg.get("show_settings_on_start", True)))
        if hasattr(self, "sp_ui_scale"):
            self.sp_ui_scale.blockSignals(True)
            self.sp_ui_scale.setValue(int(round(self._ui_scale() * 100)))
            self.sp_ui_scale.blockSignals(False)
            self._ui_scale_changed(self.sp_ui_scale.value())
        mode = str(cfg.get("send_mode", "reading")).lower()
        self.cb_send_mode.setCurrentIndex(max(0, self.cb_send_mode.findData(
            "native" if mode in ("native", "lang", "text", "target") else "reading")))
        self.chk_reverse.setChecked(str(cfg.get("direction", "out")).lower() in ("in", "reverse"))
        self.chk_slang.setChecked(bool(cfg.get("slang", True)))
        if hasattr(self, "cb_ui_lang"):
            idx = self.cb_ui_lang.findData(i18n.normalize(cfg.get("ui_lang", "ru")))
            self.cb_ui_lang.blockSignals(True)
            self.cb_ui_lang.setCurrentIndex(max(0, idx))
            self.cb_ui_lang.blockSignals(False)
            i18n.set_lang(self.cb_ui_lang.currentData() or "ru")
        if hasattr(self, "cb_test_dir"):
            self.cb_test_dir.setCurrentIndex(1 if str(cfg.get("direction", "out")).lower()
                                             in ("in", "reverse") else 0)
            self._test_dir_changed()
        self._reverse_changed()
        self.ed_open.setText(str(cfg.get("marker_open", "+")))
        self.ed_close.setText(str(cfg.get("marker_close", "+")))
        self.sp_max.setValue(int(cfg.get("max_chars", 256)))
        self.sp_debounce.setValue(int(cfg.get("debounce_ms", 450)))
        self.chk_auto.setChecked(bool(cfg.get("auto_mode", False)))
        self.sp_every.setValue(int(cfg.get("auto_every", 4)))
        pos = str(cfg.get("auto_position", "last"))
        self.cb_pos.setCurrentIndex(max(0, self.cb_pos.findData(pos)))
        self.sp_frag.setValue(int(cfg.get("auto_fragments", 1)))
        self.sp_min.setValue(int(cfg.get("auto_min_words", 1)))
        self.sp_maxw.setValue(int(cfg.get("auto_max_words", 3)))
        self.chk_prefer.setChecked(bool(cfg.get("auto_prefer_glossary", True)))
        self.chk_filler.setChecked(bool(cfg.get("filler_always", True)))
        self.chk_send.setChecked(bool(cfg.get("game_send", True)))
        self.chk_chat_first.setChecked(bool(cfg.get("game_open_chat_first", True)))
        self.chk_submit.setChecked(bool(cfg.get("game_submit", True)))
        self.ed_chatkey.setText(str(cfg.get("game_chat_key", "t"))[:1])
        self.sp_focus.setValue(int(cfg.get("game_focus_delay_ms", 150)))
        self.sp_opendelay.setValue(int(cfg.get("game_open_delay_ms", 300)))
        self.sp_paste.setValue(int(cfg.get("game_paste_delay_ms", 150)))
        for key, box in getattr(self, "chk_modules", {}).items():
            box.blockSignals(True)
            box.setChecked(bool(cfg.get(key, True)))
            box.blockSignals(False)
        if hasattr(self, "chk_dlx"):
            self.chk_dlx.setChecked(bool(cfg.get("dlx_enabled", False)))
            self.chk_dlx_autostart.setChecked(bool(cfg.get("dlx_autostart", True)))
            self.chk_dlx_update.setChecked(bool(cfg.get("dlx_auto_update", True)))
            self.sp_dlx_port.setValue(int(cfg.get("dlx_port", 0) or 0))
            self.ed_dlx_proxy.setText(str(cfg.get("dlx_proxy") or ""))
            self.chk_dlx_sysproxy.setChecked(
                bool(cfg.get("dlx_use_system_proxy", True)))
            self._dlx_proxy_note()
            self.ed_dlx_pro.setText(str(cfg.get("dlx_pro_token") or ""))
            self.ed_dlx_url.setText(str(cfg.get("dlx_url") or ""))
            self.ed_dlx_url_token.setText(str(cfg.get("dlx_url_token") or ""))
            self._dlx_refresh()
        self.header_sub.setText(i18n.tf(
            "Язык: %s · горячая клавиша: %s · частота автоперевода: каждое %d-е",
            langs.label(langs.code_of(cfg.get("target_lang", "it"))),
            _pretty_hotkey(cfg.get("hotkey", "F6")), int(cfg.get("auto_every", 4))))
        if hasattr(self, "chk_anims"):
            self.chk_anims.blockSignals(True)
            self.chk_anims.setChecked(bool(cfg.get("anims_enabled", False)))
            self.chk_anims.blockSignals(False)
            self.ed_anim_stop.setText(str(cfg.get("anim_stop_key", "f") or "f"))
            self.chk_anim_stop_sa.blockSignals(True)
            self.chk_anim_stop_sa.setChecked(bool(cfg.get("anim_stop_by_sa", True)))
            self.chk_anim_stop_sa.blockSignals(False)
            self.chk_anim_stop_key.blockSignals(True)
            self.chk_anim_stop_key.setChecked(bool(cfg.get("anim_stop_by_key", False)))
            self.chk_anim_stop_key.blockSignals(False)
        if hasattr(self, "sp_anim_gap"):
            self.sp_anim_gap.blockSignals(True)
            self.sp_anim_gap.setValue(self._anim_extra(cfg))
            self.sp_anim_gap.blockSignals(False)
            self.chk_anim_negation.blockSignals(True)
            self.chk_anim_negation.setChecked(bool(cfg.get("anim_skip_negation", True)))
            self.chk_anim_negation.blockSignals(False)
            self._anim_stop_changed()
            self._fill_anims()
        self._hotkey_changed()

    def _reset_all(self):
        ans = QMessageBox.question(
            self, i18n.t("Сброс настроек"),
            i18n.t("Вернуть все настройки к заводским?\nСловари и горячая клавиша тоже "
                   "станут стандартными (F6, итальянский)."))
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.cfg = dict(DEFAULT_CONFIG)
        self.cfg.update({"hotkey": "F6", "target_lang": "it"})
        self._load_widgets()
        self._load_language("it", reload_table=True)
        self.footer_hint.setText(
            i18n.t("Настройки сброшены — нажмите «Сохранить», чтобы применить."))

    def _is_dirty(self):
        """Есть ли неприменённые правки / whether there are unsaved edits."""
        try:
            cur = dict(self.cfg)
            self._write_widgets(cur)
        except Exception:                                 # окно ещё не собрано целиком
            return False
        if cur != self.cfg:
            return True
        return bool(self.dirty or self.glossary_changed or self._slang_pending)

    def _flash_hint(self, text=None, bad=False):
        """Пишет в подвал, что настройки применились, и убирает через 5 секунд.

        Shows in the footer that the settings were applied, then restores the
        usual hint after five seconds.
        """
        self.footer_hint.setText(i18n.t(text or "Настройки сохранены и применены."))
        self.footer_hint.setStyleSheet("color:#ff6b6b;" if bad else "color:#66d18b;")
        if getattr(self, "_hint_timer", None) is None:
            self._hint_timer = QTimer(self)
            self._hint_timer.setSingleShot(True)
            self._hint_timer.timeout.connect(self._hint_idle)
        self._hint_timer.start(5000)

    def _hint_idle(self):
        """Возвращает подвал к обычной подсказке / restores the idle footer text."""
        self.footer_hint.setStyleSheet("")
        self.footer_hint.setText(i18n.t(_FOOTER_IDLE))

    def _cancel(self):
        """Закрывает окно, но не теряет правки молча.

        Closes the window; unsaved edits are never dropped without asking.
        """
        if self._is_dirty():
            ans = QMessageBox.question(
                self, i18n.t("Несохранённые изменения"),
                i18n.t("В настройках есть неприменённые изменения.\nЗакрыть окно без сохранения?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if ans != QMessageBox.StandardButton.Yes:
                return
        super().reject()

    def reject(self):
        """Esc и крестик окна идут тем же путём, что и кнопка «Закрыть»."""
        self._cancel()

    def keyPressEvent(self, e):
        """Enter сохраняет, Esc закрывает — без «кнопки по умолчанию».

        Enter saves and Esc closes without giving any button a permanent
        default-button look.
        """
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._save()
            return
        if e.key() == Qt.Key.Key_Escape:
            self._cancel()
            return
        super().keyPressEvent(e)

    def _save(self):
        self._sync_glossary()
        self._sync_slang()
        if hasattr(self, "chk_anims"):
            stop_ok = self._anim_stop_changed()
            problems = self._anims_problems()
            if problems:
                index, problem = problems[0]
                self.nav.setCurrentRow(self._anims_row)
                QMessageBox.warning(
                    self, i18n.t("Анимации"),
                    i18n.tf("Правило в строке %d: %s. Исправьте его или удалите — "
                            "без этого настройки не сохранятся.",
                            index + 1, i18n.t(problem)))
                return
            if not stop_ok:
                self.nav.setCurrentRow(self._anims_row)
                QMessageBox.warning(self, i18n.t("Анимации"),
                                    self.lb_anim_stop.text())
                return
        if not self._hotkey_changed():
            self.nav.setCurrentRow(0)
            self.lb_hotkey.setObjectName("err")
            self.lb_hotkey.setStyleSheet("color:#ff6b6b;")
            QMessageBox.warning(self, i18n.t("Горячая клавиша"),
                                self.lb_hotkey.text() or i18n.t("Проверьте горячую клавишу."))
            return
        cfg = dict(self.cfg)
        self._write_widgets(cfg)
        cfg["setup_done"] = True
        saved_glossaries = []
        for code in list(self.dirty):
            if save_glossary_data(code, self.docs.get(code) or {}):
                saved_glossaries.append(code)
        self.dirty.clear()
        try:
            save_config(cfg)
        except OSError as e:
            QMessageBox.critical(self, i18n.t("Сохранение"),
                                 i18n.t("Не удалось записать config.json:\n") + str(e))
            return
        log.info("Настройки сохранены: язык %s, hotkey %s, словари %s",
                 cfg.get("target_lang"), cfg.get("hotkey"), saved_glossaries)
        self.cfg = cfg
        self.glossary_changed = False
        self._slang_pending = False
        self.saved.emit(cfg)
        if self.first_run:
            # первичная настройка закончена, но окно остаётся открытым: игрок сам
            # решает, когда закончить, и программа не прячется в трей
            # the first run is over, yet the window stays open: the player decides
            # when to finish and the program never hides into the tray by itself
            self.first_run = False
            self.setWindowTitle(i18n.t("Настройки — RP Chat Overlay"))
            self.header_title.setText(i18n.t("Настройки"))
            log.info("Первичная настройка завершена, окно остаётся открытым")
        self._flash_hint()
        # на всякий случай возвращаем окно на экран: сохранение не должно его
        # прятать, даже если фокус ушёл в игру
        # bring the window back on screen just in case: saving must never hide it,
        # even when the focus went to the game
        self.show()
        self.raise_()
        self.activateWindow()


def _pretty_hotkey(spec):
    """«f6» -> «F6», «ctrl+alt+t» -> «Ctrl+Alt+T»."""
    out = []
    for p in str(spec or "F6").split("+"):
        p = p.strip()
        if not p:
            continue
        out.append(p.upper() if len(p) == 1 or p.lower().startswith("f") else p.capitalize())
    return "+".join(out) or "F6"


def _sz(w, h):
    from PySide6.QtCore import QSize
    return QSize(w, h)


class AnimProps(QDialog):
    """Свойства анимации: варианты, их названия и описания.

    Animation properties: the variants, their titles and descriptions.

    Зачем / why
    -----------
    Один ключ часто подходит к нескольким анимациям: «Опёрся руками» — это и
    ``anim_counterleanbar``, и ``anim_leanrail``. Когда вариантов два и больше,
    в игре открывается оверлей выбора, и игроку нужно показать не имя команды,
    а человеческое название с описанием.
    One keyword often fits several animations: «Опёрся руками» is both
    ``anim_counterleanbar`` and ``anim_leanrail``. With two or more variants the
    game shows a chooser, and the player must see a human title with a
    description rather than a command name.

    Здесь же задаётся и обычное правило без вариантов: одна строка — это просто
    название анимации, как в таблице. Так диалог остаётся единственным местом,
    где меняются свойства, и неважно, один вариант или несколько.
    The dialog also edits an ordinary single-animation rule: one row is just the
    animation name, as in the table. That keeps the dialog the one place where
    properties are edited, whether there is one variant or several.
    """

    def __init__(self, rule, parent=None):
        super().__init__(parent)
        self.rule = rule
        self.setWindowTitle(i18n.t("Свойства анимации"))
        self.setStyleSheet(style_sheet(1.0))
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 14)
        lay.setSpacing(10)

        head = QLabel(i18n.tf("Ключевые слова: %s",
                              rule.keywords.strip() or i18n.t("не заданы")))
        head.setStyleSheet("font-size:14px;font-weight:600;")
        head.setWordWrap(True)
        lay.addWidget(head)

        lay.addWidget(_hint(i18n.t(
            "Заполните варианты: имя для /anim, название и описание. Если "
            "вариантов два и больше, в игре откроется оверлей выбора — игрок "
            "увидит название и описание, а не имя команды. Один вариант — "
            "обычное правило, оно играет сразу.")))

        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(
            [i18n.t("/anim"), i18n.t("Название"), i18n.t("Описание")])
        head_view = self.tbl.horizontalHeader()
        head_view.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        head_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        head_view.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setMinimumHeight(190)
        lay.addWidget(self.tbl, 1)

        btns = QHBoxLayout()
        self.bt_add = QPushButton(i18n.t("Добавить вариант"))
        self.bt_add.clicked.connect(self._add)
        self.bt_del = QPushButton(i18n.t("Удалить вариант"))
        self.bt_del.setObjectName("danger")
        self.bt_del.clicked.connect(self._del)
        self.bt_up = QPushButton(i18n.t("Выше"))
        self.bt_up.clicked.connect(lambda: self._move(-1))
        self.bt_down = QPushButton(i18n.t("Ниже"))
        self.bt_down.clicked.connect(lambda: self._move(1))
        for button in (self.bt_add, self.bt_del, self.bt_up, self.bt_down):
            btns.addWidget(button)
        btns.addStretch(1)
        lay.addLayout(btns)

        self.lb_problem = QLabel("")
        self.lb_problem.setProperty("no_i18n", True)
        self.lb_problem.setWordWrap(True)
        self.lb_problem.setStyleSheet("color:#ffb45b;")
        lay.addWidget(self.lb_problem)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.bt_cancel = QPushButton(i18n.t("Отмена"))
        self.bt_cancel.setAutoDefault(False)
        self.bt_cancel.clicked.connect(self.reject)
        self.bt_ok = QPushButton(i18n.t("Готово"))
        self.bt_ok.setObjectName("primary")
        self.bt_ok.setDefault(True)
        self.bt_ok.clicked.connect(self._accept)
        bottom.addWidget(self.bt_cancel)
        bottom.addWidget(self.bt_ok)
        lay.addLayout(bottom)

        self._fill()
        self.tbl.itemSelectionChanged.connect(self._sync_buttons)
        # правка любой ячейки сразу перепроверяет варианты: кнопка «Готово»
        # гаснет и загорается по мере ввода, без нажатий «проверить»
        # editing any cell revalidates at once: the Done button dims and lights up
        # as the text is typed, with no separate "check" press
        self.tbl.itemChanged.connect(lambda *_: self._validate())
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                 | QAbstractItemView.EditTrigger.SelectedClicked
                                 | QAbstractItemView.EditTrigger.EditKeyPressed
                                 | QAbstractItemView.EditTrigger.AnyKeyPressed)

    # --- таблица ---
    def _fill(self):
        """Заполнить таблицу вариантами правила / the rule variants in the table."""
        variants = self.rule.variant_list()
        self.tbl.blockSignals(True)
        self.tbl.setRowCount(0)
        for choice in variants:
            self._add_row(choice)
        self.tbl.blockSignals(False)
        self._sync_buttons()
        self._validate()

    def _add_row(self, choice):
        row = self.tbl.rowCount()
        self.tbl.insertRow(row)
        for column, text in enumerate((choice.name, choice.title,
                                       choice.description)):
            item = QTableWidgetItem(text)
            item.setToolTip(text)
            self.tbl.setItem(row, column, item)
        return row

    def _add(self):
        row = self._add_row(anims.Choice())
        self.tbl.selectRow(row)
        self.tbl.setCurrentCell(row, 0)
        self.tbl.editItem(self.tbl.item(row, 0))
        self._validate()

    def _del(self):
        rows = sorted({index.row() for index in self.tbl.selectedIndexes()},
                      reverse=True)
        if not rows:
            self._problem_hint(i18n.t("Сначала выберите вариант."))
            return
        for row in rows:
            self.tbl.removeRow(row)
        self._sync_buttons()
        self._validate()

    def _move(self, delta):
        rows = self.tbl.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        target = row + delta
        if not 0 <= target < self.tbl.rowCount():
            return
        cells = []
        for column in range(self.tbl.columnCount()):
            item = self.tbl.takeItem(row, column)
            cells.append(item if item is not None else QTableWidgetItem(""))
        self.tbl.removeRow(row)
        self.tbl.insertRow(target)
        for column, item in enumerate(cells):
            self.tbl.setItem(target, column, item)
        self.tbl.selectRow(target)

    def _sync_buttons(self):
        has = bool(self.tbl.selectionModel().selectedRows())
        for button in (self.bt_del, self.bt_up, self.bt_down):
            button.setEnabled(has)

    def _problem_hint(self, text):
        self.lb_problem.setText(text)

    def _validate(self):
        """Проверить варианты на месте и сказать, что не так.

        Check the variants right here and say what is wrong.
        """
        problems = []
        seen = set()
        for row in range(self.tbl.rowCount()):
            choice = self._choice_at(row)
            problem = choice.problem()
            if problem:
                problems.append(i18n.tf("Строка %d: ", row + 1) + i18n.t(problem))
                continue
            if choice.name in seen:
                problems.append(i18n.tf("Строка %d: ", row + 1)
                                + i18n.t("такая анимация уже есть в списке"))
            seen.add(choice.name)
        if self.tbl.rowCount() > anims.MAX_CHOICES:
            problems.append(i18n.t(anims.VAL_TOO_MANY_CHOICES))
        self.lb_problem.setText(" ".join(problems))
        self.bt_ok.setEnabled(not problems and self.tbl.rowCount() > 0)
        return not problems

    def _choice_at(self, row) -> "anims.Choice":
        def text(column):
            item = self.tbl.item(row, column)
            return item.text().strip() if item is not None else ""
        return anims.Choice(name=text(0).lstrip("/"), title=text(1),
                            description=text(2))

    def choices(self) -> list["anims.Choice"]:
        """Итоговые варианты в порядке таблицы / the variants in table order."""
        return [self._choice_at(row) for row in range(self.tbl.rowCount())]

    def _accept(self):
        if not self._validate():
            return
        self.accept()


def ask_anim_props(rule, parent=None):
    """ПКМ по правилу: свойства анимации; меняет ``rule`` на месте.

    Right-click on a rule: the animation properties; ``rule`` is changed in place.
    Возвращает True, если игрок нажал «Готово».
    Returns True when the player pressed Done.
    """
    dialog = AnimProps(rule, parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False
    variants = dialog.choices()
    # один вариант — обычное правило: имя переезжает в name, вариантов нет,
    # чтобы конфиг остался прежним и старые версии его понимали
    # one variant is an ordinary rule: the name goes into name and the variants
    # are dropped, so the config stays the old shape and older versions read it
    if len(variants) == 1:
        rule.name = variants[0].name
        rule.choices = []
    else:
        rule.choices = variants
        rule.name = ""
    return True


class DlxConsent(QDialog):
    """Окно согласия на локальный сервис DeepL / consent for the local DeepL service.

    Показывается один раз при запуске: человек видит, что именно скачивается,
    куда уходит текст и как это выключить, и может отказаться.
    Shown once at start: the user sees what is downloaded, where the text goes and
    how to switch it off, and may say no.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DeepL рядом (DLX)")
        self.setStyleSheet(style_sheet(1.0))
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        lay.setSpacing(12)
        title = QLabel("Перевод получше: DeepL рядом")
        title.setStyleSheet("font-size:16px;font-weight:600;")
        lay.addWidget(title)
        text = QLabel(
            "Рядом с программой можно развернуть отдельный сервис перевода — "
            "бесплатную программу DLX с открытым кодом (лицензия MIT).\n\n"
            "· качество DeepL выше, чем у бесплатных сервисов Google;\n"
            "· занимает около 15 МБ и запускается вместе с программой;\n"
            "· текст перевода уходит на серверы DeepL — так же, как сейчас в Google;\n"
            "· сервис неофициальный: DeepL может ограничить запросы, и тогда перевод "
            "сам вернётся к стандартным сервисам;\n"
            "· выключить можно в любой момент: Настройки → DeepL.")
        text.setWordWrap(True)
        lay.addWidget(text)
        self.chk_download = QCheckBox("Скачать сервис сейчас (около 15 МБ)")
        self.chk_download.setChecked(True)
        lay.addWidget(self.chk_download)
        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_no = QPushButton("Остаться на стандартных")
        self.btn_no.setAutoDefault(False)
        self.btn_no.clicked.connect(self.reject)
        self.btn_yes = QPushButton("Включить DeepL")
        self.btn_yes.setObjectName("primary")
        self.btn_yes.setAutoDefault(False)
        self.btn_yes.clicked.connect(self.accept)
        row.addWidget(self.btn_no)
        row.addWidget(self.btn_yes)
        lay.addLayout(row)

    def wants_download(self) -> bool:
        """Скачивать ли сервис сразу / whether to download the service now."""
        return bool(self.chk_download.isChecked())


def ask_dlx_consent(cfg, parent=None):
    """Спрашивает про DLX один раз; возвращает (включён, скачать).

    Asks about DLX once; returns (enabled, download). The answer is written into
    cfg by the caller, so the question is never repeated.
    """
    dialog = DlxConsent(parent)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    return accepted, (accepted and dialog.wants_download())


def open_settings(cfg, parent=None, first_run=False, dlx=None, anims_api=None):
    """Создаёт окно, загружает значения и возвращает его (без exec)."""
    win = SettingsWindow(cfg, parent=parent, first_run=first_run, dlx=dlx,
                         anims_api=anims_api)
    win._load_widgets()
    win._load_language(langs.code_of(cfg.get("target_lang", "it")), reload_table=True)
    return win
