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

from PySide6.QtCore import (
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app import dlx as dlx_mod
from app import history, i18n, langs, modules, slang
from app import animations as anims
from app.config import (
    CONFIG_PATH,
    DATA,
    DEFAULT_CONFIG,
    SLANG_PATH,
    log,
    read_json,
    save_config,
    write_json,
)
from app.engine import (
    Engine,
    Glossary,
    glossary_path,
    load_glossary_data,
    reset_glossary,
    save_glossary_data,
)
from app.translator import TranslateError, Translator
from app.settings_widgets import (
    DragTable,
    KeyCapture,
    _card,
    _hint,
    _num_row,
    _small_spin,
    _pretty_hotkey,
    _title,
)

# Backwards-compatible export used by the existing settings UI test and callers.
from app.settings_widgets import ToggleSwitch as ToggleSwitch  # noqa: F401
from app.settings_style import style_sheet
from app.animations.settings.page import AnimationsSettingsMixin
from app.settings_dlx_ui import DlxSettingsMixin


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
            cells.append(
                (
                    item.text() if item is not None else None,
                    item.checkState() if item is not None and hasattr(item, "checkState") else None,
                    (widget.currentIndex(), widget.count())
                    if widget is not None and hasattr(widget, "currentIndex")
                    else None,
                )
            )
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
            len(cells) != table.columnCount() for cells in rows
        ):
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
    return {
        "cfg": cfg if isinstance(cfg, dict) else {},
        "docs": docs,
        "slang": slang_file if isinstance(slang_file, dict) else {},
    }


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


ALLOWED_PLAIN = {
    "insert",
    "delete",
    "home",
    "end",
    "pageup",
    "pagedown",
    "pause",
    "tab",
    "space",
    "`",
}
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
    ok_key = (
        k in ALLOWED_PLAIN
        or (len(k) == 1 and k.isascii() and k.isalnum())
        or (k.startswith("f") and k[1:].isdigit() and 1 <= int(k[1:]) <= 24)
    )
    if not ok_key:
        return False, f"Клавиша «{k}» не поддерживается."
    return True, ""


# Цвета, которые в погашенном разделе становятся серыми: и в styleSheet виджета,
# и в правилах таблицы стилей. Один список, чтобы «серый» был одним и тем же.
# Colours that turn grey inside a dimmed section, both in a widget stylesheet and
# in the shared rules. One list, so that "grey" stays the same grey.
_DIM_COLOR = "#8193ad"
_DIM_SOURCES = ("#dae6f7", "#a0b2ca", "#91a4bd", "#91a4bd", "#b5d0ff", "#f2f6fc", "#eaf1fa")


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


def _sep():
    s = QFrame()
    s.setObjectName("sep")
    s.setFrameShape(QFrame.Shape.HLine)
    return s


class SettingsWindow(DlxSettingsMixin, AnimationsSettingsMixin, QDialog):
    """Окно настроек. signal saved(cfg) — после сохранения."""

    saved = Signal(dict)
    anim_test_done = Signal(bool, str)  # ручная отправка /anim: успех и ответ игры
    # manual /anim send: success and reply

    def __init__(
        self, cfg, parent=None, first_run=False, dlx=None, anims_api=None, clear_cache=None
    ):
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
        self.clear_cache_callback = clear_cache
        self.cfg = dict(cfg)
        self.docs = {}  # код языка -> данные словаря
        self.dirty = set()  # языки с несохранёнными правками словаря
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
        self._hist_applying = False  # сейчас применяем снимок / applying a snapshot
        self._hist_busy = False  # запись шага идёт / recording a step
        self._hist_field = {}  # поле -> последнее значение / field metadata
        self._disk_cache = {"cfg": {}, "docs": {}}  # диск на момент снимка / disk view

        self.setWindowTitle("Настройки — FiveM Chat Overlay")
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
        self._views = []  # страницы в прокрутке, по порядку
        self._page_rows = {}  # имя страницы -> строка в списке слева
        self._anims_row = 0  # номер строки «Анимации» в списке разделов
        pages = (
            ("Основные", "page_main", self._page_main),
            ("Автоперевод", "page_auto", self._page_auto),
            ("Чат игры", "page_game", self._page_game),
            ("Словарь", "page_glossary", self._page_glossary),
            ("Сокращения", "page_slang", self._page_slang),
            ("Проверка", "page_test", self._page_test),
            ("DeepL", "page_dlx", self._page_dlx),
            ("Анимации", "page_anims", self._page_anims),
            ("Модули", "page_modules", self._page_modules),
        )
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
        self.setWindowTitle(i18n.t("Настройки — FiveM Chat Overlay"))
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
        w.setStyleSheet("QWidget#header { background:#121d2d; }")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 14, 20, 12)
        lay.setSpacing(2)
        self.header_title = _title(
            "Настройки" if not self.first_run else "Добро пожаловать в FiveM Chat Overlay", "h1"
        )
        lay.addWidget(self.header_title)
        self.header_sub = QLabel()
        self.header_sub.setProperty("no_i18n", True)
        self.header_sub.setObjectName("sub")
        lay.addWidget(self.header_sub)
        return w

    def _build_footer(self):
        w = QWidget()
        w.setObjectName("footer")
        w.setStyleSheet("QWidget#footer { background:#121d2d;border-top:1px solid #24344b; }")
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
            self.move(
                avail.x() + max(0, (avail.width() - w) // 2),
                avail.y() + max(0, (avail.height() - h) // 2),
            )

    def resizeEvent(self, e):
        """Меню разделов подстраивается под ширину окна, а не режет подписи.

        The section list adapts to the window width instead of cutting captions.
        """
        super().resizeEvent(e)
        if hasattr(self, "nav"):
            self.nav.setFixedWidth(
                max(132, min(int(210 * self._ui_scale()), int(self.width() * 0.28)))
            )

    def _ui_scale_changed(self, value=None):
        """Ползунок масштаба: сразу меняет шрифт и размер окна.

        The scale slider: it changes the font and the window size at once.
        """
        pct = int(value if value is not None else self.sp_ui_scale.value())
        k = min(max(pct / 100.0, 0.8), 1.8)
        self.cfg["ui_scale"] = round(k, 2)
        self.setStyleSheet(style_sheet(k))
        self._apply_adaptive_size(center=False)
        self.lb_ui_scale.setText(
            i18n.tf("Шрифт и отступы окна: %d %%. На маленьком экране поставьте меньше.", pct)
        )

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
        for val, text in (
            ("full", "Всё сообщение — на язык перевода"),
            ("partial", "Только выделенные слова и фразы (обычный режим)"),
            ("to_ru", "Ваш язык → русский"),
        ):
            self.cb_mode.addItem(text, val)
        self.cb_mode.setToolTip(
            "Полный: в чат уходит весь текст на языке перевода.\n"
            "Частичный: переводятся только выделенные +слова и фразы+, "
            "остальное — как написали.\n"
            "Обратный: пишете на своём языке, в чат уходит русский текст."
        )
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
            "«Текст на языке» — в чат уходит «Ciao» (для серверов, где читают латиницу)."
        )
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
        cl.addWidget(
            _hint(
                "Сокращения из живого чата раскрываются до перевода, поэтому "
                "в русском тексте сразу верные падеж, род и время: "
                "«brb» → «я скоро вернусь», «afk» → «я не за клавиатурой», "
                "«ty» → «спасибо». Если сервис всё же вернёт «afk» или «gg» "
                "латиницей, подставляется короткий русский вариант. "
                "В обратную сторону так же раскрываются русские сокращения: "
                "«спс» → «спасибо», «мб» → «может быть»."
            )
        )
        self.chk_slang = QCheckBox("Разворачивать сленг и сокращения")
        self.chk_slang.setObjectName("moduleToggle")
        self.chk_slang.toggled.connect(lambda on: self._mirror_own_flag("slang", on))
        self.chk_slang.setToolTip(
            "lol, brb, afk, idk, idc, omw, gtg, gg, wp, ez, ty, thx, np, pls, sry,\n"
            "btw, imo, tbh, ngl, rn, asap, wdym, wbu, sup, cya, gn, gm, tmrw, cuz,\n"
            "ppl, rp, ooc, ic и растянутый смех (looool, lmaooo, xD).\n"
            "Обратное направление: спс, пж, нз, мб, крч, ща, оч, тож, збс, норм, прив."
        )
        cl.addWidget(self.chk_slang)
        lay.addWidget(card)

        # горячая клавиша
        card, cl = _card()
        cl.addWidget(_title("Горячая клавиша", "sec"))
        self.lb_hotkey_hint = _hint("")
        self.lb_hotkey_hint.setProperty("no_i18n", True)
        cl.addWidget(self.lb_hotkey_hint)
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
            "или при масштабе Windows 150 % удобнее 120–130 %."
        )
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
        cl.addWidget(
            _hint("Внутри таких скобок текст переводится принудительно: «+привет+» → «Ciao».")
        )
        lay.addWidget(card)

        # Кэш переводов: локальные результаты не отправляются никуда.
        card, cl = _card()
        cl.addWidget(_title("Кэш переводов", "sec"))
        cl.addWidget(
            _hint(
                "Сохранённые переводы ускоряют повторные сообщения и доступны "
                "только на этом компьютере."
            )
        )
        self.cb_cache_cleanup = QComboBox()
        for value, label in (
            ("off", "Выключена"),
            ("daily", "Раз в день"),
            ("weekly", "Раз в неделю"),
            ("monthly", "Раз в месяц"),
        ):
            self.cb_cache_cleanup.addItem(label, value)
        self.cb_cache_cleanup.setToolTip(
            "Автоматически удалять сохранённые переводы с выбранным интервалом."
        )
        self.lb_cache_cleanup_hint = _hint(
            "Период отсчитывается от последней очистки. Ручная очистка начинает отсчёт заново."
        )
        cache_row = QHBoxLayout()
        cache_row.addWidget(QLabel("Автоочистка:"))
        cache_row.addWidget(self.cb_cache_cleanup)
        cache_row.addStretch(1)
        cl.addLayout(cache_row)
        cl.addWidget(self.lb_cache_cleanup_hint)
        self.btn_clear_cache = QPushButton("Очистить кэш переводов")
        self.btn_clear_cache.setToolTip(
            "Удалить все сохранённые переводы с этого компьютера. Новые переводы "
            "будут кэшироваться снова."
        )
        self.btn_clear_cache.clicked.connect(self._clear_translation_cache)
        cl.addWidget(self.btn_clear_cache, alignment=Qt.AlignmentFlag.AlignLeft)
        cl.addWidget(
            _hint(
                "Очистка не затрагивает словари и настройки. Автоочистка сохранится "
                "после нажатия «Сохранить»."
            )
        )
        lay.addWidget(card)

        card, cl = _card()
        cl.addWidget(_title("Диагностика приложения", "sec"))
        self.chk_usage_report = QCheckBox("Собирать отчёт производительности")
        self.chk_usage_report.setToolTip(
            "Измерять длительность основных операций и считать их количество и ошибки."
        )
        cl.addWidget(self.chk_usage_report)
        cl.addWidget(
            _hint(
                "По умолчанию выключено. При включении создаётся локальный файл "
                "data/usage-report.md с агрегатами времени, количеством операций и "
                "ошибок. Текст чата, имена игроков и названия игр не записываются; "
                "отчёт не отправляется автоматически."
            )
        )
        lay.addWidget(card)
        lay.addStretch(1)
        return page

    def _clear_translation_cache(self):
        if self.clear_cache_callback is None:
            QMessageBox.information(
                self,
                i18n.t("Кэш переводов"),
                i18n.t("Очистка кэша доступна после запуска приложения."),
            )
            return
        answer = QMessageBox.question(
            self,
            i18n.t("Очистить кэш переводов?"),
            i18n.t("Все сохранённые переводы будут удалены. Продолжить?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.clear_cache_callback()
        except OSError as error:
            QMessageBox.warning(
                self,
                i18n.t("Кэш переводов"),
                i18n.t("Не удалось очистить файл кэша:\n") + str(error),
            )
            return
        QMessageBox.information(self, i18n.t("Кэш переводов"), i18n.t("Кэш переводов очищен."))

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
                for dep in module.requires
                if modules.get(dep)
            )
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
                self.lb_ui_scale.setText(
                    i18n.tf(
                        "Шрифт и отступы окна: %d %%. На маленьком экране поставьте меньше.",
                        int(self.sp_ui_scale.value()),
                    )
                )
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
            self.lb_mode.setText(
                i18n.t(
                    "Режим переводчика: пишете на своём языке — в чат уходит русский текст. "
                    "Переводится каждое сообщение целиком, включая действия *...*; команды "
                    "/… остаются как есть. Автоперевод, слова-паразиты и выбор «что уходит "
                    "в чат» здесь не работают."
                )
            )
        elif mode == "full":
            self.lb_mode.setText(
                i18n.t(
                    "Полный перевод: в чат уходит всё сообщение на языке перевода. Словарь "
                    "важнее сервисов, слова-паразиты и автоперевод не участвуют, скобки "
                    "+…+ не нужны — переводится всё."
                )
            )
        else:
            self.lb_mode.setText(
                i18n.t(
                    "Обычный режим: в чат уходит ваш русский текст, а переведёнными — только "
                    "выделенные +слова и фразы+ и то, что выбрал автоперевод. Работают "
                    "слова-паразиты и выбор «что уходит в чат»."
                )
            )

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
        hotkey = _pretty_hotkey(self.ed_hotkey.text().strip() or "F6")
        chat_key = (self.ed_chatkey.text().strip() or "T").upper()
        self.lb_hotkey_hint.setText(
            i18n.tf(
                "Клавиша «%s» открывает оверлей; чат игры перед этим открывается "
                "клавишей «%s». При открытом оверлее нажатие не закрывает окно.",
                hotkey,
                chat_key,
            )
        )
        ok, warn = check_hotkey(self.ed_hotkey.text())
        self.lb_hotkey.setText("" if ok else warn)
        self.lb_hotkey.setObjectName("warn")
        if hasattr(self, "header_sub"):
            self._update_header()
        return ok

    def _chatkey_changed(self, *_args):
        key = (self.ed_chatkey.text().strip() or "T").upper()
        self.chk_chat_first.setText(
            i18n.tf("Сначала открывать чат игры (клавиша %s), потом оверлей", key)
        )
        if hasattr(self, "lb_hotkey_hint"):
            self._hotkey_changed()

    def _lang_changed_ui(self, *_):
        code = self.cb_lang.currentData()
        self._sync_glossary()
        self._load_language(code, reload_table=True)
        self._update_header()
        self._do_preview()

    def _update_header(self):
        self.header_sub.setText(
            i18n.tf(
                "Язык: %s · горячая клавиша: %s · частота автоперевода: каждое %d-е",
                langs.label(langs.code_of(self.cb_lang.currentData() or "it")),
                _pretty_hotkey(self.ed_hotkey.text()),
                int(self.sp_every.value()),
            )
        )

    def _load_language(self, code, reload_table=False):
        """Показывает описание языка и (при необходимости) словарь этого языка.

        Shows the language description and, when needed, that language's glossary.
        """
        code = langs.code_of(code)
        meta = langs.get(code)
        about = (
            i18n.t(meta["about_en"]) if (i18n.is_en() and meta.get("about_en")) else meta["about"]
        )
        self.lb_lang_about.setText(about)
        note = ""
        if not langs.reading(code):
            note = i18n.t(
                "Для этого языка русская запись по звучанию не делается — "
                "в оверлее показывается сам текст. Чтение есть только "
                "у фраз из словаря."
            )
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
        cl.addWidget(
            _hint(
                "Перевод вставляется в обычную русскую речь, чтобы она выглядела живой. "
                "Например: «мне срочно нужна помощь» → «мне срочно нужна Aiutami»."
            )
        )
        self.chk_auto = QCheckBox("Включить автоперевод")
        self.chk_auto.setObjectName("moduleToggle")
        self.chk_auto.toggled.connect(lambda on: self._mirror_own_flag("autotranslate", on))
        cl.addWidget(self.chk_auto)
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.sp_every = _small_spin(QSpinBox(), 2, 20, "-е сообщение", 230, prefix="каждое ")
        self.sp_every.setToolTip("Как часто переводить: одно сообщение из N")
        form.addRow("Частота", _num_row(self.sp_every))
        self.cb_pos = QComboBox()
        self.cb_pos.setMaximumWidth(340)
        for val, text in (
            ("last", "последнее в серии (каждое N-е)"),
            ("first", "первое в серии"),
            ("random", "случайное в серии"),
        ):
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
        self.chk_send.setObjectName("moduleToggle")
        self.chk_send.toggled.connect(lambda on: self._mirror_own_flag("game_send", on))
        cl.addWidget(self.chk_send)
        self.chk_chat_first = QCheckBox()
        self.chk_chat_first.setProperty("no_i18n", True)
        self.chk_chat_first.setToolTip(
            "Окружающие видят, что вы печатаете, а не стоите без действия"
        )
        cl.addWidget(self.chk_chat_first)
        self.chk_submit = QCheckBox("Отправлять сразу (Enter в игре)")
        cl.addWidget(self.chk_submit)
        lay.addWidget(card)

        card, cl = _card()
        cl.addWidget(_title("Клавиша чата и задержки", "sec"))
        cl.addWidget(
            _hint(
                "Задержки нужны, чтобы игра успевала открыть чат и вставить текст. "
                "Если сообщения пропадают — увеличьте «после чата»."
            )
        )
        cl.addWidget(
            _hint(
                "Перед вставкой поле ввода чата полностью очищается (Ctrl+A, "
                "Backspace): остаток прошлой строки не приклеится к команде."
            )
        )
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.ed_chatkey = QLineEdit()
        self.ed_chatkey.setMaxLength(3)
        self.ed_chatkey.setFixedWidth(72)
        self.ed_chatkey.setPlaceholderText("T")
        self.ed_chatkey.setToolTip("Одна буква/цифра или функциональная клавиша F1–F24.")
        self.ed_chatkey.textChanged.connect(self._chatkey_changed)
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
        self.lb_glang.setStyleSheet("font-size:14px;font-weight:600;color:#dae6f7;")
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
        self.tbl.setHorizontalHeaderLabels(
            ["Паразит", "Фраза", "Русская запись", "Русские значения (через ;)"]
        )
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
        lay.addWidget(
            _hint(
                "Строки перетаскиваются мышью — порядок сохраняется вместе со "
                "словарём. Он важен: если у двух фраз одинаковое русское значение, "
                "срабатывает та, что ниже в таблице."
            )
        )

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
        lay.addWidget(
            _hint(
                "Галочка в первой колонке — слово-паразит: фраза переводится в каждом "
                "сообщении, даже когда автоперевод ещё не сработал. Выбор сохраняется "
                "вместе со словарём. Значения — это то, что вы печатаете по-русски; "
                "«е/ё» и «и/й» считаются одной буквой."
            )
        )
        return page

    def _fill_table(self, data):
        self.tbl.blockSignals(True)
        phrases = data.get("phrases") or {}
        fillers = {
            self._norm_key(f.get("target"))
            for f in (data.get("_fillers") or [])
            if isinstance(f, dict)
        }
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
            mark.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            mark.setCheckState(
                Qt.CheckState.Checked
                if self._norm_key(phrase) in fillers
                else Qt.CheckState.Unchecked
            )
            mark.setToolTip(i18n.t("Переводить эту фразу в каждом сообщении"))
            items = [
                mark,
                QTableWidgetItem(str(phrase)),
                QTableWidgetItem(ru.strip()),
                QTableWidgetItem(meanings.strip().lstrip(";").strip()),
            ]
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
        self.lb_gcount.setText(
            i18n.tf("показано %d из %d", shown, total)
            if needle
            else i18n.tf("всего фраз: %d", total)
        )

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
        self._hist_shadow = self._hist_state()  # состояние до перетаскивания
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
            i18n.tf("Для этого языка: %s", ", ".join(names) if names else i18n.t("список не задан"))
        )
        has_pack = langs.get(self.glang).get("pack")
        self.lb_gcount.setText(
            i18n.tf("всего фраз: %d", len(data.get("phrases") or {}))
            + ("" if has_pack else i18n.t(" · встроенного словаря нет"))
        )

    def _add_phrase(self):
        self.tbl.blockSignals(True)
        r = self.tbl.rowCount()
        self.tbl.insertRow(r)
        mark = QTableWidgetItem("")
        mark.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
        )
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
            QMessageBox.information(
                self, i18n.t("Словарь"), i18n.t("Сначала выберите строку (строки).")
            )
            return
        for r in rows:
            self.tbl.removeRow(r)
        self.glossary_changed = True
        self._collect_glossary()
        self._update_glossary_ui()

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            i18n.t("Загрузить словарь"),
            str(DATA),
            i18n.t("Словари (*.json *.csv *.txt);;Все файлы (*)"),
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except OSError as e:
            QMessageBox.warning(
                self, i18n.t("Импорт"), i18n.t("Не удалось прочитать файл:\n") + str(e)
            )
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
            QMessageBox.warning(self, i18n.t("Импорт"), i18n.t("Файл не подошёл:\n") + str(e))
            return
        if not phrases:
            QMessageBox.information(self, i18n.t("Импорт"), i18n.t("В файле не нашлось фраз."))
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
            self,
            i18n.t("Импорт"),
            i18n.tf(
                "Загружено в «%s»: новых %d, обновлено %d.\nНажмите «Сохранить», чтобы применить.",
                langs.label(self.glang),
                added,
                replaced,
            ),
        )

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            i18n.t("Сохранить словарь"),
            str(glossary_path(self.glang)),
            "JSON (*.json);;CSV (*.csv)",
        )
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
                Path(path).write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        except OSError as e:
            QMessageBox.warning(
                self, i18n.t("Экспорт"), i18n.t("Не удалось записать файл:\n") + str(e)
            )
            return
        QMessageBox.information(self, i18n.t("Экспорт"), i18n.t("Словарь сохранён:\n") + str(path))

    def _reset_glossary(self):
        ans = QMessageBox.question(
            self,
            i18n.t("Сбросить словарь"),
            i18n.tf(
                "Вернуть встроенный словарь для «%s»?\nВаши добавленные фразы "
                "этого языка будут потеряны.",
                langs.label(self.glang),
            ),
        )
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
            "это обратное направление."
        )
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
            ["Сокращение", "Разворот (полная фраза)", "Русский вариант"]
        )
        for c in range(3):
            self.tbl_slang.horizontalHeader().setSectionResizeMode(
                c, QHeaderView.ResizeMode.Stretch
            )
        self.tbl_slang.verticalHeader().setVisible(False)
        self.tbl_slang.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_slang.itemChanged.connect(self._slang_edited)
        lay.addWidget(self.tbl_slang, 1)
        lay.addWidget(
            _hint(
                "Строки перетаскиваются мышью — порядок запоминается в настройках "
                "и остаётся таким при следующем открытии окна."
            )
        )

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

        lay.addWidget(
            _hint(
                "У каждого языка своя таблица: выберите его в списке сверху, правки "
                "запоминаются отдельно и не мешают друг другу. Свои сокращения работают "
                "так же, как встроенные, и перекрывают их: «afaik» → «as far as I know» → "
                "«насколько знаю». Во второй колонке — полная фраза на языке собеседника: её "
                "получает переводчик, поэтому падеж и род выходят верными. В третьей — "
                "короткая подстановка, если сервис вернул латиницу. Пустые колонки "
                "выключают сокращение. Смайлы вроде «xD» и «x)» не трогаются никогда."
            )
        )
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
            items = [QTableWidgetItem(token), QTableWidgetItem(expand), QTableWidgetItem(ru)]
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
            i18n.tf("Показано: %d из %d\nСвоих: %d", shown, total, own)
            if needle
            else i18n.tf("Всего: %d\nСвоих: %d", total, own)
        )

    def _update_slang_ui(self):
        if hasattr(self, "lb_slang_count"):
            own = len(slang.user_entries(self._slang_lang))
            total = len(slang.entries(self._slang_lang))
            self.lb_slang_count.setText(i18n.tf("Всего: %d\nСвоих: %d", total, own))
        if hasattr(self, "lb_slang_lang_hint"):
            self.lb_slang_lang_hint.setText(
                i18n.t("Таблица языка сервера: разворот уходит в переводчик до перевода.")
            )

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
                continue  # встроенное не тронуто / untouched
            slate[token] = [expand, ru]
        for token in built:
            if token not in rows:
                slate[token] = ["", ""]  # выключено игроком / switched off
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
            (
                self.tbl_slang.item(row, 0).text().lstrip("★ ").strip()
                if self.tbl_slang.item(row, 0)
                else ""
            )
            for row in range(self.tbl_slang.rowCount())
        ]
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
        slang.save_languages(
            {code: self._slate_of(code, rows) for code, rows in self._slang_drafts.items()}
        )
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
            QMessageBox.information(
                self, i18n.t("Сокращения"), i18n.t("Сначала выберите строку (строки).")
            )
            return
        for r in rows:
            self.tbl_slang.removeRow(r)
        self._collect_slang()
        self._update_slang_ui()

    def _import_slang(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            i18n.t("Загрузить сокращения"),
            str(DATA),
            i18n.t("Сокращения (*.json *.csv *.txt);;Все файлы (*)"),
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except OSError as e:
            QMessageBox.warning(
                self, i18n.t("Импорт"), i18n.t("Не удалось прочитать файл:\n") + str(e)
            )
            return
        loaded = {}
        foreign = {}  # запись чужого языка -> его код / other languages
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
                    loaded[row[0].strip()] = [
                        row[1].strip(),
                        row[2].strip() if len(row) > 2 else "",
                    ]
        except Exception as e:
            QMessageBox.warning(self, i18n.t("Импорт"), i18n.t("Файл не подошёл:\n") + str(e))
            return
        if not loaded and not foreign:
            QMessageBox.information(
                self, i18n.t("Импорт"), i18n.t("В файле не нашлось сокращений.")
            )
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
            self,
            i18n.t("Импорт"),
            i18n.tf(
                "Загружено сокращений: %d (новых %d).\nНажмите «Сохранить», чтобы применить.",
                total,
                added,
            ),
        )

    def _export_slang(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            i18n.t("Сохранить сокращения"),
            str(DATA / "slang-export.json"),
            "JSON (*.json);;CSV (*.csv)",
        )
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
                payload = {
                    "custom": {
                        token: {"lang": code, "expand": expand, "ru": ru}
                        for token, expand, ru, _o in data
                        if token in own
                    }
                }
                if not payload["custom"]:
                    payload = {
                        "custom": {
                            token: {"lang": code, "expand": expand, "ru": ru}
                            for token, expand, ru, _o in data
                        }
                    }
                Path(path).write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        except OSError as e:
            QMessageBox.warning(
                self, i18n.t("Экспорт"), i18n.t("Не удалось записать файл:\n") + str(e)
            )
            return
        QMessageBox.information(
            self, i18n.t("Экспорт"), i18n.t("Сокращения сохранены:\n") + str(path)
        )

    def _reset_slang(self):
        ans = QMessageBox.question(
            self,
            i18n.t("Сбросить сокращения"),
            i18n.tf(
                "Вернуть встроенный список сокращений для языка «%s»?\n"
                "Ваши добавления на этом языке будут потеряны, остальные "
                "языки не изменятся.",
                self.cb_slang_lang.currentText(),
            ),
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        code = self._slang_lang
        self._slang_drafts.pop(code, None)
        slang.set_user({}, code)
        self._slang_pending = True
        self._fill_slang()

    # ------------------------------------------------------------ DeepL
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
        cl.addWidget(
            _hint(
                "Каждую часть программы можно выключить. Данные при этом "
                "не теряются: словари, сокращения и настройки остаются "
                "на месте, а программу можно вернуть к полному набору "
                "в любой момент."
            )
        )

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
            desc.setStyleSheet("color:#a0b2ca;font-size:12px;")
            rl.addWidget(desc)
            self._module_rows.append((box, desc, module))
            if module.requires:
                names = ", ".join(
                    (modules.get(dep).title_en if i18n.is_en() else modules.get(dep).title_ru)
                    for dep in module.requires
                    if modules.get(dep)
                )
                dep_label = QLabel(i18n.t("Зависит от модуля: ") + names)
                dep_label.setProperty("no_i18n", True)
                self._module_deps.append((dep_label, module))
                dep_label.setWordWrap(True)
                dep_label.setStyleSheet("color:#91a4bd;font-size:11px;")
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
            "border-radius:8px; padding:10px 12px;"
        )
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
                names = ", ".join(
                    (modules.get(dep).title_en if i18n.is_en() else modules.get(dep).title_ru)
                    for dep in missing
                    if modules.get(dep)
                )
                answer = QMessageBox.question(
                    self,
                    i18n.t("Нужен ещё один модуль"),
                    i18n.tf(
                        "«%s» не работает без модуля: %s.\n\nВключить его?",
                        module.title_en if i18n.is_en() else module.title_ru,
                        names,
                    ),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
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
        return {
            row: self.HIST_MAIN,
            3: "glossary",  # страница «Словарь»
            7: "anims",
        }.get(row, self.HIST_MAIN)

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
            "tables": {name: _table_state(table) for name, table in self._hist_tables()},
            # Черновики сокращений по языкам: таблица показывает один язык, но
            # правки другого тоже обязаны откатываться.
            # The abbreviation drafts per language: the table shows one language,
            # yet the other languages' edits must roll back too.
            "slang_drafts": {
                code: {token: list(pair) for token, pair in rows.items()}
                for code, rows in self._slang_drafts.items()
            },
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
        return [
            (name, getattr(self, name))
            for name in ("tbl", "tbl_slang", "tbl_anims")
            if hasattr(self, name)
        ]

    def _hist_widgets(self):
        """Поля, которые входят в историю: ключ -> виджет.

        The fields that take part in the history: key to widget.
        """
        names = (
            "cb_lang",
            "cb_mode",
            "cb_send_mode",
            "cb_ui_lang",
            "ed_hotkey",
            "ed_open",
            "ed_close",
            "sp_max",
            "sp_debounce",
            "ed_chatkey",
            "sp_focus",
            "sp_opendelay",
            "sp_ui_scale",
            "chk_show_settings",
            "chk_filler",
            "chk_prefer",
            "sp_every",
            "cb_pos",
            "sp_frag",
            "sp_min",
            "sp_maxw",
            "chk_slang",
            "chk_auto",
            "chk_send",
            "chk_submit",
            "chk_dlx",
            "ed_dlx_pro",
            "ed_dlx_proxy",
            "ed_dlx_url",
            "ed_dlx_url_token",
            "sp_dlx_port",
        )
        return [(name, getattr(self, name)) for name in names if hasattr(self, name)]

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
                label.setText(i18n.t("Ctrl+Z — отменить правку в разделе · Ctrl+Y — вернуть"))
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
        can, step = (section.can_undo, section.undo) if undo else (section.can_redo, section.redo)
        if not can():
            return False
        state = step()
        if state is None:
            return False
        drafts_before = {
            code: {token: list(pair) for token, pair in rows.items()}
            for code, rows in self._slang_drafts.items()
        }
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
        self._slang_drafts = {
            code: {token: list(pair) for token, pair in rows.items()}
            for code, rows in (state.get("slang_drafts") or {}).items()
        }
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
        # Используем тот же путь, что и на странице «Модули»: он предлагает
        # включить родительский модуль, если без него текущий модуль не работает.
        # Use the same path as the Modules page so enabling a child can offer to
        # turn on its required parent instead of silently leaving it dimmed.
        self._module_toggled(key, bool(checked))

    def _mode_flag_tip(self, key):
        """Подсказка для флажка, который в этом режиме не нужен.

        The tooltip of a checkbox the current mode does not need.
        """
        module = modules.get(key)
        if module is None or not modules.needed_in_other_mode(self._cfg_now(), key):
            return ""
        return i18n.tf(
            "«%s» нужен только в частичном режиме перевода. В других режимах он ничего не делает.",
            module.title_en if i18n.is_en() else module.title_ru,
        )

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
            own_switch = self._own_module_box(module.key)
            for child in page.findChildren(QWidget):
                # Подсказку и переключатель самого модуля не блокируем: иначе
                # выключенный модуль нельзя было бы включить со своей страницы.
                # Keep the hint and the module's own switch interactive, or the
                # module could not be enabled from its own settings page.
                if child.objectName() == "moduleOff":
                    continue
                if child is own_switch:
                    child.setEnabled(True)
                    continue
                child.setEnabled(active and not other_mode)
            page.setProperty("moduleOff", not active or other_mode)
            banner = page.findChild(QLabel, "moduleOff")
            if banner is not None:
                banner.setVisible(not active or other_mode)
                if other_mode:
                    banner.setText(
                        i18n.tf(
                            "Модуль «%s» в этом режиме не нужен: он работает только в "
                            "частичном режиме. Переключите режим на странице «Основные» — "
                            "настройки вернутся.",
                            module.title_en if i18n.is_en() else module.title_ru,
                        )
                    )
                elif not active:
                    banner.setText(
                        i18n.tf(
                            "Модуль «%s» выключен — настройки раздела недоступны. "
                            "Включите его здесь или в разделе «Модули».",
                            module.title_en if i18n.is_en() else module.title_ru,
                        )
                    )
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
        for child in page.findChildren(QWidget) if page is not None else []:
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
        # Динамический селектор задан на родительской странице, но Qt не всегда
        # пересчитывает его для уже созданных потомков после смены свойства.
        # Переполируем всю страницу сейчас, а не ждём следующей перестройки
        # таблицы (например, добавления правила анимации).
        # The dynamic selector belongs to the page, but Qt does not always
        # recalculate it for existing descendants when the property changes.
        # Repolish the whole page now instead of waiting for a later table rebuild
        # (such as adding an animation rule).
        widgets = [page, *page.findChildren(QWidget)] if page is not None else []
        if view is not None:
            widgets.extend((view, view.viewport()))
        for widget in widgets:
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
        item.setForeground(QColor("#8799b2") if off else QColor("#bdcbe0"))

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
        self.lb_test_hint = _hint("")  # текст зависит от направления (см. ниже)
        self.lb_test_hint.setProperty("no_i18n", True)
        lay.addWidget(self.lb_test_hint)
        row_dir = QHBoxLayout()
        row_dir.addWidget(QLabel("Направление:"))
        self.cb_test_dir = QComboBox()
        self.cb_test_dir.addItem("Всё сообщение → выбранный язык", "full")
        self.cb_test_dir.addItem("Только выделенные слова и фразы → выбранный язык", "partial")
        self.cb_test_dir.addItem("Ваш язык → русский", "to_ru")
        self.cb_test_dir.setMinimumWidth(200)
        self.cb_test_dir.setToolTip(
            "Проверить можно оба направления. «Ваш язык → русский» показывает, что "
            "уйдёт в чат игры в режиме для иностранного игрока: сокращения "
            "раскрываются, служебные команды остаются как есть."
        )
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
        QMessageBox.information(
            self,
            i18n.tf("Слова-паразиты — %s", langs.label(self.glang)),
            "\n".join(rows) or i18n.t("Для этого языка список не задан."),
        )

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
                self.lb_test_hint.setText(
                    i18n.t(
                        "Введите фразу по-русски — увидите, что уйдёт в игру в полном "
                        "режиме: весь текст на языке перевода, без +скобок+."
                    )
                )
            self.ed_test.setPlaceholderText(
                i18n.t("например: Слушай, брат, мне срочно нужна помощь")
            )
            self.lb_test_dir.setText(
                i18n.t("Проверяем полный режим: в чат уйдёт всё сообщение на языке перевода.")
            )
            if not silent:
                self._do_preview()
            return
        if mode == "partial":
            if hasattr(self, "lb_test_hint"):
                self.lb_test_hint.setText(
                    i18n.t(
                        "Введите фразу по-русски — увидите, что уйдёт в игру в обычном "
                        "режиме: переводятся только выделенные слова и фразы и паразиты."
                    )
                )
            self.ed_test.setPlaceholderText(
                i18n.t("например: Слушай, брат, мне срочно нужна помощь")
            )
            self.lb_test_dir.setText(
                i18n.t(
                    "Проверяем обычный режим: в чат уйдёт ваш текст, а переведёнными — "
                    "только выделенные слова и фразы."
                )
            )
            if not silent:
                self._do_preview()
            return
        if self._test_reverse():
            if hasattr(self, "lb_test_hint"):
                self.lb_test_hint.setText(
                    i18n.t(
                        "Введите фразу на языке сервера — увидите, что именно уйдёт в чат "
                        "игры на русском. Работает по текущим настройкам окна (до сохранения)."
                    )
                )
            self.ed_test.setPlaceholderText(i18n.t("например: brb, I'm afk, ty"))
            self.lb_test_dir.setText(
                i18n.t("Проверяем режим для иностранного игрока: в чат уйдёт перевод на русский.")
            )
        else:
            if hasattr(self, "lb_test_hint"):
                self.lb_test_hint.setText(
                    i18n.t(
                        "Введите фразу по-русски — увидите, что именно уйдёт в игру и как это "
                        "читать вслух. Работает по текущим настройкам окна (до сохранения)."
                    )
                )
            self.ed_test.setPlaceholderText(
                i18n.t("например: Слушай, брат, мне срочно нужна помощь")
            )
            self.lb_test_dir.setText(
                i18n.t("Проверяем обычный режим: в чат уйдёт текст на выбранном языке перевода.")
            )
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
        self._collect_slang()  # проверка учитывает свои сокращения
        self.lb_test_mode.setStyleSheet("")
        self.lb_test_mode.setText(i18n.t("перевожу…"))
        # если сервисы отвечают долго — честно об этом пишем, а не молчим
        # when the services answer slowly, say so honestly instead of staying silent
        if not hasattr(self, "_slow_timer"):
            self._slow_timer = QTimer(self)
            self._slow_timer.setSingleShot(True)
            self._slow_timer.timeout.connect(
                lambda: self.lb_test_mode.setText(i18n.t("перевожу… (сервисы заняты)"))
            )
        self._slow_timer.start(5000)
        threading.Thread(
            target=self._preview_job, args=(cfg, code, text, self._test_mode()), daemon=True
        ).start()

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
                payload = {
                    "out": res.text or "—",
                    "sub": (i18n.t("Исходное сообщение: ") + res.native)
                    if res.native and res.native != res.text
                    else "",
                    "note": i18n.t("Способ: переведено в чат игры")
                    if res.translated
                    else i18n.t("Способ: без перевода (одна команда)"),
                }
            elif mode == "full":
                res = engine.process_full(text)
                sent = res.native or res.text
                other = ""
            else:
                res = engine.process(text, auto=bool(cfg.get("auto_mode")), seed=1.0)
                native = str(cfg.get("send_mode") or "reading") in (
                    "native",
                    "lang",
                    "text",
                    "target",
                )
                sent = (res.native or res.text) if native else (res.text or res.native)
                other = res.text if native else res.native
            if mode != "to_ru":
                payload = {
                    "out": sent or "—",
                    "sub": (i18n.t("На языке: ") + other) if other and other != sent else "",
                    "note": i18n.t("Способ: ")
                    + (
                        i18n.t("переведено")
                        if res.translated
                        else i18n.t("без перевода (только маркеры/команды)")
                    ),
                }
            ok, msg = True, ""
        except TranslateError as e:
            payload, ok, msg = (
                None,
                False,
                i18n.tf(
                    "Перевод не удался: %s. Повторите через минуту — проверка попробует "
                    "другой сервис, а в чате перевод пойдёт по словарю.",
                    str(e)[:140],
                ),
            )
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
        if hasattr(self, "chk_usage_report"):
            cfg["usage_report_enabled"] = bool(self.chk_usage_report.isChecked())
        if hasattr(self, "cb_cache_cleanup"):
            cfg["cache_cleanup_interval"] = self.cb_cache_cleanup.currentData() or "off"
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
        cfg["game_chat_key"] = (self.ed_chatkey.text().strip() or "T").upper()
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
        if hasattr(self, "chk_usage_report"):
            self.chk_usage_report.setChecked(bool(cfg.get("usage_report_enabled", False)))
        if hasattr(self, "cb_cache_cleanup"):
            self.cb_cache_cleanup.setCurrentIndex(
                max(0, self.cb_cache_cleanup.findData(cfg.get("cache_cleanup_interval", "off")))
            )
        if hasattr(self, "sp_ui_scale"):
            self.sp_ui_scale.blockSignals(True)
            self.sp_ui_scale.setValue(int(round(self._ui_scale() * 100)))
            self.sp_ui_scale.blockSignals(False)
            self._ui_scale_changed(self.sp_ui_scale.value())
        mode = str(cfg.get("send_mode", "reading")).lower()
        self.cb_send_mode.setCurrentIndex(
            max(
                0,
                self.cb_send_mode.findData(
                    "native" if mode in ("native", "lang", "text", "target") else "reading"
                ),
            )
        )
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
            self.cb_test_dir.setCurrentIndex(max(0, self.cb_test_dir.findData(test_mode)))
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
        self.ed_chatkey.setText(str(cfg.get("game_chat_key", "t"))[:3])
        self._chatkey_changed()
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
            self.chk_dlx_sysproxy.setChecked(bool(cfg.get("dlx_use_system_proxy", True)))
            self._dlx_proxy_note()
            self.ed_dlx_pro.setText(str(cfg.get("dlx_pro_token") or ""))
            self.ed_dlx_url.setText(str(cfg.get("dlx_url") or ""))
            self.ed_dlx_url_token.setText(str(cfg.get("dlx_url_token") or ""))
            self._dlx_refresh()
        self.header_sub.setText(
            i18n.tf(
                "Язык: %s · горячая клавиша: %s · частота автоперевода: каждое %d-е",
                langs.label(langs.code_of(cfg.get("target_lang", "it"))),
                _pretty_hotkey(cfg.get("hotkey", "F6")),
                int(cfg.get("auto_every", 4)),
            )
        )
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
            self,
            i18n.t("Сброс настроек"),
            i18n.t(
                "Вернуть все настройки к заводским?\nСловари и горячие клавиши тоже станут "
                "стандартными (F6 для оверлея, T для чата, итальянский)."
            ),
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.cfg = dict(DEFAULT_CONFIG)
        self.cfg.update({"hotkey": "F6", "game_chat_key": "t", "target_lang": "it"})
        self._load_widgets()
        self._load_language("it", reload_table=True)
        self.footer_hint.setText(
            i18n.t("Настройки сброшены — нажмите «Сохранить», чтобы применить.")
        )

    def _is_dirty(self):
        """Есть ли неприменённые правки / whether there are unsaved edits."""
        try:
            cur = dict(self.cfg)
            self._write_widgets(cur)
        except Exception:  # окно ещё не собрано целиком
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
                self,
                i18n.t("Несохранённые изменения"),
                i18n.t("В настройках есть неприменённые изменения.\nЗакрыть окно без сохранения?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
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
                    self,
                    i18n.t("Анимации"),
                    i18n.tf(
                        "Правило в строке %d: %s. Исправьте его или удалите — "
                        "без этого настройки не сохранятся.",
                        index + 1,
                        i18n.t(problem),
                    ),
                )
                return
            if not stop_ok:
                self.nav.setCurrentRow(self._anims_row)
                QMessageBox.warning(self, i18n.t("Анимации"), self.lb_anim_stop.text())
                return
        if not self._hotkey_changed():
            self.nav.setCurrentRow(0)
            self.lb_hotkey.setObjectName("err")
            self.lb_hotkey.setStyleSheet("color:#ff6b6b;")
            QMessageBox.warning(
                self,
                i18n.t("Горячая клавиша"),
                self.lb_hotkey.text() or i18n.t("Проверьте горячую клавишу."),
            )
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
            QMessageBox.critical(
                self, i18n.t("Сохранение"), i18n.t("Не удалось записать config.json:\n") + str(e)
            )
            return
        log.info(
            "Настройки сохранены: язык %s, hotkey %s, словари %s",
            cfg.get("target_lang"),
            cfg.get("hotkey"),
            saved_glossaries,
        )
        # Сохранение — тоже шаг истории: иначе Ctrl+Z после «Сохранить» не вернул
        # бы файл, а игра продолжила бы делать отменённое. Состояние «до» берём
        # как есть, а новое состояние диска становится кэшем.
        # A save is a history step too: otherwise Ctrl+Z after "Save" would not
        # put the file back and the game would keep doing what was undone.
        before = self._hist_state()
        self._disk_cache = {
            "cfg": dict(cfg),
            "docs": {code: dict(self.docs.get(code) or {}) for code in saved_glossaries},
            "slang": read_json(SLANG_PATH, {}),
        }
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
            self.setWindowTitle(i18n.t("Настройки — FiveM Chat Overlay"))
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


def _sz(w, h):

    return QSize(w, h)


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
            "· выключить можно в любой момент: Настройки → DeepL."
        )
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


def open_settings(cfg, parent=None, first_run=False, dlx=None, anims_api=None, clear_cache=None):
    """Создаёт окно, загружает значения и возвращает его (без exec)."""
    win = SettingsWindow(
        cfg,
        parent=parent,
        first_run=first_run,
        dlx=dlx,
        anims_api=anims_api,
        clear_cache=clear_cache,
    )
    win._load_widgets()
    win._load_language(langs.code_of(cfg.get("target_lang", "it")), reload_table=True)
    return win
