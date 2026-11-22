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

from PySide6.QtCore import (QEasingCurve, QEvent, QObject, QPoint, QRect, QRectF,
                            QSize, Qt, QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import (QColor, QDrag, QFont, QGuiApplication, QKeySequence,
                           QPainter, QPixmap, QPolygon)
import urllib.parse

from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QCheckBox, QComboBox,
                               QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit,
                               QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit,
                               QPushButton, QScrollArea, QSizePolicy, QSpinBox,
                               QStackedWidget, QTableWidget, QTableWidgetItem,
                               QToolButton, QVBoxLayout, QWidget)

from app import dlx as dlx_mod
from app import anims, history, i18n, langs, modules, morph, slang
from app.config import (CONFIG_PATH, DATA, DEFAULT_CONFIG, SLANG_PATH, log,
                        read_json, save_config, write_json)
from app.engine import (Engine, Glossary, glossary_path, load_glossary_data,
                        reset_glossary, save_glossary_data)
from app.translator import TranslateError, Translator

def _table_state(table):
    """Содержимое таблицы для снимка: текст, галочки, виджеты-ячейки.

    A table's contents for a snapshot: text, check marks, cell widgets.

    Комбобоксы в ячейках («Режим», «Формы») тоже входят: их выбор — такая же
    правка, как набранный текст.
    The combo boxes inside cells ("Mode", "Forms") count too: choosing there is an
    edit just like typed text.
    """
    rows = []
    for row in range(table.rowCount()):
        cells = []
        for column in range(table.columnCount()):
            item = table.item(row, column)
            widget = table.cellWidget(row, column) if hasattr(table, "cellWidget") else None
            cells.append((
                item.text() if item is not None else None,
                item.checkState() if item is not None and hasattr(item, "checkState") else None,
                (widget.currentIndex(), widget.count()) if widget is not None
                and hasattr(widget, "currentIndex") else None,
            ))
        rows.append(tuple(cells))
    return tuple(rows)


def _restore_table(table, rows):
    """Вернуть таблицу к снимку, не порождая новых правок.

    Put the table back to a snapshot without creating new edits.
    """
    if rows is None:
        return
    table.blockSignals(True)
    try:
        if len(rows) != table.rowCount() or any(
                len(cells) != table.columnCount() for cells in rows):
            table.setRowCount(len(rows))
            table.setColumnCount(len(rows[0]) if rows else table.columnCount())
        for row, cells in enumerate(rows):
            for column, (text, check, combo) in enumerate(cells):
                item = table.item(row, column)
                if item is not None and text is not None and item.text() != text:
                    item.setText(text)
                if item is not None and check is not None and hasattr(item, "checkState"):
                    item.setCheckState(check)
                widget = table.cellWidget(row, column) if hasattr(table, "cellWidget") else None
                if combo is not None and widget is not None and hasattr(widget, "setCurrentIndex"):
                    widget.setCurrentIndex(combo[0])
    finally:
        table.blockSignals(False)


def _read_disk_state():
    """Что сейчас записано на диск: config.json и словари.

    What is on the disk right now: config.json and the glossaries.

    Нужно для отмены после сохранения: файл обязан вернуться в прежнее
    состояние, иначе игра продолжит играть отменённую анимацию.
    Needed for undo after a save: the file has to go back to its previous state,
    otherwise the game keeps playing the animation that was undone.
    """
    cfg = read_json(CONFIG_PATH, {})
    docs = {}
    try:
        from app.engine import glossary_path
        folder = glossary_path("it").parent
        for path in sorted(folder.glob("*.json")):
            data = read_json(path, None)
            if isinstance(data, dict):
                docs[path.stem] = data
    except Exception:
        log.exception("Отмена: не удалось прочитать файлы словарей")
    # Свои сокращения меняются в окне, и отмена обязана вернуть файл: без этого
    # после Ctrl+Z таблица на экране старая, а в игре новая.
    # The player's own abbreviations change in the window, and an undo has to put
    # the file back: otherwise the table is old on screen and new in game.
    slang_file = read_json(SLANG_PATH, None)
    return {"cfg": cfg if isinstance(cfg, dict) else {}, "docs": docs,
            "slang": slang_file if isinstance(slang_file, dict) else {}}


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
/* Плашка состояния сервиса DeepL. Цвет говорит то же, что и слово: зелёный —
   работает, янтарный — работает, но DeepL отказывает, серый — выключен,
   красный — ошибка. Перед словом стоит точка, чтобы состояние читалось и без
   цвета: на некоторых экранах зелёный и янтарный почти неразличимы.
   The DeepL state badge carries its meaning in colour and in words: green means
   running, amber means running while DeepL refuses, grey means off, red means an
   error. A dot precedes the words so the state still reads without colour: on
   some screens green and amber are nearly the same. */
QLabel#dlxState { font-weight: 600; padding: 2px 0; }
QLabel#dlxState[state="ready"] { color: #7ff0b0; }
QLabel#dlxState[state="upstream"] { color: #ffd06b; }
QLabel#dlxState[state="starting"] { color: #a9c4ff; }
QLabel#dlxState[state="off"], QLabel#dlxState[state="missing"] { color: #9a9aa6; }
QLabel#dlxState[state="error"] { color: #ff9c9c; }
/* Надпись у тумблера: называет то же состояние, что и бегунок, и красится
   вместе с ним. Плоская кнопка — чтобы её можно было нажать, но она не
   выглядела второй кнопкой рядом с тумблером.
   The switch caption names the same state as the knob and takes its colour.
   It is a flat button: clickable, yet it does not look like a second button. */
QPushButton#dlxSwitch { background: transparent; border: none; padding: 2px 2px;
                        font-weight: 600; min-height: 18px; }
QPushButton#dlxSwitch[state="ready"] { color: #7ff0b0; }
QPushButton#dlxSwitch[state="upstream"] { color: #ffd06b; }
QPushButton#dlxSwitch[state="starting"] { color: #a9c4ff; }
QPushButton#dlxSwitch[state="off"], QPushButton#dlxSwitch[state="missing"] {
    color: #9a9aa6; }
QPushButton#dlxSwitch[state="error"] { color: #ff9c9c; }
QPushButton#dlxSwitch:hover { color: #ffffff; }
QPushButton#dlxSwitch:disabled { color: #6b6b79; }
/* погашенный раздел: плашка, тумблер и надпись теряют цвет вместе с остальным
   a dimmed section: badge, switch and caption lose their colour with the rest */
QWidget#page[moduleOff="true"] QLabel#dlxState,
QWidget#page[moduleOff="true"] QPushButton#dlxSwitch {
    background: transparent; border: none; color: #6b6b79; }
/* вертикальная черта между тумблером и служебными кнопками
   the vertical line between the switch and the service buttons */
QFrame#vsep { background: #2e2e3a; max-width: 1px; border: none; }
QListWidget#nav { background: #17171e; border: none; border-right: 1px solid #26262f;
                  padding: 8px 6px; outline: 0; }
QListWidget#nav::item { padding: 10px 12px; border-radius: 8px; margin: 2px 4px; color: #c8c8d2; }
QListWidget#nav::item:selected { background: #26263a; color: #ffffff; }
QListWidget#nav::item:hover { background: #20202b; }
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit { background: #0e0e12;
    border: 1px solid #3a3a48; border-radius: 6px; padding: 6px 8px;
    min-height: 18px; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {
    border: 1px solid #5b8cff; }
QLineEdit:read-only, QPlainTextEdit:read-only { color: #b9c4ff; }
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
/* Раздел с выключенным модулем: содержимое уходит в серый, карточки и рамки
   гаснут, а подсказка сверху (QLabel#moduleOff) остаётся своего цвета — её и
   надо прочитать. A section with its module off goes grey: fields, cards and
   frames fade, while the hint on top (QLabel#moduleOff) keeps its own colour,
   because that is the line to read. */
QWidget#page[moduleOff="true"] QLabel,
QWidget#page[moduleOff="true"] QCheckBox { color: #6b6b79; }
QWidget#page[moduleOff="true"] QFrame#card { background: #17171d; border: 1px solid #24242d; }
QWidget#page[moduleOff="true"] QLineEdit,
QWidget#page[moduleOff="true"] QSpinBox,
QWidget#page[moduleOff="true"] QComboBox { background: #101014; border: 1px solid #2b2b36;
                                           color: #6b6b79; }
QWidget#page[moduleOff="true"] QTableWidget { background: #101014; border: 1px solid #2b2b36;
                                              gridline-color: #202028; color: #6b6b79; }
QWidget#page[moduleOff="true"] QHeaderView::section { background: #17171d; color: #6b6b79; }
QWidget#page[moduleOff="true"] QPushButton { background: #191920; border: 1px solid #2b2b36;
                                             color: #6b6b79; }
QWidget#page[moduleOff="true"] QPushButton#primary { background: #262f42; border: 1px solid #2c3548;
                                                     color: #7c8496; }
QScrollArea#scroll { background: transparent; border: none; }
QScrollArea#scroll > QWidget > QWidget { background: #14141a; }
QScrollBar:horizontal { background: #14141a; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #33333f; border-radius: 5px; min-width: 30px; }
"""


def style_sheet(scale=1.0):
    """Таблица стилей с масштабом шрифта.

    Один и тот же набор правил работает и на 1366×768, и на 4K: меняется
    только базовый размер шрифта, остальное подстраивает компоновка.

    The style sheet with the font scale.

    The same set of rules works on 1366×768 and on 4K: only the base
    font size changes, the layout adapts the rest.
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
    # button sizes come from the same scale: at 150 % a finger and a mouse
    # hit the button as surely as at 100 %
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


def _fit_dialog(win, ratio=0.94):
    """Окно по размеру экрана: не шире и не выше рабочей области.

    A window sized to the screen: no wider and no taller than the work area.

    Отдельные окна (свойства анимации, развёрнутая таблица) задают размер сами и
    на большом экране ошибаются в другую сторону — упираются в края. Здесь одно
    место, где это считается.
    Standalone windows (the animation properties, the expanded table) size
    themselves and get it wrong the other way on a large screen — they run into
    the edges. This is the one place where it is worked out.
    """
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return
    area = screen.availableGeometry()
    win.resize(int(area.width() * ratio), int(area.height() * ratio))
    win.move(area.x() + (area.width() - win.width()) // 2,
             area.y() + (area.height() - win.height()) // 2)


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
        return False, ("Одиночная буква/цифра будет мешать печати — добавьте Ctrl/Alt "
                      "или выберите F-клавишу.")
    return True, ""


class KeyCapture(QLineEdit):
    """Поле горячей клавиши: нажмите сочетание — оно запишется.

    The hotkey field: press a combination and it is recorded.
    """

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


# Цвета, которые в погашенном разделе становятся серыми: и в styleSheet виджета,
# и в правилах таблицы стилей. Один список, чтобы «серый» был одним и тем же.
# Colours that turn grey inside a dimmed section, both in a widget stylesheet and
# in the shared rules. One list, so that "grey" stays the same grey.
_DIM_COLOR = "#6b6b79"
_DIM_SOURCES = ("#dfe3ff", "#9aa0b4", "#8a8fa3", "#8a8a96", "#b9c4ff", "#f2f2f2", "#e9e9f2")


def _dimmed_css(css):
    """Стиль виджета с серыми цветами / a widget stylesheet with grey colours.

    Меняются только цвета: размеры, веса и всё остальное остаются как были, иначе
    заголовок карточки на погашенном разделе поехал бы по размеру.
    Only colours change: sizes, weights and the rest stay as they were, or a card
    title would change size on a dimmed section.
    """
    out = str(css or "")
    for colour in _DIM_SOURCES:
        out = out.replace(colour, _DIM_COLOR).replace(colour.upper(), _DIM_COLOR)
    return out


def _dim_state(widget):
    """Спрятать цветное состояние виджета за серым / hide a coloured state.

    Настоящее состояние запоминается в свойстве ``_dim_state_real``, а само
    свойство ``state`` ставится в ``off`` — по нему правило стиля и выбирает
    серый. ``_dim_restore_state`` возвращает всё назад.
    The real state is kept in the ``_dim_state_real`` property while ``state``
    becomes ``off``, which is the grey rule in the stylesheet. The restore
    function puts everything back.
    """
    if widget.property("_dim_state_real") is None:
        widget.setProperty("_dim_state_real", widget.property("state"))
    if widget.property("state") == "off":
        return
    widget.setProperty("state", "off")
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def _dim_restore_state(widget):
    """Вернуть цветное состояние виджета / restore a widget's coloured state."""
    real = widget.property("_dim_state_real")
    if real is None:
        return
    widget.setProperty("_dim_state_real", None)
    if widget.property("state") == real:
        return
    widget.setProperty("state", real)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


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

    WIDTH = 46                     # ширина дорожки / the track width
    HEIGHT = 24                    # высота дорожки / the track height
    KNOB = 18                      # диаметр бегунка / the knob diameter
    ON_COLOR = QColor("#2e7d55")   # зелёная дорожка: включено / on
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
        self._pos = 0.0            # 0 — выключен, 1 — включён / 0 off, 1 on
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(140)
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

    def paintEvent(self, event):          # noqa: N802 — имя из Qt / a Qt name
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
                QRectF(-2.5, -2.5, self.WIDTH + 4, self.HEIGHT + 4),
                radius + 2, radius + 2)
        painter.end()


def _hint(text):
    lab = QLabel(text)
    lab.setObjectName("hint")
    lab.setWordWrap(True)
    return lab


def _dlx_languages():
    """Языки DeepL: код и название на русском / DeepL languages: code and Russian name.

    Названия на русском, потому что i18n.t() вернёт их как есть на русском интерфейсе
    и подменит на английские значения из STRINGS на английском.
    Names are in Russian: i18n.t() returns them as-is on a Russian UI and substitutes
    the English value from STRINGS on an English UI.

    «auto» не входит — его добавляет вызывающий код только для источника.
    "auto" is not included; the caller adds it for the source side only.
    """
    return [
        ("BG", "Болгарский"),
        ("CS", "Чешский"),
        ("DA", "Датский"),
        ("DE", "Немецкий"),
        ("EL", "Греческий"),
        ("EN", "Английский"),
        ("ES", "Испанский"),
        ("ET", "Эстонский"),
        ("FI", "Финский"),
        ("FR", "Французский"),
        ("HU", "Венгерский"),
        ("ID", "Индонезийский"),
        ("IT", "Итальянский"),
        ("JA", "Японский"),
        ("KO", "Корейский"),
        ("LT", "Литовский"),
        ("LV", "Латышский"),
        ("NL", "Нидерландский"),
        ("PL", "Польский"),
        ("PT", "Португальский"),
        ("RO", "Румынский"),
        ("RU", "Русский"),
        ("SK", "Словацкий"),
        ("SL", "Словенский"),
        ("SV", "Шведский"),
        ("TR", "Турецкий"),
        ("UK", "Украинский"),
        ("ZH", "Китайский"),
    ]


def _small_spin(spin, lo, hi, suffix="", width=170, step=None, prefix=None):
    """Компактный счётчик: не растягивается на всю карточку.

    A compact counter: it does not stretch across the whole card.
    """
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
        if target in (source, source + 1):        # на то же место / same place
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
        # Несохранённые правки по языкам: {код: {сокращение: [разворот, вариант]}}.
        # Таблица показывает один язык, но правки другого не теряются при
        # переключении — они ждут «Сохранить».
        # Unsaved edits per language: {code: {token: [expansion, variant]}}.
        # The table shows one language, yet edits to another are never lost on a
        # switch: they wait for "Save".
        self._slang_drafts = {}
        self._slang_lang = slang.code_for(cfg.get("slang_lang") or cfg.get("target_lang"))
        self.glang = langs.code_of(self.cfg.get("target_lang", "it"))
        self.glossary_changed = False
        self.first_run = first_run
        self._busy = False
        # Отмена и повтор: история своя у каждого раздела, снимки несут и то,
        # что уже записано на диск.
        # Undo and redo: a history per section, snapshots include what already
        # reached the disk.
        self._hist = history.History()
        self._hist_applying = False     # сейчас применяем снимок / applying a snapshot
        self._hist_busy = False         # запись шага идёт / recording a step
        self._hist_field = {}           # поле -> последнее значение / field metadata
        self._disk_cache = {"cfg": {}, "docs": {}}   # диск на момент снимка / disk view

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
        self._page_rows = {}             # имя страницы -> строка в списке слева
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
            self._page_rows[attr] = page_index
            page = maker()
            self._add_module_banner(page, attr)
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
        # первый расчёт: какие разделы погашены при текущих флагах модулей
        # the first pass: which sections are dimmed with the current flags
        self._sync_module_pages()
        # окно собрано: с этого места смена режима может дёргать проверку перевода
        # the window is built, so a mode change may now trigger the preview
        self._mode_ready = True
        # окно заполнено — с этого места начинается история правок
        # the window is filled in, so the edit history starts here
        self._reset_history()
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
        # подпись отмены живёт рядом с общей подсказкой: она короткая и
        # появляется только когда отменять действительно есть что
        # the undo caption sits next to the shared hint: it is short and appears
        # only when there is something to take back
        self.lb_hist = QLabel("")
        self.lb_hist.setProperty("no_i18n", True)
        self.lb_hist.setObjectName("hint")
        lay.addWidget(self.btn_reset)
        lay.addWidget(self.footer_hint, 1)
        lay.addWidget(self.lb_hist)
        lay.addWidget(self.btn_cancel)
        lay.addWidget(self.btn_save)
        return w

    # ------------------------------------------------ размер под экран
    # fitting the screen
    def _ui_scale(self):
        """Масштаб интерфейса из настроек: 0.8…1.8 (в окне — проценты).

        The interface scale from the settings: 0.8…1.8 (percent in the window).
        """
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

        Fits the window to the screen: no more than 94 % of the work area.

        On a small laptop the window shrinks, on a large monitor it stays as
        before; whatever does not fit in height is scrolled.
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
        """Меню разделов подстраивается под ширину окна, а не режет подписи.

        The section list adapts to the window width instead of cutting captions.
        """
        super().resizeEvent(e)
        if hasattr(self, "nav"):
            self.nav.setFixedWidth(max(132, min(int(210 * self._ui_scale()),
                                                int(self.width() * 0.28))))

    def _ui_scale_changed(self, value=None):
        """Ползунок масштаба: сразу меняет шрифт и размер окна.

        The scale slider: it changes the font and the window size at once.
        """
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
        # раздел мог быть погашен, пока его не было на экране: состояние
        # модулей проверяем при каждом заходе
        # the section may have been dimmed while off screen: the module state is
        # re-checked on every visit
        self._sync_module_pages()
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

        # режим перевода — первое, что видит игрок: от него зависит, какие
        # карточки ниже вообще работают
        # the translation mode comes first: it decides which cards below matter
        card, cl = _card()
        cl.addWidget(_title("Режим перевода", "sec"))
        self.cb_mode = QComboBox()
        self.cb_mode.setMinimumWidth(340)
        for val, text in (("full", "Всё сообщение — на язык перевода"),
                          ("partial", "Только выделенные слова и фразы (обычный режим)"),
                          ("to_ru", "Ваш язык → русский")):
            self.cb_mode.addItem(text, val)
        self.cb_mode.setToolTip(
            "Полный: в чат уходит весь текст на языке перевода.\n"
            "Частичный: переводятся только выделенные +слова и фразы+, "
            "остальное — как написали.\n"
            "Обратный: пишете на своём языке, в чат уходит русский текст.")
        self.cb_mode.currentIndexChanged.connect(self._mode_changed)
        row_mode = QHBoxLayout()
        row_mode.addWidget(QLabel("Что переводить:"))
        row_mode.addWidget(self.cb_mode)
        row_mode.addStretch(1)
        cl.addLayout(row_mode)
        self.lb_mode = QLabel("")
        self.lb_mode.setProperty("no_i18n", True)
        self.lb_mode.setWordWrap(True)
        cl.addWidget(self.lb_mode)
        lay.addWidget(card)

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
        # строка целиком прячется, когда выбора нет: полный и обратный режим
        # отправляют в чат один-единственный вариант
        # the whole row hides when there is no choice: full and reverse mode send
        # exactly one variant
        self.w_send_mode = QWidget()
        self.w_send_mode.setLayout(row)
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
        cl.addWidget(self.w_send_mode)

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
        self.chk_slang.toggled.connect(
            lambda on: self._mirror_own_flag("slang", on))
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
        # window scale: adapting to small and large screens
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
        """Переключение языка интерфейса прямо в окне настроек.

        Switching the interface language right inside the settings window.
        """
        i18n.set_lang(self.cb_ui_lang.currentData() or "ru")
        i18n.retranslate(self)
        # названия и пояснения модулей берутся из реестра, а не из таблицы
        # переводов, поэтому обновляем их отдельно
        # module titles and descriptions come from the registry rather than the
        # translation table, so they are updated separately
        if hasattr(self, "cb_lang"):
            current = self.cb_lang.currentData()
            self.cb_lang.blockSignals(True)
            for index, name in enumerate(name for _, name in langs.choices()):
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
        """Обновляет подписи, которые собираются в коде (счётчики, подсказки).

        Refreshes the captions built in code (counters, hints).
        """
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
        """Подсказка под списком режимов: что именно уйдёт в чат.

        The hint under the mode list: what exactly leaves for the chat.
        """
        if not hasattr(self, "lb_mode"):
            return
        mode = self._mode()
        if mode == "to_ru":
            self.lb_mode.setText(i18n.t(
                "Режим переводчика: пишете на своём языке — в чат уходит русский текст. "
                "Переводится каждое сообщение целиком, включая действия *...*; команды "
                "/… остаются как есть. Автоперевод, слова-паразиты и выбор «что уходит "
                "в чат» здесь не работают."))
        elif mode == "full":
            self.lb_mode.setText(i18n.t(
                "Полный перевод: в чат уходит всё сообщение на языке перевода. Словарь "
                "важнее сервисов, слова-паразиты и автоперевод не участвуют, скобки "
                "+…+ не нужны — переводится всё."))
        else:
            self.lb_mode.setText(i18n.t(
                "Обычный режим: в чат уходит ваш русский текст, а переведёнными — только "
                "выделенные +слова и фразы+ и то, что выбрал автоперевод. Работают "
                "слова-паразиты и выбор «что уходит в чат»."))

    def _mode(self):
        """Текущий режим из списка / the mode chosen in the list."""
        if hasattr(self, "cb_mode"):
            return self.cb_mode.currentData() or "partial"
        return self.cfg.get("mode") or "partial"

    def _mode_changed(self, *_):
        """Смена режима: гасим то, что в этом режиме не работает.

        The mode changed: dim whatever does not work in it.

        В полном и обратном режиме нет ни автоперевода, ни слов-паразитов, ни
        выбора «что уходит в чат»: там переводится всё сообщение, и выбирать
        нечего. Прятать их совсем — хуже: игрок решит, что настройки пропали.
        Full and reverse mode have no auto-translation, no fillers and no
        "what goes to the chat" choice: the whole message is translated, so there
        is nothing to choose. Hiding them would be worse: the settings would look
        lost.
        """
        mode = self._mode()
        partial = mode == "partial"
        for widget in (getattr(self, "gb_auto", None), getattr(self, "gb_filler", None)):
            if widget is not None:
                widget.setVisible(partial)
        if hasattr(self, "w_send_mode"):
            self.w_send_mode.setVisible(partial)
        self._reverse_changed()
        self._sync_module_pages()
        if getattr(self, "_mode_ready", False):
            self._do_preview()

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
        """Показывает описание языка и (при необходимости) словарь этого языка.

        Shows the language description and, when needed, that language's glossary.
        """
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
        """Данные словаря языка (из памяти или с диска).

        The glossary data of a language (from memory or from the disk).
        """
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
        self.gb_auto = card
        cl.addWidget(_title("Автоперевод", "sec"))
        cl.addWidget(_hint("Перевод вставляется в обычную русскую речь, чтобы она выглядела живой. "
                           "Например: «мне срочно нужна помощь» → «мне срочно нужна Aiutami»."))
        self.chk_auto = QCheckBox("Включить автоперевод")
        self.chk_auto.toggled.connect(
            lambda on: self._mirror_own_flag("autotranslate", on))
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
        self.gb_filler = card
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
        self.chk_send.toggled.connect(lambda on: self._mirror_own_flag("game_send", on))
        cl.addWidget(self.chk_send)
        self.chk_chat_first = QCheckBox("Сначала открывать чат игры (клавиша T), потом оверлей")
        self.chk_chat_first.setToolTip(
            "Окружающие видят, что вы печатаете, а не стоите без действия")
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
        """Правка ячейки словаря / a glossary cell was edited.

        Порядок важен: сначала данные, потом шаг истории. Снимок «после» обязан
        нести уже правленый словарь, иначе повтор вернул бы таблицу без данных
        и ячейка откатилась бы не туда.
        The order matters: data first, the history step second. The "after"
        snapshot has to carry the already edited glossary, or a redo would return
        a table without its data and the cell would roll back to the wrong place.
        """
        row = item.row() if item is not None else -1
        col = item.column() if item is not None else -1
        self.glossary_changed = True
        self._collect_glossary()
        self._mark(f"glossary:{self.glang}:{row}:{col}")

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
        self._hist_shadow = self._hist_state()   # состояние до перетаскивания
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

        # язык таблицы выбирается здесь же: у каждого языка своя таблица, и
        # правка немецкой не лезет в английскую
        # the table's language is chosen right here: every language keeps its own
        # table, so editing German does not touch English
        lang_row = QHBoxLayout()
        lang_row.setSpacing(8)
        lang_row.addWidget(QLabel("Язык таблицы"))
        self.cb_slang_lang = QComboBox()
        for code, title in slang.languages():
            self.cb_slang_lang.addItem(title, code)
        # названия языков пишутся на самих языках и не переводятся
        # language names are written in their own languages and stay untranslated
        self.cb_slang_lang.setProperty("no_i18n", True)
        self.cb_slang_lang.setMinimumWidth(150)
        self.cb_slang_lang.setMaximumWidth(220)
        self.cb_slang_lang.setToolTip(
            "Сокращения языка сервера разворачиваются перед переводом на русский. "
            "Русские сокращения («спс», «мб») работают всегда и в списке не нужны: "
            "это обратное направление.")
        self.cb_slang_lang.currentIndexChanged.connect(self._slang_lang_changed)
        lang_row.addWidget(self.cb_slang_lang)
        self.lb_slang_lang_hint = _hint("")
        lang_row.addWidget(self.lb_slang_lang_hint, 1)
        lay.addLayout(lang_row)

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
            "У каждого языка своя таблица: выберите его в списке сверху, правки "
            "запоминаются отдельно и не мешают друг другу. Свои сокращения работают "
            "так же, как встроенные, и перекрывают их: «afaik» → «as far as I know» → "
            "«насколько знаю». Во второй колонке — полная фраза на языке собеседника: её "
            "получает переводчик, поэтому падеж и род выходят верными. В третьей — "
            "короткая подстановка, если сервис вернул латиницу. Пустые колонки "
            "выключают сокращение. Смайлы вроде «xD» и «x)» не трогаются никогда."))
        return page

    # заполнение и сбор таблицы сокращений
    def _slang_lang_changed(self, *_):
        """Переключили язык таблицы сокращений / the abbreviation language changed.

        Правки покидаемого языка сначала уходят в черновик, поэтому ничего не
        пропадает: вернувшись, игрок увидит их на месте, даже если не сохранял.
        The edits of the language being left go into its draft first, so nothing
        is lost: coming back shows them again, saved or not.
        """
        code = self.cb_slang_lang.currentData()
        if not code or code == self._slang_lang:
            return
        self._collect_slang(self._slang_lang)
        self._slang_lang = code
        # рабочая таблица переключается сразу: иначе предпросмотр на соседней
        # странице показывал бы сокращения прежнего языка
        # the working table switches at once, or the preview on the next page
        # would still show the previous language's abbreviations
        slang.set_language(code)
        self._fill_slang()

    def _slang_draft(self, code):
        """Черновик языка: сокращение -> [разворот, вариант], в порядке таблицы.

        The draft of one language: token -> [expansion, variant], in table order.

        Черновик начинается с того, что реально работает сейчас (встроенные плюс
        сохранённые свои записи), и дальше живёт отдельно — до «Сохранить».
        A draft starts as what actually works now (the built-ins plus the saved
        own entries) and lives apart from then on, until "Save".
        """
        code = slang.code_for(code)
        draft = self._slang_drafts.get(code)
        if draft is None:
            draft = {}
            for token, expand, ru, _own in slang.entries(code):
                draft[token] = [expand, ru]
            self._slang_drafts[code] = draft
        return draft

    def _fill_slang(self):
        if not hasattr(self, "tbl_slang"):
            return
        code = slang.code_for(getattr(self, "_slang_lang", "en"))
        self._slang_lang = code
        if hasattr(self, "cb_slang_lang"):
            index = self.cb_slang_lang.findData(code)
            if index >= 0 and self.cb_slang_lang.currentIndex() != index:
                self.cb_slang_lang.blockSignals(True)
                self.cb_slang_lang.setCurrentIndex(index)
                self.cb_slang_lang.blockSignals(False)
        draft = self._slang_draft(code)
        self.tbl_slang.blockSignals(True)
        self.tbl_slang.setRowCount(0)
        # порядок из настроек: перетащенные строки остаются на своих местах,
        # новые и незнакомые идут в конце / the saved order comes first
        order = {token: index for index, token in enumerate(self._slang_order)}
        rows = sorted(draft.items(), key=lambda row: order.get(row[0], len(order)))
        for token, (expand, ru) in rows:
            r = self.tbl_slang.rowCount()
            self.tbl_slang.insertRow(r)
            items = [QTableWidgetItem(token),
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
        own = len(slang.user_entries(self._slang_lang))
        self.lb_slang_count.setText(
            i18n.tf("Показано: %d из %d\nСвоих: %d", shown, total, own) if needle
            else i18n.tf("Всего: %d\nСвоих: %d", total, own))

    def _update_slang_ui(self):
        if hasattr(self, "lb_slang_count"):
            own = len(slang.user_entries(self._slang_lang))
            total = len(slang.entries(self._slang_lang))
            self.lb_slang_count.setText(i18n.tf("Всего: %d\nСвоих: %d", total, own))
        if hasattr(self, "lb_slang_lang_hint"):
            self.lb_slang_lang_hint.setText(
                i18n.t("Таблица языка сервера: разворот уходит в переводчик "
                       "до перевода."))

    def _slang_edited(self, item):
        """Правка ячейки сокращений / an abbreviation cell was edited.

        Сначала черновик языка, потом шаг истории: снимок «после» должен нести
        уже правленую таблицу, иначе повтор покажет старое слово.
        The language's draft first, the history step second: the "after"
        snapshot has to carry the edited table, or a redo would show the old word.
        """
        row = item.row() if item is not None else -1
        col = item.column() if item is not None else -1
        self._slang_pending = True
        self._collect_slang()
        self._mark(f"slang:{self._slang_lang}:{row}:{col}")

    def _collect_slang(self, code=None):
        """Переносит таблицу в черновик языка (в памяти).

        Copy the table into the language's draft, in memory.

        Вызывается и при переключении языка — тогда ``code`` указывает, какой
        язык покидаем, а таблица ещё показывает его.
        Also called on a language switch: then ``code`` names the language being
        left, which the table still shows.
        """
        code = slang.code_for(code or self._slang_lang)
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
            rows[token] = [cells[1], cells[2]]
        self._slang_drafts[code] = rows
        slate = self._slate_of(code, rows)
        # своё применяем сразу: иначе предпросмотр и движок видели бы старое
        # the own entries are applied at once, or the preview would see the old ones
        slang.set_user(slate, code)
        self._slang_pending = True
        return slate

    @staticmethod
    def _slate_of(code, rows):
        """Черновик -> то, что отличается от встроенного.

        A draft turned into what differs from the built-in table.

        В файл и в память уходят только отличия: полная таблица на шесть языков
        весит больше, чем весь остальной slang.json, и повторять её в файле
        незачем. Встроенное, которого в черновике нет, считается выключенным.
        Only the differences are stored and applied: the full tables of six
        languages weigh more than the rest of slang.json put together, and there
        is no reason to repeat them in the file. A built-in missing from the draft
        counts as disabled.
        """
        built = slang.builtin(code)
        slate = {}
        for token, (expand, ru) in rows.items():
            if token in built and [expand, ru] == list(built[token]):
                continue                     # встроенное не тронуто / untouched
            slate[token] = [expand, ru]
        for token in built:
            if token not in rows:
                slate[token] = ["", ""]       # выключено игроком / switched off
        return slate

    def _move_slang_row(self, source, target):
        self._hist_shadow = self._hist_state()
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

    def _sync_slang(self):
        """Сохранить свои сокращения на диск (вызывается по «Сохранить»).

        Write the player's own abbreviations to the disk on "Save".

        Уходят все черновики сразу: игрок мог поправить три языка и не
        возвращаться к каждому.
        Every draft goes at once: the player may have edited three languages and
        need not come back to each.
        """
        if not hasattr(self, "tbl_slang"):
            return
        self._collect_slang()
        slang.save_languages({code: self._slate_of(code, rows)
                              for code, rows in self._slang_drafts.items()})
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
        foreign = {}                 # запись чужого языка -> его код / other languages
        try:
            if path.lower().endswith(".json"):
                obj = json.loads(text)
                src = obj.get("custom") if isinstance(obj, dict) and "custom" in obj else obj
                if not isinstance(src, dict):
                    raise ValueError(i18n.t("в JSON нужен объект «сокращение: разворот»"))
                for k, v in src.items():
                    if isinstance(v, dict):
                        pair = [str(v.get("expand", "")), str(v.get("ru", ""))]
                        code = slang.code_for(v.get("lang") or self._slang_lang)
                        if code != self._slang_lang:
                            # чужой язык не подмешиваем в текущий: он уедет в свой
                            # a foreign language is not mixed in: it goes to its own
                            foreign.setdefault(code, {})[str(k)] = pair
                            continue
                        loaded[str(k)] = pair
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
        if not loaded and not foreign:
            QMessageBox.information(self, i18n.t("Импорт"),
                                    i18n.t("В файле не нашлось сокращений."))
            return
        total = len(loaded) + sum(len(rows) for rows in foreign.values())
        added = 0
        for code, rows in [(self._slang_lang, loaded)] + list(foreign.items()):
            draft = self._slang_draft(code)
            added += sum(1 for k in rows if k not in draft)
            draft.update(rows)
        self._fill_slang()
        self._slang_pending = True
        QMessageBox.information(
            self, i18n.t("Импорт"),
            i18n.tf("Загружено сокращений: %d (новых %d).\n"
                    "Нажмите «Сохранить», чтобы применить.", total, added))

    def _export_slang(self):
        path, _ = QFileDialog.getSaveFileName(
            self, i18n.t("Сохранить сокращения"), str(DATA / "slang-export.json"),
            "JSON (*.json);;CSV (*.csv)")
        if not path:
            return
        data = slang.entries(self._slang_lang)
        try:
            if path.lower().endswith(".csv"):
                with open(path, "w", encoding="utf-8-sig", newline="") as f:
                    w = csv.writer(f, delimiter=";")
                    w.writerow(["Сокращение", "Разворот", "Русский вариант"])
                    for token, expand, ru, _own in data:
                        w.writerow([token, expand, ru])
            else:
                code = self._slang_lang
                own = slang.user_entries(code)
                payload = {"custom": {
                    token: {"lang": code, "expand": expand, "ru": ru}
                    for token, expand, ru, _o in data if token in own}}
                if not payload["custom"]:
                    payload = {"custom": {
                        token: {"lang": code, "expand": expand, "ru": ru}
                        for token, expand, ru, _o in data}}
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
            i18n.tf("Вернуть встроенный список сокращений для языка «%s»?\n"
                    "Ваши добавления на этом языке будут потеряны, остальные "
                    "языки не изменятся.",
                    self.cb_slang_lang.currentText()))
        if ans != QMessageBox.StandardButton.Yes:
            return
        code = self._slang_lang
        self._slang_drafts.pop(code, None)
        slang.set_user({}, code)
        self._slang_pending = True
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
        self.chk_dlx.toggled.connect(lambda on: self._mirror_own_flag("dlx", on))
        self.chk_dlx.setToolTip("Без этого флажка работает обычная цепочка сервисов")
        cl.addWidget(self.chk_dlx)
        self.chk_dlx_autostart = QCheckBox("Запускать сервис вместе с программой")
        cl.addWidget(self.chk_dlx_autostart)
        self.chk_dlx_update = QCheckBox("Проверять обновления сервиса при запуске")
        cl.addWidget(self.chk_dlx_update)
        lay.addWidget(card)

        card, cl = _card()
        cl.addWidget(_title("Состояние", "sec"))
        # Состояние — цветной плашкой, а не серой строкой: раньше «Работает» и
        # «Остановлен» выглядели одинаково, и понять, включён ли DeepL, можно
        # было только вчитавшись. Цвет и слово говорят одно и то же.
        # The state is a coloured badge instead of a grey line: "Running" and
        # "Stopped" used to look alike, so whether DeepL works took reading the
        # words. Colour and words now say the same thing.
        self.lb_dlx_state = QLabel("")
        self.lb_dlx_state.setObjectName("dlxState")
        self.lb_dlx_state.setProperty("no_i18n", True)
        self.lb_dlx_state.setWordWrap(True)
        self.lb_dlx_state.setSizePolicy(QSizePolicy.Policy.Preferred,
                                        QSizePolicy.Policy.Minimum)
        cl.addWidget(self.lb_dlx_state)
        # Тумблер с надписью вместо пары кнопок: положение бегунка и слово
        # отвечают на один вопрос — работает сервис или нет. Слева тумблер,
        # справа служебное: проверить, обновить, удалить.
        # A switch with a caption replaces the button pair: the knob position and
        # the word answer one question — does the service run. The switch sits on
        # the left; the service buttons on the right are housekeeping.
        row = QHBoxLayout()
        row.setSpacing(10)
        self.sw_dlx = ToggleSwitch()
        self.sw_dlx.setToolTip("Включить или выключить локальный сервис DeepL")
        self.sw_dlx.setAccessibleName("Сервис DeepL")
        self.sw_dlx.clicked.connect(self._dlx_toggle)
        self.b_dlx_start = QPushButton("Остановлено")
        self.b_dlx_start.setObjectName("dlxSwitch")
        self.b_dlx_start.setProperty("no_i18n", True)   # текст меняется в коде
        self.b_dlx_start.setFlat(True)
        self.b_dlx_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_dlx_start.clicked.connect(self._dlx_toggle)
        row.addWidget(self.sw_dlx)
        row.addWidget(self.b_dlx_start)
        line = QFrame()
        line.setObjectName("vsep")
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFixedWidth(1)
        row.addWidget(line)
        self.b_dlx_check = QPushButton("Проверить")
        self.b_dlx_check.setToolTip("Короткий запрос к сервису: отвечает ли он")
        self.b_dlx_check.clicked.connect(self._dlx_check)
        self.b_dlx_install = QPushButton("Установить")
        self.b_dlx_install.setObjectName("primary")
        self.b_dlx_install.setToolTip("Скачать сервис с GitHub (около 15 МБ)")
        self.b_dlx_install.clicked.connect(self._dlx_install)
        self.b_dlx_remove = QPushButton("Удалить сервис")
        self.b_dlx_remove.setObjectName("danger")
        self.b_dlx_remove.clicked.connect(self._dlx_remove)
        for button in (self.b_dlx_check, self.b_dlx_install, self.b_dlx_remove):
            button.setAutoDefault(False)
            row.addWidget(button)
        row.addStretch(1)
        self.b_dlx_start.setAutoDefault(False)
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
        form.addRow("Токен программы", self.ed_dlx_token)
        # OAuth-токен DeepL Pro относится к доступу к сервису, а не к прокси,
        # поэтому живёт здесь, рядом с остальными токенами.
        # The DeepL Pro OAuth token belongs to service access, not to the proxy,
        # so it lives here next to the other tokens.
        self.ed_dlx_pro = QLineEdit()
        self.ed_dlx_pro.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_dlx_pro.setPlaceholderText("необязательно")
        self.ed_dlx_pro.setToolTip("OAuth-токен DeepL Pro; без него работает "
                                   "бесплатный путь")
        form.addRow("Токен DeepL Pro", self.ed_dlx_pro)
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
        # Сервис может подняться или упасть сам, без нажатия кнопок: состояние
        # в окне должно меняться вместе с ним, иначе «Запущено» так и висело бы
        # после падения. Опрос дешёвый — одно чтение полей под замком.
        # The service may come up or die on its own, without a button press, and
        # the window has to follow: otherwise "Running" would stay after a crash.
        # The poll is cheap: it reads a few fields under one lock.
        self._dlx_live_key = None
        self._dlx_busy_now = False
        self._dlx_was_applied = False      # первый проход без анимации / no animation first
        self._dlx_live = QTimer(self)
        self._dlx_live.setInterval(1000)
        self._dlx_live.timeout.connect(self._dlx_live_tick)
        self._dlx_live.start()
        # Переводчик DeepL: левое окно — язык источника и текст для перевода,
        # правое — язык перевода и результат. Как в обычных переводчиках.
        # DeepL translator: source language and text on the left, target
        # language and result on the right — like in regular translators.
        card, cl = _card()
        cl.addWidget(_title(i18n.t("Переводчик DeepL"), "sec"))
        cl.addWidget(_hint(
            i18n.t("Переведите фразу через локальный сервис DeepL. "
                   "Выберите языки, наберите текст слева и нажмите Перевести.")))

        row = QHBoxLayout()
        row.setSpacing(16)

        # Левая панель: язык источника + поле ввода
        # Left panel: source language + input field
        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(QLabel(i18n.t("Язык исходного текста")))
        self.cb_dlx_src = QComboBox()
        self.cb_dlx_src.setMinimumWidth(220)
        self.cb_dlx_src.setEditable(True)
        self.cb_dlx_src.lineEdit().setPlaceholderText(
            i18n.t("Выберите язык или наберите для поиска"))
        # поле редактируемое — можно набирать название языка для поиска.
        # строго не read-only, иначе клик по полю не откроет список.
        completer = self.cb_dlx_src.completer()
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.cb_dlx_src.addItem(i18n.t("Автоопределение языка"), "auto")
        for code, name in _dlx_languages():
            self.cb_dlx_src.addItem(i18n.t(name), code)
        self.cb_dlx_src.setCurrentIndex(0)
        self.cb_dlx_src.setToolTip(
            i18n.t("Язык, с которого переводить. «Автоопределение» — "
                   "сервис узнает язык сам."))
        # клик по полю редактирования открывает список, как в Google Translate
        # clicking the field opens the dropdown, like in Google Translate
        self.cb_dlx_src.lineEdit().installEventFilter(self)
        left.addWidget(self.cb_dlx_src)
        self.ed_dlx_src = QPlainTextEdit()
        self.ed_dlx_src.setPlaceholderText(
            i18n.t("Вставьте или наберите текст…"))
        self.ed_dlx_src.setMinimumHeight(210)
        self.ed_dlx_src.setObjectName("dlxSrc")
        left.addWidget(self.ed_dlx_src, 1)

        # Кнопка обмена языками между панелями
        swap_col = QVBoxLayout()
        swap_col.addStretch(1)
        self.b_dlx_swap = QPushButton("⇄")
        self.b_dlx_swap.setFont(QFont("Segoe UI Symbol", 16, QFont.Weight.Bold))
        self.b_dlx_swap.setFixedSize(40, 40)
        self.b_dlx_swap.setToolTip(i18n.t("Поменять языки местами"))
        self.b_dlx_swap.clicked.connect(self._dlx_swap_langs)
        swap_col.addWidget(self.b_dlx_swap)
        swap_col.addStretch(1)

        # Правая панель: язык перевода + поле результата
        # Right panel: target language + result field
        right = QVBoxLayout()
        right.setSpacing(8)
        right.addWidget(QLabel(i18n.t("Язык перевода")))
        self.cb_dlx_dst = QComboBox()
        self.cb_dlx_dst.setMinimumWidth(220)
        self.cb_dlx_dst.setEditable(True)
        self.cb_dlx_dst.lineEdit().setPlaceholderText(
            i18n.t("Выберите язык или наберите для поиска"))
        # поле редактируемое — можно набирать название языка для поиска.
        completer = self.cb_dlx_dst.completer()
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        for code, name in _dlx_languages():
            self.cb_dlx_dst.addItem(i18n.t(name), code)
        # целевой язык по умолчанию — русский, если есть
        # default target language — Russian when available
        idx = self.cb_dlx_dst.findData("RU")
        self.cb_dlx_dst.setCurrentIndex(idx if idx >= 0 else 0)
        self.cb_dlx_dst.setToolTip(
            i18n.t("Язык, на который переводить."))
        # клик по полю редактирования открывает список, как в Google Translate
        # clicking the field opens the dropdown, like in Google Translate
        self.cb_dlx_dst.lineEdit().installEventFilter(self)
        right.addWidget(self.cb_dlx_dst)
        self.ed_dlx_dst = QPlainTextEdit()
        self.ed_dlx_dst.setPlaceholderText(
            i18n.t("Перевод появится здесь"))
        self.ed_dlx_dst.setReadOnly(True)
        self.ed_dlx_dst.setMinimumHeight(210)
        self.ed_dlx_dst.setObjectName("dlxDst")
        right.addWidget(self.ed_dlx_dst, 1)

        row.addLayout(left, 1)
        row.addLayout(swap_col)
        row.addLayout(right, 1)
        cl.addLayout(row)

        # Кнопки под панелями
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.b_dlx_translate = QPushButton(i18n.t("Перевести"))
        self.b_dlx_translate.setObjectName("primary")
        self.b_dlx_translate.setMinimumWidth(140)
        self.b_dlx_translate.clicked.connect(self._dlx_translate)
        self.b_dlx_clear = QPushButton(i18n.t("Очистить"))
        self.b_dlx_clear.clicked.connect(self._dlx_clear)
        btn_row.addWidget(self.b_dlx_translate)
        btn_row.addWidget(self.b_dlx_clear)
        btn_row.addStretch(1)
        self.lb_dlx_trans_note = QLabel("")
        self.lb_dlx_trans_note.setProperty("no_i18n", True)
        self.lb_dlx_trans_note.setWordWrap(True)
        btn_row.addWidget(self.lb_dlx_trans_note, 1)
        cl.addLayout(btn_row)

        lay.addWidget(card)

        self._dlx_refresh()
        return page

    # ------------------------------------------------ работа с сервисом
    # working with the service
    def _dlx_state_text(self):
        """Текст состояния сервиса / the service state as text.

        Слова подобраны так, чтобы каждое состояние начиналось с ответа на
        главный вопрос «работает или нет»: «Работает», «Остановлен», «Ошибка».
        The first word answers the main question — does it run or not.
        """
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
        # точка перед словом: состояние понятно и тем, кто не различает цвета
        # a dot precedes the words, so the state reads without colour too
        text = "● " + words.get(state, str(state))
        version = status.get("version")
        if version:
            text += i18n.tf(" · версия %s", version)
        note = status.get("note")
        if note:
            text += i18n.tf(" · %s", note)
        return text

    def _dlx_set_state(self, state, text):
        """Красит плашку состояния и надпись у тумблера / paint badge and caption.

        Свойство ``state`` переключает правила стиля, а ``unpolish``/``polish``
        заставляют Qt перечитать их: без этого цвет остался бы прежним.
        The ``state`` property picks the style rules, and unpolish/polish make Qt
        read them again: otherwise the old colour stays.
        """
        for widget in (self.lb_dlx_state, self.b_dlx_start):
            if widget.property("state") == state:
                continue
            widget.setProperty("state", state)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
        self.lb_dlx_state.setText(text)

    def _dlx_apply(self, status):
        """Тумблер, надпись и плашка по состоянию сервиса.

        The switch, its caption and the badge, taken from the service state.

        Тумблер — единственное место, где сервис включают и выключают: он стоит
        в правом положении, пока сервис работает, и в левом, когда нет. Надпись
        рядом называет то же состояние словом и меняет цвет вместе с ним.
        The switch is the only place the service is turned on and off: it sits on
        the right while the service runs and on the left when it does not. The
        caption names the same state in words and changes colour with it.
        """
        state = status.get("state") if status else None
        # Решает состояние, а не живость процесса: у своего сервиса по адресу
        # процесс не наш, и «жив» он даже когда его никто не запускал.
        # The state decides, not the process: a service of your own is not our
        # child process and counts as alive even when nobody started it.
        running = bool(status) and (state in ("ready", "upstream", "starting")
                                    or (state not in ("off", "missing", "error")
                                        and status.get("running")))
        if state == "upstream":
            caption = i18n.t("Запущено")
            tip = i18n.t("Сервис работает, но DeepL отказывает (503) — чаще всего "
                         "из-за региональной блокировки. Выключите тумблер, чтобы "
                         "остановить.")
        elif state == "starting":
            caption = i18n.t("Запускается…")
            tip = i18n.t("Сервис поднимается; тумблер остановит его.")
        elif running:
            caption = i18n.t("Запущено")
            tip = i18n.t("Сервис работает. Выключите тумблер, чтобы остановить.")
        else:
            caption = i18n.t("Остановлено")
            tip = i18n.t("Поднять локальный сервис. Пока он не запущен, DeepL "
                         "не используется.")
        switch = self.sw_dlx
        # первый показ — без анимации: окно ещё не на экране, и бегунок не
        # должен проезжать вхолостую при каждом открытии настроек
        # the first paint is not animated: the window is not on screen yet, and
        # the knob should not slide on its own every time the settings open
        switch.set_on(running, animate=self._dlx_was_applied)
        self._dlx_was_applied = True
        enabled = self.dlx is not None and not self._dlx_page_dimmed()
        switch.setEnabled(enabled and not self._dlx_busy_now)
        switch.setToolTip(tip)
        switch.setAccessibleDescription(caption)
        self.b_dlx_start.setText(caption)
        self.b_dlx_start.setToolTip(tip)
        self.b_dlx_start.setEnabled(enabled and not self._dlx_busy_now)
        # подсказка у плашки: что происходит, пока сервис не запущен
        # the badge tooltip explains what a stopped service means
        self.lb_dlx_state.setToolTip(
            "" if running else i18n.t(
                "Пока сервис не запущен, перевод идёт через стандартные сервисы, "
                "а DeepL не используется."))
        self._dlx_set_state(state or "off", self._dlx_state_text())

    def _dlx_page_dimmed(self):
        """Погашен ли раздел / is the page dimmed right now?

        На погашенном разделе тумблер обязан остаться неактивным: иначе
        обновление состояния тихо вернуло бы ему нажимаемость.
        On a dimmed page the switch must stay inactive, or a state refresh would
        quietly make it clickable again.
        """
        page = getattr(self, "page_dlx", None)
        return bool(page is not None and page.property("moduleOff"))

    def _dlx_refresh(self):
        """Обновляет подписи страницы по текущему состоянию / refresh the page."""
        if not hasattr(self, "lb_dlx_state"):
            return
        status = self.dlx.status() if self.dlx is not None else None
        self._dlx_live_key = self._dlx_status_key(status)
        self._dlx_apply(status)
        if self.dlx is not None:
            token = self.dlx.token
            self.ed_dlx_token.setText(token[:8] + "…" if token else "")
            self.lb_dlx_path.setText(i18n.tf("Файлы сервиса: %s", str(self.dlx.dir)))
            self.b_dlx_install.setText(i18n.t("Обновить") if self.dlx.installed()
                                       else i18n.t("Установить"))
        for button in (self.b_dlx_install, self.b_dlx_remove, self.b_dlx_check,
                       self.b_dlx_token):
            button.setEnabled(self.dlx is not None)

    def _dlx_swap_langs(self):
        """Поменять исходный и целевой языки местами / swap source and target."""
        src_idx = self.cb_dlx_src.currentIndex()
        dst_idx = self.cb_dlx_dst.currentIndex()
        self.cb_dlx_src.setCurrentIndex(dst_idx)
        self.cb_dlx_dst.setCurrentIndex(src_idx)

    def _dlx_clear(self):
        """Очистить оба поля / clear both fields."""
        self.ed_dlx_src.clear()
        self.ed_dlx_dst.clear()
        self.lb_dlx_trans_note.setText("")

    def eventFilter(self, obj, event):
        """Открыть выпадающий список комбо при клике по полю ввода.

        Open the combo popup when the user clicks the editable field,
        not only the arrow button — like in Google Translate.
        """
        if event.type() == QEvent.MouseButtonPress:
            if obj is self.cb_dlx_src.lineEdit():
                self.cb_dlx_src.showPopup()
                return True
            if obj is self.cb_dlx_dst.lineEdit():
                self.cb_dlx_dst.showPopup()
                return True
        return super().eventFilter(obj, event)

    def _dlx_translate(self):
        """Перевести текст через сервис DeepL / translate via DeepL service."""
        text = self.ed_dlx_src.toPlainText().strip()
        if not text:
            self.lb_dlx_trans_note.setText(i18n.t("Вставьте или наберите текст…"))
            return
        if len(text) > 1500:
            self.lb_dlx_trans_note.setStyleSheet("color:#ff8f8f;font-size:11px;")
            self.lb_dlx_trans_note.setText(
                i18n.t("Слишком длинный текст (макс. 1500 символов)"))
            return
        # currentData() на редактируемом комбо может вернуть None, если
        # введённый текст не совпадает ни с одним пунктом — берём «авто» в этом случае.
        source = self.cb_dlx_src.currentData() or "auto"
        target = self.cb_dlx_dst.currentData() or "RU"
        if self.dlx is None:
            self.lb_dlx_trans_note.setText(i18n.t("Сервис не запущен"))
            return
        status = self.dlx.status()
        state = status.get("state") if status else None
        running = (state in ("ready", "upstream", "starting")
                   or bool(status.get("running"))) if status else False
        if not running:
            self.lb_dlx_trans_note.setText(i18n.t("Запустите сервис DeepL выше"))
            return

        self.b_dlx_translate.setEnabled(False)
        self.lb_dlx_trans_note.setStyleSheet("color:#a9c4ff;font-size:11px;")
        self.lb_dlx_trans_note.setText(i18n.t("Перевожу…"))

        def run():
            try:
                result = self.dlx.translate(text, source=source, target=target)
                self._dlx_trans_result = result
                self._dlx_trans_error = None
            except Exception as error:  # noqa: BLE001 — покажем игроку
                log.exception("DLX: перевод не удался")
                self._dlx_trans_result = None
                self._dlx_trans_error = str(error) or type(error).__name__
            finally:
                # кнопку всегда возвращаем, даже если перевода не вышло
                # the button is always re-enabled, even if translation failed
                QTimer.singleShot(0, self._dlx_translate_done)

        threading.Thread(target=run, daemon=True).start()

    def _dlx_translate_done(self):
        """Результат перевода на главном потоке / result on the main thread."""
        self.b_dlx_translate.setEnabled(True)
        if getattr(self, "_dlx_trans_error", None):
            self.lb_dlx_trans_note.setStyleSheet("color:#ff8f8f;font-size:11px;")
            self.lb_dlx_trans_note.setText(
                i18n.tf("Перевод не удался: %s", self._dlx_trans_error))
        else:
            result = getattr(self, "_dlx_trans_result", "")
            self.ed_dlx_dst.setPlainText(result)
            self.lb_dlx_trans_note.setStyleSheet("color:#66d18b;font-size:11px;")
            words = len(result.split())
            self.lb_dlx_trans_note.setText(
                i18n.tf("Вставлено %d слов", words))

    @staticmethod
    def _dlx_status_key(status):
        """Короткая подпись состояния для сравнения / a short state key."""
        if not status:
            return None
        return (status.get("state"), status.get("port"), status.get("version"),
                status.get("installed"), status.get("running"))

    def _dlx_live_tick(self):
        """Раз в секунду: не изменилось ли состояние сервиса / poll the state.

        Пока идёт установка или проверка, опрос молчит: прогресс пишется в ту же
        плашку, и перерисовка затёрла бы его.
        The poll stays quiet while an action runs: the progress text goes into
        the same badge, and a repaint would wipe it.
        """
        if self.dlx is None or getattr(self, "_dlx_busy_now", False):
            return
        if self._dlx_status_key(self.dlx.status()) == getattr(self, "_dlx_live_key", None):
            return
        self._dlx_refresh()

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
        self._dlx_busy_now = bool(busy)
        for button in (self.b_dlx_check, self.b_dlx_install, self.b_dlx_remove,
                       self.b_dlx_token, self.b_dlx_proxy_check):
            button.setEnabled(not busy)
        # тумблер на время работы не двигается: пуск и остановка идут в фоне,
        # и второе нажатие поверх первого только спутало бы состояние
        # the switch does not move while an action runs: start and stop go to a
        # thread, and a second press would only muddle the state
        free = not busy and self.dlx is not None and not self._dlx_page_dimmed()
        self.sw_dlx.setEnabled(free)
        self.b_dlx_start.setEnabled(free)
        if not busy and not text:
            # работа кончилась: в плашку возвращается настоящее состояние
            # the work is over: the badge returns to the real state
            self._dlx_refresh()
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

    def _dlx_toggle(self):
        """Кнопка «Запустить / Запущено»: пуск или остановка / start or stop.

        Одна кнопка отвечает за оба состояния, поэтому нажатие на «Запущено»
        останавливает сервис — как выключатель, а не как надпись. Отдельная
        «Остановить» рядом остаётся для тех, кто ищет именно её, и видна
        только у работающего сервиса.
        One button covers both states, so pressing "Running" stops the service —
        a switch rather than a caption. The separate "Stop" stays for those who
        look for it and is visible only while the service runs.
        """
        if not self._dlx_guard():
            return
        status = self.dlx.status()
        state = status.get("state")
        running = state in ("ready", "upstream", "starting") or bool(status.get("running"))
        if running:
            self.dlx.stop()
            self._dlx_refresh()
        else:
            self._dlx_start()

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

        # Таблица — первая на странице: это то, ради чего сюда заходят, и ей
        # нужна высота. Настройки модуля и проверки стоят ниже и прокручиваются.
        # The table comes first: it is what the page is opened for, and it needs
        # the height. The module settings and the checks sit below and scroll.
        lay.addWidget(self._anim_table_block(), 1)

        card, cl = _card()
        self.chk_anims = QCheckBox("Включить модуль «Анимации»")
        self.chk_anims.setChecked(bool(self.cfg.get("anims_enabled", False)))
        self.chk_anims.toggled.connect(self._anims_toggled)
        self.chk_anims.toggled.connect(lambda on: self._mirror_own_flag("anims", on))
        cl.addWidget(self.chk_anims)
        cl.addWidget(_hint(
            "Ключевое слово в вашем сообщении запускает анимацию: в чат игры уходит "
            "/anim «название», а через заданное время она останавливается — командой "
            "/sa, нажатием клавиши или обоими способами, как выбрано ниже. При "
            "зацикливании остановки нет: по истечении того же времени анимация "
            "просто запускается снова, пока не нажать клавишу остановки. "
            "Длительность 0 мс означает «не останавливать вовсе». Работает только "
            "вместе с модулем «Отправка в игру»."))

        # Режим «В машине»: главный выключатель тишины. Стоит рядом с включением
        # модуля, потому что это такое же «работать или нет», только на время
        # поездки. Дублируется пунктом в меню трея — включать его в поездке
        # удобнее оттуда.
        # The "In a vehicle" mode: the main silence switch. It sits next to the
        # module switch, because it is the same "run or not", only for the length
        # of a ride. The tray menu item does the same, and is handier on the move.
        self.chk_anim_vehicle = QCheckBox(
            "В машине — не играть анимации (ни /anim, ни /sa)")
        self.chk_anim_vehicle.setChecked(bool(self.cfg.get("anim_in_vehicle", False)))
        self.chk_anim_vehicle.setToolTip(
            "В транспорте анимации ломают позу, а /sa и нажатие клавиши "
            "выбрасывают из машины. Пока галочка стоит, в игру не уходит ни одна "
            "команда анимаций: очередь снимается, зацикливание прекращается, "
            "уходит один /sa — и дальше тишина. Включается и из меню трея.")
        self.chk_anim_vehicle.toggled.connect(self._anim_vehicle_changed)
        cl.addWidget(self.chk_anim_vehicle)
        self.lb_anim_vehicle = _hint("")
        self.lb_anim_vehicle.setProperty("no_i18n", True)
        self.lb_anim_vehicle.setWordWrap(True)
        cl.addWidget(self.lb_anim_vehicle)

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

        # Подсказки в оверлее: список ключевых слов под полем ввода и
        # пролистывание по Tab. Выключить можно, если список мешает.
        # Hints in the overlay: the keyword list under the input and Tab walking.
        # They can be switched off when the list gets in the way.
        self.chk_anim_hints = QCheckBox(
            "Подсказывать ключевые слова в оверлее (Tab — пролистать)")
        self.chk_anim_hints.setChecked(bool(self.cfg.get("anim_hints", True)))
        self.chk_anim_hints.setToolTip(
            "Пока вы печатаете, под полем ввода появляются ключевые слова "
            "правил, начинающиеся с набранного: Tab листает их, Enter "
            "подставляет выбранное, Esc убирает список. Подсказка заменяет "
            "только последнее набранное слово, остальной текст не трогает.")
        self.chk_anim_hints.toggled.connect(self._anims_changed)
        cl.addWidget(self.chk_anim_hints)

        # высота строк таблицы: длинные ключевые фразы в низких строках не
        # читаются, а в высоких таблица занимает весь экран
        # the row height: long keyword phrases do not read in short rows, and in
        # tall ones the table fills the screen
        row_row = QHBoxLayout()
        row_row.addWidget(_title("Высота строк таблицы, пкс", "sec"))
        self.sp_anim_row = QSpinBox()
        self.sp_anim_row.setRange(24, 96)
        self.sp_anim_row.setSingleStep(2)
        self.sp_anim_row.setValue(self._anim_base_row())
        self.sp_anim_row.setMaximumWidth(120)
        self.sp_anim_row.setToolTip(
            "Строки правил можно сделать выше: длинные фразы и подписи режимов "
            "читаются лучше. Двойной щелчок по шапке таблицы разворачивает её "
            "на весь экран — там строки ещё выше.")
        self.sp_anim_row.valueChanged.connect(self._anim_row_changed)
        row_row.addWidget(self.sp_anim_row)
        row_row.addStretch(1)
        cl.addLayout(row_row)

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
            "ПКМ по строке — «Варианты и свойства…»: там задаются варианты, если "
            "одному ключу подходят несколько анимаций. Например, ключ «оперся "
            "руками» с вариантами anim_counterleanbar и anim_leanrail: в игре "
            "откроется оверлей выбора с названием и описанием каждого. Один "
            "вариант — обычное правило, оно играет сразу."))
        self._fill_anims()
        self._update_anims_ui()
        return page

    def _anim_table_block(self):
        """Таблица правил: поиск, крупные строки, разворот на весь экран.

        The rules table: a search box, taller rows and a full-screen expander.

        Таблица — единственный источник правил, пока окно открыто, поэтому
        переезд на весь экран её не пересобирает: та же таблица просто
        переносится в отдельное окно и обратно, и введённое не теряется.
        The table is the only source of rules while the window is open, so the
        full-screen move does not rebuild it: the same table is re-parented into
        a separate window and back, and nothing typed is lost.
        """
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        # место, куда таблица возвращается из большого окна
        # the slot the table returns to from the big window
        self._anim_table_slot = lay

        find_row = QHBoxLayout()
        self.ed_anim_find = QLineEdit()
        self.ed_anim_find.setPlaceholderText(
            i18n.t("Поиск по словам, /anim и описаниям вариантов"))
        self.ed_anim_find.setClearButtonEnabled(True)
        self.ed_anim_find.textChanged.connect(self._anim_find_changed)
        self.ed_anim_find.setToolTip(i18n.t(
            "Ищет по ключевым словам, по названию /anim и по описаниям "
            "вариантов. Строки, которые не подходят, прячутся, а правила "
            "остаются на своих местах."))
        find_row.addWidget(self.ed_anim_find, 1)
        self.bt_anim_expand = QPushButton(i18n.t("На весь экран"))
        self.bt_anim_expand.setCheckable(True)
        self.bt_anim_expand.setToolTip(i18n.t(
            "Развернуть таблицу правил на весь экран — удобнее править длинные "
            "ключевые слова. То же самое делает двойной щелчок по шапке таблицы."))
        self.bt_anim_expand.toggled.connect(self._anim_expand_toggled)
        find_row.addWidget(self.bt_anim_expand)
        lay.addLayout(find_row)

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
        # строки выше обычных: в правиле живут длинные фразы, а подписи режима
        # и форм срезались, когда высота была стандартной
        # taller rows than usual: a rule holds long phrases, and the mode and
        # forms captions were cut off at the standard height
        self._anim_row_height()
        self.tbl_anims.itemChanged.connect(self._anims_edited)
        self.tbl_anims.itemSelectionChanged.connect(self._update_anims_ui)
        # двойной щелчок по шапке разворачивает таблицу: привычный жест, и
        # кнопка говорит о нём же
        # a double click on the header expands the table: a familiar gesture, and
        # the button says so as well
        head.sectionDoubleClicked.connect(lambda _column: self._anim_expand(True))
        # ПКМ по правилу — свойства анимации: варианты, названия и описания.
        # Это же меню умеет добавить второй вариант к обычному правилу.
        # right-click a rule opens its properties: variants, titles and
        # descriptions. The same menu adds a second variant to a plain rule.
        self.tbl_anims.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tbl_anims.customContextMenuRequested.connect(self._anims_menu)
        # ниже этой высоты таблица бесполезна: видно две строки
        # below this height the table is useless: only two rows are visible
        self.tbl_anims.setMinimumHeight(260)
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
        return box

    def _anim_row_height(self, height=None):
        """Высота строки таблицы правил: крупнее обычной, с учётом масштаба.

        The rules table row height: taller than the default, scaled with the UI.
        """
        if not hasattr(self, "tbl_anims"):
            return
        try:
            base = int(height if height is not None
                       else self.cfg.get("anim_row_height", 34) or 34)
        except (TypeError, ValueError):
            base = 34
        base = max(24, min(96, base))
        self.tbl_anims.verticalHeader().setDefaultSectionSize(
            int(round(base * self._ui_scale())))

    def _anim_expand_toggled(self, on):
        """Кнопка «На весь экран» / the full-screen button."""
        self._anim_expand(on)

    def _anim_expand(self, on: bool) -> None:
        """Развернуть таблицу на весь экран или вернуть на страницу.

        Expand the table to the whole screen, or put it back on the page.

        Таблица не пересобирается: она переезжает в отдельное окно вместе с
        прокруткой, выделением и фильтром, поэтому ничего введённого не теряется.
        The table is not rebuilt: it moves into a separate window together with
        its scroll position, selection and filter, so nothing typed is lost.
        """
        on = bool(on)
        if not hasattr(self, "tbl_anims"):
            return
        if on == bool(getattr(self, "_anim_expanded", False)):
            return
        self._anim_expanded = on
        if on:
            win = QDialog(self)
            win.setWindowTitle(i18n.t("Анимации — правила"))
            box = QVBoxLayout(win)
            box.setContentsMargins(12, 12, 12, 12)
            box.setSpacing(8)
            head = QHBoxLayout()
            head.addWidget(_title(i18n.t("Правила анимаций"), "sec"))
            head.addStretch(1)
            b_close = QPushButton(i18n.t("Вернуть на страницу"))
            b_close.clicked.connect(lambda: self._anim_expand(False))
            head.addWidget(b_close)
            box.addLayout(head)
            box.addWidget(self.tbl_anims, 1)
            self._anim_expand_win = win
            win.finished.connect(lambda _result: self._anim_expand(False))
            _fit_dialog(win)
            win.showMaximized()
            # на большом экране строки ещё выше: читать проще
            # on a large screen the rows are taller still: easier to read
            self._anim_row_height(max(38, self._anim_base_row() + 8))
        else:
            win = getattr(self, "_anim_expand_win", None)
            self._anim_expand_win = None
            if win is not None:
                # таблицу возвращаем на страницу ДО закрытия окна: иначе Qt
                # удалит её вместе с окном
                # the table goes back to the page BEFORE the window closes:
                # otherwise Qt deletes it together with the window
                self._anim_table_slot.addWidget(self.tbl_anims, 1)
                win.blockSignals(True)
                win.close()
                win.deleteLater()
            self._anim_row_height()
            if getattr(self, "bt_anim_expand", None) is not None:
                self.bt_anim_expand.blockSignals(True)
                self.bt_anim_expand.setChecked(False)
                self.bt_anim_expand.blockSignals(False)

    def _anim_base_row(self) -> int:
        """Высота строки из настроек, без масштаба / the configured row height."""
        try:
            return max(24, min(96, int(self.cfg.get("anim_row_height", 34) or 34)))
        except (TypeError, ValueError):
            return 34

    def _anim_find_changed(self, text):
        """Поиск по таблице: слова, /anim и описания вариантов.

        The table search: the keywords, the /anim name and variant descriptions.

        Прячется только строка таблицы — правило остаётся на своём месте,
        поэтому перетаскивание и «Выше/Ниже» работают как обычно.
        Only the row is hidden — the rule stays where it was, so dragging and
        "Up/Down" keep working as usual.
        """
        needle = " ".join((text or "").casefold().split())
        shown = 0
        total = self.tbl_anims.rowCount()
        for row in range(total):
            match = True
            if needle:
                parts: list[str] = []
                for column in (1, 2):
                    item = self.tbl_anims.item(row, column)
                    parts.append(item.text() if item is not None else "")
                name_item = self.tbl_anims.item(row, 2)
                if name_item is not None:
                    raw = name_item.data(Qt.ItemDataRole.UserRole + 1)
                    if isinstance(raw, list):
                        for entry in raw:
                            if isinstance(entry, dict):
                                parts.append(str(entry.get("title") or ""))
                                parts.append(str(entry.get("description") or ""))
                hay = " ".join(" ".join(parts).casefold().split())
                match = needle in hay
            self.tbl_anims.setRowHidden(row, not match)
            shown += int(match)
        self._anim_find_note(shown, total, bool(needle))

    def _anim_find_note(self, shown, total, filtering):
        """Строка над таблицей: сколько правил видно.

        The line above the table: how many rules are visible.
        """
        if not hasattr(self, "lb_anims_count"):
            return
        if not filtering:
            self.lb_anims_count.setText(i18n.tf("Правил: %d", total))
            return
        text = i18n.tf("Найдено: %d из %d", shown, total)
        if not shown:
            text += " — " + i18n.t("ничего не подходит, очистите поиск")
        self.lb_anims_count.setText(text)

    # ------------------------------------------------ состояние и проверка
    # state and checks
    def _anim_combo_hint(self, combo):
        """Подсказка поля «Режим»: полное объяснение выбранного режима.

        The tooltip of the "Mode" field: a full explanation of the chosen mode.
        """
        mode = combo.currentData()
        if mode is None:
            return
        combo.setToolTip(i18n.t(anims.describe_mode_hint(int(mode), False)))

    def _anim_forms_hint(self, combo):
        """Подсказка поля «Формы»: что именно сравнивается со словом.

        The tooltip of the "Forms" field: what exactly is compared with the word.
        """
        forms = combo.currentData()
        if forms is None:
            return
        combo.setToolTip(i18n.t(morph.describe_forms_hint(int(forms), False)))

    def _anim_say(self, text, seconds=8.0):
        """Заметка под кнопками проверки: живёт несколько секунд.

        The note under the test buttons: it lives for a few seconds.
        """
        self._anim_note = (text, time.monotonic() + seconds)
        self.lb_anim_live.setText(text)

    def _anim_row_changed(self, value):
        """Ползунок высоты строк: сразу перерисовать таблицу.

        The row height spinner: the table is redrawn at once.
        """
        self.cfg["anim_row_height"] = int(value)
        self._anim_row_height(int(value))
        self._anims_changed()

    def _anim_vehicle_changed(self, on):
        """Галочка «В машине»: сразу применить режим / apply the mode at once.

        Режим — именно та настройка, которую нельзя отложить до «Сохранить»:
        игрок ставит галочку, уже сидя в машине, и анимации должны замолчать
        немедленно, а не после закрытия окна.
        The mode is the one setting that cannot wait for "Save": the player ticks
        it while already sitting in a vehicle, and the animations must fall silent
        at once, not after the window closes.
        """
        on = bool(on)
        api = getattr(self, "anims_api", None)
        if api is not None:
            try:
                api["set_vehicle"](on)
            except Exception:
                log.exception("Не удалось переключить режим «В машине»")
        self._anim_vehicle_note(on)

    def _anim_vehicle_note(self, on=None):
        """Подпись под галочкой «В машине» / the caption under the vehicle switch."""
        if not hasattr(self, "lb_anim_vehicle"):
            return
        if on is None:
            on = bool(getattr(self, "chk_anim_vehicle", None)
                      and self.chk_anim_vehicle.isChecked())
        if not on:
            self.lb_anim_vehicle.setText("")
            return
        text = i18n.t(
            "Режим включён: ни /anim, ни /sa в игру не уходят. Действует до "
            "выключения галочки, в том числе после перезапуска программы.")
        if getattr(self, "anims_api", None) is None:
            text += " " + i18n.t("Применится после сохранения.")
        self.lb_anim_vehicle.setText(text)

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
        if state.get("vehicle"):
            # режим «В машине» важнее всего остального: игрок должен сразу
            # видеть, почему сейчас ничего не играет
            # the "In a vehicle" mode outranks the rest: the player must see at
            # once why nothing plays right now
            parts.append(i18n.t("режим «В машине»: команды не отправляются"))
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
        """Остановить текущую зацикленную анимацию из настроек.

        Stop the currently looping animation from the settings.
        """
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
        actions. Пункт «Варианты и свойства…» — единственный вход в варианты,
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
        act_props = menu.addAction(i18n.t("Варианты и свойства…"))
        act_variant = None
        act_merge = None
        act_merge_all = None
        rules = self._collect_anims()
        current = rules[row] if 0 <= row < len(rules) else None
        if current is not None:
            act_variant = menu.addAction(i18n.t("Добавить ещё один вариант…"))
            # «Объединить правило с…» — для двух правил с одним смыслом и разными
            # ключевыми словами: одно слово на анимацию, а не пять правил-двойников
            # "Merge the rule with..." is for two rules with one meaning and
            # different keywords: one word per animation, not five twin rules
            act_merge = menu.addAction(i18n.t("Объединить правило с…"))
            act_merge_all = menu.addMenu(i18n.t("Объединить сразу с несколькими…"))
            for other in range(len(rules)):
                if other == row:
                    continue
                name = rules[other].keywords.strip().split(",")[0].strip() or "?"
                action = act_merge_all.addAction(i18n.tf("Взять «%s»", name))
                action.setData(other)
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
        elif act_merge is not None and chosen is act_merge:
            self._merge_anim(row)
        elif act_merge_all is not None and chosen is not None \
                and isinstance(chosen.data(), int):
            self._merge_anim(row, others=[int(chosen.data())])
        elif chosen is act_dup:
            self._duplicate_anim(row)
        elif chosen is act_del:
            self._del_anim()

    def _merge_anim(self, row, others=None):
        self._hist_shadow = self._hist_state()
        """«Объединить правило с…»: два правила становятся одним.

        "Merge the rule with...": two rules become one.

        Зачем / why
        -----------
        У одной анимации бывает несколько ключевых слов, и игрок заводит по
        правилу на каждое. Потом выясняется, что задержку надо менять в трёх
        местах, а варианты анимации в двух из них забыты. Объединение сводит
        это в одно правило: ключевые слова складываются без повторов, варианты
        тоже, второе правило исчезает.

        One animation may have several keywords, and the player creates one rule
        per keyword. Then the delay has to be changed in three places, and the
        variants are forgotten in two of them. A merge brings this into one rule:
        keywords and variants are combined without duplicates and the second rule
        disappears.

        Задержка, повтор, словоформы и режим переносятся только при совпадении:
        иначе поле остаётся пустым, и игрок обязан задать его сам — угадывать,
        какое из двух значений «правильное», программа не станет.
        The delay, loop, word forms and mode carry over only when both rules
        agree; otherwise the field stays empty and the player must fill it in.
        """
        rules = self._collect_anims()
        if not 0 <= row < len(rules):
            return
        if others is None:
            others = self._ask_merge_target(row, rules)
        others = [i for i in (others or []) if 0 <= i < len(rules) and i != row]
        if not others:
            return
        merged = rules[row]
        empty = []
        for other in others:
            merged, empty = anims.merge_rules(merged, rules[other])
        # второе (и третье) правило больше не нужно: его слова уже в объединённом
        # the second (and third) rule is no longer needed: its keywords moved over
        for other in sorted(others, reverse=True):
            rules.pop(other)
        target = row - sum(1 for other in others if other < row)
        rules[target] = merged
        self._fill_anims(rules)
        self.tbl_anims.selectRow(target)
        self._anims_changed()
        log.info("Анимации: правило «%s» объединено с %d другим(и)",
                 merged.keywords[:40], len(others))
        if empty:
            self._anim_say(i18n.tf(
                "Правила объединены. Осталось задать: %s — заполните в «Варианты "
                "и свойства…» или в таблице.", self._empty_fields_text(empty)))
        else:
            self._anim_say(i18n.t("Правила объединены: задержка, повтор и режим "
                                  "совпадали и перенесены."))

    @staticmethod
    def _empty_fields_text(fields):
        """Названия незаполненных полей по-человечески / human names of empty fields."""
        names = {"duration_ms": i18n.t("задержка"), "loop": i18n.t("повтор"),
                 "forms": i18n.t("словоформы"), "mode": i18n.t("режим")}
        return ", ".join(names.get(f, f) for f in fields)

    def _ask_merge_target(self, row, rules):
        """Спросить, с каким правилом объединять / ask which rule to merge with."""
        menu = QMenu(self)
        for other, rule in enumerate(rules):
            if other == row:
                continue
            name = rule.keywords.strip().split(",")[0].strip() or "?"
            action = menu.addAction(i18n.tf("С «%s»", name))
            action.setData(other)
        chosen = menu.exec(self.tbl_anims.viewport().mapToGlobal(
            self.tbl_anims.rect().center()))
        if chosen is None:
            return []
        return [int(chosen.data())]

    def _anim_props(self, row, force_variants=False):
        self._hist_shadow = self._hist_state()
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
        self._hist_shadow = self._hist_state()
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
        for mode, title in zip(anims.MODES, titles, strict=True):
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
        for forms, title in zip(morph.FORMS, forms_titles, strict=True):
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
            if choice.group:
                line += "  [" + choice.group + "]"
            lines.append(line)
        return "\n".join(lines)

    def _anims_combo_changed(self, *_):
        """Сменили режим чтения в строке / the read mode of a row changed."""
        self._anims_changed()

    def _anims_edited(self, item=None):
        """Правка ячейки: проверяем длительность и обновляем подсказки.

        A cell was edited: check the duration and refresh the hints.
        """
        row = item.row() if item is not None else -1
        col = item.column() if item is not None else -1
        if item is not None and item.column() == 5:
            text = (item.text() or "").strip()
            if text and not text.lstrip("-").isdigit():
                # в поле длительности ждём число; буквы не чиним молча, а
                # подсвечиваем строку и говорим об этом подсказкой
                # the duration field wants a number; letters are not fixed
                # silently, the row is highlighted and the hint explains why
                self._anims_changed()
                self._mark(f"anims:{row}:{col}")
                return
        self._anims_changed()
        self._mark(f"anims:{row}:{col}")

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

            def text(column, row=row):
                """Текст ячейки строки; ``row`` связан по умолчанию.

                The cell text of the row; ``row`` is bound by default, so the
                closure does not read the loop variable after it moved on.
                """
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
        note = i18n.tf("Правил: %d, готовы к работе: %d, с зацикливанием: %d",
                       total, active, loops)
        # поиск не должен теряться за счётчиком: сколько правил он оставил
        # the search must not disappear behind the counter: how many it left
        find = getattr(self, "ed_anim_find", None)
        if find is not None and find.text().strip():
            shown = sum(1 for row in range(total)
                        if not self.tbl_anims.isRowHidden(row))
            note = i18n.tf("Найдено: %d из %d", shown, total) + " · " + note
        self.lb_anims_count.setText(note)
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
        """Галочка модуля: сразу видно, будет ли что-то работать.

        A module checkbox: it is at once clear whether anything will work.
        """
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
        """Новое правило с разумными значениями по умолчанию.

        A new rule with sensible defaults.
        """
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
        self._hist_shadow = self._hist_state()
        """Удаляет выбранные правила / remove the selected rules."""
        rows = sorted({index.row() for index in
                       self.tbl_anims.selectionModel().selectedRows()}, reverse=True)
        if not rows:
            return
        for row in rows:
            self.tbl_anims.removeRow(row)
        self._anims_changed()

    def _move_anim(self, delta):
        """Правило выше или ниже: порядок = порядок срабатывания.

        Move a rule up or down: the order is the order of firing.
        """
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
        # строка -> модуль: по нему переключатель знает, какой флажок обновить
        # row -> module: the switch uses it to update the flag it mirrors
        self._module_by_key = {}
        self._module_switching = False
        for module in modules.MODULES:
            row = QWidget()
            rl = QVBoxLayout(row)
            rl.setContentsMargins(0, 6, 0, 6)
            rl.setSpacing(2)
            title = module.title_en if i18n.is_en() else module.title_ru
            box = QCheckBox(title)
            # Флажок здесь рабочий у ВСЕХ модулей, даже у тех, что включаются на
            # своей странице: два разных переключателя одного и того же флага —
            # это гарантированный рассинхрон. Страница модуля остаётся главной,
            # а этот флажок её повторяет и сам же её обновляет.
            # The checkbox works for EVERY module here, including the ones switched
            # on their own page: two independent switches for one flag are a
            # guaranteed desync. The module page stays the primary one, and this
            # checkbox mirrors it and updates it in turn.
            box.setChecked(modules.is_enabled(self.cfg, module.key))
            self.chk_modules[module.config_key] = box
            self._module_by_key[module.key] = (box, module)
            box.toggled.connect(lambda checked, key=module.key: self._module_toggled(key, checked))
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

    def _add_module_banner(self, page, attr):
        """Подсказка сверху раздела: модуль выключен, настройки недоступны.

        A hint on top of a section: the module is off, its settings are inactive.

        Баннер создаётся сразу и скрыт, пока модуль включён. Скрывать его через
        ``setVisible``, а не удалять, важно: раздел перерисовывается при каждом
        переключении, и пересоздавать виджет на каждое движение флажка незачем.
        The banner is created at once and hidden while the module is on. Hiding it
        with ``setVisible`` instead of deleting matters: the section is refreshed on
        every toggle, and recreating a widget per flag change is pointless.
        """
        layout = page.layout()
        if layout is None:
            return
        banner = QLabel("")
        banner.setObjectName("moduleOff")
        # своя рамка и свои цвета: на погашенном разделе подсказка обязана
        # остаться читаемой, поэтому она не участвует в общем затухании
        # its own frame and colours: on a dimmed section the hint has to stay
        # readable, so it takes no part in the shared fade
        banner.setWordWrap(True)
        banner.setProperty("no_i18n", True)
        banner.setStyleSheet(
            "color:#ffcf80; background:#2a2418; border:1px solid #5a4a28;"
            "border-radius:8px; padding:10px 12px;")
        banner.setVisible(False)
        layout.insertWidget(0, banner)

    def _module_toggled(self, key, checked):
        """Переключатель модуля на странице «Модули».

        The module switch on the Modules page.

        Модуль с выключенным родителем включить нельзя: предлагаем включить
        родителя и честно говорим, что без него модуль не работает.
        A module whose parent is off cannot be switched on: we offer to switch the
        parent on and say plainly that it does not work without it.
        """
        if self._module_switching:
            return
        module = modules.get(key)
        if module is None:
            return
        if checked:
            missing = modules.blockers(self._cfg_now(), key)
            if missing:
                names = ", ".join((modules.get(dep).title_en if i18n.is_en()
                                   else modules.get(dep).title_ru)
                                  for dep in missing if modules.get(dep))
                answer = QMessageBox.question(
                    self, i18n.t("Нужен ещё один модуль"),
                    i18n.tf("«%s» не работает без модуля: %s.\n\nВключить его?",
                            module.title_en if i18n.is_en() else module.title_ru,
                            names),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes)
                if answer != QMessageBox.StandardButton.Yes:
                    # Возвращаем флажок на место. Сигналы НЕ блокируем: именно
                    # повторный `toggled(False)` откатывает галочку, которую
                    # уже поставил клик. Флаг `_module_switching` внутри
                    # `_set_module_flag` не даёт уйти в рекурсию.
                    # Put the checkbox back. Signals are NOT blocked: the repeated
                    # `toggled(False)` is what rolls back the tick the click has
                    # already made. `_set_module_flag` guards against recursion.
                    self._set_module_flag(key, False)
                    return
                for dep in missing:
                    self._set_module_flag(dep, True)
        self._set_module_flag(key, True if checked else False)

    def _cfg_now(self):
        """Текущее состояние флагов модулей из интерфейса / the module flags as shown."""
        cfg = dict(self.cfg)
        for module in modules.MODULES:
            box = self.chk_modules.get(module.config_key)
            if box is not None:
                cfg[module.config_key] = bool(box.isChecked())
        # режим — тоже часть текущего состояния: от него зависит, какие разделы
        # считать ненужными в этом режиме
        # the mode is part of the current state too: it decides which sections
        # count as unnecessary right now
        cfg["mode"] = self._mode()
        return cfg

    def _set_module_flag(self, key, value):
        """Задать флаг модуля в интерфейсе и обновить все его переключатели.

        Set a module flag in the interface and refresh every switch of it: the
        checkbox on the Modules page and the one on the module's own page.
        """
        module = modules.get(key)
        if module is None:
            return
        self._module_switching = True
        try:
            # Сам флаг пишется в cfg, а не только в флажок: `_cfg_now` берёт
            # флажки из `chk_modules`, но остальное состояние — отсюда.
            # The flag goes into cfg as well as into the checkbox: `_cfg_now`
            # reads the checkboxes from `chk_modules`, and the rest of the state
            # from here.
            self.cfg[module.config_key] = bool(value)
            box = self.chk_modules.get(module.config_key)
            if box is not None:
                box.setChecked(bool(value))
            # флажок на своей странице — тот же самый ключ конфигурации
            # the checkbox on the module's own page carries the same config key
            own = self._own_module_box(key)
            if own is not None and own is not box:
                own.blockSignals(True)
                own.setChecked(bool(value))
                own.blockSignals(False)
        finally:
            self._module_switching = False
        self._sync_module_pages()

    # ------------------------------------------------ отмена и повтор
    # undo and redo
    HIST_MAIN = "main"

    def _section_key(self):
        """История какого раздела сейчас работает / which section's history applies.

        Открытая страница — это и есть раздел: словарь помнит свои шаги, таблица
        сокращений свои, правила анимаций свои. На «Основных» и прочих страницах
        без таблиц история общая, потому что правки там — отдельные поля.

        The open page is the section: the glossary keeps its own steps, the
        abbreviations theirs, the animation rules theirs. On the pages without
        tables the history is shared, because the edits there are single fields.
        """
        row = self.nav.currentRow() if hasattr(self, "nav") else 0
        if row == 4:
            # у каждой таблицы сокращений своя история: отмена в немецкой не
            # должна переписывать английскую
            # every abbreviation table keeps its own history: an undo in German
            # must not rewrite English
            return "slang:" + slang.code_for(getattr(self, "_slang_lang", "en"))
        return {row: self.HIST_MAIN,
                3: "glossary",       # страница «Словарь»
                7: "anims"}.get(row, self.HIST_MAIN)

    def _hist_state(self):
        """Текущее состояние всего, что правят в окне, вместе с диском.

        The current state of everything the window edits, the disk included.

        В снимок входит и то, что уже сохранено в config.json: отмена после
        сохранения обязана вернуть файл, иначе игра продолжит делать то, что
        игрок только что отменил.
        The snapshot also carries what already reached config.json: undo after a
        save must put the file back, otherwise the game keeps doing what the
        player has just undone.
        """
        fields = {}
        for key, widget in self._hist_widgets():
            fields[key] = self._hist_read(widget)
        docs = {code: dict(data) for code, data in self.docs.items()}
        return {
            "fields": fields,
            "tables": {name: _table_state(table)
                       for name, table in self._hist_tables()},
            # Черновики сокращений по языкам: таблица показывает один язык, но
            # правки другого тоже обязаны откатываться.
            # The abbreviation drafts per language: the table shows one language,
            # yet the other languages' edits must roll back too.
            "slang_drafts": {code: {token: list(pair) for token, pair in rows.items()}
                             for code, rows in self._slang_drafts.items()},
            "docs": docs,
            "self_cfg": dict(self.cfg),
            # Диск берётся из кэша: снимок делается на каждое нажатие клавиши, а
            # чтение всех файлов словарей на каждую букву — это рывки ввода.
            # The disk part comes from the cache: a snapshot is taken on every
            # keystroke, and reading every glossary file per letter makes typing
            # stutter.
            "disk": self._disk_cache,
        }

    def _hist_tables(self):
        """Таблицы раздела, которые входят в историю / the section's tables.

        Таблицы входят в снимок целиком: правка ячейки меняет не поле настроек,
        а строку, и без этого отмена не видела бы разницы.
        Tables are snapshotted whole: an edited cell changes a row rather than a
        settings field, and without this the undo would see no difference.
        """
        return [(name, getattr(self, name)) for name in
                ("tbl", "tbl_slang", "tbl_anims") if hasattr(self, name)]

    def _hist_widgets(self):
        """Поля, которые входят в историю: ключ -> виджет.

        The fields that take part in the history: key to widget.
        """
        names = ("cb_lang", "cb_mode", "cb_send_mode", "cb_ui_lang", "ed_hotkey",
                 "ed_open", "ed_close", "sp_max", "sp_debounce", "ed_chatkey",
                 "sp_focus", "sp_opendelay", "sp_ui_scale", "chk_show_settings",
                 "chk_filler", "chk_prefer", "sp_every", "cb_pos", "sp_frag",
                 "sp_min", "sp_maxw", "chk_slang", "chk_auto", "chk_send",
                 "chk_submit", "chk_dlx", "ed_dlx_pro", "ed_dlx_proxy",
                 "ed_dlx_url", "ed_dlx_url_token", "sp_dlx_port")
        return [(name, getattr(self, name)) for name in names
                if hasattr(self, name)]

    @staticmethod
    def _hist_read(widget):
        """Значение поля для снимка / a widget's value for the snapshot."""
        for getter in ("isChecked", "value", "currentData", "text"):
            method = getattr(widget, getter, None)
            if callable(method):
                try:
                    value = method()
                except Exception:
                    return None
                return value
        return None

    @staticmethod
    def _hist_write(widget, value):
        """Вернуть полю значение из снимка / restore a widget from a snapshot."""
        if value is None:
            return
        if hasattr(widget, "setChecked") and isinstance(value, bool):
            widget.setChecked(value)
        elif hasattr(widget, "setValue") and isinstance(value, int):
            widget.setValue(value)
        elif hasattr(widget, "setCurrentIndex") and hasattr(widget, "findData"):
            index = widget.findData(value)
            if index >= 0:
                widget.setCurrentIndex(index)
        elif hasattr(widget, "setText") and isinstance(value, str):
            widget.setText(value)

    def _mark(self, tag, force=False):
        """Запомнить шаг: состояние до и после правки.

        Remember a step: the state before and after the edit.

        ``tag`` — подпись правила. Правки одного поля с одной подписью склеиваются,
        поэтому ввод слова в таблицу — один шаг, а не десять.

        ``tag`` labels the edit. Edits with the same tag are coalesced, so typing a
        word into a table is one step and not ten.
        """
        if self._hist_applying or self._hist_busy:
            return
        now = time.monotonic()
        before = getattr(self, "_hist_shadow", None)
        if before is None:
            before = self._hist_state()
            self._hist_shadow = before
            return
        after = self._hist_state()
        if after == before:
            return
        section = self._hist.section(self._section_key())
        self._hist_busy = True
        try:
            if force:
                # действие целиком (сохранение, объединение правил) не склеивается
                # с соседними правками: это отдельный шаг
                # a whole action (a save, a merge) never coalesces with a
                # neighbouring edit: it is a step of its own
                added = section.record(before, after, tag)
            else:
                added = section.record_field(before, after, tag, now)
            self._hist_shadow = after
        finally:
            self._hist_busy = False
        if added:
            self._hist_field[tag] = True
        self._hist_note()

    def _refresh_disk(self):
        """Перечитать диск — только там, где он правда мог измениться.

        Re-read the disk, but only where it may really have changed: at the start
        and after every write.
        """
        self._disk_cache = _read_disk_state()

    def _reset_history(self):
        """Новый отсчёт: окно только что загрузилось / a fresh start after loading."""
        self._refresh_disk()
        self._hist.reset()
        self._hist_shadow = self._hist_state()
        self._hist_note()

    def _hist_note(self):
        """Подпись в подвале: что можно отменить / the footer caption."""
        for name in ("lb_hist",):
            label = getattr(self, name, None)
            if label is None:
                continue
            key = self._section_key()
            if self._hist.can_undo(key):
                label.setText(i18n.t("Ctrl+Z — отменить правку в разделе · "
                                     "Ctrl+Y — вернуть"))
            else:
                label.setText("")

    def _undo(self):
        """Ctrl+Z: шаг назад в текущем разделе / one step back in this section."""
        self._apply_history(undo=True)

    def _redo(self):
        """Ctrl+Y: шаг вперёд после отмены / reapply after an undo."""
        self._apply_history(undo=False)

    def _apply_history(self, undo):
        """Применить снимок и записать его на диск.

        Apply a snapshot and write it to the disk.

        Диск пишется сразу: иначе отмена осталась бы только на экране, а игра
        продолжала бы делать отменённое.
        The disk is written at once: otherwise the undo would stay on screen only,
        while the game kept doing what was undone.
        """
        section = self._hist.section(self._section_key())
        can, step = (section.can_undo, section.undo) if undo else \
            (section.can_redo, section.redo)
        if not can():
            return False
        state = step()
        if state is None:
            return False
        drafts_before = {code: {token: list(pair) for token, pair in rows.items()}
                         for code, rows in self._slang_drafts.items()}
        self._hist_applying = True
        try:
            self._restore_state(state)
            self._write_disk_state(state)
            # после записи диск равен этому снимку — кэш обновляем без чтения
            # after the write the disk equals this snapshot, so the cache is set
            # without reading it back
            self._disk_cache = dict(state.get("disk") or {"cfg": {}, "docs": {}})
            # Диск вернулся к снимку, а в памяти снова черновики: несохранённые
            # правки остаются на экране и в предпросмотре, но в файле их нет —
            # ровно как было до «Сохранить».
            # The disk is back to the snapshot, while memory holds the drafts
            # again: unsaved edits stay on screen and in the preview but not in
            # the file, exactly as before "Save".
            self._apply_slang_drafts(force=self._slang_drafts != drafts_before)
        finally:
            self._hist_applying = False
        self._hist_shadow = self._hist_state()
        self._hist_note()
        self._flash_hint()
        return True

    def _apply_slang_drafts(self, force=False):
        """Применить черновики к таблицам сокращений в памяти.

        Apply the drafts to the abbreviation tables in memory.

        ``force`` пишет и файл: после отмены без этого таблица на экране и файл
        разъехались бы.
        ``force`` writes the file too: without it an undo would leave the table on
        screen and the file disagreeing.
        """
        rows = {code: self._slate_of(code, rows) for code, rows in self._slang_drafts.items()}
        for code, slate in rows.items():
            slang.set_user(slate, code)
        if force:
            try:
                slang.save_languages(rows)
            except OSError:
                log.exception("Отмена: не удалось записать slang.json")

    def _restore_state(self, state):
        """Вернуть интерфейс и память окна к снимку / restore the window to a snapshot."""
        for key, value in (state.get("fields") or {}).items():
            widget = getattr(self, key, None)
            if widget is not None:
                self._hist_write(widget, value)
        for name, rows in (state.get("tables") or {}).items():
            table = getattr(self, name, None)
            if table is not None:
                _restore_table(table, rows)
        self.docs = {code: dict(data) for code, data in (state.get("docs") or {}).items()}
        self._slang_drafts = {code: {token: list(pair) for token, pair in rows.items()}
                              for code, rows in (state.get("slang_drafts") or {}).items()}
        self.cfg = dict(state.get("self_cfg") or self.cfg)
        # таблицы перерисовываются из восстановленных данных, а не наоборот
        # the tables are redrawn from the restored data, not the other way round
        try:
            self._fill_tables_from_state()
        except Exception:
            log.exception("Не удалось восстановить таблицы после отмены")

    def _fill_tables_from_state(self):
        """Перерисовать таблицы из восстановленного состояния.

        Redraw the tables from the restored state.

        Молча, без записи шага: отмена не должна порождать новую правку.
        Quietly, without recording a step: an undo must not create a new edit.
        """
        self.glossary_changed = True
        self._load_language(self.glang, reload_table=True)
        self._fill_slang()
        if hasattr(self, "tbl_anims"):
            self._fill_anims()

    @staticmethod
    def _write_disk_state(state):
        """Записать на диск то, что несёт снимок / write the snapshot's disk part."""
        disk = state.get("disk") or {}
        cfg = disk.get("cfg")
        if isinstance(cfg, dict):
            try:
                save_config(cfg)
            except OSError:
                log.exception("Отмена: не удалось записать config.json")
        for code, data in (disk.get("docs") or {}).items():
            try:
                save_glossary_data(code, data)
            except OSError:
                log.exception("Отмена: не удалось записать словарь %s", code)
        slang_file = disk.get("slang")
        if isinstance(slang_file, dict):
            try:
                write_json(SLANG_PATH, slang_file)
                slang.load_user()
            except OSError:
                log.exception("Отмена: не удалось записать slang.json")

    def _mirror_own_flag(self, key, checked):
        """Флажок на странице модуля изменился — обновить «Модули».

        The checkbox on a module's own page changed: refresh the Modules page.

        Два переключателя одного флага обязаны показывать одно и то же, иначе
        «Модули» врут о состоянии программы.
        Two switches of one flag must show the same thing, otherwise the Modules
        page lies about the program's state.
        """
        if getattr(self, "_module_switching", False):
            return
        box = self.chk_modules.get(modules.get(key).config_key) if modules.get(key) else None
        if box is None:
            return
        self._module_switching = True
        try:
            box.blockSignals(True)
            box.setChecked(bool(checked))
            box.blockSignals(False)
        finally:
            self._module_switching = False
        self._sync_module_pages()

    def _mode_flag_tip(self, key):
        """Подсказка для флажка, который в этом режиме не нужен.

        The tooltip of a checkbox the current mode does not need.
        """
        module = modules.get(key)
        if module is None or not modules.needed_in_other_mode(self._cfg_now(), key):
            return ""
        return i18n.tf("«%s» нужен только в частичном режиме перевода. "
                       "В других режимах он ничего не делает.",
                       module.title_en if i18n.is_en() else module.title_ru)

    def _own_module_box(self, key):
        """Флажок модуля на его собственной странице / the module's own checkbox."""
        return {
            "slang": getattr(self, "chk_slang", None),
            "autotranslate": getattr(self, "chk_auto", None),
            "game_send": getattr(self, "chk_send", None),
            "dlx": getattr(self, "chk_dlx", None),
            "anims": getattr(self, "chk_anims", None),
        }.get(key)

    def _sync_module_pages(self):
        """Погасить разделы выключенных модулей, оставив их видимыми.

        Dim the sections of disabled modules and keep them visible.

        Раздел не прячется: игрок должен видеть, что настройки существуют и
        почему сейчас недоступны. Сверху появляется подсказка о выключенном
        модуле, а содержимое становится неактивным.
        The section is not hidden: the player must see that the settings exist and
        why they are unavailable. A hint about the disabled module appears on top
        and the content becomes inactive.
        """
        cfg = self._cfg_now()
        for module in modules.MODULES:
            pair = getattr(self, "_module_by_key", {}).get(module.key)
            box = pair[0] if pair else None
            if box is not None:
                tip = self._mode_flag_tip(module.key)
                box.setToolTip(tip or i18n.t("Включает и выключает модуль."))
                box.setProperty("modeOff", bool(tip))
            if not module.page_key:
                continue
            page = getattr(self, module.page_key, None)
            view = self._view_of(page)
            if page is None:
                continue
            active = modules.is_enabled(cfg, module.key)
            # третье состояние: модуль исправен, но в этом режиме не нужен —
            # так гаснет автоперевод в полном и обратном режиме
            # the third state: the module is fine but this mode does not use it,
            # which is how auto-translation dims in full and reverse mode
            other_mode = modules.needed_in_other_mode(cfg, module.key)
            for child in page.findChildren(QWidget):
                # подсказку о выключенном модуле не гасим — её и надо прочитать
                # the disabled-module hint stays readable: it is what to read
                if child.objectName() == "moduleOff":
                    continue
                child.setEnabled(active and not other_mode)
            page.setProperty("moduleOff", not active or other_mode)
            banner = page.findChild(QLabel, "moduleOff")
            if banner is not None:
                banner.setVisible(not active or other_mode)
                if other_mode:
                    banner.setText(i18n.tf(
                        "Модуль «%s» в этом режиме не нужен: он работает только в "
                        "частичном режиме. Переключите режим на странице «Основные» — "
                        "настройки вернутся.",
                        module.title_en if i18n.is_en() else module.title_ru))
                elif not active:
                    banner.setText(i18n.tf(
                        "Модуль «%s» выключен — настройки раздела недоступны. "
                        "Включите его здесь или в разделе «Модули».",
                        module.title_en if i18n.is_en() else module.title_ru))
            if view is not None:
                view.setProperty("moduleOff", not active or other_mode)
            # Содержимое гаснет в два приёма: правила [moduleOff="true"] в общей
            # таблице стилей и перезапись собственных styleSheet (заголовки
            # карточек, плашка состояния). Баннер не гаснет: это единственное,
            # что здесь надо прочитать.
            # The content fades in two steps: the [moduleOff="true"] rules of the
            # shared stylesheet and a rewrite of the widgets' own stylesheets
            # (card titles, the state badge). The banner does not fade: it is the
            # one line to read here.
            self._fade_page(page, view, not active or other_mode)
            # строка в списке разделов тоже гаснет: по одному серому содержимому
            # не всегда ясно, что дело в выключенном модуле, а не в самом разделе
            # the row in the section list fades too: grey content alone does not
            # always say whether the module is off or the section itself is dull
            self._dim_nav_row(module.page_key, not active or other_mode)

    def _fade_page(self, page, view, off):
        """Погасить содержимое раздела / fade a section's content.

        Одних правил таблицы стилей мало: у подписей карточек свой цвет прямо в
        ``styleSheet`` («Клавиша остановки зацикливания» и другие заголовки), и
        селектор предка до него не достаёт. Поэтому такие цвета подменяются на
        серый, а исходный текст стиля запоминается в свойстве виджета — при
        включении модуля он возвращается байт в байт, без пересборки раздела.
        Stylesheet rules alone are not enough: card captions carry their colour in
        a widget ``styleSheet`` ("Loop stop key" and the other card titles), which
        an ancestor selector cannot reach. Those colours are replaced with grey
        while the original text is kept in a widget property, so switching the
        module back on restores it byte for byte without rebuilding the section.
        """
        for child in (page.findChildren(QWidget) if page is not None else []):
            if child.objectName() == "moduleOff":
                continue
            own = child.styleSheet()
            # Две вещи гасятся по отдельности: собственный стиль виджета и его
            # цветное состояние (плашка DeepL). Плашка своего styleSheet не
            # имеет вовсе — цвет ей даёт правило по свойству state.
            # Two things fade separately: the widget's own stylesheet and its
            # coloured state (the DeepL badge). The badge has no stylesheet at
            # all: its colour comes from a rule on the state property.
            if own and child.property("_dim_css") is None:
                # исходный стиль запоминаем один раз: дальше в styleSheet лежит
                # уже серый вариант, и второй проход обесцветил бы его начисто
                # the original style is remembered once: the stylesheet then holds
                # the grey variant, and a second pass would wash it out for good
                child.setProperty("_dim_css", own)
            saved = child.property("_dim_css")
            if off:
                if saved is not None:
                    child.setStyleSheet(_dimmed_css(str(saved)))
                # цветное состояние на погашенном разделе тоже серое: иначе
                # зелёное «Запущено» светилось бы ярче заголовков
                # a coloured state goes grey as well, or the green "Running"
                # would shine brighter than the captions
                if child.property("state") is not None:
                    _dim_state(child)
            else:
                if saved is not None:
                    child.setStyleSheet(str(saved))
                    child.setProperty("_dim_css", None)
                _dim_restore_state(child)
        for widget in (page, view, getattr(view, "viewport", lambda: None)()):
            if widget is None:
                continue
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

    def _dim_nav_row(self, page_key, off):
        """Погасить строку раздела в списке слева / fade a section row.

        Цвет ставится самой строке, а не через таблицу стилей: у QListWidget нет
        селектора по свойству строки, а ``setForeground`` работает и на выбранной
        строке, и на обычной.
        The colour is set on the row itself rather than through the stylesheet: a
        QListWidget has no selector for a row property, while ``setForeground``
        covers both the selected and the plain row.
        """
        row = getattr(self, "_page_rows", {}).get(page_key)
        if row is None or not hasattr(self, "nav"):
            return
        item = self.nav.item(row)
        if item is None:
            return
        if bool(item.data(Qt.ItemDataRole.UserRole + 1)) == bool(off):
            return
        item.setData(Qt.ItemDataRole.UserRole + 1, bool(off))
        item.setForeground(QColor("#757583") if off else QColor("#c8c8d2"))

    def _view_of(self, page):
        """Обёртка с прокруткой для страницы / the scroll wrapper of a page."""
        for view in getattr(self, "_views", []):
            if view.widget() is page:
                return view
        return None

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
        self.cb_test_dir.addItem("Всё сообщение → выбранный язык", "full")
        self.cb_test_dir.addItem("Только выделенные слова и фразы → выбранный язык",
                                 "partial")
        self.cb_test_dir.addItem("Ваш язык → русский", "to_ru")
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
    def _test_mode(self):
        """Режим, выбранный на странице проверки / the mode chosen for the test."""
        return str(self.cb_test_dir.currentData() or "partial")

    def _test_reverse(self):
        return self._test_mode() == "to_ru"

    def _test_dir_changed(self, *_args, silent=False):
        """Подсказки и пример под выбранный режим.

        Hints and an example for the chosen mode.
        """
        mode = self._test_mode()
        if mode == "full":
            if hasattr(self, "lb_test_hint"):
                self.lb_test_hint.setText(i18n.t(
                    "Введите фразу по-русски — увидите, что уйдёт в игру в полном "
                    "режиме: весь текст на языке перевода, без +скобок+."))
            self.ed_test.setPlaceholderText(
                i18n.t("например: Слушай, брат, мне срочно нужна помощь"))
            self.lb_test_dir.setText(i18n.t(
                "Проверяем полный режим: в чат уйдёт всё сообщение на языке перевода."))
            if not silent:
                self._do_preview()
            return
        if mode == "partial":
            if hasattr(self, "lb_test_hint"):
                self.lb_test_hint.setText(i18n.t(
                    "Введите фразу по-русски — увидите, что уйдёт в игру в обычном "
                    "режиме: переводятся только выделенные слова и фразы и паразиты."))
            self.ed_test.setPlaceholderText(
                i18n.t("например: Слушай, брат, мне срочно нужна помощь"))
            self.lb_test_dir.setText(i18n.t(
                "Проверяем обычный режим: в чат уйдёт ваш текст, а переведёнными — "
                "только выделенные слова и фразы."))
            if not silent:
                self._do_preview()
            return
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
        elif self._test_mode() == "partial":
            self.ed_test.setText("Слушай, +мне срочно нужна помощь+, я опоздаю")
        else:
            self.ed_test.setText("Слушай, ну что ты, я же говорил, что приду позже")

    def _preview_cfg(self):
        """Конфиг из текущих полей (без сохранения).

        The config built from the current fields (without saving).
        """
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
        # when the services answer slowly, say so honestly instead of staying silent
        if not hasattr(self, "_slow_timer"):
            self._slow_timer = QTimer(self)
            self._slow_timer.setSingleShot(True)
            self._slow_timer.timeout.connect(
                lambda: self.lb_test_mode.setText(i18n.t("перевожу… (сервисы заняты)")))
        self._slow_timer.start(5000)
        threading.Thread(target=self._preview_job,
                         args=(cfg, code, text, self._test_mode()),
                         daemon=True).start()

    def _preview_job(self, cfg, code, text, mode="partial"):
        """Прогон через движок в том же режиме, что выбран в списке проверки.

        The text goes through the engine in the very mode picked for the test.

        Проверка обязана повторять рабочий путь: если показывать одно, а в чат
        отправлять другое, проверка вредна — она успокаивает зря.
        The test must repeat the real path: showing one thing and sending
        another makes the test harmful, because it reassures for nothing.
        """
        reverse = mode == "to_ru"
        try:
            data = self._doc(code)
            gl = Glossary(data, code)
            tr = Translator(code)
            # ключевое: проверка должна идти в том же направлении, что выбрано
            # the key point: the test must run in the very direction that is chosen
            tr.set_direction("in" if reverse else "out")
            engine = Engine(cfg, gl, tr)
            if reverse:
                res = engine.process_in(text)
                payload = {"out": res.text or "—",
                           "sub": (i18n.t("Исходное сообщение: ") + res.native)
                                  if res.native and res.native != res.text else "",
                           "note": i18n.t("Способ: переведено в чат игры") if res.translated
                                   else i18n.t("Способ: без перевода (одна команда)")}
            elif mode == "full":
                res = engine.process_full(text)
                sent = res.native or res.text
                other = ""
            else:
                res = engine.process(text, auto=bool(cfg.get("auto_mode")), seed=1.0)
                native = str(cfg.get("send_mode") or "reading") in (
                    "native", "lang", "text", "target")
                sent = (res.native or res.text) if native else (res.text or res.native)
                other = res.text if native else res.native
            if mode != "to_ru":
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
        cfg["mode"] = self._mode()
        cfg["direction"] = "in" if cfg["mode"] == "to_ru" else "out"
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
            # режим «В машине» уже применён галочкой, здесь он только пишется
            # на диск, чтобы пережить перезапуск
            # the "In a vehicle" mode was already applied by the checkbox; here it
            # is only written to disk so that it survives a restart
            cfg["anim_in_vehicle"] = bool(self.chk_anim_vehicle.isChecked())
            cfg["anim_hints"] = bool(self.chk_anim_hints.isChecked())
            cfg["anim_row_height"] = int(self.sp_anim_row.value())
        cfg["slang_order"] = list(self._slang_order)
        cfg["slang_lang"] = slang.code_for(self._slang_lang)
        # Рабочий язык таблицы переставляет главное окно после сохранения: окно
        # настроек только собирает выбор, чтобы проверка перевода и игра видели
        # одно и то же.
        # The main window moves the working table language after a save; the
        # settings window only collects the choice, so the preview and the game
        # see the same thing.
        return modules.apply_defaults(cfg)

    def _load_widgets(self):
        cfg = self.cfg
        code = slang.code_for(cfg.get("slang_lang") or cfg.get("target_lang"))
        if code != getattr(self, "_slang_lang", None):
            # черновика ещё нет, поэтому менять нечего: просто выбираем язык
            # no draft exists yet, so there is nothing to flush: just pick it
            self._slang_lang = code
            self._fill_slang()
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
        if hasattr(self, "cb_mode"):
            mode = cfg.get("mode") or "partial"
            self.cb_mode.blockSignals(True)
            self.cb_mode.setCurrentIndex(max(0, self.cb_mode.findData(mode)))
            self.cb_mode.blockSignals(False)
        self._mode_changed()
        self.chk_slang.setChecked(bool(cfg.get("slang", True)))
        if hasattr(self, "cb_ui_lang"):
            idx = self.cb_ui_lang.findData(i18n.normalize(cfg.get("ui_lang", "ru")))
            self.cb_ui_lang.blockSignals(True)
            self.cb_ui_lang.setCurrentIndex(max(0, idx))
            self.cb_ui_lang.blockSignals(False)
            i18n.set_lang(self.cb_ui_lang.currentData() or "ru")
        if hasattr(self, "cb_test_dir"):
            test_mode = cfg.get("mode") or "partial"
            self.cb_test_dir.blockSignals(True)
            self.cb_test_dir.setCurrentIndex(
                max(0, self.cb_test_dir.findData(test_mode)))
            self.cb_test_dir.blockSignals(False)
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
            # состояние режима берётся у работающего модуля: он и есть источник
            # правды, галочка в файле могла устареть
            # the mode state comes from the running module: it is the source of
            # truth, the flag in the file may be stale
            live = bool(cfg.get("anim_in_vehicle", False))
            api = getattr(self, "anims_api", None)
            if api is not None:
                try:
                    live = bool(api["state"]().get("vehicle"))
                except Exception:
                    log.exception("Не удалось прочитать режим «В машине»")
            self.chk_anim_vehicle.blockSignals(True)
            self.chk_anim_vehicle.setChecked(live)
            self.chk_anim_vehicle.blockSignals(False)
            self._anim_vehicle_note(live)
            if hasattr(self, "chk_anim_hints"):
                self.chk_anim_hints.blockSignals(True)
                self.chk_anim_hints.setChecked(bool(cfg.get("anim_hints", True)))
                self.chk_anim_hints.blockSignals(False)
            if hasattr(self, "sp_anim_row"):
                self.cfg["anim_row_height"] = int(cfg.get("anim_row_height", 34) or 34)
                self.sp_anim_row.blockSignals(True)
                self.sp_anim_row.setValue(self._anim_base_row())
                self.sp_anim_row.blockSignals(False)
                self._anim_row_height()
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
        # Отмена и повтор — по разделам. Qt.KeyboardModifier проверяется, чтобы
        # Ctrl+Z работал и с русской раскладкой, где приходит та же клавиша.
        # Undo and redo are per section. The modifier check keeps Ctrl+Z working
        # with a non-Latin layout, where the very same key arrives.
        mods = e.modifiers()
        control = bool(mods & Qt.KeyboardModifier.ControlModifier)
        if control and e.key() == Qt.Key.Key_Z:
            self._undo()
            return
        if control and e.key() == Qt.Key.Key_Y:
            self._redo()
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
        # Сохранение — тоже шаг истории: иначе Ctrl+Z после «Сохранить» не вернул
        # бы файл, а игра продолжила бы делать отменённое. Состояние «до» берём
        # как есть, а новое состояние диска становится кэшем.
        # A save is a history step too: otherwise Ctrl+Z after "Save" would not
        # put the file back and the game would keep doing what was undone.
        before = self._hist_state()
        self._disk_cache = {"cfg": dict(cfg), "docs": {
            code: dict(self.docs.get(code) or {}) for code in saved_glossaries},
            "slang": read_json(SLANG_PATH, {})}
        after = self._hist_state()
        self._hist.section(self._section_key()).record(before, after, "save")
        self._hist_shadow = after
        self._hist_note()
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
    """Варианты и свойства анимации: имена, названия и описания.

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
        self.setWindowTitle(i18n.t("Варианты и свойства"))
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

        lay.addWidget(_hint(i18n.t(
            "Группа необязательна: впишите одинаковое название у нескольких "
            "вариантов — в оверлее они встанут подряд под этим названием, а "
            "разные группы будут разделены чертой.")))

        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(
            [i18n.t("/anim"), i18n.t("Название"), i18n.t("Описание"),
             i18n.t("Группа")])
        head_view = self.tbl.horizontalHeader()
        head_view.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        head_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        head_view.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        head_view.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        head_view.setStretchLastSection(False)
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
        # Группа ставится сразу нескольким строкам: вписывать одно и то же
        # название в каждую ячейку вручную — лишняя работа.
        # A group is given to several rows at once: typing the same title into
        # every cell by hand is busywork.
        self.bt_group = QPushButton(i18n.t("Группа…"))
        self.bt_group.setToolTip(i18n.t(
            "Дать выбранным вариантам общее название группы — в оверлее они "
            "встанут подряд под ним и будут отделены чертой от других групп."))
        self.bt_group.clicked.connect(self._assign_group)
        for button in (self.bt_add, self.bt_del, self.bt_up, self.bt_down,
                       self.bt_group):
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
                                       choice.description, choice.group)):
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
        group = getattr(self, "bt_group", None)
        if group is not None:
            # группу можно дать любой строке — даже одной
            # a group can be given to any row, even a single one
            group.setEnabled(self.tbl.rowCount() > 0)

    def _assign_group(self):
        """Вписать название группы в выбранные строки (или во все).

        Write the group title into the selected rows, or into all of them.
        """
        rows = sorted({index.row() for index in self.tbl.selectedIndexes()})
        if not rows:
            rows = list(range(self.tbl.rowCount()))
        if not rows:
            return
        current = ""
        item = self.tbl.item(rows[0], 3)
        if item is not None:
            current = item.text().strip()
        title, ok = QInputDialog.getText(
            self, i18n.t("Группа вариантов"),
            i18n.tf("Название группы для строк: %d. Пустое поле — убрать группу.",
                    len(rows)),
            text=current)
        if not ok:
            return
        title = (title or "").strip()[:anims.MAX_GROUP]
        self.tbl.blockSignals(True)
        for row in rows:
            cell = self.tbl.item(row, 3)
            if cell is None:
                cell = QTableWidgetItem("")
                self.tbl.setItem(row, 3, cell)
            cell.setText(title)
            cell.setToolTip(title)
        self.tbl.blockSignals(False)
        self._validate()

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
                            description=text(2), group=text(3))

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
