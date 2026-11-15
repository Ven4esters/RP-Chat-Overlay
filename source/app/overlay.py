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
from PySide6.QtGui import (QAction, QActionGroup, QColor, QFont, QGuiApplication, QIcon,
                           QPainter, QPixmap)
from PySide6.QtWidgets import (QApplication, QFrame, QLabel, QLineEdit, QMenu,
                               QSystemTrayIcon, QVBoxLayout, QWidget)

from app import APP_NAME, gamesend as gs, i18n, langs, modules
from app.autoplan import AutoPlan
from app.config import log, save_config
from app.engine import (Engine, Result, has_fillers, has_markers, is_counted_command,
                      load_glossary, strip_markers)
from app.hotkey import HotkeyThread
from app.settings_ui import open_settings
from app.translator import Translator

STYLE = """
#box { background: rgba(18,18,22,235); border: 1px solid #3a3a46; border-radius: 8px; }
QLineEdit { background: #0e0e12; color: #f2f2f2; border: 1px solid #4a4a58; border-radius: 5px;
            padding: 6px 8px; font-size: 15px; selection-background-color: #3d6fd8; }
QLineEdit:focus { border: 1px solid #5b8cff; }
#out { color: #ffffff; font-size: 14px; }
#it { color: #9bb0ff; font-size: 12px; }
#stat { color: #8a8a96; font-size: 11px; }
"""


class Bridge(QObject):
    hotkey = Signal()
    fail = Signal(str)
    translated = Signal(int, object, str)    # номер запроса, Result | None, ошибка
    sent = Signal(bool, str)
    game_chat_opened = Signal(bool, int)    # чат игры открыт?, hwnd игры


class Worker(threading.Thread):
    """Один поток перевода: берёт только самый свежий запрос, устаревшие пропускает."""

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
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#2e7d32"))
    p.drawEllipse(4, 4, 56, 56)
    p.setPen(QColor("white"))
    p.setFont(QFont("Arial", 22, QFont.Weight.Bold))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "RP")
    p.end()
    return QIcon(pm)


class Overlay(QWidget):
    def __init__(self, cfg, engine, tracker, bridge, tray):
        super().__init__()
        self.cfg, self.engine, self.tracker, self.bridge, self.tray = cfg, engine, tracker, bridge, tray
        self.plan = AutoPlan(cfg)
        self.hwnd = 0
        self.rid = 0
        self.cur = None            # готовый Result для текущего текста
        self.err = ""
        self.want_send = False
        self.sending = False
        self.game_hwnd = None
        self.prev_hwnd = None
        self.shown_at = 0.0
        self.game_chat_open = False   # чат игры уже открыт клавишей T
        self.opening = False          # чат игры открывается (оверлей ещё не виден)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
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
        for w in (self.input, self.out, self.it, self.stat):
            lay.addWidget(w)
        self.out.hide()
        self.it.hide()

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._fire)
        self.input.textChanged.connect(self.on_text)
        self.input.returnPressed.connect(self.on_enter)
        self.worker = Worker(lambda j: (self.engine.process_in(j[1]) if j[4]
                                      else self.engine.process(j[1], j[2], j[3])),
                             lambda j, r, e: self.bridge.translated.emit(j[0], r, str(e) if e else ""))
        self.worker.start()
        bridge.translated.connect(self.on_done, Qt.ConnectionType.QueuedConnection)
        bridge.sent.connect(self.on_sent, Qt.ConnectionType.QueuedConnection)
        bridge.game_chat_opened.connect(self.on_game_chat_opened,
                                        Qt.ConnectionType.QueuedConnection)

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
        if (modules.is_enabled(self.cfg, "game_send")
                and self.cfg.get("game_open_chat_first", True)
                and self.game_hwnd):
            self.opening = True
            threading.Thread(target=self._open_chat_job,
                             args=(self.game_hwnd,), daemon=True).start()
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
        if self._rev():
            self.input.setPlaceholderText(
                i18n.t("Фраза на вашем языке — перевод уйдёт в чат по Enter"))
        else:
            self.input.setPlaceholderText(
                i18n.t("Текст, +фраза для перевода+, *действие*"))
        self.place()
        self._count()
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
            l, t, r, b = (v / dpr for v in rect)
        else:
            g = scr.geometry()
            l, t, r, b = g.left(), g.top(), g.right(), g.bottom()
        fx, fy = self.cfg.get("overlay_pos", [0.01, 0.28])
        self.move(int(l + (r - l) * fx), int(t + (b - t) * fy))

    def _reset(self):
        self.rid += 1
        self.cur, self.err, self.want_send = None, "", False
        self.timer.stop()
        self.input.blockSignals(True)
        self.input.clear()
        self.input.blockSignals(False)
        self._show_result("", "")

    def close_overlay(self, refocus: bool = True) -> None:
        """Скрыть оверлей и закрыть чат игры (Esc), чтобы не висел пустой чат.

        Hide the overlay and close the game chat (Esc), so no empty chat stays
        open behind the game.
        """
        was_open = self.game_chat_open
        hwnd = self.game_hwnd
        self.game_chat_open = False
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

    def keyPressEvent(self, e):
        ctrl = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if e.key() == Qt.Key.Key_Escape:
            self.close_overlay()
        elif ctrl and e.nativeVirtualKey() == 0x52:          # Ctrl+R в любой раскладке
            self.plan.reroll()
            self.on_text()
        else:
            super().keyPressEvent(e)

    def changeEvent(self, e):
        if (e.type() == QEvent.Type.ActivationChange and self.isVisible() and not self.isActiveWindow()
                and not self.sending and time.time() - self.shown_at > 0.8):
            QTimer.singleShot(250, self._lost_focus)
        super().changeEvent(e)

    def _lost_focus(self):
        if self.isVisible() and not self.isActiveWindow():
            self.close_overlay(refocus=False)

    # ----- ввод и перевод -----
    def _pick(self, res: Result) -> str:
        """Что именно отправить в чат: русскую запись или текст на языке.

        What exactly goes to the chat: the Russian reading or the target text,
        depending on the direction and the send_mode setting.
        """
        if self._rev():
            return res.text or res.native     # в обратном режиме показываем русский
        mode = str(self.cfg.get("send_mode", "reading")).lower()
        if mode in ("native", "lang", "text", "target"):
            return res.native or res.text
        return res.text or res.native

    def _rev(self):
        """True, если включён режим «ваш язык → русский»."""
        return str(self.cfg.get("direction", "out")).lower() in ("in", "reverse", "to_ru")

    def _lang_tag(self):
        code = str(self.cfg.get("target_lang", "it")).split("-")[0]
        return code.upper() or "IT"

    def _auto_now(self, text):
        if self._rev():
            return True          # в режиме переводчика переводится всё, что попало в поле
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
        where = i18n.t("перевод входящего → русский") if self._rev() \
            else langs.label(self.cfg.get("target_lang", "it"))
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
        tag = i18n.t("оригинал") if self._rev() else self._lang_tag()
        self.it.setText((tag + ": " + other) if other else "")
        self.it.setVisible(bool(other))
        self.adjustSize()

    def on_text(self, _=None):
        self.rid += 1
        self.cur, self.err, self.want_send = None, "", False
        self.timer.stop()
        text = self.input.text()
        self._count()
        if not text.strip():
            self._show_result("", "")
        elif (self._auto_now(text) or has_markers(text, self.cfg)
                or (self.cfg.get("filler_always", True)
                    and has_fillers(text, self.cfg, self.engine.g))):
            # слова-паразиты переводятся всегда, вне зависимости от счётчика серии
            self._show_result("перевожу…", "")
            self.timer.start(int(self.cfg.get("debounce_ms", 450)))
        else:
            self.cur = Result(text.strip(), "", False)
            self._show_result("", "")

    def _fire(self):
        text = self.input.text()
        self.worker.submit((self.rid, text, self._auto_now(text), self.plan.seed, self._rev()))

    def on_done(self, rid, res, err):
        if rid != self.rid:                       # устаревший ответ
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
        self.set_stat(i18n.tf("В чат уйдёт %d/%d · Enter — отправить · Esc — отмена",
                              len(sent), mx), len(sent) > mx)
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
        text = self.input.text().strip()
        if not text:
            self.close_overlay()
        elif self.cur is not None:
            self.finish(self._pick(self.cur))
        elif self.err:                             # второй Enter после ошибки
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
        # в счётчик серии идут обычные сообщения и /to /lto /l /wt /s /st
        if not out.startswith("/") or is_counted_command(out):
            self.plan.advance()                    # счётчик серии автоперевода
        QApplication.clipboard().setText(out)
        log.info("Готово к отправке: %r", out)
        hwnd = self.game_hwnd or self.tracker.get(True)
        chat_open = self.game_chat_open            # чат уже открыт при открытии оверлея
        self.game_chat_open = False
        self._reset()
        self.hide()
        if modules.is_enabled(self.cfg, "game_send") and hwnd:
            self.sending = True
            threading.Thread(target=self._send_job, args=(hwnd, out, chat_open),
                             daemon=True).start()
        else:
            if chat_open and hwnd:
                # чат был открыт, а отправка в игру выключена — закрыть чат
                threading.Thread(target=self._close_chat_job, args=(hwnd,), daemon=True).start()
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
        self.sending = False
        if not ok:
            self.notify(msg + i18n.t(" Текст в буфере обмена — вставьте вручную (Ctrl+V)."),
                        True)

    def notify(self, msg, warn=False):
        icon = QSystemTrayIcon.MessageIcon.Warning if warn else QSystemTrayIcon.MessageIcon.Information
        self.tray.showMessage(APP_NAME, msg, icon, 6000)


def _as_int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def run_gui(cfg: dict, open_settings_on_start: bool = False) -> int:
    """Запуск интерфейса: оверлей, трей, горячая клавиша и окно настроек.

    Starts the interface: overlay, tray icon, hotkey and settings window.
    Returns the process exit code.
    """
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)

    # язык интерфейса: при первом запуске спрашиваем, дальше берём из настроек
    if not cfg.get("ui_lang_chosen"):
        from app.ui_lang import ask_ui_language
        cfg["ui_lang"] = ask_ui_language(style=STYLE)
        cfg["ui_lang_chosen"] = True
        save_config(cfg)
    i18n.set_lang(cfg.get("ui_lang", "ru"))

    lang = langs.code_of(cfg.get("target_lang", "it"))
    translator = Translator(lang)
    engine = Engine(cfg, load_glossary(lang), translator)
    tracker = gs.GameTracker(cfg)
    bridge = Bridge()
    tray = QSystemTrayIcon(make_icon(), app)
    win = Overlay(cfg, engine, tracker, bridge, tray)
    win.hwnd = int(win.winId())
    state = {"dlg": None, "hk": None, "menu": None}

    # ---------- применение настроек ----------
    def apply_settings(newcfg):
        """Пересобирает движок, горячую клавишу и меню после сохранения настроек."""
        cfg.clear()
        cfg.update(newcfg)
        code = langs.code_of(cfg.get("target_lang", "it"))
        translator.set_target(code)
        translator.set_direction(cfg.get("direction", "out"))
        win.engine = Engine(cfg, load_glossary(code), translator)
        win.plan = AutoPlan(cfg)              # новая серия под новые параметры
        restart_hotkey()
        build_menu()
        i18n.set_lang(cfg.get("ui_lang", "ru"))
        i18n.retranslate(win)
        key = cfg["hotkey"] if modules.is_enabled(cfg, "hotkey") else "без клавиши"
        tray.setToolTip(f"{APP_NAME} · {key} · {langs.label(code)}")
        win.notify(i18n.tf("Настройки сохранены. Язык: %s, клавиша: %s.",
                           langs.label(code), cfg["hotkey"]))

    def set_direction(direction):
        """Переключение режима из меню трея: обычный / перевод входящего."""
        cfg["direction"] = "in" if str(direction).lower() in ("in", "reverse") else "out"
        save_config(cfg)
        apply_settings(dict(cfg))
        win.notify(i18n.t("Режим: ваш язык → русский") if cfg["direction"] == "in"
                   else i18n.t("Режим: русский → выбранный язык перевода"))

    # ---------- окно настроек ----------
    def open_settings_window(first_run=False):
        if state["dlg"] is not None:
            state["dlg"].show()
            state["dlg"].raise_()
            state["dlg"].activateWindow()
            return
        dlg = open_settings(cfg, parent=None, first_run=first_run)
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
            QTimer.singleShot(450, start_hotkey)   # старый поток успевает снять регистрацию

    # ---------- меню трея ----------
    def build_menu():
        """Короткое меню трея: статус переводчика, направление, настройки, выход.

        Всё остальное (язык, автоперевод, отправка в игру, слова-паразиты)
        настраивается в окне «Настройки…».
        """
        menu = QMenu()
        mode_in = str(cfg.get("direction", "out")).lower() in ("in", "reverse")
        code = langs.code_of(cfg.get("target_lang", "it"))

        status = QAction(i18n.t("Статус: ваш язык → русский") if mode_in
                         else i18n.tf("Статус: русский → %s", langs.label(code)), menu)
        status.setEnabled(False)
        menu.addAction(status)
        menu.addSeparator()

        group = QActionGroup(menu)
        group.setExclusive(True)
        for value, text in (("in", i18n.t("Ваш язык → русский")),
                            ("out", i18n.tf("Русский → %s", langs.label(code)))):
            act = QAction(text, menu)
            act.setCheckable(True)
            act.setChecked((value == "in") == mode_in)
            act.triggered.connect(
                lambda _c=False, v=value: set_direction(v) if (v == "in") != mode_in else None)
            group.addAction(act)
            menu.addAction(act)

        menu.addSeparator()
        act_settings = QAction(i18n.t("Настройки…"), menu)
        act_settings.triggered.connect(lambda: open_settings_window())
        menu.addAction(act_settings)
        menu.addAction(i18n.t("Выход"), app.quit)

        state["menu"] = menu
        tray.setContextMenu(menu)
        key = cfg["hotkey"] if modules.is_enabled(cfg, "hotkey") else "без клавиши"
        tray.setToolTip(f"{APP_NAME} · {key} · {langs.label(code)}")

    build_menu()
    # двойной клик по значку в трее открывает оверлей (пункта в меню нет)
    tray.activated.connect(lambda r: win.open_overlay()
                          if r == QSystemTrayIcon.ActivationReason.DoubleClick else None)
    tray.show()

    bridge.hotkey.connect(win.open_overlay, Qt.ConnectionType.QueuedConnection)
    bridge.fail.connect(lambda m: win.notify(m, True), Qt.ConnectionType.QueuedConnection)
    start_hotkey()
    app.aboutToQuit.connect(lambda: state["hk"] and state["hk"].stop())

    game = i18n.t("найдена") if tracker.get(True) else i18n.t("не найдена")
    key = cfg["hotkey"] if modules.is_enabled(cfg, "hotkey") else i18n.t("не назначена")
    win.notify(i18n.tf("Клавиша: %s. Язык: %s. Игра: %s.", key,
                       langs.label(langs.code_of(cfg.get("target_lang", "it"))), game))

    if open_settings_on_start or not cfg.get("setup_done") or cfg.get("show_settings_on_start"):
        QTimer.singleShot(250, lambda: open_settings_window(
            first_run=not cfg.get("setup_done")))
    return app.exec()
