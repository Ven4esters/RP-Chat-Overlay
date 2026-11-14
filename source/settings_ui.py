"""settings_ui.py — окно настроек программы (PySide6).

Слева разделы, справа содержимое:
    Основные   — язык перевода, горячая клавиша, маркеры, лимиты;
    Автоперевод — частота, доля переводимого текста, слова-паразиты;
    Чат игры   — вставка/отправка, открытие чата клавишей T, задержки;
    Словарь    — правка фраз выбранного языка, импорт и экспорт;
    Проверка   — живой предпросмотр: что именно уйдёт в игру.

Изменения применяются только после кнопки «Сохранить».
"""
import csv
import io
import json
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                               QFileDialog, QFormLayout, QFrame, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QSpinBox,
                               QStackedWidget, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

import langs
from common import DATA, DEFAULT_CONFIG, log, save_config
from engine import (Engine, Glossary, glossary_path, load_glossary_data,
                    reset_glossary, save_glossary_data)
from translator import TranslateError, Translator

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
"""

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
        self.setMinimumSize(980, 660)
        self.resize(1020, 700)
        self.setStyleSheet(STYLE)
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
        for name, attr, maker in (("Основные", "page_main", self._page_main),
                                  ("Автоперевод", "page_auto", self._page_auto),
                                  ("Чат игры", "page_game", self._page_game),
                                  ("Словарь", "page_glossary", self._page_glossary),
                                  ("Проверка", "page_test", self._page_test)):
            item = QListWidgetItem(name)
            item.setSizeHint(item.sizeHint().expandedTo(item.sizeHint() + _sz(0, 10)))
            self.nav.addItem(item)
            page = maker()
            setattr(self, attr, page)
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self._nav_changed)
        self.nav.setCurrentRow(0)
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)
        root.addWidget(self._build_footer())

        self._load_language(self.glang, reload_table=True)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._do_preview)

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

    def _nav_changed(self, row):
        self._sync_glossary()
        self.stack.setCurrentIndex(row)
        if getattr(self, "page_test", None) is self.stack.currentWidget():
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
        self.cb_lang.setMinimumWidth(320)
        for code, name in langs.choices():
            self.cb_lang.addItem(name, code)
        self.cb_lang.setToolTip("Язык, на который переводится ваш текст")
        self.cb_lang.currentIndexChanged.connect(self._lang_changed_ui)
        row.addWidget(self.cb_lang)
        self.lb_lang_about = _hint("")
        row.addWidget(self.lb_lang_about, 1)
        cl.addLayout(row)
        self.lb_lang_note = QLabel("")
        self.lb_lang_note.setObjectName("warn")
        self.lb_lang_note.setWordWrap(True)
        cl.addWidget(self.lb_lang_note)
        row = QHBoxLayout()
        row.addWidget(QLabel("Что уходит в чат:"))
        self.cb_send_mode = QComboBox()
        self.cb_send_mode.addItem("Русская запись — как это читается", "reading")
        self.cb_send_mode.addItem("Текст на языке — для международных серверов", "native")
        self.cb_send_mode.setMinimumWidth(340)
        self.cb_send_mode.setToolTip(
            "«Русская запись» — в чат уходит «Чао» (кириллицей), как в исходной версии.\n"
            "«Текст на языке» — в чат уходит «Ciao» (для серверов, где читают латиницу).")
        self.cb_send_mode.currentIndexChanged.connect(lambda *_: self._do_preview())
        row.addWidget(self.cb_send_mode)
        row.addStretch(1)
        cl.addLayout(row)
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
        self.lb_hotkey.setObjectName("warn")
        self.lb_hotkey.setWordWrap(True)
        cl.addWidget(self.lb_hotkey)
        self.chk_show_settings = QCheckBox("Открывать это окно при запуске программы")
        cl.addWidget(self.chk_show_settings)
        lay.addWidget(card)

        # оформление текста
        card, cl = _card()
        cl.addWidget(_title("Текст и маркеры", "sec"))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        row = QHBoxLayout()
        self.ed_open = QLineEdit()
        self.ed_open.setMaxLength(2)
        self.ed_open.setFixedWidth(56)
        self.ed_close = QLineEdit()
        self.ed_close.setMaxLength(2)
        self.ed_close.setFixedWidth(56)
        row.addWidget(self.ed_open)
        row.addWidget(QLabel("…"))
        row.addWidget(self.ed_close)
        row.addStretch(1)
        w = QWidget()
        w.setLayout(row)
        form.addRow("Скобки перевода", w)
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
        self.lb_lang_about.setText(meta["about"])
        note = ""
        if not langs.reading(code):
            note = ("Для этого языка русская запись по звучанию не делается — "
                    "в оверлее показывается сам текст. Чтение есть только у фраз из словаря.")
        self.lb_lang_note.setText(note)
        self.lb_lang_note.setVisible(bool(note))
        self.glang = code
        if reload_table and hasattr(self, "tbl"):
            self._fill_table(self._doc(code))
            self.lb_glang.setText("Язык: " + langs.label(code, native=True))
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
        self.lb_glang.setStyleSheet("font-size:14px;font-weight:600;color:#dfe3ff;")
        head.addWidget(self.lb_glang)
        head.addStretch(1)
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Поиск по фразе или русскому значению…")
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.setFixedWidth(300)
        self.ed_search.textChanged.connect(self._filter_table)
        head.addWidget(self.ed_search)
        lay.addLayout(head)
        self.lb_gcount = _hint("")
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
        self.lb_gcount.setText(f"показано {shown} из {total}" if needle else f"всего фраз: {total}")

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
            "Для этого языка: " + (", ".join(names) if names else "список не задан") )
        has_pack = langs.get(self.glang).get("pack")
        self.lb_gcount.setText(f"всего фраз: {len(data.get('phrases') or {})}"
                               + ("" if has_pack else " · встроенного словаря нет"))

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
            QMessageBox.information(self, "Словарь", "Сначала выберите строку (строки).")
            return
        for r in rows:
            self.tbl.removeRow(r)
        self.glossary_changed = True
        self._collect_glossary()
        self._update_glossary_ui()

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Загрузить словарь", str(DATA), "Словари (*.json *.csv *.txt);;Все файлы (*)")
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except OSError as e:
            QMessageBox.warning(self, "Импорт", f"Не удалось прочитать файл:\n{e}")
            return
        phrases = {}
        try:
            if path.lower().endswith(".json"):
                obj = json.loads(text)
                src = obj.get("phrases") if isinstance(obj, dict) and "phrases" in obj else obj
                if not isinstance(src, dict):
                    raise ValueError("в JSON нужен объект «фраза: перевод»")
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
            QMessageBox.warning(self, "Импорт", f"Файл не подошёл:\n{e}")
            return
        if not phrases:
            QMessageBox.information(self, "Импорт", "В файле не нашлось фраз.")
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
            self, "Импорт",
            f"Загружено в «{langs.label(self.glang)}»: новых {added}, обновлено {replaced}.\n"
            f"Нажмите «Сохранить», чтобы применить.")

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить словарь", str(glossary_path(self.glang)),
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
            QMessageBox.warning(self, "Экспорт", f"Не удалось записать файл:\n{e}")
            return
        QMessageBox.information(self, "Экспорт", f"Словарь сохранён:\n{path}")

    def _reset_glossary(self):
        ans = QMessageBox.question(
            self, "Сбросить словарь",
            f"Вернуть встроенный словарь для «{langs.label(self.glang)}»?\n"
            f"Ваши добавленные фразы этого языка будут потеряны.")
        if ans != QMessageBox.StandardButton.Yes:
            return
        data = reset_glossary(self.glang)
        self.docs[self.glang] = data
        self.dirty.discard(self.glang)
        self.glossary_changed = False
        self._fill_table(data)

    # ------------------------------------------------------------ Проверка
    def _page_test(self):
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)
        lay.addWidget(_title("Проверка перевода", "sec"))
        lay.addWidget(_hint("Введите фразу по-русски — увидите, что именно уйдёт в игру и как это "
                            "читать вслух. Работает по текущим настройкам окна (до сохранения)."))
        self.ed_test = QLineEdit()
        self.ed_test.setPlaceholderText("например: Слушай, брат, мне срочно нужна помощь")
        self.ed_test.setClearButtonEnabled(True)
        self.ed_test.textChanged.connect(lambda: self._preview_timer.start(400))
        lay.addWidget(self.ed_test)

        card, cl = _card()
        self.lb_test_out = QLabel("—")
        self.lb_test_out.setWordWrap(True)
        self.lb_test_out.setStyleSheet("font-size:15px;")
        self.lb_test_read = QLabel("")
        self.lb_test_read.setWordWrap(True)
        self.lb_test_read.setObjectName("sub")
        self.lb_test_mode = QLabel("")
        self.lb_test_mode.setObjectName("hint")
        for w in (self.lb_test_out, self.lb_test_read, self.lb_test_mode):
            cl.addWidget(w)
        lay.addWidget(card)

        row = QHBoxLayout()
        b_filler = QPushButton("Слова-паразиты текущего языка")
        b_filler.clicked.connect(self._show_fillers)
        b_sample = QPushButton("Вставить пример")
        b_sample.clicked.connect(lambda: self.ed_test.setText(
            "Слушай, ну что ты, я же говорил, что приду позже"))
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
        QMessageBox.information(self, "Слова-паразиты — " + langs.label(self.glang),
                                "\n".join(rows) or "Для этого языка список не задан.")

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
        self.lb_test_mode.setText("перевожу…")
        threading.Thread(target=self._preview_job, args=(cfg, code, text), daemon=True).start()

    def _preview_job(self, cfg, code, text):
        try:
            data = self._doc(code)
            gl = Glossary(data, code)
            engine = Engine(cfg, gl, Translator(code))
            res = engine.process(text, auto=bool(cfg.get("auto_mode")), seed=1.0)
            ok, msg = True, ""
        except TranslateError as e:
            res, ok, msg = None, False, "нет сети и нет в словаре: " + str(e)[:120]
        except Exception as e:
            res, ok, msg = None, False, str(e)[:160]
        self._preview_done(res, ok, msg)

    def _preview_done(self, res, ok, msg):
        self._busy = False
        if not ok:
            self.lb_test_out.setText("—")
            self.lb_test_read.setText("")
            self.lb_test_mode.setObjectName("err")
            self.lb_test_mode.setText(msg)
            self.lb_test_mode.setStyleSheet("color:#ff6b6b;")
            return
        self.lb_test_mode.setStyleSheet("")
        native = str(self.cb_send_mode.currentData() or "reading") in (
            "native", "lang", "text", "target")
        sent = (res.italian or res.text) if native else (res.text or res.italian)
        other = res.text if native else res.italian
        self.lb_test_out.setText(sent or "—")
        self.lb_test_read.setText(("На языке: " + other) if other and other != sent else "")
        mode = "переведено" if res.translated else "без перевода (только маркеры/команды)"
        self.lb_test_mode.setText("Способ: " + mode)

    # ------------------------------------------------------------ данные
    def _widgets_to_cfg(self, cfg):
        self._write_widgets(cfg)
        return cfg

    def _write_widgets(self, cfg):
        cfg["target_lang"] = self.cb_lang.currentData() or "it"
        cfg["send_mode"] = self.cb_send_mode.currentData() or "reading"
        cfg["hotkey"] = self.ed_hotkey.text().strip().lower() or "f6"
        cfg["show_settings_on_start"] = bool(self.chk_show_settings.isChecked())
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
        return cfg

    def _load_widgets(self):
        cfg = self.cfg
        idx = self.cb_lang.findData(langs.code_of(cfg.get("target_lang", "it")))
        self.cb_lang.setCurrentIndex(max(0, idx))
        self.ed_hotkey.setText(_pretty_hotkey(cfg.get("hotkey", "F6")))
        self.chk_show_settings.setChecked(bool(cfg.get("show_settings_on_start", True)))
        mode = str(cfg.get("send_mode", "reading")).lower()
        self.cb_send_mode.setCurrentIndex(max(0, self.cb_send_mode.findData(
            "native" if mode in ("native", "lang", "text", "target") else "reading")))
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
        self.header_sub.setText(
            "Язык: %s · горячая клавиша: %s · частота автоперевода: каждое %d-е"
            % (langs.label(langs.code_of(cfg.get("target_lang", "it"))),
               _pretty_hotkey(cfg.get("hotkey", "F6")), int(cfg.get("auto_every", 4))))
        self._hotkey_changed()

    def _reset_all(self):
        ans = QMessageBox.question(
            self, "Сброс настроек",
            "Вернуть все настройки к заводским?\nСловари и горячая клавиша тоже станут "
            "стандартными (F6, итальянский).")
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.cfg = dict(DEFAULT_CONFIG)
        self.cfg.update({"hotkey": "F6", "target_lang": "it"})
        self._load_widgets()
        self._load_language("it", reload_table=True)
        self.footer_hint.setText("Настройки сброшены — нажмите «Сохранить», чтобы применить.")

    def _save(self):
        self._sync_glossary()
        if not self._hotkey_changed():
            self.nav.setCurrentRow(0)
            self.lb_hotkey.setObjectName("err")
            self.lb_hotkey.setStyleSheet("color:#ff6b6b;")
            QMessageBox.warning(self, "Горячая клавиша",
                                self.lb_hotkey.text() or "Проверьте горячую клавишу.")
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
            QMessageBox.critical(self, "Сохранение", f"Не удалось записать config.json:\n{e}")
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
