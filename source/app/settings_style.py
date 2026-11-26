"""Shared dark stylesheet and fit-to-screen helper for settings dialogs."""

from PySide6.QtGui import QGuiApplication


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
        % (
            int(round(20 * k)),
            int(round(8 * k)),
            int(round(16 * k)),
            int(round(26 * k)),
            int(round(24 * k)),
            int(round(15 * k)),
            int(round(16 * k)),
            int(round(16 * k)),
            int(round(18 * k)),
            int(round(18 * k)),
        )
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
    win.move(
        area.x() + (area.width() - win.width()) // 2, area.y() + (area.height() - win.height()) // 2
    )
