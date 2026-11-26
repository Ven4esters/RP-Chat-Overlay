"""DeepL (DLX) Settings page and its background job."""

import threading
import urllib.parse

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app import dlx as dlx_mod, i18n
from app.config import log
from app.settings_widgets import ToggleSwitch, _card, _hint, _num_row, _small_spin, _title


class DlxJob(QObject):
    """Фоновое действие над сервисом DLX / a background action on the DLX service.

    Сеть и запуск процесса могут занять секунды, поэтому они уходят в поток, а
    окно получает только результат — сигналом, то есть в главном потоке.
    Network calls and process start can take seconds, so they run in a thread and
    the window only receives the result, through a signal, on the main thread.
    """

    finished = Signal(bool, str)  # получилось?, причина / ok?, reason

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def start(self) -> None:
        """Запускает действие в отдельном потоке / starts the action in a thread."""

        def run():
            ok, reason = False, ""
            try:
                ok = bool(self.fn())
            except Exception as error:  # noqa: BLE001 — причину покажем игроку
                log.exception("DLX: фоновое действие не удалось")
                reason = str(error) or type(error).__name__
            self.finished.emit(ok, reason)

        threading.Thread(target=run, daemon=True, name="dlx-job").start()


class DlxSettingsMixin:
    """DLX page and its live status/actions, isolated from the main dialog."""

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
        cl.addWidget(
            _hint(
                "Никому не обязательно. Без DeepL программа переводит через Google и "
                "остальные сервисы — так она работает сразу после установки, и "
                "большинству игроков этого достаточно. DeepL — это шаг в качестве для "
                "тех, кто готов потратить пять минут: либо включите VPN с зарубежным "
                "выходом, либо разверните свой сервис и впишите его адрес ниже (как "
                "это сделать — VERCEL.md в папке source/tools/deeplx-local). Общий "
                "адрес у всех быть не может: DeepL быстро упирается в лимиты частоты, "
                "и один перегруженный сервис отказывает всем сразу."
            )
        )
        lay.addWidget(card)

        card, cl = _card()
        cl.addWidget(_title("DeepL рядом (DLX)", "sec"))
        cl.addWidget(
            _hint(
                "DLX — отдельная бесплатная программа с открытым кодом (лицензия MIT), "
                "которая работает на вашем компьютере и переводит через движок DeepL. "
                "Она занимает около 15 МБ и запускается вместе с программой. Текст при "
                "этом уходит на серверы DeepL — так же, как сейчас уходит в Google. "
                "Сервис неофициальный: DeepL может ограничить запросы, и тогда перевод "
                "автоматически вернётся к стандартным сервисам."
            )
        )
        self.chk_dlx = QCheckBox("Переводить через DeepL в первую очередь")
        self.chk_dlx.setObjectName("moduleToggle")
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
        self.lb_dlx_state.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
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
        self.b_dlx_start.setProperty("no_i18n", True)  # текст меняется в коде
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
        cl.addWidget(
            _hint(
                "Сервис слушает только ваш компьютер. Порт выбирается свободный, а "
                "запросы подписываются токеном, чтобы чужие программы не могли гонять "
                "трафик через ваш DeepL."
            )
        )
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
        self.ed_dlx_pro.setToolTip("OAuth-токен DeepL Pro; без него работает бесплатный путь")
        form.addRow("Токен DeepL Pro", self.ed_dlx_pro)
        # свой сервис вместо бинарника: локальный сервер на Node.js или
        # развёрнутый DeepLX / a service of your own instead of the binary
        self.ed_dlx_url = QLineEdit()
        self.ed_dlx_url.setPlaceholderText("http://127.0.0.1:1188")
        self.ed_dlx_url.setToolTip(
            "Пусто — работать через dlx.exe. Адрес своего сервиса — и файл скачивать не нужно"
        )
        form.addRow("Свой адрес сервиса", self.ed_dlx_url)
        self.ed_dlx_url_token = QLineEdit()
        self.ed_dlx_url_token.setPlaceholderText("необязательно")
        self.ed_dlx_url_token.setToolTip(
            "Токен, с которым запущен ваш сервис (TOKEN=…); если он не задан — пусто"
        )
        form.addRow("Токен своего сервиса", self.ed_dlx_url_token)
        cl.addLayout(form)
        # пояснение под полем адреса: откуда взяться своему сервису
        # a remark under the address field: where such a service comes from
        self.lb_dlx_url_note = QLabel(
            "Укажите совместимый с DLX HTTP-сервис, например свой сервер Vercel из "
            "source/tools/deeplx-local, и его токен. Включите «Переводить через DeepL "
            "в первую очередь»: приложение отправит текст и выбранный язык сюда первым, "
            "а при ошибке вернётся к обычным переводчикам. Язык выбирается на странице "
            "«Основные» из списка поддерживаемых приложением. Можно вставить базовый "
            "адрес или полный /api/translate — маршрут программа подставит сама. "
            "При заданном адресе файл dlx.exe не нужен."
        )
        self.lb_dlx_url_note.setWordWrap(True)
        self.lb_dlx_url_note.setStyleSheet("color:#91a4bd;font-size:11px;")
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
        cl.addWidget(
            _hint(
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
                "владельцев подписки и снимает лимиты."
            )
        )
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
        self.chk_dlx_sysproxy = QCheckBox("Брать прокси из настроек Windows, если свой не задан")
        self.chk_dlx_sysproxy.setToolTip(
            "VPN в режиме «системный прокси» прописывает адрес в Windows — "
            "сервис будет ходить через него"
        )
        cl.addWidget(self.chk_dlx_sysproxy)
        row = QHBoxLayout()
        self.b_dlx_proxy_check = QPushButton("Проверить выход")
        self.b_dlx_proxy_check.setAutoDefault(False)
        self.b_dlx_proxy_check.setToolTip(
            "Покажет адрес и страну, из которой выходит прокси (запрос идёт через него)"
        )
        self.b_dlx_proxy_check.clicked.connect(self._dlx_proxy_exit)
        row.addWidget(self.b_dlx_proxy_check)
        row.addStretch(1)
        cl.addLayout(row)
        self.lb_dlx_proxy_note = QLabel("")
        self.lb_dlx_proxy_note.setWordWrap(True)
        self.lb_dlx_proxy_note.setProperty("no_i18n", True)
        self.lb_dlx_proxy_note.setStyleSheet("color:#91a4bd;font-size:11px;")
        cl.addWidget(self.lb_dlx_proxy_note)
        self.ed_dlx_proxy.textChanged.connect(self._dlx_proxy_note)
        lay.addWidget(card)
        lay.addStretch(1)
        # прогресс скачивания приходит из потока строкой; окно читает её таймером
        # download progress arrives from a thread as plain text; a timer reads it
        self._dlx_progress = ""
        self._dlx_timer = QTimer(self)
        self._dlx_timer.setInterval(300)
        self._dlx_timer.timeout.connect(
            lambda: self.lb_dlx_state.setText(self._dlx_progress) if self._dlx_progress else None
        )
        # Сервис может подняться или упасть сам, без нажатия кнопок: состояние
        # в окне должно меняться вместе с ним, иначе «Запущено» так и висело бы
        # после падения. Опрос дешёвый — одно чтение полей под замком.
        # The service may come up or die on its own, without a button press, and
        # the window has to follow: otherwise "Running" would stay after a crash.
        # The poll is cheap: it reads a few fields under one lock.
        self._dlx_live_key = None
        self._dlx_busy_now = False
        self._dlx_was_applied = False  # первый проход без анимации / no animation first
        self._dlx_live = QTimer(self)
        self._dlx_live.setInterval(1000)
        self._dlx_live.timeout.connect(self._dlx_live_tick)
        self._dlx_live.start()
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
        running = bool(status) and (
            state in ("ready", "upstream", "starting")
            or (state not in ("off", "missing", "error") and status.get("running"))
        )
        if state == "upstream":
            caption = i18n.t("Запущено")
            tip = i18n.t(
                "Сервис работает, но DeepL отказывает (503) — чаще всего "
                "из-за региональной блокировки. Выключите тумблер, чтобы "
                "остановить."
            )
        elif state == "starting":
            caption = i18n.t("Запускается…")
            tip = i18n.t("Сервис поднимается; тумблер остановит его.")
        elif running:
            caption = i18n.t("Запущено")
            tip = i18n.t("Сервис работает. Выключите тумблер, чтобы остановить.")
        else:
            caption = i18n.t("Остановлено")
            tip = i18n.t("Поднять локальный сервис. Пока он не запущен, DeepL не используется.")
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
            ""
            if running
            else i18n.t(
                "Пока сервис не запущен, перевод идёт через стандартные сервисы, "
                "а DeepL не используется."
            )
        )
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
            self.b_dlx_install.setText(
                i18n.t("Обновить") if self.dlx.installed() else i18n.t("Установить")
            )
        for button in (self.b_dlx_install, self.b_dlx_remove, self.b_dlx_check, self.b_dlx_token):
            button.setEnabled(self.dlx is not None)

    @staticmethod
    def _dlx_status_key(status):
        """Короткая подпись состояния для сравнения / a short state key."""
        if not status:
            return None
        return (
            status.get("state"),
            status.get("port"),
            status.get("version"),
            status.get("installed"),
            status.get("running"),
        )

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
            self.lb_dlx_proxy_note.setText(
                i18n.t("Адрес не подходит: нужен http://, https:// или socks5:// с портом.")
            )
            return
        self.lb_dlx_proxy_note.setStyleSheet("color:#91a4bd;font-size:11px;")
        parsed = urllib.parse.urlparse(normalized)
        if parsed.scheme == "http" and parsed.port in (1080, 1081, 9050):
            self.lb_dlx_proxy_note.setText(
                i18n.tf("Порт %d — обычно у SOCKS5; сервис сам подставит socks5://.", parsed.port)
            )
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
            QMessageBox.information(
                self, i18n.t("DeepL рядом"), i18n.t("Прокси не задан — сервис ходит напрямую.")
            )
            return
        proxy = dlx_mod.normalize_proxy(text)
        if not proxy:
            QMessageBox.warning(
                self,
                i18n.t("DeepL рядом"),
                i18n.t("Адрес не подходит: нужен http://, https:// или socks5:// с портом."),
            )
            return
        verdict = {}

        def job():
            ok, line = dlx_mod.proxy_exit(proxy)
            verdict["text"] = line
            return ok

        def done(ok, reason):
            line = verdict.get("text") or reason or i18n.t("неизвестно")
            self.lb_dlx_proxy_note.setStyleSheet(
                "color:#66d18b;font-size:11px;" if ok else "color:#ff8f8f;font-size:11px;"
            )
            self.lb_dlx_proxy_note.setText(line)
            if ok:
                QMessageBox.information(
                    self, i18n.t("DeepL рядом"), i18n.tf("Прокси работает. Выход: %s", line)
                )
            else:
                QMessageBox.warning(
                    self, i18n.t("DeepL рядом"), i18n.tf("Прокси не годится: %s", line)
                )

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
            QMessageBox.warning(
                self,
                i18n.t("DeepL рядом"),
                i18n.t("Сервис не подключён — перезапустите программу."),
            )
            return False
        return True

    def _dlx_busy(self, busy, text=""):
        """Блокирует кнопки на время работы / locks the buttons while working."""
        if text:
            self.lb_dlx_state.setText(text)
        self._dlx_busy_now = bool(busy)
        for button in (
            self.b_dlx_check,
            self.b_dlx_install,
            self.b_dlx_remove,
            self.b_dlx_token,
            self.b_dlx_proxy_check,
        ):
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
        self._dlx_job = job  # ссылка, иначе объект соберёт сборщик мусора

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
                self,
                i18n.t("DeepL рядом"),
                i18n.t("Сервис отвечает нормально.")
                if ok
                else i18n.t("Сервис не отвечает. Нажмите «Запустить» или «Установить»."),
            )

        self._dlx_run(self.dlx.health, i18n.t("Проверяю…"), done)

    def _dlx_start(self):
        """Запуск сервиса вручную / start the service by hand."""
        if not self._dlx_guard():
            return

        def done(ok, reason):
            if not ok:
                QMessageBox.warning(
                    self,
                    i18n.t("DeepL рядом"),
                    i18n.t("Запустить не удалось: %s")
                    % (self.dlx.status().get("reason") or reason or i18n.t("неизвестно")),
                )

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
            self,
            i18n.t("Установка сервиса"),
            i18n.t(
                "Скачать локальный сервис DeepL с GitHub?\n\n"
                "Около 15 МБ, лицензия MIT, файл кладётся рядом с программой.\n"
                "Текст перевода будет уходить на серверы DeepL."
            ),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        def job():
            return self.dlx.install(lambda text: setattr(self, "_dlx_progress", text))

        def done(ok, reason):
            if not ok:
                QMessageBox.warning(
                    self,
                    i18n.t("DeepL рядом"),
                    i18n.t("Установить не удалось: %s")
                    % (self.dlx.status().get("reason") or reason or i18n.t("неизвестно")),
                )
                return
            self._dlx_refresh()
            QMessageBox.information(
                self, i18n.t("DeepL рядом"), i18n.t("Сервис установлен и готов к работе.")
            )
            if self.chk_dlx.isChecked():
                # запуск тоже в фоне: ожидание готовности занимает секунды
                # the start also runs in the background: waiting for readiness
                # takes seconds
                self._dlx_run(self.dlx.ensure, i18n.t("Запускается…"), lambda ok, reason: None)

        self._dlx_run(job, i18n.t("Скачиваю…"), done)

    def _dlx_remove(self):
        """Удаление сервиса с диска / remove the service from disk."""
        if not self._dlx_guard():
            return
        answer = QMessageBox.question(
            self,
            i18n.t("Удаление сервиса"),
            i18n.t(
                "Удалить сервис DeepL с диска?\nПрограмма вернётся к обычным "
                "сервисам перевода, настройки останутся."
            ),
        )
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
