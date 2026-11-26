"""Animation rule properties dialog used by the Settings window."""

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app import i18n
from app import animations as anims


def _hint(text):
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


class AnimProps(QDialog):
    """Варианты и свойства анимации: имена, названия и описания.

    Animation properties: the variants, their titles and descriptions.

    Зачем / why
    -----------
    Один ключ часто подходит к нескольким анимациям: «Опёрся руками» — это и
    ``anim_counterleanbar``, и ``anim_leanrail``. Когда вариантов два и больше,
    в игре открывается оверлей выбора, и игроку нужно показать не имя команды,
    а человеческое название с описанием.
    One keyword often fits several animations: «Опёрся руками» is both
    ``anim_counterleanbar`` and ``anim_leanrail``. With two or more variants the
    game shows a chooser, and the player must see a human title with a
    description rather than a command name.

    Здесь же задаётся и обычное правило без вариантов: одна строка — это просто
    название анимации, как в таблице. Так диалог остаётся единственным местом,
    где меняются свойства, и неважно, один вариант или несколько.
    The dialog also edits an ordinary single-animation rule: one row is just the
    animation name, as in the table. That keeps the dialog the one place where
    properties are edited, whether there is one variant or several.
    """

    def __init__(self, rule, parent=None, style_factory=None):
        super().__init__(parent)
        self.rule = rule
        self.setWindowTitle(i18n.t("Варианты и свойства"))
        self.setStyleSheet(style_factory(1.0) if style_factory else "")
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 14)
        lay.setSpacing(10)

        head = QLabel(i18n.tf("Ключевые слова: %s", rule.keywords.strip() or i18n.t("не заданы")))
        head.setStyleSheet("font-size:14px;font-weight:600;")
        head.setWordWrap(True)
        lay.addWidget(head)

        lay.addWidget(
            _hint(
                i18n.t(
                    "Заполните варианты: имя для /anim, название и описание. Если "
                    "вариантов два и больше, в игре откроется оверлей выбора — игрок "
                    "увидит название и описание, а не имя команды. Один вариант — "
                    "обычное правило, оно играет сразу."
                )
            )
        )

        lay.addWidget(
            _hint(
                i18n.t(
                    "Группа необязательна: впишите одинаковое название у нескольких "
                    "вариантов — в оверлее они встанут подряд под этим названием, а "
                    "разные группы будут разделены чертой."
                )
            )
        )

        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(
            [i18n.t("/anim"), i18n.t("Название"), i18n.t("Описание"), i18n.t("Группа")]
        )
        head_view = self.tbl.horizontalHeader()
        head_view.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        head_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        head_view.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        head_view.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        head_view.setStretchLastSection(False)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setMinimumHeight(190)
        lay.addWidget(self.tbl, 1)

        btns = QHBoxLayout()
        self.bt_add = QPushButton(i18n.t("Добавить вариант"))
        self.bt_add.clicked.connect(self._add)
        self.bt_del = QPushButton(i18n.t("Удалить вариант"))
        self.bt_del.setObjectName("danger")
        self.bt_del.clicked.connect(self._del)
        self.bt_up = QPushButton(i18n.t("Выше"))
        self.bt_up.clicked.connect(lambda: self._move(-1))
        self.bt_down = QPushButton(i18n.t("Ниже"))
        self.bt_down.clicked.connect(lambda: self._move(1))
        # Группа ставится сразу нескольким строкам: вписывать одно и то же
        # название в каждую ячейку вручную — лишняя работа.
        # A group is given to several rows at once: typing the same title into
        # every cell by hand is busywork.
        self.bt_group = QPushButton(i18n.t("Группа…"))
        self.bt_group.setToolTip(
            i18n.t(
                "Дать выбранным вариантам общее название группы — в оверлее они "
                "встанут подряд под ним и будут отделены чертой от других групп."
            )
        )
        self.bt_group.clicked.connect(self._assign_group)
        for button in (self.bt_add, self.bt_del, self.bt_up, self.bt_down, self.bt_group):
            btns.addWidget(button)
        btns.addStretch(1)
        lay.addLayout(btns)

        self.lb_problem = QLabel("")
        self.lb_problem.setProperty("no_i18n", True)
        self.lb_problem.setWordWrap(True)
        self.lb_problem.setStyleSheet("color:#ffb45b;")
        lay.addWidget(self.lb_problem)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.bt_cancel = QPushButton(i18n.t("Отмена"))
        self.bt_cancel.setAutoDefault(False)
        self.bt_cancel.clicked.connect(self.reject)
        self.bt_ok = QPushButton(i18n.t("Готово"))
        self.bt_ok.setObjectName("primary")
        self.bt_ok.setDefault(True)
        self.bt_ok.clicked.connect(self._accept)
        bottom.addWidget(self.bt_cancel)
        bottom.addWidget(self.bt_ok)
        lay.addLayout(bottom)

        self._fill()
        self.tbl.itemSelectionChanged.connect(self._sync_buttons)
        # правка любой ячейки сразу перепроверяет варианты: кнопка «Готово»
        # гаснет и загорается по мере ввода, без нажатий «проверить»
        # editing any cell revalidates at once: the Done button dims and lights up
        # as the text is typed, with no separate "check" press
        self.tbl.itemChanged.connect(lambda *_: self._validate())
        self.tbl.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )

    # --- таблица ---
    def _fill(self):
        """Заполнить таблицу вариантами правила / the rule variants in the table."""
        variants = self.rule.variant_list()
        self.tbl.blockSignals(True)
        self.tbl.setRowCount(0)
        for choice in variants:
            self._add_row(choice)
        self.tbl.blockSignals(False)
        self._sync_buttons()
        self._validate()

    def _add_row(self, choice):
        row = self.tbl.rowCount()
        self.tbl.insertRow(row)
        for column, text in enumerate(
            (choice.name, choice.title, choice.description, choice.group)
        ):
            item = QTableWidgetItem(text)
            item.setToolTip(text)
            self.tbl.setItem(row, column, item)
        return row

    def _add(self):
        row = self._add_row(anims.Choice())
        self.tbl.selectRow(row)
        self.tbl.setCurrentCell(row, 0)
        self.tbl.editItem(self.tbl.item(row, 0))
        self._validate()

    def _del(self):
        rows = sorted({index.row() for index in self.tbl.selectedIndexes()}, reverse=True)
        if not rows:
            self._problem_hint(i18n.t("Сначала выберите вариант."))
            return
        for row in rows:
            self.tbl.removeRow(row)
        self._sync_buttons()
        self._validate()

    def _move(self, delta):
        rows = self.tbl.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        target = row + delta
        if not 0 <= target < self.tbl.rowCount():
            return
        cells = []
        for column in range(self.tbl.columnCount()):
            item = self.tbl.takeItem(row, column)
            cells.append(item if item is not None else QTableWidgetItem(""))
        self.tbl.removeRow(row)
        self.tbl.insertRow(target)
        for column, item in enumerate(cells):
            self.tbl.setItem(target, column, item)
        self.tbl.selectRow(target)

    def _sync_buttons(self):
        has = bool(self.tbl.selectionModel().selectedRows())
        for button in (self.bt_del, self.bt_up, self.bt_down):
            button.setEnabled(has)
        group = getattr(self, "bt_group", None)
        if group is not None:
            # группу можно дать любой строке — даже одной
            # a group can be given to any row, even a single one
            group.setEnabled(self.tbl.rowCount() > 0)

    def _assign_group(self):
        """Вписать название группы в выбранные строки (или во все).

        Write the group title into the selected rows, or into all of them.
        """
        rows = sorted({index.row() for index in self.tbl.selectedIndexes()})
        if not rows:
            rows = list(range(self.tbl.rowCount()))
        if not rows:
            return
        current = ""
        item = self.tbl.item(rows[0], 3)
        if item is not None:
            current = item.text().strip()
        title, ok = QInputDialog.getText(
            self,
            i18n.t("Группа вариантов"),
            i18n.tf("Название группы для строк: %d. Пустое поле — убрать группу.", len(rows)),
            text=current,
        )
        if not ok:
            return
        title = (title or "").strip()[: anims.MAX_GROUP]
        self.tbl.blockSignals(True)
        for row in rows:
            cell = self.tbl.item(row, 3)
            if cell is None:
                cell = QTableWidgetItem("")
                self.tbl.setItem(row, 3, cell)
            cell.setText(title)
            cell.setToolTip(title)
        self.tbl.blockSignals(False)
        self._validate()

    def _problem_hint(self, text):
        self.lb_problem.setText(text)

    def _validate(self):
        """Проверить варианты на месте и сказать, что не так.

        Check the variants right here and say what is wrong.
        """
        problems = []
        seen = set()
        for row in range(self.tbl.rowCount()):
            choice = self._choice_at(row)
            problem = choice.problem()
            if problem:
                problems.append(i18n.tf("Строка %d: ", row + 1) + i18n.t(problem))
                continue
            if choice.name in seen:
                problems.append(
                    i18n.tf("Строка %d: ", row + 1) + i18n.t("такая анимация уже есть в списке")
                )
            seen.add(choice.name)
        if self.tbl.rowCount() > anims.MAX_CHOICES:
            problems.append(i18n.t(anims.VAL_TOO_MANY_CHOICES))
        self.lb_problem.setText(" ".join(problems))
        self.bt_ok.setEnabled(not problems and self.tbl.rowCount() > 0)
        return not problems

    def _choice_at(self, row) -> "anims.Choice":
        def text(column):
            item = self.tbl.item(row, column)
            return item.text().strip() if item is not None else ""

        return anims.Choice(
            name=text(0).lstrip("/"), title=text(1), description=text(2), group=text(3)
        )

    def choices(self) -> list["anims.Choice"]:
        """Итоговые варианты в порядке таблицы / the variants in table order."""
        return [self._choice_at(row) for row in range(self.tbl.rowCount())]

    def _accept(self):
        if not self._validate():
            return
        self.accept()


def ask_anim_props(rule, parent=None, style_factory=None):
    """ПКМ по правилу: свойства анимации; меняет ``rule`` на месте.

    Right-click on a rule: the animation properties; ``rule`` is changed in place.
    Возвращает True, если игрок нажал «Готово».
    Returns True when the player pressed Done.
    """
    dialog = AnimProps(rule, parent, style_factory=style_factory)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False
    variants = dialog.choices()
    # один вариант — обычное правило: имя переезжает в name, вариантов нет,
    # чтобы конфиг остался прежним и старые версии его понимали
    # one variant is an ordinary rule: the name goes into name and the variants
    # are dropped, so the config stays the old shape and older versions read it
    if len(variants) == 1:
        rule.name = variants[0].name
        rule.choices = []
    else:
        rule.choices = variants
        rule.name = ""
    return True
