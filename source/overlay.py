"""overlay.py — оверлей-чат (PySide6).

Порядок работы: горячая клавиша → СНАЧАЛА открывается чат игры (T),
чтобы окружающие видели, что вы пишете, → только потом оверлей,
Enter → вставка в уже открытый чат и отправка. Esc → чат игры закрывается.
"""
import sys
import threading
import time

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QActionGroup, QColor, QFont, QGuiApplication, QIcon,
                           QPainter, QPixmap)
from PySide6.QtWidgets import (QApplication, QFrame, QLabel, QLineEdit, QMenu,
                               QSystemTrayIcon, QVBoxLayout, QWidget)

import gamesend as gs
import langs
from autoplan import AutoPlan
from common import log, save_config
from engine import (Engine, Result, has_fillers, has_markers, is_counted_command,
                      load_glossary, strip_markers)
from hotkey import HotkeyThread
from settings_ui import open_settings
from translator import Translator

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
        self.input.setPlaceholderText("Текст, +фраза для перевода+, *действие*")  # язык — в статусе
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
        self.worker = Worker(lambda j: self.engine.process(j[1], j[2], j[3]),
                             lambda j, r, e: self.bridge.translated.emit(j[0], r, str(e) if e else ""))
        self.worker.start()
        bridge.translated.connect(self.on_done, Qt.ConnectionType.QueuedConnection)
        bridge.sent.connect(self.on_sent, Qt.ConnectionType.QueuedConnection)
        bridge.game_chat_opened.connect(self.on_game_chat_opened,
                                        Qt.ConnectionType.QueuedConnection)

    # ----- показ / скрытие -----
    def open_overlay(self, *_):
        """Сначала открыть чат игры (T), только потом показать оверлей.

        Так окружающие в игре видят, что вы пишете, а не стоите без действия.
        Пока чат открывается (пауза game_open_delay_ms), оверлей не виден.
        """
        if self.sending or self.opening:
            return
        if self.isVisible():
            self.close_overlay()
            return
        self.prev_hwnd = gs.user32.GetForegroundWindow()
        self.game_hwnd = self.tracker.get(True)
        if (self.cfg.get("game_send", True)
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

    def close_overlay(self, refocus=True):
        """Скрыть оверлей и закрыть чат игры (Esc), чтобы не висел пустой чат."""
        was_open = self.game_chat_open
        hwnd = self.game_hwnd
        self.game_chat_open = False
        self._reset()
        self.hide()
        if was_open and self.cfg.get("game_send", True) and hwnd:
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
    def _pick(self, res):
        """Что именно отправить в чат: русскую запись или текст на языке."""
        mode = str(self.cfg.get("send_mode", "reading")).lower()
        if mode in ("native", "lang", "text", "target"):
            return res.italian or res.text
        return res.text or res.italian

    def _lang_tag(self):
        code = str(self.cfg.get("target_lang", "it")).split("-")[0]
        return code.upper() or "IT"

    def _auto_now(self, text):
        # /to /lto /l /wt /s /st участвуют в счётчике наравне с обычным текстом
        if text.lstrip().startswith("/") and not is_counted_command(text):
            return False
        return self.plan.is_auto()

    def set_stat(self, text, err=False):
        self.stat.setStyleSheet("color:#ff6b6b;" if err else "")
        self.stat.setText(text)

    def _count(self):
        n, mx = len(self.input.text()), int(self.cfg.get("max_chars", 256))
        game = "найдена" if self.game_hwnd else "НЕ найдена"
        parts = [f"{n}/{mx}", f"{langs.label(self.cfg.get('target_lang', 'it'))}", f"игра: {game}"]
        auto = self.plan.label()
        if auto:
            parts.append(auto)
        parts.append("Enter — отправить · Esc — отмена")
        self.set_stat(" · ".join(parts), n > mx)

    def _show_result(self, out, other="", err=False):
        self.out.setStyleSheet("color:#ff6b6b;" if err else "")
        self.out.setText(out)
        self.out.setVisible(bool(out))
        self.it.setText((self._lang_tag() + ": " + other) if other else "")
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
        self.worker.submit((self.rid, text, self._auto_now(text), self.plan.seed))

    def on_done(self, rid, res, err):
        if rid != self.rid:                       # устаревший ответ
            return
        mx = int(self.cfg.get("max_chars", 256))
        if err:
            self.err = err
            self.want_send = False
            self._show_result("Ошибка перевода: " + err[:160], "", True)
            self.set_stat("Enter — отправить без перевода · Esc — отмена", True)
            return
        self.cur = res
        sent = self._pick(res)
        other = res.italian if sent == res.text else res.text
        self._show_result(sent, other if res.translated else "")
        self.set_stat(f"В чат уйдёт {len(sent)}/{mx} · Enter — отправить · Esc — отмена",
                      len(sent) > mx)
        if self.want_send:
            self.want_send = False
            self.finish(sent)

    def on_enter(self):
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
    def finish(self, out):
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
        if self.cfg.get("game_send", True) and hwnd:
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
            self.notify("Скопировано в буфер обмена (Ctrl+V).")

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
            self.notify(msg + " Текст в буфере обмена — вставьте вручную (Ctrl+V).", True)

    def notify(self, msg, warn=False):
        icon = QSystemTrayIcon.MessageIcon.Warning if warn else QSystemTrayIcon.MessageIcon.Information
        self.tray.showMessage("RP Chat Overlay", msg, icon, 6000)


def _as_int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def run_gui(cfg, open_settings_on_start=False):
    """Запуск интерфейса: оверлей, трей, горячая клавиша и окно настроек."""
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)

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
        win.engine = Engine(cfg, load_glossary(code), translator)
        win.plan = AutoPlan(cfg)              # новая серия под новые параметры
        restart_hotkey()
        build_menu()
        tray.setToolTip(f"RP Chat Overlay · {cfg['hotkey']} · {langs.label(code)}")
        win.notify(f"Настройки сохранены. Язык: {langs.label(code)}, "
                   f"клавиша: {cfg['hotkey']}.")

    def set_lang(code):
        """Быстрое переключение языка из меню трея."""
        cfg["target_lang"] = langs.code_of(code)
        save_config(cfg)
        apply_settings(dict(cfg))

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
        hk = HotkeyThread(cfg["hotkey"], bridge.hotkey.emit, active, bridge.fail.emit)
        state["hk"] = hk
        hk.start()

    def restart_hotkey():
        old = state["hk"]
        if old is not None:
            old.stop()
        QTimer.singleShot(450, start_hotkey)   # старый поток успевает снять регистрацию

    # ---------- меню трея ----------
    def toggle(parent, key, label):
        act = QAction(label, parent)
        act.setCheckable(True)
        act.setChecked(bool(cfg.get(key)))
        act.toggled.connect(lambda v, k=key: set_cfg(k, bool(v)))
        parent.addAction(act)
        return act

    def choice(parent, title, key, options):
        sub = parent.addMenu(title)
        group = QActionGroup(sub)
        group.setExclusive(True)
        cur = str(cfg.get(key)).lower()
        for value, text in options:
            act = QAction(text, sub)
            act.setCheckable(True)
            act.setChecked(str(value).lower() == cur)
            group.addAction(act)
            sub.addAction(act)
            act.triggered.connect(lambda _c=False, k=key, v=value: set_cfg(k, v))
        return sub

    def set_cfg(key, value):
        cfg[key] = value
        save_config(cfg)
        win.plan.changed()

    def build_menu():
        menu = QMenu()
        menu.addAction(f"Открыть оверлей ({cfg['hotkey']})", win.open_overlay)
        act_settings = QAction("Настройки…", menu)
        act_settings.triggered.connect(lambda: open_settings_window())
        menu.addAction(act_settings)

        sub_lang = menu.addMenu("Язык перевода")
        group = QActionGroup(sub_lang)
        group.setExclusive(True)
        cur = langs.code_of(cfg.get("target_lang", "it"))
        for code, name in langs.choices():
            act = QAction(name, sub_lang)
            act.setCheckable(True)
            act.setChecked(code == cur)
            group.addAction(act)
            sub_lang.addAction(act)
            act.triggered.connect(lambda _c=False, c=code: set_lang(c))

        menu.addSeparator()
        toggle(menu, "game_send", "Вставлять в чат игры")
        toggle(menu, "game_open_chat_first", "Сначала открывать чат игры (T)")
        toggle(menu, "game_submit", "Сразу отправлять (Enter в игре)")
        toggle(menu, "filler_always", "Слова-паразиты всегда")

        auto = menu.addMenu("Авто-перевод")
        toggle(auto, "auto_mode", "Включить автоперевод")
        every = sorted({2, 3, 4, 5, 6, 8, 10, _as_int(cfg.get("auto_every"), 4)})
        choice(auto, "Серия сообщений", "auto_every", [(v, f"по {v} сообщ.") for v in every])
        choice(auto, "Какое в серии переводить", "auto_position",
               [("last", "последнее (каждое N-е)"), ("first", "первое"),
                ("random", "случайное")])
        choice(auto, "Фрагментов в сообщении", "auto_fragments", [(1, "1"), (2, "2"), (3, "3")])
        choice(auto, "Длина фрагмента", "auto_max_words",
               [(1, "только слова"), (2, "до 2 слов"), (3, "до 3 слов"), (4, "до 4 слов")])
        toggle(auto, "auto_prefer_glossary", "Предпочитать фразы из словаря")

        menu.addSeparator()
        menu.addAction("Выход", app.quit)
        state["menu"] = menu
        tray.setContextMenu(menu)
        tray.setToolTip(f"RP Chat Overlay · {cfg['hotkey']} · "
                        f"{langs.label(langs.code_of(cfg.get('target_lang', 'it')))}")

    build_menu()
    tray.show()

    bridge.hotkey.connect(win.open_overlay, Qt.ConnectionType.QueuedConnection)
    bridge.fail.connect(lambda m: win.notify(m, True), Qt.ConnectionType.QueuedConnection)
    start_hotkey()
    app.aboutToQuit.connect(lambda: state["hk"] and state["hk"].stop())

    game = "найдена" if tracker.get(True) else "не найдена"
    win.notify(f"Клавиша: {cfg['hotkey']}. Язык: "
               f"{langs.label(langs.code_of(cfg.get('target_lang', 'it')))}. Игра: {game}.")

    if open_settings_on_start or not cfg.get("setup_done") or cfg.get("show_settings_on_start"):
        QTimer.singleShot(250, lambda: open_settings_window(
            first_run=not cfg.get("setup_done")))
    return app.exec()
