"""Оверлей-чат поверх игры / the overlay chat above the game.

Порядок работы / the order of events
------------------------------------
    горячая клавиша -> СНАЧАЛА открывается чат игры (T), чтобы окружающие
    видели, что вы печатаете -> только потом оверлей -> Enter вставляет текст
    в уже открытый чат и отправляет -> Esc закрывает и оверлей, и чат игры.
    hotkey -> the game chat opens FIRST (T), so other players see that you are
    typing -> only then the overlay appears -> Enter pastes the text into the
    already open chat and sends it -> Esc closes both the overlay and the chat.

Модули / modules: если отправка в игру или глобальная клавиша выключены,
поведение меняется, но программа продолжает работать (см. app.modules).
With sending into the game or the global hotkey disabled the behaviour changes,
yet the program keeps working (see app.modules).
"""

import sys
import threading
import time

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, gamesend as gs, i18n, langs, modules, slang
from app import animchoice
from app import anims as anims_mod
from app.autoplan import AutoPlan
from app.config import log, resource_path, save_config
from app.engine import (
    Engine,
    Result,
    has_fillers,
    has_markers,
    is_counted_command,
    load_glossary,
    strip_markers,
)
from app.hotkey import HotkeyThread, parse_hotkey
from app import dlx as dlx_mod
from app.settings_ui import ask_dlx_consent, open_settings
from app.translator import Translator

STYLE = """
#box { background: rgba(18,18,22,235); border: 1px solid #3a3a46; border-radius: 8px; }
QLineEdit { background: #0e0e12; color: #f2f2f2; border: 1px solid #4a4a58; border-radius: 5px;
            padding: 6px 8px; font-size: 15px; selection-background-color: #3d6fd8; }
QLineEdit:focus { border: 1px solid #5b8cff; }
#out { color: #ffffff; font-size: 14px; }
#it { color: #9bb0ff; font-size: 12px; }
#stat { color: #8a8a96; font-size: 11px; }

/* панель подсказок ключевых слов / the keyword suggestion strip */
#hints { background: rgba(26,26,34,240); border: 1px solid #3a3a46; border-radius: 6px; }
QLabel#hintItem {
    background: #1e1e28; border: 1px solid #33333f; border-radius: 5px;
    padding: 3px 7px; color: #dfe3ff; font-size: 12px;
}
QLabel#hintItem[active="true"] {
    background: #2a3a5c; border: 1px solid #5b8cff; color: #ffffff;
}
QLabel#hintKey { color: #9bb0ff; font-size: 11px; padding: 3px 2px; }
"""


class Bridge(QObject):
    hotkey = Signal()
    fail = Signal(str)
    translated = Signal(int, object, str)  # номер запроса, Result | None, ошибка
    sent = Signal(bool, str)
    game_chat_opened = Signal(bool, int)  # чат игры открыт?, hwnd игры
    dlx_text = Signal(str, bool)  # сообщение сервиса DLX, ошибка?
    # DLX message, is it an error
    anims_text = Signal(str, bool)  # сообщение модуля анимаций / animation module message


class Worker(threading.Thread):
    """Один поток перевода: берёт только самый свежий запрос, устаревшие пропускает.

    One translation thread: it takes the freshest request and skips stale ones.
    """

    def __init__(self, fn, on_done):
        super().__init__(daemon=True, name="translate")
        self.fn, self.on_done, self.job, self.cv = fn, on_done, None, threading.Condition()

    def submit(self, job):
        with self.cv:
            self.job = job
            self.cv.notify()

    def run(self):
        while True:
            with self.cv:
                while self.job is None:
                    self.cv.wait()
                job, self.job = self.job, None
            try:
                res, err = self.fn(job), None
            except Exception as e:
                res, err = None, e
            self.on_done(job, res, err)


def make_icon():
    """Запасная иконка, если рядом нет icon.ico: рисуем её сами.

    The fallback icon for a missing icon.ico: drawn in code. Drawn large, so Qt
    scales it down smoothly for the title bar and the taskbar.
    """
    pm = QPixmap(256, 256)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#2e7d32"))
    p.drawRoundedRect(0, 0, 256, 256, 56, 56)
    p.setPen(QColor("white"))
    p.setFont(QFont("Arial", 92, QFont.Weight.Bold))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "RP")
    p.end()
    return QIcon(pm)


def app_icon() -> QIcon:
    """Иконка программы: заголовок окна, панель задач, Alt+Tab и трей.

    The program icon for the window title, the taskbar, Alt+Tab and the tray.
    Берётся из ``icon.ico`` — в сборке он лежит рядом с exe и внутри архива
    PyInstaller; файла нет или он битый — рисуем запасную.
    Comes from ``icon.ico``: in a build it sits next to the exe and inside the
    PyInstaller bundle; a missing or broken file falls back to the drawn icon.
    """
    path = resource_path("icon.ico")
    if path.is_file():
        icon = QIcon(str(path))
        if not icon.isNull():
            return icon
        log.warning("Иконка %s не читается — рисую запасную", path)
    else:
        log.warning("Файл icon.ico не найден — рисую запасную иконку")
    return make_icon()


def set_app_id() -> None:
    """Своя иконка и своя группа в панели задач Windows, а не python.exe.

    The program's own icon and taskbar group on Windows instead of python.exe's.
    Без этого Windows берёт значок из файла запуска, и у exe из-под Python
    в панели задач появляется заглушка.
    Without this call Windows takes the icon from the launcher file, which is
    where the placeholder in the taskbar comes from.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Chat_n_AutoAnimations_RP_Overlay.Overlay.1"
        )
    except Exception:
        log.exception("Не удалось задать AppUserModelID для панели задач")


class Overlay(QWidget):
    def __init__(self, cfg, engine, tracker, bridge, tray):
        super().__init__()
        self.cfg, self.engine = cfg, engine
        self.tracker, self.bridge, self.tray = tracker, bridge, tray
        self.plan = AutoPlan(cfg)
        self.hwnd = 0
        self.rid = 0
        self.cur = None  # готовый Result для текущего текста
        self.err = ""
        self.want_send = False
        self.sending = False
        self.game_hwnd = None
        self.prev_hwnd = None
        self.shown_at = 0.0
        self.game_chat_open = False  # чат игры уже открыт клавишей T
        self.anims = None  # очередь анимаций, создаётся при запуске
        # the animation queue, created on startup
        self._anim_text = ""  # текст, ждущий проверки правилами анимаций
        # text waiting for the animation rules
        self.opening = False  # чат игры открывается (оверлей ещё не виден)
        self._hints = []  # подсказки ключевых слов / keyword hints
        self._hint_pick = -1  # которая выбрана пролистыванием / picked
        self._hint_done = ""  # только что подставленный ключ / just applied
        self._pending_text = ""  # набранное, сохранённое при закрытии оверлея
        # typed text saved when the overlay closes, so it
        # survives minimising/restoring the game

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        box = QFrame()
        box.setObjectName("box")
        outer.addWidget(box)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(10, 10, 10, 8)
        lay.setSpacing(5)
        self.input = QLineEdit()
        self.input.setPlaceholderText(i18n.t("Текст, +фраза для перевода+, *действие*"))
        self.out, self.it, self.stat = QLabel(), QLabel(), QLabel()
        for w, name in ((self.out, "out"), (self.it, "it"), (self.stat, "stat")):
            w.setObjectName(name)
            w.setWordWrap(True)
        # Подсказки стоят под полем ввода и над переводом: игрок смотрит на то,
        # что печатает, и не должен искать глазами по всему оверлею.
        # The hints sit under the input and above the translation: the player
        # looks at what is being typed and should not hunt across the overlay.
        self.hints_box = QFrame()
        self.hints_box.setObjectName("hints")
        hints_lay = QVBoxLayout(self.hints_box)
        hints_lay.setContentsMargins(6, 5, 6, 5)
        hints_lay.setSpacing(4)
        self.hints_row = QWidget()
        self.hints_row_lay = QHBoxLayout(self.hints_row)
        self.hints_row_lay.setContentsMargins(0, 0, 0, 0)
        self.hints_row_lay.setSpacing(5)
        self.hints_scroll = QScrollArea()
        self.hints_scroll.setWidgetResizable(True)
        self.hints_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.hints_scroll.setWidgetResizable(True)
        self.hints_scroll.setWidget(self.hints_row)
        self.hints_scroll.setFixedHeight(34)
        self.hints_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.hints_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.hints_scroll.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        hints_lay.addWidget(self.hints_scroll)
        self.hints_hint = QLabel("")
        self.hints_hint.setObjectName("hintKey")
        self.hints_hint.setProperty("no_i18n", True)
        # перенос строки обязателен: иначе длинная подсказка растягивает оверлей
        # шире игры / wrapping is required: otherwise a long note widens the
        # overlay beyond the game
        self.hints_hint.setWordWrap(True)
        # подсказка не должна требовать ширины: она подстраивается под оверлей
        # the note must not demand width: it fits the overlay instead
        self.hints_hint.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        hints_lay.addWidget(self.hints_hint)
        self.hints_box.hide()

        for w in (self.input, self.hints_box, self.out, self.it, self.stat):
            lay.addWidget(w)
        self.out.hide()
        self.it.hide()

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._fire)
        self.input.textChanged.connect(self.on_text)
        self.input.returnPressed.connect(self.on_enter)
        # Tab и Shift+Tab листают подсказки, как в обычном чате с командами.
        # Перехват стоит на самом поле: иначе Qt увёл бы фокус на другой виджет.
        # Tab and Shift+Tab walk the hints, as a normal command chat does. The
        # filter sits on the field itself: otherwise Qt would move the focus.
        self.input.installEventFilter(self)
        self.worker = Worker(
            lambda j: self._run_engine(j),
            lambda j, r, e: self.bridge.translated.emit(j[0], r, str(e) if e else ""),
        )
        self.worker.start()
        bridge.translated.connect(self.on_done, Qt.ConnectionType.QueuedConnection)
        bridge.sent.connect(self.on_sent, Qt.ConnectionType.QueuedConnection)
        bridge.game_chat_opened.connect(
            self.on_game_chat_opened, Qt.ConnectionType.QueuedConnection
        )

    # ----- показ / скрытие -----
    def open_overlay(self, *_args) -> None:
        """Сначала открыть чат игры (T), только потом показать оверлей.

        Так окружающие в игре видят, что вы пишете, а не стоите без действия.
        Пока чат открывается (пауза game_open_delay_ms), оверлей не виден.
        The game chat opens first and the overlay follows, so other players see
        that you are typing instead of standing still. While the chat is opening
        (the game_open_delay_ms pause) the overlay stays hidden.
        """
        if self.sending or self.opening:
            return
        if self.isVisible():
            self.close_overlay()
            return
        self.prev_hwnd = gs.user32.GetForegroundWindow()
        self.game_hwnd = self.tracker.get(True)
        if (
            modules.is_enabled(self.cfg, "game_send")
            and self.cfg.get("game_open_chat_first", True)
            and self.game_hwnd
        ):
            self.opening = True
            threading.Thread(
                target=self._open_chat_job, args=(self.game_hwnd,), daemon=True
            ).start()
            return
        self._show_overlay()

    def _open_chat_job(self, hwnd):
        try:
            ok = gs.open_chat(self.cfg, hwnd)
        except Exception:
            log.exception("Не удалось открыть чат игры")
            ok = False
        self.bridge.game_chat_opened.emit(bool(ok), int(hwnd or 0))

    def on_game_chat_opened(self, ok, hwnd):
        self.opening = False
        self.game_chat_open = bool(ok)
        if ok:
            log.info("Чат игры открыт, показываю оверлей")
        else:
            log.warning("Чат игры не открылся, показываю оверлей без него")
        if not self.isVisible() and not self.sending:
            self._show_overlay()

    def _show_overlay(self):
        self._reset()
        # Восстановить набранное, если оверлей был закрыт не по отправке
        # (например, игра свернули) — текст вернётся в поле ввода.
        # Restore what was typed if the overlay was closed without sending
        # (e.g. the game was minimised) — the text comes back into the input.
        if self._pending_text:
            self.input.blockSignals(True)
            self.input.setText(self._pending_text)
            self.input.blockSignals(False)
            self._pending_text = ""
        if self._rev():
            self.input.setPlaceholderText(
                i18n.t("Фраза на вашем языке — перевод уйдёт в чат по Enter")
            )
        else:
            self.input.setPlaceholderText(i18n.t("Текст, +фраза для перевода+, *действие*"))
        self.place()
        self._count()
        self.on_text()  # подсказки ключевых слов для восстановленного текста
        self.shown_at = time.time()
        self.show()
        self.raise_()
        self.activateWindow()
        gs.focus(self.hwnd)
        self.input.setFocus()

    def place(self):
        self.setFixedWidth(int(self.cfg.get("overlay_width", 560)))
        scr = QGuiApplication.primaryScreen()
        dpr = scr.devicePixelRatio() or 1.0
        rect = gs.window_rect(self.game_hwnd) if self.game_hwnd else None
        if rect:
            left, top, right, bottom = (v / dpr for v in rect)
        else:
            g = scr.geometry()
            left, top, right, bottom = (g.left(), g.top(), g.right(), g.bottom())
        fx, fy = self.cfg.get("overlay_pos", [0.01, 0.28])
        self.move(int(left + (right - left) * fx), int(top + (bottom - top) * fy))

    def _reset(self):
        self.rid += 1
        self.cur, self.err, self.want_send = None, "", False
        self.timer.stop()
        self.input.blockSignals(True)
        self.input.clear()
        self.input.blockSignals(False)
        self._hint_hide()
        self._show_result("", "")

    def close_overlay(self, refocus: bool = True) -> None:
        """Скрыть оверлей и закрыть чат игры (Esc), чтобы не висел пустой чат.

        Hide the overlay and close the game chat (Esc), so no empty chat stays
        open behind the game.
        """
        was_open = self.game_chat_open
        hwnd = self.game_hwnd
        self.game_chat_open = False
        # Сохраним то, что игрок набрал, чтобы текст не пропал при закрытии
        # оверлея — в том числе при сворачивании игры (потеря фокуса). При
        # повторном открытии вернём его обратно в поле ввода.
        # Save what the player typed so it is not lost when the overlay closes —
        # including when the game is minimised (focus lost). Restore it back into
        # the input field on the next open.
        self._pending_text = self.input.text()
        self._reset()
        self.hide()
        if was_open and modules.is_enabled(self.cfg, "game_send") and hwnd:
            threading.Thread(target=self._close_chat_job, args=(hwnd,), daemon=True).start()
        else:
            h = hwnd or self.prev_hwnd
            if refocus and h:
                threading.Thread(target=gs.focus, args=(h,), daemon=True).start()

    def _close_chat_job(self, hwnd):
        try:
            gs.close_chat(self.cfg, hwnd)
        except Exception:
            log.exception("Не удалось закрыть чат игры")

    def _chooser(self):
        """Окно выбора анимации, если оно сейчас что-то показывает.

        The animation chooser, when it is showing something.
        """
        try:
            return animchoice.chooser() if animchoice.chooser().busy() else None
        except Exception:
            return None

    def keyPressEvent(self, e):
        ctrl = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
        # Окно выбора анимации смотрит в игру, а нажатия идут сюда: без этого
        # цифры и Esc работали только с мышью, а окно висело само по себе.
        # The chooser looks into the game while the keys arrive here: without
        # this the digits and Esc worked only with the mouse, and the window just
        # hung there.
        chooser = self._chooser()
        if chooser is not None:
            key = e.key()
            if key == Qt.Key.Key_Escape:
                chooser.close_window()
                return
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                chooser.confirm()
                return
            if Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
                if chooser.type_digit(key - Qt.Key.Key_0):
                    return
        if e.key() == Qt.Key.Key_Escape and self._hints:
            # Esc со списком на экране убирает только список: закрывать оверлей
            # в этот момент игрок ещё не просил
            # Esc with the list on screen hides only the list: the player has not
            # asked to close the overlay yet
            self._hint_hide()
        elif e.key() == Qt.Key.Key_Escape:
            self.close_overlay()
        elif ctrl and e.nativeVirtualKey() == 0x52:  # Ctrl+R в любой раскладке
            self.plan.reroll()
            self.on_text()
        else:
            super().keyPressEvent(e)

    def changeEvent(self, e):
        if (
            e.type() == QEvent.Type.ActivationChange
            and self.isVisible()
            and not self.isActiveWindow()
            and not self.sending
            and time.time() - self.shown_at > 0.8
        ):
            QTimer.singleShot(250, self._lost_focus)
        super().changeEvent(e)

    def _lost_focus(self):
        if self.isVisible() and not self.isActiveWindow():
            self.close_overlay(refocus=False)

    # ----- ввод и перевод -----
    def _run_engine(self, job):
        """Перевод одного задания в режиме, который выбран сейчас.

        One job translated in the mode chosen right now.

        Режимов три, и различаются они не украшением, а тем, что уходит в чат:
        полный — всё сообщение на языке перевода, частичный — только +...+ или
        выбранные счётчиком куски, обратный — весь чужой текст по-русски.
        Three modes, and the difference is what leaves for the chat: full mode
        translates everything, partial mode only the marked fragments, and
        reverse mode turns all foreign text into Russian.
        """
        rid, text, auto, seed, _rev = job
        if self._rev():
            return self.engine.process_in(text)
        if self._full():
            return self.engine.process_full(text)
        return self.engine.process(text, auto, seed)

    def _pick(self, res: Result) -> str:
        """Что именно отправить в чат: русскую запись или текст на языке.

        What exactly goes to the chat: the Russian reading or the target text,
        depending on the direction and the send_mode setting.
        """
        if self._rev():
            return res.text or res.native  # в обратном режиме показываем русский
        if self._full():
            return res.native or res.text  # в полном — только текст на языке
        mode = str(self.cfg.get("send_mode", "reading")).lower()
        if mode in ("native", "lang", "text", "target"):
            return res.native or res.text
        return res.text or res.native

    def _rev(self):
        """True для режима «ваш язык → русский» (режим 3)."""
        return self.cfg.get("mode") == "to_ru"

    def _full(self):
        """True для полного перевода всего сообщения (режим 1)."""
        return self.cfg.get("mode") == "full"

    def _lang_tag(self):
        code = str(self.cfg.get("target_lang", "it")).split("-")[0]
        return code.upper() or "IT"

    def _auto_now(self, text):
        if self._rev() or self._full():
            # в этих режимах переводится всё, что попало в поле, и счётчик не нужен
            # both modes translate everything in the field, so no counter is needed
            return False
        # /to /lto /l /wt /s /st участвуют в счётчике наравне с обычным текстом
        # the counted commands take part in the series like ordinary messages
        if text.lstrip().startswith("/") and not is_counted_command(text):
            return False
        if not modules.is_enabled(self.cfg, "autotranslate"):
            return False
        return self.plan.is_auto()

    def set_stat(self, text, err=False):
        self.stat.setStyleSheet("color:#ff6b6b;" if err else "")
        self.stat.setText(text)

    def _count(self):
        n, mx = len(self.input.text()), int(self.cfg.get("max_chars", 256))
        game = i18n.t("найдена") if self.game_hwnd else i18n.t("НЕ найдена")
        if self._rev():
            where = i18n.t("ваш язык → русский")
        elif self._full():
            where = i18n.tf("всё на %s", langs.label(self.cfg.get("target_lang", "it")))
        else:
            where = i18n.tf("по маркерам → %s", langs.label(self.cfg.get("target_lang", "it")))
        parts = [f"{n}/{mx}", where, i18n.tf("игра: %s", game)]
        auto = self.plan.label()
        if auto:
            parts.append(auto)
        parts.append(i18n.t("Enter — отправить · Esc — отмена"))
        self.set_stat(" · ".join(parts), n > mx)

    def _show_result(self, out, other="", err=False):
        self.out.setStyleSheet("color:#ff6b6b;" if err else "")
        self.out.setText(out)
        self.out.setVisible(bool(out))
        if self._full():
            # в полном режиме обе строки совпадают: показывать нечего
            # in full mode both lines are the same, so there is nothing to show
            self.it.setText("")
            self.it.setVisible(False)
            self.adjustSize()
            return
        tag = i18n.t("оригинал") if self._rev() else self._lang_tag()
        self.it.setText((tag + ": " + other) if other else "")
        self.it.setVisible(bool(other))
        self.adjustSize()

    # ----- подсказки ключевых слов / keyword hints
    def eventFilter(self, obj, event):
        """Tab и Shift+Tab в поле ввода листают подсказки.

        Tab and Shift+Tab in the input field walk the suggestions.

        Работает только когда подсказки есть: без них Tab остаётся обычным
        переходом фокуса, и ничего не ломается. Подсказка не подставляется сама —
        её сначала выбирают пролистыванием, а подставляет Enter или сам Tab в
        конце списка, как в чате с командами.
        This only works when there are suggestions: without them Tab stays an
        ordinary focus move, and nothing breaks. A suggestion is never applied by
        itself — Tab walks the list, and Enter (or Tab past the end) applies it,
        exactly like a command chat.
        """
        if obj is getattr(self, "input", None) and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                back = bool(
                    event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                    or key == Qt.Key.Key_Backtab
                )
                if self._hints:
                    self._hint_walk(-1 if back else 1)
                    return True
        return super().eventFilter(obj, event)

    def _hint_walk(self, step: int) -> None:
        """Сдвинуть выбор по подсказкам; на шаге за краем — подставить.

        Move the picked suggestion; stepping past the end applies it.

        Так же ведёт себя чат с командами: листаешь, пока не остановился, а
        последний Tab подтверждает выбор. Иначе пришлось бы отпускать Tab и
        тянуться к Enter.
        A command chat behaves the same: you walk until you stop, and the last Tab
        confirms the pick. Otherwise you would have to leave Tab and reach for
        Enter.
        """
        if not self._hints:
            return
        index = self._hint_pick + step
        if index >= len(self._hints):
            self._hint_apply()
            return
        if index < 0:
            index = len(self._hints) - 1
        self._hint_pick = index
        self._hint_paint()

    def _hint_apply(self) -> None:
        """Подставить выбранную подсказку в поле ввода.

        Put the picked suggestion into the input field.

        Каретка встаёт в конец подставленного ключа, подсказки прячутся: игрок
        уже выбрал, и список поверх текста только мешает.
        The caret goes to the end of the inserted keyword and the hints hide: the
        player has chosen, and a list over the text only gets in the way.
        """
        if not self._hints:
            return
        hint = self._hints[max(0, min(self._hint_pick, len(self._hints) - 1))]
        text, caret = anims_mod.complete(self.input.text(), hint)
        self.input.blockSignals(True)
        self.input.setText(text)
        self.input.setCursorPosition(caret)
        self.input.blockSignals(False)
        self._hint_done = " ".join(hint.keyword.casefold().split())
        self._hints, self._hint_pick = [], -1
        self._hint_paint()
        # перевод запускаем вручную: сигнал был заблокирован, а текст изменился
        # the translation is started by hand: the signal was blocked but the
        # text did change
        self.on_text()

    def _hint_refresh(self, text: str) -> None:
        """Пересчитать подсказки по набранному тексту.

        Recompute the suggestions for the typed text.

        Подсказки бывают только при включённом модуле анимаций: выключенный
        модуль не играет ничего, и предлагать слова было бы обманом.
        Suggestions only exist while the animations module is on: a disabled module
        plays nothing, and offering words would be a lie.
        """
        if not self.cfg.get("anim_hints", True):
            self._hints, self._hint_pick = [], -1
            self._hint_paint()
            return
        runner = self.anims
        rules = []
        if runner is not None:
            try:
                if runner.enabled() and not runner.vehicle():
                    rules = runner.rules()
            except Exception:
                log.exception("Подсказки анимаций: не удалось прочитать правила")
                rules = []
        # Только что подставленный ключ второй раз не предлагаем: список над
        # готовым словом закрывал бы перевод, который игрок и хочет увидеть.
        # A keyword that was just inserted is not offered again: a list over a
        # finished word would cover the translation the player wants to see.
        tail = " ".join(anims_mod.current_word(text).casefold().split())
        if tail and tail == self._hint_done:
            self._hints, self._hint_pick = [], -1
            self._hint_paint()
            return
        if tail != self._hint_done:
            self._hint_done = ""
        found = anims_mod.suggestions(rules, text, int(self.cfg.get("anim_hints_max", 8) or 8))
        if [hint.keyword for hint in found] != [hint.keyword for hint in self._hints]:
            self._hint_pick = -1
        self._hints = found
        self._hint_paint()

    def _hint_paint(self) -> None:
        """Нарисовать полосу подсказок / draw the suggestion strip."""
        while self.hints_row_lay.count():
            item = self.hints_row_lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not self._hints:
            self.hints_box.hide()
            self.adjustSize()
            return
        for index, hint in enumerate(self._hints):
            # В полосе — только само слово: оверлей узкий, и подпись анимации
            # растянула бы полосу так, что соседние слова ушли бы за край.
            # The strip shows the word alone: the overlay is narrow, and an
            # animation label would stretch the strip and push its neighbours out.
            label = QLabel(hint.keyword)
            label.setObjectName("hintItem")
            if index == self._hint_pick:
                label.setProperty("active", "true")
            tip = hint.keyword
            if hint.label and hint.label != hint.keyword:
                tip += f" → {hint.label}"
            label.setToolTip(tip)
            self.hints_row_lay.addWidget(label)
        self.hints_row_lay.addStretch(1)
        # Ширину полосы задаём минимальной, а не фиксированной: фиксированная
        # обнуляет максимальный размер контейнера, и после первой же пересборки
        # все слова получают нулевую ширину и пропадают. Минимум же задаёт
        # только нижнюю границу — лишние слова уезжают под прокрутку, и
        # выбранное можно подкрутить в видимую часть.
        # The strip's width is a minimum, never fixed: a fixed width zeroes the
        # container's maximum size, and after the first rebuild every word gets
        # zero width and disappears. A minimum only sets the lower bound — extra
        # words go under the scroll and the picked one can be brought into view.
        total = 0
        for index in range(self.hints_row_lay.count()):
            widget = self.hints_row_lay.itemAt(index).widget()
            if widget is not None:
                total += widget.sizeHint().width() + self.hints_row_lay.spacing()
        self.hints_row.setMinimumWidth(total)
        self.hints_row.setMaximumWidth(16777215)
        self.hints_row.setMinimumHeight(0)
        chosen = self._hints[max(0, self._hint_pick)] if self._hint_pick >= 0 else None
        if chosen is not None:
            # выбранное слово прокручиваем в видимую часть полосы: иначе при
            # десяти подсказках выбор уезжает за край и его не видно
            # the picked word is scrolled into view: with ten suggestions the pick
            # would otherwise slide out of sight
            item = self.hints_row_lay.itemAt(max(0, self._hint_pick))
            if item is not None and item.widget() is not None:
                self.hints_scroll.ensureWidgetVisible(item.widget(), 8, 0)
            # название анимации уже прокручено в полосе выше, а здесь — только
            # что нажимать, иначе строка занимает две строки впустую
            # the animation label is already scrolled into the strip above, so
            # this line carries the keys only, or it wastes a second row
            self.hints_hint.setText(
                i18n.t("Tab — дальше · Enter — подставить · Esc — скрыть список")
            )
        else:
            self.hints_hint.setText(
                i18n.tf(
                    "Ключевые слова: %d · Tab — пролистать · Enter — отправить", len(self._hints)
                )
            )
        self.hints_box.show()
        self.adjustSize()

    def _hint_hide(self) -> None:
        """Скрыть подсказки, ничего не подставляя / hide the hints, applying none."""
        self._hint_done = ""
        if self._hints or self._hint_pick >= 0:
            self._hints, self._hint_pick = [], -1
            self._hint_paint()

    def on_text(self, _=None):
        self.rid += 1
        self.cur, self.err, self.want_send = None, "", False
        self.timer.stop()
        text = self.input.text()
        self._hint_refresh(text)
        self._count()
        if not text.strip():
            self._show_result("", "")
        elif (
            self._auto_now(text)
            or has_markers(text, self.cfg)
            or self._full()  # полный режим: переводим всё, без условий
            or (self._partial_fillers() and has_fillers(text, self.cfg, self.engine.g))
        ):
            # слова-паразиты переводятся всегда, вне зависимости от счётчика серии
            # fillers are translated in every message, whatever the series counter says
            self._show_result("перевожу…", "")
            self.timer.start(int(self.cfg.get("debounce_ms", 450)))
        else:
            self.cur = Result(text.strip(), "", False)
            self._show_result("", "")

    def _partial_fillers(self):
        """Слова-паразиты участвуют только в частичном режиме (режим 2).

        Fillers only take part in partial mode (mode 2); full and reverse mode
        translate everything and have no fillers of their own.
        """
        return self.cfg.get("mode") == "partial" and bool(self.cfg.get("filler_always", True))

    def _fire(self):
        text = self.input.text()
        self.worker.submit((self.rid, text, self._auto_now(text), self.plan.seed, self._rev()))

    def on_done(self, rid, res, err):
        if rid != self.rid:  # устаревший ответ
            return
        mx = int(self.cfg.get("max_chars", 256))
        if err:
            self.err = err
            self.want_send = False
            self._show_result(i18n.tf("Ошибка перевода: %s", err[:160]), "", True)
            self.set_stat(i18n.t("Enter — отправить без перевода · Esc — отмена"), True)
            return
        self.cur = res
        sent = self._pick(res)
        other = res.native if sent == res.text else res.text
        self._show_result(sent, other if res.translated else "")
        self.set_stat(
            i18n.tf("В чат уйдёт %d/%d · Enter — отправить · Esc — отмена", len(sent), mx),
            len(sent) > mx,
        )
        if self.want_send:
            self.want_send = False
            self.finish(sent)

    def on_enter(self) -> None:
        """Enter: отправить готовый перевод, без перевода или закрыть оверлей.

        Enter: send the finished translation, send without translating, or just
        close the overlay when the field is empty.
        """
        if self.sending:
            return
        # выбрана подсказка — Enter сначала подставляет её: игрок как раз
        # листал список, и отправлять недописанное слово было бы грубо
        # a suggestion is picked, so Enter applies it first: the player was walking
        # the list, and sending a half-typed word would be rude
        if self._hint_pick >= 0 and self._hints:
            self._hint_apply()
            return
        text = self.input.text().strip()
        if not text:
            self.close_overlay()
        elif self.cur is not None:
            self.finish(self._pick(self.cur))
        elif self.err:  # второй Enter после ошибки
            self.finish(strip_markers(text, self.cfg))
        else:
            self.want_send = True
            self.timer.stop()
            self._fire()
            self.set_stat("Перевожу… отправлю сразу после перевода")

    # ----- отправка -----
    def finish(self, out: str) -> None:
        """Отправка готового текста в игру или в буфер обмена.

        Sends the finished text into the game, or to the clipboard when the
        game_send module is disabled.
        """
        mx = int(self.cfg.get("max_chars", 256))
        if not out.strip():
            return
        if len(out) > mx:
            self.set_stat(f"Слишком длинно: {len(out)}/{mx}", True)
            return
        # ключевые слова ищем в том, что игрок напечатал сам: перевод уже мог
        # заменить слова на языке сервера, и правила перестали бы совпадать.
        # Проверка идёт после отправки сообщения, иначе /anim и текст сообщения
        # одновременно лезут в чат игры и мешают друг другу.
        # keywords are looked up in what the player typed: the translation may
        # already have replaced the words, and the rules would stop matching.
        # The check runs after the message is sent, otherwise /anim and the
        # message text fight over the same game chat.
        self._anim_text = self.input.text() or out
        # в счётчик серии идут обычные сообщения и /to /lto /l /wt /s /st
        if not out.startswith("/") or is_counted_command(out):
            self.plan.advance()  # счётчик серии автоперевода
        QApplication.clipboard().setText(out)
        log.info("Готово к отправке: %r", out)
        hwnd = self.game_hwnd or self.tracker.get(True)
        chat_open = self.game_chat_open  # чат уже открыт при открытии оверлея
        self.game_chat_open = False
        self._reset()
        self._pending_text = ""  # отправленное не возвращаем при следующем открытии
        # sent text is not brought back on the next open
        self.hide()
        if modules.is_enabled(self.cfg, "game_send") and hwnd:
            self.sending = True
            threading.Thread(
                target=self._send_job, args=(hwnd, out, chat_open), daemon=True
            ).start()
        else:
            if chat_open and hwnd:
                # чат был открыт, а отправка в игру выключена — закрыть чат
                # the chat was open while sending to the game is off, so close the chat
                threading.Thread(target=self._close_chat_job, args=(hwnd,), daemon=True).start()
            self._anim_text = ""  # анимациям нужен чат игры
            h = self.prev_hwnd
            if h:
                threading.Thread(target=gs.focus, args=(h,), daemon=True).start()
            self.notify(i18n.t("Скопировано в буфер обмена (Ctrl+V)."))

    def _send_job(self, hwnd, out, chat_open=False):
        try:
            ok, msg = gs.send_chat(self.cfg, hwnd, out, chat_open=chat_open)
        except Exception as e:
            log.exception("Ошибка отправки в игру")
            ok, msg = False, str(e)
        self.bridge.sent.emit(ok, msg)

    def on_sent(self, ok, msg):
        """Сообщение ушло (или нет): только теперь можно запускать анимацию.

        The message is out (or not): only now may an animation start, so the two
        never type into the game chat at the same time. The short pause lets the
        game close its chat after Enter.
        """
        self.sending = False
        text, self._anim_text = self._anim_text, ""
        if ok and text and self.anims is not None:
            QTimer.singleShot(250, lambda: self.anims.feed(text))
        if not ok:
            self.notify(msg + i18n.t(" Текст в буфере обмена — вставьте вручную (Ctrl+V)."), True)

    def notify(self, msg, warn=False):
        kind = QSystemTrayIcon.MessageIcon
        icon = kind.Warning if warn else kind.Information
        self.tray.showMessage(APP_NAME, msg, icon, 6000)


# Подписи режимов: одна таблица на уведомление, меню и подсказку.
# Mode captions: one table shared by the notification, the menu and the tooltip.
MODE_TITLES = (
    ("full", "Режим: всё сообщение на язык перевода"),
    ("partial", "Режим: только выделенные слова и фразы"),
    ("to_ru", "Режим: ваш язык → русский"),
)

MODE_HINTS = {
    "full": "Всё сообщение уходит на языке перевода. Автоперевод и слова-паразиты не участвуют.",
    "partial": "Переводятся только выделенные +слова и фразы+, плюс автоперевод "
    "по счётчику и слова-паразиты.",
    "to_ru": "Пишете на своём языке — в чат уходит русский текст.",
}


def run_gui(cfg: dict, open_settings_on_start: bool = False) -> int:
    """Запуск интерфейса: оверлей, трей, горячая клавиша и окно настроек.

    Starts the interface: overlay, tray icon, hotkey and settings window.
    Returns the process exit code.
    """
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    # иконка на все окна сразу: заголовок, панель задач, Alt+Tab и трей
    # one icon for every window at once: title bar, taskbar, Alt+Tab and the tray
    set_app_id()
    icon = app_icon()
    app.setWindowIcon(icon)
    # сторож главного потока: если окно замрёт, в журнал ошибок попадёт стек всех
    # потоков, и причину будет видно / a main-thread watchdog: a frozen window
    # leaves every thread stack in the error log, so the cause is visible
    try:
        from app import errorlog

        errorlog.watch_main_thread(20.0, parent=app)
    except Exception:
        log.exception("Не удалось включить сторож главного потока")

    # язык интерфейса: при первом запуске спрашиваем, дальше берём из настроек
    # interface language: asked once on the first run, taken from the
    # settings afterwards
    if not cfg.get("ui_lang_chosen"):
        from app.ui_lang import ask_ui_language

        cfg["ui_lang"] = ask_ui_language(style=STYLE)
        cfg["ui_lang_chosen"] = True
        save_config(cfg)
    i18n.set_lang(cfg.get("ui_lang", "ru"))

    # согласие на локальный сервис DeepL — один раз и до окон, чтобы вопрос не
    # всплывал поверх настроек; скачивание начнётся позже, в фоне
    # consent for the DeepL service — once and before the windows, so the question
    # never pops up over the settings; the download starts later, in the background
    pending_download = {"value": False}
    if not cfg.get("dlx_asked"):
        accepted, want = ask_dlx_consent(cfg)
        cfg["dlx_asked"] = True
        cfg["dlx_enabled"] = bool(accepted)
        pending_download["value"] = bool(accepted and want)
        save_config(cfg)
        log.info("DLX: согласие=%s, скачивать=%s", accepted, want)

    lang = langs.code_of(cfg.get("target_lang", "it"))
    translator = Translator(lang)
    # язык таблицы сокращений — до первого перевода
    # the abbreviation table language, before the first translation
    slang.use_for(cfg)
    engine = Engine(cfg, load_glossary(lang), translator)
    tracker = gs.GameTracker(cfg)
    bridge = Bridge()
    tray = QSystemTrayIcon(icon, app)
    win = Overlay(cfg, engine, tracker, bridge, tray)
    win.setWindowIcon(icon)
    win.hwnd = int(win.winId())
    state = {"dlg": None, "hk": None, "menu": None, "stop": None}

    # ---------- локальный сервис DeepL ----------
    def dlx_event(kind, text):
        """Сообщение от сервиса: остановился, поднялся снова / a service message.

        Вызывается из потока наблюдения, поэтому в интерфейс попадает только
        сигналом: виджеты Qt трогать из фонового потока нельзя.
        Called from the watchdog thread, so it reaches the interface through a
        signal only: Qt widgets must not be touched from a background thread.
        """
        log.info("DLX: %s", text)
        bridge.dlx_text.emit(i18n.t(text), kind == "stopped")

    bridge.dlx_text.connect(
        lambda text, error: win.notify(text, error), Qt.ConnectionType.QueuedConnection
    )

    dlx = dlx_mod.service_for(cfg, on_event=dlx_event)
    state["dlx"] = dlx

    def attach_local():
        """Подключает или отключает локальное звено перевода / wire the local link."""
        use = bool(cfg.get("dlx_enabled")) and modules.is_enabled(cfg, "dlx")
        translator.local = dlx if use else None
        if not use and dlx.installed():
            dlx.stop()

    attach_local()

    # ---------- модуль «Анимации» ----------
    # Чат игры принимает новое T не мгновенно: сразу после Enter предыдущей
    # команды нажатие пропадает, и команда не уходит. Поэтому между командами
    # выдерживается пауза на «отдых» чата — это не пауза между анимациями, а
    # время на саму игру.
    # The game chat does not take a new T instantly: right after the Enter of the
    # previous command the press is lost and the command goes nowhere. So the
    # commands keep a chat rest — this is not the animation pause, it is the game.
    CHAT_REST_MS = 300
    chat_state = {"at": 0.0}

    def anims_send(command):
        """Отправка команды анимации в чат игры / send an animation command.

        Вызывается из потока модуля: чат игры открывается заново — фокус в игру,
        клавиша чата (T), вставка, Enter, — потому что к этому моменту чат и
        фокус уже не там, где были при отправке сообщения.
        Called from the module thread: the game chat is opened again — focus, the
        chat key (T), paste, Enter — because by then the chat and the focus are no
        longer where they were when the message was sent.
        """
        if not modules.is_enabled(cfg, "anims") or not modules.is_enabled(cfg, "game_send"):
            return False, i18n.t("отправка в игру выключена в настройках")
        hwnd = win.game_hwnd or tracker.get(True)
        if not hwnd:
            return False, i18n.t("окно игры не найдено")
        rest = CHAT_REST_MS / 1000.0 - (time.monotonic() - chat_state["at"])
        if rest > 0:
            # чат ещё «остывает» после прошлой команды
            # the chat is still recovering from the previous command
            log.info("Анимации: пауза чата %d мс перед %s", int(rest * 1000), command)
            time.sleep(rest)
        # игра вставляет текст из буфера обмена: если команду туда не положить,
        # в чат уйдёт прошлое сообщение игрока (и оно продублируется)
        # the game pastes from the clipboard: without putting the command there
        # the chat receives the player's previous message and repeats it
        if str(cfg.get("game_input_mode", "paste")) != "type":
            if not gs.set_clipboard(command):
                return False, i18n.t("не удалось положить команду в буфер обмена")
        try:
            ok, message = gs.send_chat(cfg, hwnd, command, chat_open=False)
        except Exception as error:
            log.exception("Анимации: сбой отправки %s", command)
            return False, str(error)[:120]
        finally:
            chat_state["at"] = time.monotonic()
        if ok:
            return True, message
        # один повтор: игра могла не успеть отдать фокус, а без команды
        # пропадает вся анимация
        # one retry: the game may have been slow with the focus, and a lost
        # command costs the whole animation
        log.warning("Анимации: %s не ушло (%s) — повторяю", command, message)
        time.sleep(0.4)
        try:
            ok, message = gs.send_chat(cfg, hwnd, command, chat_open=False)
        except Exception as error:
            log.exception("Анимации: повтор не удался %s", command)
            return False, str(error)[:120]
        finally:
            chat_state["at"] = time.monotonic()
        return ok, message

    def anims_press_key(spec):
        """Симуляция нажатия клавиши в игре / simulate a key press in the game.

        Нужна для остановки анимации клавишей: игра получает настоящее нажатие,
        поэтому её собственный обработчик срабатывает как обычно.
        Used to stop an animation with a key: the game receives a real press, so
        its own handler works as usual.
        """
        hwnd = win.game_hwnd or tracker.get(True)
        if not hwnd:
            return False, i18n.t("окно игры не найдено")
        try:
            _mods, vk = parse_hotkey(str(spec or "f"))
        except Exception:
            log.exception("Анимации: клавиша «%s» не разобрана", spec)
            vk = 0
        if not vk:
            return False, i18n.t("клавиша остановки не разобрана")
        if not gs.focus(hwnd):
            return False, i18n.t("не удалось переключиться в игру")
        gs.tap(vk)
        return True, ""

    def anim_equivalent(phrase):
        """Ключ перевода фразы: одинаковый ключ — одинаковый перевод.

        The translation key of a phrase: the same key means the same translation.

        «Чёрт» и «проклятье» оба дают «Mannaggia», а «да ну» и «да брось» —
        «ma dai», поэтому правило на одну фразу срабатывает и на другую: по
        словарю, без обращения к сети.
        «Чёрт» and «проклятье» both give «Mannaggia», «да ну» and «да брось»
        both give «ma dai», so a rule for one phrase fires on the other — straight
        from the glossary, with no network call.
        """
        try:
            glossary = win.engine.g
            return glossary.find_meaning(phrase) or ""
        except Exception:
            return ""

    def anim_text_keys(text):
        """Какие фразы словаря есть в сообщении: [(начало, конец, ключ)].

        Which glossary phrases sit in the text: [(start, end, key)]. По этому
        списку ловятся многословные синонимы — «да ну» на правиле «да брось».
        It is what catches multi-word synonyms — «да ну» on a «да брось» rule.
        """
        try:
            glossary = win.engine.g
            return glossary.phrase_keys(text)
        except Exception:
            return []

    def anims_event(kind, text):
        """Событие модуля: ошибку и остановку видит игрок, остальное — журнал.

        The module reports an error or a stop to the player; the rest goes to
        the log only, so a working animation never nags with notifications.
        """
        if kind == "error":
            bridge.anims_text.emit(i18n.tf("Анимация: %s", text), True)
        elif kind == "stopped":
            bridge.anims_text.emit(i18n.t("Зацикленная анимация остановлена."), False)
        else:
            log.info("Анимации: %s — %s", kind, text)

    bridge.anims_text.connect(
        lambda text, error: win.notify(text, error), Qt.ConnectionType.QueuedConnection
    )
    # выбор варианта анимации: у правила с двумя и более /anim открывается
    # оверлей, и в чат уходит то, что выбрал игрок
    # the variant chooser: a rule with two or more /anim commands opens an
    # overlay, and what the player picked goes into the chat
    # Передаём сам объект выбора, а не обёртку: у него есть `cancel` и
    # `rule_finished`, которыми очередь закрывает окно и снимает пометки.
    # The chooser object itself is passed, not a wrapper: it carries `cancel` and
    # `rule_finished`, which the queue uses to close the window and clear marks.
    runner = anims_mod.Runner(
        cfg,
        send=anims_send,
        on_event=anims_event,
        equivalent=anim_equivalent,
        press_key=anims_press_key,
        text_keys=anim_text_keys,
        chooser=animchoice.chooser(),
    )
    win.anims = runner
    # окно настроек проверяет этим словарём, доходит ли команда до игры
    # the settings window uses this mapping to check whether a command arrives
    anims_api = {
        "state": runner.state,
        "stop": runner.stop_user,
        "send": lambda name: anims_send(f"/anim {name}".strip()),
        "vehicle": runner.vehicle,
        "set_vehicle": runner.set_vehicle,
    }

    def start_stop_watcher():
        """Клавиша остановки: перезапуск после каждой смены настроек.

        The stop key watcher: restarted after every settings change, because the
        key itself may have changed.
        """
        old = state["stop"]
        if old is not None:
            old.stop()
            state["stop"] = None
        if not cfg.get("anims_enabled"):
            return
        # клавиша остановки следит только за зацикливанием — это её прямое
        # назначение. Иначе обычное нажатие F в игре (в GTA это вход в машину и
        # другие действия) обрывало бы обычные анимации и снимало очередь.
        # the stop key watches looping animations only, which is its purpose.
        # Otherwise an ordinary F press in the game (enter a vehicle and other
        # actions in GTA) would cut one-shot animations and drop the queue.
        watcher = anims_mod.StopWatcher(
            str(cfg.get("anim_stop_key", "f") or "f"),
            runner.stop_user,
            lambda: bool(runner.state().get("loop")),
        )
        state["stop"] = watcher
        watcher.start()

    # ---------- применение настроек ----------
    # applying the settings
    def apply_settings(newcfg):
        """Пересобирает движок, горячую клавишу и меню после сохранения настроек.

        Rebuilds the engine, the hotkey and the menu after the settings were saved.
        """
        cfg.clear()
        cfg.update(newcfg)
        code = langs.code_of(cfg.get("target_lang", "it"))
        translator.set_target(code)
        translator.set_direction(cfg.get("direction", "out"))
        attach_local()
        # включили DeepL в настройках — поднимаем сервис в фоне, не задерживая окно
        # DeepL was switched on in the settings — start the service in the
        # background instead of holding the window
        if (
            cfg.get("dlx_enabled")
            and modules.is_enabled(cfg, "dlx")
            and dlx.installed()
            and not dlx.status().get("running")
        ):
            dlx_job()
        elif dlx.needs_restart():
            # прокси или токен поменяли — сервис перезапускаем с новыми ключами
            # the proxy or the token changed, so restart with the new flags
            log.info("DLX: параметры запуска изменились, перезапуск")
            threading.Thread(target=dlx.restart, name="dlx-restart", daemon=True).start()
        # Язык таблицы сокращений следует за настройками: на немецком сервере
        # первой работает немецкая таблица, а свой выбор игрок задаёт вручную.
        # Здесь, в главном потоке, и только здесь: окно настроек и проверка
        # перевода не должны менять рабочий язык на ходу.
        # The abbreviation table follows the settings: a German server uses the
        # German table first, and the player may name one by hand. Set here, in
        # the main thread, and only here: the settings window and the preview must
        # not switch the working language under the running engine.
        slang.use_for(cfg)
        win.engine = Engine(cfg, load_glossary(code), translator)
        win.plan = AutoPlan(cfg)  # новая серия под новые параметры
        runner.reload(cfg)  # новые правила анимаций
        start_stop_watcher()  # и, возможно, новая клавиша остановки
        restart_hotkey()
        build_menu()
        i18n.set_lang(cfg.get("ui_lang", "ru"))
        i18n.retranslate(win)
        key = cfg["hotkey"] if modules.is_enabled(cfg, "hotkey") else "без клавиши"
        tray.setToolTip(f"{APP_NAME} · {key} · {langs.label(code)}")
        win.notify(
            i18n.tf("Настройки сохранены. Язык: %s, клавиша: %s.", langs.label(code), cfg["hotkey"])
        )

    def set_mode(mode):
        """Переключение режима перевода из меню трея.

        Switches the translation mode from the tray menu.

        Старое имя ``set_direction`` осталось ради совместимости: оно понимает
        и ``in``/``out``, чтобы старые ярлыки и скрипты не сломались.
        The old ``set_direction`` name is kept for compatibility and understands
        ``in``/``out`` so that old shortcuts and scripts keep working.
        """
        mode = {"in": "to_ru", "reverse": "to_ru", "out": "partial"}.get(mode, mode)
        if mode not in ("full", "partial", "to_ru"):
            mode = "partial"
        cfg["mode"] = mode
        cfg["direction"] = "in" if mode == "to_ru" else "out"
        save_config(cfg)
        apply_settings(dict(cfg))
        win.notify(i18n.t(dict(MODE_TITLES)[mode]))

    def set_vehicle(on):
        """Режим «В машине» из меню трея / the "In a vehicle" mode from the tray.

        Пока режим включён, ни `/anim`, ни `/sa` в игру не уходят: включение
        один раз гасит текущую анимацию, и всё. Флаг пишется в настройки, чтобы
        пережить перезапуск программы.
        While the mode is on, neither `/anim` nor `/sa` leaves for the game: turning
        it on stops the current animation once, and that is all. The flag is saved
        so that it survives a restart.
        """
        on = bool(on)
        if on == bool(runner.vehicle()):
            # меню уже пересобрано под это состояние — второй раз незачем
            # the menu already shows this state, no need to rebuild it
            return
        runner.set_vehicle(on)
        cfg["anim_in_vehicle"] = on
        save_config(cfg)
        build_menu()
        win.notify(
            i18n.t("Режим «В машине» включён: анимации не играют.")
            if on
            else i18n.t("Анимации снова работают.")
        )

    def set_direction(direction):
        """Устаревшее имя переключателя режима / legacy name for set_mode."""
        set_mode("to_ru" if str(direction).lower() in ("in", "reverse") else "partial")

    # ---------- окно настроек ----------
    def open_settings_window(first_run=False):
        if state["dlg"] is not None:
            state["dlg"].show()
            state["dlg"].raise_()
            state["dlg"].activateWindow()
            return
        dlg = open_settings(cfg, parent=None, first_run=first_run, dlx=dlx, anims_api=anims_api)
        dlg.saved.connect(apply_settings)
        dlg.finished.connect(lambda *_: state.update(dlg=None))
        state["dlg"] = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    # ---------- горячая клавиша ----------
    def active():
        g = tracker.get()
        return (not g) or gs.user32.GetForegroundWindow() in (g, win.hwnd)

    def start_hotkey():
        """Запускает поток горячей клавиши, если модуль включён.

        Starts the hotkey thread when the module is enabled; otherwise the
        overlay is opened by double-clicking the tray icon.
        """
        if not modules.is_enabled(cfg, "hotkey"):
            log.info("Модуль горячей клавиши выключен")
            return
        hk = HotkeyThread(cfg["hotkey"], bridge.hotkey.emit, active, bridge.fail.emit)
        state["hk"] = hk
        hk.start()

    def restart_hotkey():
        """Перезапуск клавиши после смены настроек / restart after new settings."""
        old = state["hk"]
        if old is not None:
            old.stop()
            state["hk"] = None
        if modules.is_enabled(cfg, "hotkey"):
            QTimer.singleShot(450, start_hotkey)  # старый поток успевает снять регистрацию

    # ---------- меню трея ----------
    def build_menu():
        """Короткое меню трея: статус переводчика, режим, настройки, выход.

        Всё остальное (язык, автоперевод, отправка в игру, слова-паразиты)
        настраивается в окне «Настройки…».

        Режим переключается здесь, потому что это решение на один вечер: сегодня
        играю на итальянском сервере, завтра на русском. Лазить за этим в
        настройки — лишние три клика посреди боя.
        The mode is switched right here because it is a per-evening decision:
        an Italian server today, a Russian one tomorrow. Digging into the
        settings for that is three extra clicks in the middle of a fight.
        """
        menu = QMenu()
        mode = cfg.get("mode") or "partial"
        code = langs.code_of(cfg.get("target_lang", "it"))
        label = langs.label(code)
        if mode == "to_ru":
            status = QAction(i18n.t("Статус: ваш язык → русский"), menu)
        elif mode == "full":
            status = QAction(i18n.tf("Статус: всё сообщение → %s", label), menu)
        else:
            status = QAction(i18n.tf("Статус: выделенные слова и фразы → %s", label), menu)
        status.setEnabled(False)
        menu.addAction(status)
        menu.addSeparator()

        group = QActionGroup(menu)
        group.setExclusive(True)
        for value, text in (
            ("full", i18n.tf("Всё сообщение → %s", label)),
            ("partial", i18n.tf("Только выделенные слова и фразы → %s", label)),
            ("to_ru", i18n.t("Ваш язык → русский")),
        ):
            act = QAction(text, menu)
            act.setCheckable(True)
            act.setChecked(value == mode)
            act.setToolTip(MODE_HINTS[value])
            act.triggered.connect(lambda _c=False, v=value: set_mode(v) if v != mode else None)
            group.addAction(act)
            menu.addAction(act)

        # Режим «В машине»: пункт с галочкой, чтобы включать его одним движением
        # прямо в поездке, не открывая настройки.
        # The "In a vehicle" mode: a checkable item, so it can be switched with one
        # move right in the middle of a ride, without opening the settings.
        menu.addSeparator()
        act_vehicle = QAction(i18n.t("В машине — не играть анимации"), menu)
        act_vehicle.setCheckable(True)
        # setChecked сам испускает toggled, а обработчик пересобирает это же
        # меню — без блокировки сигнала получилась бы бесконечная пересборка
        # setChecked emits toggled on its own, and the handler rebuilds this very
        # menu — without blocking the signal it would rebuild for ever
        act_vehicle.blockSignals(True)
        act_vehicle.setChecked(bool(runner.vehicle()))
        act_vehicle.blockSignals(False)
        act_vehicle.setToolTip(
            i18n.t(
                "Пока галочка стоит, ни /anim, ни /sa в игру не уходят: в машине "
                "анимации ломают позу и выбрасывают из транспорта."
            )
        )
        act_vehicle.toggled.connect(set_vehicle)
        menu.addAction(act_vehicle)

        menu.addSeparator()
        act_settings = QAction(i18n.t("Настройки…"), menu)
        act_settings.triggered.connect(lambda: open_settings_window())
        menu.addAction(act_settings)
        menu.addAction(i18n.t("Выход"), app.quit)

        state["menu"] = menu
        tray.setContextMenu(menu)
        short = {
            "full": i18n.t("всё на язык"),
            "partial": i18n.t("по маркерам"),
            "to_ru": i18n.t("на русский"),
        }[mode]
        key = cfg["hotkey"] if modules.is_enabled(cfg, "hotkey") else "без клавиши"
        tray.setToolTip(f"{APP_NAME} · {key} · {short} · {label}")

    # Сохранённый режим «В машине» поднимается при старте: игрок включил его
    # нарочно, и после перезапуска он должен остаться включённым. Вреда нет —
    # при старте ничего не играет, поэтому ни /sa, ни /anim не уйдут.
    # The saved "In a vehicle" mode comes back at start-up: the player turned it
    # on on purpose, and it must stay on after a restart. Nothing is harmed —
    # nothing plays at start-up, so neither /sa nor /anim leaves.
    if cfg.get("anim_in_vehicle"):
        runner.set_vehicle(True)
    build_menu()
    # двойной клик по значку в трее открывает оверлей (пункта в меню нет)
    # a double click on the tray icon opens the overlay (there is no menu item)
    tray.activated.connect(
        lambda r: win.open_overlay() if r == QSystemTrayIcon.ActivationReason.DoubleClick else None
    )
    tray.show()

    bridge.hotkey.connect(win.open_overlay, Qt.ConnectionType.QueuedConnection)
    bridge.fail.connect(lambda m: win.notify(m, True), Qt.ConnectionType.QueuedConnection)
    start_hotkey()
    app.aboutToQuit.connect(lambda: state["hk"] and state["hk"].stop())
    app.aboutToQuit.connect(dlx.shutdown)
    app.aboutToQuit.connect(translator.flush_cache)
    app.aboutToQuit.connect(runner.shutdown)
    app.aboutToQuit.connect(lambda: state["stop"] and state["stop"].stop())

    game = i18n.t("найдена") if tracker.get(True) else i18n.t("не найдена")
    key = cfg["hotkey"] if modules.is_enabled(cfg, "hotkey") else i18n.t("не назначена")
    win.notify(
        i18n.tf(
            "Клавиша: %s. Язык: %s. Игра: %s.",
            key,
            langs.label(langs.code_of(cfg.get("target_lang", "it"))),
            game,
        )
    )

    def dlx_say(text, error=False):
        """Сообщение игроку из любого потока / a message to the player from any thread."""
        bridge.dlx_text.emit(text, error)

    def dlx_job(download=False):
        """Сеть и процесс — в фоновом потоке / network and process in a worker thread.

        Всё, что может занять секунды — скачивание, запуск, проверка обновлений, —
        живёт здесь, чтобы окно не замирало. Интерфейс трогаем только сигналами.
        Everything that can take seconds (download, start, update check) lives here
        so the window never freezes. The interface is touched through signals only.
        """

        def work():
            try:
                # файла нет или он оказался битым — скачиваем заново: согласие
                # игрока уже получено / the file is missing or broken, so download
                # again: the player's consent was given already
                if download or not dlx.installed():
                    dlx_say(i18n.t("Скачиваю локальный сервис DeepL…"))
                    if not dlx.install():
                        dlx_say(
                            i18n.tf(
                                "Сервис DeepL не установился: %s", dlx.status().get("reason") or ""
                            ),
                            True,
                        )
                        return
                if not dlx.installed():
                    dlx_say(
                        i18n.t("Сервис DeepL не установлен — работаю через стандартные сервисы."),
                        True,
                    )
                    return
                if dlx.ensure():
                    # свой сервис по адресу живёт сам: обновлять нечего
                    # a service of your own lives outside, nothing to update
                    if dlx.external_url():
                        dlx_say(i18n.t("Своя служба DeepL отвечает — перевожу через неё."))
                        return
                    dlx_say(i18n.t("DeepL рядом готов — перевожу через него."))
                elif dlx.status().get("state") == "upstream":
                    dlx_say(
                        i18n.t(
                            "Сервис DeepL запущен, но DeepL не отвечает "
                            "(503). Помогает прокси: Настройки → DeepL."
                        ),
                        True,
                    )
                else:
                    dlx_say(
                        i18n.tf(
                            "Сервис DeepL не запустился (%s) — перевожу через стандартные сервисы.",
                            dlx.status().get("reason") or "",
                        ),
                        True,
                    )
                if cfg.get("dlx_auto_update", True):
                    newest = dlx.check_update()
                    if newest:
                        dlx_say(
                            i18n.tf(
                                "Для сервиса DeepL есть версия %s: Настройки → DeepL → Обновить.",
                                newest,
                            )
                        )
            except Exception:
                log.exception("DLX: сбой при запуске сервиса")
                dlx_say(
                    i18n.tf(
                        "Сервис DeepL не запустился (%s) — перевожу через стандартные сервисы.",
                        i18n.t("см. logs/errors.log"),
                    ),
                    True,
                )

        threading.Thread(target=work, name="dlx-boot", daemon=True).start()

    def dlx_boot():
        """Запуск сервиса после старта — только решения, без диалогов.

        The service start after launch: decisions only, no dialogs. Ответ игрока
        уже получен до окон; здесь остаётся скачивание (если он согласился),
        запуск с health-check и предложение обновиться.
        The player's answer was taken before the windows; what is left is the
        download (when agreed), the start with a health check and an update offer.
        """
        if not cfg.get("dlx_enabled"):
            return
        attach_local()
        if pending_download["value"] and not dlx.installed():
            pending_download["value"] = False
            dlx_job(download=True)
            return
        if not cfg.get("dlx_autostart", True):
            log.info("DLX: автозапуск выключен в настройках")
            return
        dlx_job()

    QTimer.singleShot(1200, dlx_boot)

    if open_settings_on_start or not cfg.get("setup_done") or cfg.get("show_settings_on_start"):
        QTimer.singleShot(250, lambda: open_settings_window(first_run=not cfg.get("setup_done")))
    return app.exec()
