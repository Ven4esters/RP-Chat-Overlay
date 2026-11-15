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
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                               QFileDialog, QFormLayout, QFrame, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QSpinBox, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from app import i18n, langs, modules, slang
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
QComboBox QAbstractItemView { background: #1c1c24; selection-background-color: #2e3f6b;
                              border: 1px solid #3a3a48; }
QPushButton { background: #26262f; border: 1px solid #3a3a48; border-radius: 7px;
              padding: 7px 14px; }
QPushButton:hover { background: #2e2e3a; }
QPushButton:pressed { background: #232331; }
QPushButton#primary { background: #3d6fd8; border: 1px solid #4f7ee6; font-weight: 600; }
QPushButton#primary:hover { background: #4a7ce8; }
QPushButton#danger { color: #ff9c9c; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px;
                       border: 1px solid #4a4a58; background: #0e0e12; }
QCheckBox::indicator:checked { background: #3d6fd8; border: 1px solid #4f7ee6; }
QTableWidget { background: #0e0e12; border: 1px solid #3a3a48; border-radius: 8px;
               gridline-color: #26262f; selection-background-color: #2e3f6b; }
QHeaderView::section { background: #1c1c24; color: #b9b9c6; border: none;
                       border-bottom: 1px solid #3a3a48; padding: 6px; }
QTableWidget::item { padding: 4px; }
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
    return out


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


def _sep():
    s = QFrame()
    s.setObjectName("sep")
    s.setFrameShape(QFrame.Shape.HLine)
    return s


class SettingsWindow(QDialog):
    """Окно настроек. signal saved(cfg) — после сохранения."""

    saved = Signal(dict)

    def __init__(self, cfg, parent=None, first_run=False):
        super().__init__(parent)
        self.cfg = dict(cfg)
        self.docs = {}            # код языка -> данные словаря
        self.dirty = set()        # языки с несохранёнными правками словаря
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
        for name, attr, maker in (("Основные", "page_main", self._page_main),
                                  ("Автоперевод", "page_auto", self._page_auto),
                                  ("Чат игры", "page_game", self._page_game),
                                  ("Словарь", "page_glossary", self._page_glossary),
                                  ("Сокращения", "page_slang", self._page_slang),
                                  ("Проверка", "page_test", self._page_test),
                                  ("Модули", "page_modules", self._page_modules)):
            item = QListWidgetItem(name)
            item.setSizeHint(item.sizeHint().expandedTo(item.sizeHint() + _sz(0, 10)))
            self.nav.addItem(item)
            page = maker()
            setattr(self, attr, page)
            view = _scroll_page(page)
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
        self._apply_adaptive_size(center=True)

    # ------------------------------------------------------------ каркас
    def _build_header(self):
        w = QWidget()
        w.setStyleSheet("background:#17171e;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 14, 20, 12)
        lay.setSpacing(2)
        title = _title("Настройки" if not self.first_run else "Добро пожаловать в RP Chat Overlay",
                       "h1")
        lay.addWidget(title)
        self.header_sub = QLabel()
        self.header_sub.setProperty("no_i18n", True)
        self.header_sub.setObjectName("sub")
        lay.addWidget(self.header_sub)
        return w

    def _build_footer(self):
        w = QWidget()
        w.setStyleSheet("background:#17171e;border-top:1px solid #26262f;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(20, 12, 20, 12)
        lay.setSpacing(10)
        self.footer_hint = _hint("Изменения применятся после «Сохранить».")
        lay.addWidget(self.footer_hint, 1)
        self.btn_reset = QPushButton("Сбросить всё")
        self.btn_reset.setToolTip("Вернуть заводские настройки (словари не затрагиваются)")
        self.btn_reset.clicked.connect(self._reset_all)
        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("Сохранить")
        self.btn_save.setObjectName("primary")
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self._save)
        for b in (self.btn_reset, self.btn_cancel, self.btn_save):
            lay.addWidget(b)
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
        row_scale.addWidget(self.sp_ui_scale)
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
        form.addRow("Максимум в сообщении", self.sp_max)
        self.sp_debounce = _small_spin(QSpinBox(), 100, 2000, " мс", 170, step=50)
        self.sp_debounce.setToolTip("Пауза после последнего символа, перед переводом")
        form.addRow("Задержка перевода", self.sp_debounce)
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
        self._refresh_dynamic()

    def _refresh_dynamic(self):
        """Обновляет подписи, которые собираются в коде (счётчики, подсказки)."""
        try:
            self._update_header()
            self._reverse_changed()
            self._load_language(self.glang, reload_table=False)
            self._update_glossary_ui()
            self._update_slang_ui()
            self._test_dir_changed(silent=True)
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
        self.header_sub.setText(
            "Язык: %s · горячая клавиша: %s · частота автоперевода: каждое %d-е"
            % (langs.label(langs.code_of(self.cb_lang.currentData() or "it")),
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
        if reload_table and hasattr(self, "tbl"):
            self._fill_table(self._doc(code))
            self.lb_glang.setText(i18n.tf("Язык: %s", langs.label(code, native=True)))
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
        form.addRow("Частота", self.sp_every)
        self.cb_pos = QComboBox()
        self.cb_pos.setMaximumWidth(340)
        for val, text in (("last", "последнее в серии (каждое N-е)"),
                          ("first", "первое в серии"),
                          ("random", "случайное в серии")):
            self.cb_pos.addItem(text, val)
        form.addRow("Какое сообщение", self.cb_pos)
        self.sp_frag = _small_spin(QSpinBox(), 1, 3, " фрагм.", 170)
        form.addRow("Фрагментов в сообщении", self.sp_frag)
        row = QHBoxLayout()
        self.sp_min = _small_spin(QSpinBox(), 1, 6, "", 62)
        self.sp_maxw = _small_spin(QSpinBox(), 1, 8, "", 62)
        row.addWidget(QLabel("от"))
        row.addWidget(self.sp_min)
        row.addWidget(QLabel("до"))
        row.addWidget(self.sp_maxw)
        row.addWidget(QLabel("слов"))
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
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.ed_chatkey = QLineEdit()
        self.ed_chatkey.setMaxLength(1)
        self.ed_chatkey.setFixedWidth(56)
        form.addRow("Клавиша чата", self.ed_chatkey)
        self.sp_focus = _small_spin(QSpinBox(), 0, 2000, " мс", 170, step=10)
        form.addRow("После переключения в игру", self.sp_focus)
        self.sp_opendelay = _small_spin(QSpinBox(), 0, 2000, " мс", 170, step=10)
        form.addRow("После открытия чата", self.sp_opendelay)
        self.sp_paste = _small_spin(QSpinBox(), 0, 2000, " мс", 170, step=10)
        form.addRow("После вставки текста", self.sp_paste)
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

        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(["Фраза", "Русская запись", "Русские значения (через ;)"])
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setAlternatingRowColors(False)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.itemChanged.connect(self._table_edited)
        lay.addWidget(self.tbl, 1)

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
        lay.addWidget(_hint("Фразы-паразиты отмечены «★» — они переводятся в каждом сообщении. "
                            "Значения — это то, что вы печатаете по-русски; «е/ё» и «и/й» считаются одной буквой."))
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
            star = "★ " if self._norm_key(phrase) in fillers else ""
            items = [QTableWidgetItem(star + str(phrase)),
                     QTableWidgetItem(ru.strip()),
                     QTableWidgetItem(meanings.strip().lstrip(";").strip())]
            for c, it in enumerate(items):
                it.setData(Qt.ItemDataRole.UserRole, str(phrase))
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
        """Переносит таблицу в данные словаря текущего языка."""
        if not self.glossary_changed:
            return
        data = self._doc(self.glang)
        phrases = {}
        for r in range(self.tbl.rowCount()):
            cells = []
            for c in range(3):
                it = self.tbl.item(r, c)
                cells.append(it.text().strip() if it else "")
            phrase = cells[0].lstrip("★").strip()
            if not phrase:
                continue
            reading = cells[1] or phrase
            meanings = "; ".join(x.strip() for x in cells[2].split(";") if x.strip())
            phrases[phrase] = reading + " | " + meanings if meanings else reading + " | "
        data["phrases"] = phrases
        self.docs[self.glang] = data
        self.dirty.add(self.glang)
        self.glossary_changed = False

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
        for c in range(3):
            self.tbl.setItem(r, c, QTableWidgetItem(""))
        self.tbl.blockSignals(False)
        self.glossary_changed = True
        self._filter_table()
        self.tbl.editItem(self.tbl.item(r, 0))

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

        self.tbl_slang = QTableWidget(0, 3)
        self.tbl_slang.setHorizontalHeaderLabels(
            ["Сокращение", "Разворот (полная фраза)", "Русский вариант"])
        for c in range(3):
            self.tbl_slang.horizontalHeader().setSectionResizeMode(
                c, QHeaderView.ResizeMode.Stretch)
        self.tbl_slang.verticalHeader().setVisible(False)
        self.tbl_slang.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_slang.itemChanged.connect(self._slang_edited)
        lay.addWidget(self.tbl_slang, 1)

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
        for token, expand, ru, own in slang.entries():
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
            i18n.tf("показано %d из %d", shown, total) if needle
            else i18n.tf("всего сокращений: %d · своих: %d", total, own))

    def _update_slang_ui(self):
        if hasattr(self, "lb_slang_count"):
            own = len(slang.user_entries())
            total = len(slang.entries())
            self.lb_slang_count.setText(
                i18n.tf("всего сокращений: %d · своих: %d", total, own))

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

    # ------------------------------------------------------------ Проверка
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
            if module.requires:
                names = ", ".join(
                    (modules.get(dep).title_en if i18n.is_en() else modules.get(dep).title_ru)
                    for dep in module.requires if modules.get(dep)
                )
                dep_label = QLabel(i18n.t("Зависит от модуля: ") + names)
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
    def _widgets_to_cfg(self, cfg):
        self._write_widgets(cfg)
        return cfg

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
        self.header_sub.setText(i18n.tf(
            "Язык: %s · горячая клавиша: %s · частота автоперевода: каждое %d-е",
            langs.label(langs.code_of(cfg.get("target_lang", "it"))),
            _pretty_hotkey(cfg.get("hotkey", "F6")), int(cfg.get("auto_every", 4))))
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

    def _save(self):
        self._sync_glossary()
        self._sync_slang()
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
        self.saved.emit(cfg)
        self.accept()


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


def open_settings(cfg, parent=None, first_run=False):
    """Создаёт окно, загружает значения и возвращает его (без exec)."""
    win = SettingsWindow(cfg, parent=parent, first_run=first_run)
    win._load_widgets()
    win._load_language(langs.code_of(cfg.get("target_lang", "it")), reload_table=True)
    return win
