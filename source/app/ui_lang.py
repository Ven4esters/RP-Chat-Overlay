"""Выбор языка интерфейса при первом запуске / first-run interface language picker.

Окно показывает оба языка сразу, без перевода: на первом запуске ещё
неизвестно, какой из них нужен игроку. Выбор записывается в конфиг
(ui_lang, ui_lang_chosen) и потом меняется в настройках.
The dialog shows both languages at once, without translating: on the first run
the program cannot know which one the player needs. The choice is stored in the
config and can be changed later in the settings.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


def ask_ui_language(parent=None, style: str = "") -> str:
    """Показать окно выбора языка. Возвращает "ru" или "en".

    Shows the language dialog and returns "ru" or "en".
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle("Язык интерфейса · Interface language")
    dlg.setMinimumWidth(440)
    if style:
        dlg.setStyleSheet(style)

    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(22, 20, 22, 18)
    lay.setSpacing(10)

    head = QLabel("Язык интерфейса · Interface language")
    head.setStyleSheet("font-size:15px;font-weight:600;")
    lay.addWidget(head)

    ru = QLabel(
        "Выберите язык кнопок, подсказок и меню.\n"
        "Поменять его можно в любой момент: Настройки → Основные."
    )
    ru.setWordWrap(True)
    lay.addWidget(ru)

    en = QLabel(
        "Choose the language of buttons, hints and menus.\n"
        "You can change it any time: Settings → General."
    )
    en.setWordWrap(True)
    lay.addWidget(en)

    row = QHBoxLayout()
    row.setSpacing(10)
    b_ru = QPushButton("Русский")
    b_ru.setMinimumHeight(38)
    b_ru.clicked.connect(lambda: dlg.done(0))
    b_en = QPushButton("English")
    b_en.setMinimumHeight(38)
    b_en.clicked.connect(lambda: dlg.done(1))
    row.addWidget(b_ru)
    row.addWidget(b_en)
    lay.addSpacing(6)
    lay.addLayout(row)

    b_ru.setDefault(True)
    b_ru.setFocus()
    dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    choice = dlg.exec()
    return "en" if choice == 1 else "ru"
