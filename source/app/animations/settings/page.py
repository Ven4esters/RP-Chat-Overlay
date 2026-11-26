"""Animation settings page and its behavior mixin."""

import json
from pathlib import Path
import threading
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app import i18n, langs, morph
from app import animations as anims
from app.config import DATA, log
from app.engine import Glossary
from app.animations.settings.properties import ask_anim_props
from app.settings_style import _fit_dialog, style_sheet
from app.settings_widgets import DragTable, KeyCapture, _card, _hint, _pretty_hotkey, _title


class AnimationsSettingsMixin:
    """Methods that build and manage the dedicated Animations settings page."""

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
        self.chk_anims.setObjectName("moduleToggle")
        self.chk_anims.setChecked(bool(self.cfg.get("anims_enabled", False)))
        self.chk_anims.toggled.connect(self._anims_toggled)
        self.chk_anims.toggled.connect(lambda on: self._mirror_own_flag("anims", on))
        cl.addWidget(self.chk_anims)
        cl.addWidget(
            _hint(
                "Ключевое слово в вашем сообщении запускает анимацию: в чат игры уходит "
                "/anim «название», а через заданное время она останавливается — командой "
                "/sa, нажатием клавиши или обоими способами, как выбрано ниже. При "
                "зацикливании остановки нет: по истечении того же времени анимация "
                "просто запускается снова, пока не нажать клавишу остановки. "
                "Длительность 0 мс означает «не останавливать вовсе». Работает только "
                "вместе с модулем «Отправка в игру»."
            )
        )

        # Режим «В машине»: главный выключатель тишины. Стоит рядом с включением
        # модуля, потому что это такое же «работать или нет», только на время
        # поездки. Дублируется пунктом в меню трея — включать его в поездке
        # удобнее оттуда.
        # The "In a vehicle" mode: the main silence switch. It sits next to the
        # module switch, because it is the same "run or not", only for the length
        # of a ride. The tray menu item does the same, and is handier on the move.
        self.chk_anim_vehicle = QCheckBox("В машине — не играть анимации (ни /anim, ни /sa)")
        self.chk_anim_vehicle.setChecked(bool(self.cfg.get("anim_in_vehicle", False)))
        self.chk_anim_vehicle.setToolTip(
            "В транспорте анимации ломают позу, а /sa и нажатие клавиши "
            "выбрасывают из машины. Пока галочка стоит, в игру не уходит ни одна "
            "команда анимаций: очередь снимается, зацикливание прекращается, "
            "уходит один /sa — и дальше тишина. Включается и из меню трея."
        )
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
            "игра, поэтому подойдёт обычная игровая клавиша вроде F."
        )
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
        self.chk_anim_stop_sa.setToolTip("В чат игры уходит /sa — так анимацию гасит сама игра.")
        self.chk_anim_stop_sa.toggled.connect(self._anim_stop_changed)
        cl.addWidget(self.chk_anim_stop_sa)

        self.chk_anim_stop_key = QCheckBox("Останавливать анимацию нажатием клавиши F (симуляция)")
        self.chk_anim_stop_key.setProperty("no_i18n", True)
        self.chk_anim_stop_key.setChecked(bool(self.cfg.get("anim_stop_by_key", False)))
        self.chk_anim_stop_key.setToolTip(
            "Программа нажимает клавишу остановки в игре, как если бы её нажали вы. "
            "Клавиша берётся из поля выше."
        )
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
            "выключается."
        )
        self.chk_anim_negation.toggled.connect(self._anims_changed)
        cl.addWidget(self.chk_anim_negation)

        # Подсказки в оверлее: список ключевых слов под полем ввода и
        # пролистывание по Tab. Выключить можно, если список мешает.
        # Hints in the overlay: the keyword list under the input and Tab walking.
        # They can be switched off when the list gets in the way.
        self.chk_anim_hints = QCheckBox("Подсказывать ключевые слова в оверлее (Tab — пролистать)")
        self.chk_anim_hints.setChecked(bool(self.cfg.get("anim_hints", True)))
        self.chk_anim_hints.setToolTip(
            "Пока вы печатаете, под полем ввода появляются ключевые слова "
            "правил, начинающиеся с набранного: Tab листает их, Enter "
            "подставляет выбранное, Esc убирает список. Подсказка заменяет "
            "только последнее набранное слово, остальной текст не трогает."
        )
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
            "на весь экран — там строки ещё выше."
        )
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
            "0 — запускать сразу после анимации."
        )
        self.sp_anim_gap.valueChanged.connect(self._anims_changed)
        gap_row.addWidget(self.sp_anim_gap)
        gap_row.addStretch(1)
        cl.addLayout(gap_row)
        lay.addWidget(card)

        live_card, ll = _card()
        ll.addWidget(_title("Проверка в игре", "sec"))
        ll.addWidget(
            _hint(
                "Слова проверяются в окне настроек, а отправку видит только игра. "
                "Кнопка «Отправить /anim в игру» запускает выбранное правило прямо "
                "сейчас — так видно, доходит ли команда: если игра не ответила, "
                "причина появится здесь же."
            )
        )
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
        tl.addWidget(
            _hint(
                "Напишите фразу так, как отправили бы её в игру, и посмотрите, какие "
                "правила на неё сработают. Здесь проверяются только слова: отправку "
                "команд проверяет блок «Проверка в игре» выше."
            )
        )
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

        lay.addWidget(
            _hint(
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
                "считаются: «Сел откинувшись, а потом сел прямо» запустит обе."
            )
        )
        lay.addWidget(
            _hint(
                "Строки таблицы перетаскиваются мышью — вместе с правилом едут его "
                "режим, формы, длительность и галочки. Пока строку тянут, она "
                "подсвечена, а синяя линия показывает, куда она встанет. Порядок в "
                "таблице нужен для удобства: в игре анимации играют по порядку слов "
                "в сообщении."
            )
        )
        lay.addWidget(
            _hint(
                "ПКМ по строке — «Варианты и свойства…»: там задаются варианты, если "
                "одному ключу подходят несколько анимаций. Например, ключ «оперся "
                "руками» с вариантами anim_counterleanbar и anim_leanrail: в игре "
                "откроется оверлей выбора с названием и описанием каждого. Один "
                "вариант — обычное правило, оно играет сразу."
            )
        )
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
        self.ed_anim_find.setPlaceholderText(i18n.t("Поиск по словам, /anim и описаниям вариантов"))
        self.ed_anim_find.setClearButtonEnabled(True)
        self.ed_anim_find.textChanged.connect(self._anim_find_changed)
        self.ed_anim_find.setToolTip(
            i18n.t(
                "Ищет по ключевым словам, по названию /anim и по описаниям "
                "вариантов. Строки, которые не подходят, прячутся, а правила "
                "остаются на своих местах."
            )
        )
        find_row.addWidget(self.ed_anim_find, 1)
        self.bt_anim_expand = QPushButton(i18n.t("На весь экран"))
        self.bt_anim_expand.setCheckable(True)
        self.bt_anim_expand.setToolTip(
            i18n.t(
                "Развернуть таблицу правил на весь экран — удобнее править длинные "
                "ключевые слова. То же самое делает двойной щелчок по шапке таблицы."
            )
        )
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
            ["Вкл", "Ключевые слова", "/anim", "Режим", "Формы", "мс", "Зацикливать"]
        )
        head = self.tbl_anims.horizontalHeader()
        head.setMinimumSectionSize(38)
        for column, policy in (
            (0, QHeaderView.ResizeMode.ResizeToContents),
            (1, QHeaderView.ResizeMode.Stretch),
            (2, QHeaderView.ResizeMode.Stretch),
            (3, QHeaderView.ResizeMode.Fixed),
            (4, QHeaderView.ResizeMode.Fixed),
            (5, QHeaderView.ResizeMode.ResizeToContents),
            (6, QHeaderView.ResizeMode.ResizeToContents),
        ):
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
        for button in (
            self.bt_anim_add,
            self.bt_anim_del,
            self.bt_anim_up,
            self.bt_anim_down,
            b_imp,
            b_exp,
        ):
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
            base = int(height if height is not None else self.cfg.get("anim_row_height", 34) or 34)
        except (TypeError, ValueError):
            base = 34
        base = max(24, min(96, base))
        self.tbl_anims.verticalHeader().setDefaultSectionSize(int(round(base * self._ui_scale())))

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
            on = bool(getattr(self, "chk_anim_vehicle", None) and self.chk_anim_vehicle.isChecked())
        if not on:
            self.lb_anim_vehicle.setText("")
            return
        text = i18n.t(
            "Режим включён: ни /anim, ни /sa в игру не уходят. Действует до "
            "выключения галочки, в том числе после перезапуска программы."
        )
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
            self._anim_say(
                i18n.t("Проверка в игре работает, когда настройки открыты из программы.")
            )
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
            self._anim_say(i18n.t("Сначала выберите правило с названием анимации."))
            return
        problem = anims.Rule(keywords="слово", name=name).problem()
        if problem:
            self._anim_say(i18n.t("Название не подойдёт: ") + i18n.t(problem))
            return
        if len(variants) > 1:
            # честно: проверяется только один из вариантов
            # honest: only one of the variants is being checked
            self._anim_say(
                i18n.tf(
                    "У правила %d варианта(ов) — отправляю первый: /anim %s", len(variants), name
                ),
                seconds=25.0,
            )
        else:
            self._anim_say(i18n.tf("Отправляю /anim %s в игру…", name), seconds=25.0)
        threading.Thread(
            target=lambda: self.anim_test_done.emit(*api["send"](name)),
            name="anim-test",
            daemon=True,
        ).start()

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
            self._anim_say(i18n.t("Остановка доступна, когда настройки открыты из программы."))
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
        log.info(
            "Анимации: правило «%s» переставлено (%d -> %d)", rule.keywords[:30], source, target
        )

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
        elif act_merge_all is not None and chosen is not None and isinstance(chosen.data(), int):
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
        log.info(
            "Анимации: правило «%s» объединено с %d другим(и)", merged.keywords[:40], len(others)
        )
        if empty:
            self._anim_say(
                i18n.tf(
                    "Правила объединены. Осталось задать: %s — заполните в «Варианты "
                    "и свойства…» или в таблице.",
                    self._empty_fields_text(empty),
                )
            )
        else:
            self._anim_say(
                i18n.t("Правила объединены: задержка, повтор и режим совпадали и перенесены.")
            )

    @staticmethod
    def _empty_fields_text(fields):
        """Названия незаполненных полей по-человечески / human names of empty fields."""
        names = {
            "duration_ms": i18n.t("задержка"),
            "loop": i18n.t("повтор"),
            "forms": i18n.t("словоформы"),
            "mode": i18n.t("режим"),
        }
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
        chosen = menu.exec(self.tbl_anims.viewport().mapToGlobal(self.tbl_anims.rect().center()))
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
        if not ask_anim_props(rule, self, style_factory=style_sheet):
            return
        # правило заменяется целиком: имя, варианты, всё остальное как было
        # the rule is replaced as a whole: the name, the variants, the rest as is
        rules[row] = rule
        self._fill_anims(rules)
        self.tbl_anims.selectRow(row)
        self._anims_changed()
        log.info(
            "Анимации: свойства правила «%s» сохранены (вариантов: %d)",
            rule.keywords[:30],
            len(rule.variant_list()),
        )

    def _duplicate_anim(self, row):
        self._hist_shadow = self._hist_state()
        """Скопировать правило в новую строку под ним / copy a rule below itself."""
        rules = self._collect_anims()
        if not 0 <= row < len(rules):
            return
        copy = anims.Rule.from_dict(rules[row].to_dict())
        copy.id = anims.Rule().id  # новый id, чтобы строки не путались
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
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            return item

        item_on = checkable(rule.enabled)
        # id едет в первой ячейке вместе с галочкой — по нему правило находится
        # после пересборки таблицы
        # the id travels in the first cell next to the checkbox, so the rule can
        # be found again after the table is rebuilt
        item_on.setData(Qt.ItemDataRole.UserRole, rule.id)
        item_loop = checkable(rule.loop)
        cells = [
            item_on,
            QTableWidgetItem(rule.keywords),
            QTableWidgetItem(self._anim_name_cell(rule)),
            None,  # режим — выпадающий список,
            None,  # формы — тоже список,
            QTableWidgetItem(str(rule.duration_ms)),
            item_loop,
        ]
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
                name_item.setData(
                    Qt.ItemDataRole.UserRole + 1, [choice.to_dict() for choice in rule.choices]
                )
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
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
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
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        forms_combo.setMinimumContentsLength(6)
        forms_combo.setMinimumWidth(88)
        forms_combo.setCurrentIndex(max(0, int(forms_combo.findData(int(rule.forms)))))
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
            if isinstance(forms_combo, QComboBox) and forms_combo.currentData() is not None:
                forms = int(forms_combo.currentData())
            raw_ms = text(5).replace(" ", "")
            try:
                duration = int(raw_ms)
            except ValueError:
                duration = -1  # problem() скажет «длительность должна быть…»
            item_loop = self.tbl_anims.item(row, 6)
            # варианты из ячейки имени: обычное правило их не имеет, и тогда
            # остаётся только name, как раньше
            # the variants come from the name cell; a plain rule has none, and
            # then only name remains, exactly as before
            name_item = self.tbl_anims.item(row, 2)
            raw_choices = (
                name_item.data(Qt.ItemDataRole.UserRole + 1) if name_item is not None else None
            )
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
        note = i18n.tf("Правил: %d, готовы к работе: %d, с зацикливанием: %d", total, active, loops)
        # поиск не должен теряться за счётчиком: сколько правил он оставил
        # the search must not disappear behind the counter: how many it left
        find = getattr(self, "ed_anim_find", None)
        if find is not None and find.text().strip():
            shown = sum(1 for row in range(total) if not self.tbl_anims.isRowHidden(row))
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
            lines = [
                i18n.tf("Строка %d: ", index + 1) + i18n.t(problem) for index, problem in problems
            ]
            notes.append(i18n.t("Проверьте правила: ") + "; ".join(lines))
        if not morph.lemmas_available() and any(rule.forms == morph.FORMS_LEMMA for rule in rules):
            # честно: без пакета pymorphy3 уровень «Леммы» работает как «Основы»
            # honest: without pymorphy3 the "Lemmas" level behaves like "Stems"
            notes.append(i18n.t("Пакет pymorphy3 не найден: уровень «Леммы» сравнивает по основе."))
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
            self.lb_anims_count.setText(self.lb_anims_count.text() + i18n.t(" · модуль выключен"))

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
            self.chk_anim_stop_key.setText(
                i18n.tf("Останавливать анимацию нажатием клавиши %s (симуляция)", pretty)
            )
        by_sa = (
            bool(self.chk_anim_stop_sa.isChecked()) if hasattr(self, "chk_anim_stop_sa") else True
        )
        by_key = (
            bool(self.chk_anim_stop_key.isChecked())
            if hasattr(self, "chk_anim_stop_key")
            else False
        )
        if problem:
            self.lb_anim_stop.setText(i18n.t(problem))
            self.lb_anim_stop.setStyleSheet("color:#ff6b6b;")
            return False
        if by_sa and by_key:
            note = i18n.tf("Анимация останавливается командой /sa и нажатием «%s».", pretty)
        elif by_sa:
            note = i18n.t("Анимация останавливается командой /sa.")
        elif by_key:
            note = i18n.tf("Анимация останавливается нажатием «%s» (симуляция).", pretty)
        else:
            note = i18n.t(
                "Остановка выключена: анимация играет, пока её не сменит "
                "другая или пока её не остановит игра."
            )
        self.lb_anim_stop.setText(
            note
            + " "
            + i18n.t("Клавишу остановки получает и игра, поэтому подойдёт обычная игровая клавиша.")
        )
        self.lb_anim_stop.setStyleSheet("color:#8a8a96;")
        return True

    def _add_anim(self):
        """Новое правило с разумными значениями по умолчанию.

        A new rule with sensible defaults.
        """
        rule = anims.Rule(
            keywords="", name="", mode=anims.MODE_ALWAYS, duration_ms=anims.DEFAULT_MS
        )
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
        rows = sorted(
            {index.row() for index in self.tbl_anims.selectionModel().selectedRows()}, reverse=True
        )
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
        code = langs.code_of(
            self.cb_lang.currentData()
            if hasattr(self, "cb_lang") and self.cb_lang.currentData()
            else self.cfg.get("target_lang", "it")
        )
        cached = getattr(self, "_anim_glossary", (None, None))
        if cached[0] != code:
            try:
                cached = (code, Glossary(self._doc(code), code))
            except Exception:
                log.exception("Не удалось прочитать словарь для проверки анимаций")
                cached = (code, None)
            self._anim_glossary = cached
        glossary = cached[1]
        negation = (
            bool(self.chk_anim_negation.isChecked()) if hasattr(self, "chk_anim_negation") else True
        )
        if glossary is None:
            return anims.Context(negation=negation)
        return anims.Context(
            equivalent=lambda phrase: glossary.find_meaning(phrase) or "",
            text_keys=glossary.phrase_keys,
            negation=negation,
        )

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
        hits = [
            (position, self._anim_hit_label(rule), form)
            for position, _index, rule, form in anims.plan(rules, text, ctx)
        ]
        if hits:
            # видно не только правило, но и какая именно форма его задела
            # shows the rule and the exact form that fired it
            parts = ["/anim " + name + (f" ← «{form}»" if form else "") for _, name, form in hits]
            text_out = i18n.t("Сработают: ") + ", ".join(parts)
            # правило может сработать и при этом не дойти до игры: проверка
            # слов не равна работе модуля, о выключенных модулях говорим прямо
            # a rule may fire and still never reach the game: this check is about
            # the words, so the disabled modules are called out
            why = self._anim_blockers()
            if why:
                text_out += " " + i18n.t("Но в игру ничего не уйдёт: ") + ", ".join(why) + "."
            self.lb_anims_test.setText(text_out)
            self.lb_anims_test.setStyleSheet("color:#ffb45b;" if why else "color:#66d18b;")
        else:
            self.lb_anims_test.setText(
                i18n.t(
                    "Ни одно правило не сработает: в этом режиме ключевого слова в сообщении нет."
                )
            )
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
        return i18n.tf("выбор из %d: ", len(names)) + ", ".join(names)

    def _export_anims(self):
        """Правила в JSON — их можно перенести на другой компьютер."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            i18n.t("Экспорт правил анимаций"),
            str(DATA / "animations.json"),
            i18n.t("Правила анимаций (*.json);;Все файлы (*)"),
        )
        if not path:
            return
        payload = {
            "format": "rpchatoverlay-animations",
            "version": 1,
            "rules": anims.rules_to_cfg(self._collect_anims()),
            "stop_key": self.ed_anim_stop.text().strip().lower(),
        }
        try:
            Path(path).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as e:
            QMessageBox.warning(
                self, i18n.t("Экспорт"), i18n.t("Не удалось записать файл:\n") + str(e)
            )
            return
        QMessageBox.information(
            self, i18n.t("Экспорт"), i18n.t("Правила сохранены в файл ") + str(path)
        )

    def _import_anims(self):
        """Правила из JSON, созданного кнопкой «Экспорт…»."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            i18n.t("Импорт правил анимаций"),
            str(DATA),
            i18n.t("Правила анимаций (*.json);;Все файлы (*)"),
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
            data = json.loads(text)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, i18n.t("Импорт"), i18n.t("Файл не подошёл:\n") + str(e))
            return
        raw = data.get("rules") if isinstance(data, dict) and "rules" in data else data
        if not isinstance(raw, list):
            QMessageBox.warning(
                self, i18n.t("Импорт"), i18n.t('В файле нужен список правил: {"rules": [ … ]}.')
            )
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
            QMessageBox.information(self, i18n.t("Импорт"), i18n.t("В файле не нашлось правил."))
        self._anims_changed()

    # ------------------------------------------------------------ Модули
