"""Shared dark stylesheet and fit-to-screen helper for settings dialogs."""

from PySide6.QtGui import QGuiApplication


STYLE = """
QDialog, QWidget#page { background: #0b1422; color: #f2f6fc; }
QWidget { color: #f2f6fc; font-size: 13px; }
QLabel#h1 { font-size: 19px; font-weight: 600; }
QLabel#sub { color: #91a4bd; font-size: 12px; }
QLabel#hint { color: #91a4bd; font-size: 11px; }
QLabel#warn { color: #ffb45b; font-size: 11px; }
QLabel#err { color: #ff6b6b; font-size: 12px; }
QLabel#ok { color: #66d18b; font-size: 12px; }
QFrame#card { background: #162337; border: 1px solid #2a3d57; border-radius: 10px; }
QFrame#sep { background: #22334a; max-height: 1px; border: none; }
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
QLabel#dlxState[state="off"], QLabel#dlxState[state="missing"] { color: #8496b0; }
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
    color: #8496b0; }
QPushButton#dlxSwitch[state="error"] { color: #ff9c9c; }
QPushButton#dlxSwitch:hover { color: #ffffff; }
QPushButton#dlxSwitch:disabled { color: #8193ad; }
/* погашенный раздел: плашка, тумблер и надпись теряют цвет вместе с остальным
   a dimmed section: badge, switch and caption lose their colour with the rest */
QWidget#page[moduleOff="true"] QLabel#dlxState,
QWidget#page[moduleOff="true"] QPushButton#dlxSwitch {
    background: transparent; border: none; color: #8193ad; }
/* вертикальная черта между тумблером и служебными кнопками
   the vertical line between the switch and the service buttons */
QFrame#vsep { background: #2a3d57; max-width: 1px; border: none; }
QListWidget#nav { background: #121d2d; border: none; border-right: 1px solid #24344b;
                  padding: 8px 6px; outline: 0; }
QListWidget#nav::item { padding: 10px 12px; border-radius: 8px; margin: 2px 4px; color: #bdcbe0; }
QListWidget#nav::item:selected { background: #1d3049; color: #ffffff; }
QListWidget#nav::item:hover { background: #1a293e; }
QLineEdit, QSpinBox, QComboBox { background: #0f1928; border: 1px solid #30445d;
                                 border-radius: 6px; padding: 6px 8px; min-height: 18px; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border: 1px solid #4e8bff; }
QLineEdit:read-only { color: #b5d0ff; }
/* у счётчиков свои кнопки «−» и «+», штатные стрелки убираем совсем, иначе
   они отнимают у поля почти всю ширину. Spin boxes draw their − and + as real
   buttons, so the built-in arrows are given zero width instead of a hidden one. */
QSpinBox::up-button, QSpinBox::down-button { width: 0px; height: 0px;
                                            border: none; background: transparent; }
QComboBox QAbstractItemView { background: #162337; selection-background-color: #263e63;
                              border: 1px solid #30445d; }
QMenu { background: #162337; color: #eaf1fa; border: 1px solid #30445d; padding: 4px; }
QMenu::item { padding: 5px 22px; }
QMenu::item:selected { background: #1d3049; color: #ffffff; }
QMenu::separator { height: 1px; background: #2a3d57; margin: 4px 8px; }
/* Кнопки: заметная рамка, отдельные состояния и видимый фокус для клавиатуры.
   Buttons carry a visible outline, distinct hover/pressed states and a focus ring
   for keyboard users. */
QPushButton { background: #1b2b42; border: 1px solid #30445c; border-radius: 8px;
              padding: 8px 16px; color: #eaf1fa; min-height: 20px; }
QPushButton:hover { background: #253750; border: 1px solid #445c7a; }
QPushButton:pressed { background: #142136; border: 1px solid #4e8bff; }
QPushButton:focus { border: 1px solid #445c7a; }
QPushButton:disabled { background: #152236; border: 1px solid #22334a; color: #8193ad; }
/* главная кнопка: ровная заливка без светлой рамки — рамка того же цвета,
   что и фон, поэтому кнопка не выглядит постоянно нажатой / the main button is
   a flat fill: its border matches the fill, so it never looks stuck in focus */
QPushButton#primary { background: #2864e8; border: 1px solid #2864e8; color: #ffffff;
                      font-weight: 600; }
QPushButton#primary:hover { background: #3978fa; border: 1px solid #3978fa; }
QPushButton#primary:pressed { background: #1f54c7; border: 1px solid #1f54c7; }
QPushButton#primary:focus { background: #3878fa; border: 1px solid #3878fa; }
QPushButton#primary:disabled { background: #213a61; border: 1px solid #365179; color: #a6b8d1; }
QPushButton#danger { color: #ff9c9c; border: 1px solid #4a3238; }
QPushButton#danger:hover { background: #2a1e22; border: 1px solid #7a4a52; color: #ffbcbc; }
QPushButton#soft { color: #ffcf9c; border: 1px solid #2a3d57; background: transparent; }
QPushButton#soft:hover { background: #2a2418; border: 1px solid #7a6444; color: #ffd9ae; }
QToolButton#step { background: #1b2b42; border: 1px solid #30445c; border-radius: 8px;
                   color: #eaf1fa; font-weight: 600; }
QToolButton#step:hover { background: #2c405a; border: 1px solid #4e8bff; }
QToolButton#step:pressed { background: #142136; border: 1px solid #4e8bff; }
QToolButton#step:disabled { color: #8193ad; border: 1px solid #22334a; background: #152236; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px;
                       border: 1px solid #3c526d; background: #0f1928; }
QCheckBox::indicator:checked { background: #2864e8; border: 1px solid #4f7ee6; }
QTableWidget { background: #0f1928; border: 1px solid #30445d; border-radius: 8px;
               gridline-color: #24344b; selection-background-color: #263e63; }
QHeaderView::section { background: #162337; color: #bdcbe0; border: none;
                       border-bottom: 1px solid #30445d; padding: 6px; }
QTableWidget::item { padding: 4px; }
/* галочки в таблице словаря: свой индикатор, иначе Qt рисует тонкую «птичку»
   без рамки, которую на тёмном фоне почти не видно. Table check indicators are
   drawn explicitly: the default is a thin tick with no box, nearly invisible here. */
QTableWidget::indicator, QTableView::indicator { width: 18px; height: 18px; }
QTableWidget::indicator:unchecked, QTableView::indicator:unchecked {
    border: 1px solid #556b88; border-radius: 4px; background: #122034; }
QTableWidget::indicator:unchecked:hover, QTableView::indicator:unchecked:hover {
    border: 1px solid #7ab2ff; }
QTableWidget::indicator:checked, QTableView::indicator:checked {
    border: 1px solid #7ab2ff; border-radius: 4px; background: #2864e8; }
QScrollBar:vertical { background: #0b1422; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #2a3d57; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QToolTip { background: #1b2a40; color: #f2f6fc; border: 1px solid #30445d; padding: 4px; }
/* Раздел с выключенным модулем: содержимое уходит в серый, карточки и рамки
   гаснут, а подсказка сверху (QLabel#moduleOff) остаётся своего цвета — её и
   надо прочитать. A section with its module off goes grey: fields, cards and
   frames fade, while the hint on top (QLabel#moduleOff) keeps its own colour,
   because that is the line to read. */
QWidget#page[moduleOff="true"] QLabel,
QWidget#page[moduleOff="true"] QCheckBox { color: #8193ad; }
QWidget#page[moduleOff="true"] QCheckBox#moduleToggle { color: #eaf1fa; }
QWidget#page[moduleOff="true"] QFrame#card { background: #121d2d; border: 1px solid #1a293e; }
QWidget#page[moduleOff="true"] QLineEdit,
QWidget#page[moduleOff="true"] QSpinBox,
QWidget#page[moduleOff="true"] QComboBox { background: #0f1928; border: 1px solid #22334a;
                                           color: #8193ad; }
QWidget#page[moduleOff="true"] QTableWidget { background: #0f1928; border: 1px solid #22334a;
                                              gridline-color: #17263a; color: #8193ad; }
QWidget#page[moduleOff="true"] QHeaderView::section { background: #121d2d; color: #8193ad; }
QWidget#page[moduleOff="true"] QPushButton { background: #17253a; border: 1px solid #22334a;
                                             color: #8193ad; }
QWidget#page[moduleOff="true"] QPushButton#primary { background: #1b304c; border: 1px solid #253a56;
                                                     color: #8fa3be; }
QScrollArea#scroll { background: transparent; border: none; }
QScrollArea#scroll > QWidget > QWidget { background: #0b1422; }
QScrollBar:horizontal { background: #0b1422; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #2a3d57; border-radius: 5px; min-width: 30px; }
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
