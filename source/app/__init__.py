"""Пакет приложения RP Chat Overlay — переводчик чата для GTA V и FiveM.

RP Chat Overlay application package: a chat translator for GTA V and FiveM.

Структура пакета / package layout:
    config.py       пути, журнал, конфигурация / paths, logging, configuration
    modules.py      реестр модулей и их включение / module registry and toggles
    engine.py       разбор сообщения и словарь / message parsing and glossary
    translator.py   цепочка сервисов перевода / translation service chain
    langs.py        реестр языков перевода / target language registry
    langpacks/      встроенные словари языков / built-in language packs
    slang.py        сленг и сокращения: замена и свои записи / slang expansion and own entries
    slang_data.py   сокращения по языкам, ~300 на язык / abbreviations per language
    translit.py     русская запись по звучанию / Russian reading of foreign words
    i18n.py         функции языка интерфейса / interface language functions
    i18n_en.py      английский каталог / English string catalog
    settings_anim_props.py диалог свойств анимации / animation properties dialog
    settings_widgets.py  общие Qt-виджеты настроек / reusable settings widgets
    usage_report.py локальный отчёт производительности (opt-in) / local performance report
    autoplan.py     счётчик автоперевода / auto-translation counter
    anims.py        анимации по ключевому слову / keyword-driven animations
    morph.py        словоформы ключевых слов / keyword word forms
    gamesend.py     ввод в окно игры (Windows API) / game window input
    hotkey.py       глобальная горячая клавиша / global hotkey
    overlay.py      оверлей-чат / overlay chat window
    settings_ui.py  окно настроек / settings window
    ui_lang.py      выбор языка при первом запуске / first-run language picker

Правило импорта / import rule: модули пакета импортируются только абсолютно
(`from app.config import log`), чтобы PyInstaller находил их при сборке exe.
Package modules use absolute imports only, so PyInstaller bundles them reliably.
"""

from __future__ import annotations

APP_NAME = "RP Chat Overlay"
APP_NAME_FULL = "RP Chat Overlay"
VERSION = "1.18.0"
VERSION_TUPLE = (1, 18, 0, 0)

# Имя мьютекса одиночного запуска / single-instance mutex name.
MUTEX_NAME = "Local\\RPChatOverlayMutex"

# Заголовок главного окна и трея / main window and tray title.
WINDOW_TITLE = f"Настройки — {APP_NAME}"

__all__ = [
    "APP_NAME",
    "APP_NAME_FULL",
    "VERSION",
    "VERSION_TUPLE",
    "MUTEX_NAME",
    "WINDOW_TITLE",
]
