"""Реестр модулей программы / application module registry.

Зачем это нужно / why it exists
-------------------------------
Программа собрана из независимых частей: перевод по сети, словарь, сокращения,
автоперевод, отправка в игру и глобальная клавиша. Каждую часть можно выключить
в настройках, и приложение продолжит работать — просто без этой возможности.
The program is built from independent parts: online translation, glossary,
abbreviations, auto-translation, sending into the game and the global hotkey.
Each part can be switched off in the settings, and the program keeps working —
just without that feature.

Как пользоваться / how to use
----------------------------
    from app.modules import is_enabled

    if is_enabled(cfg, "game_send"):
        ...            # работаем с окном игры / talk to the game window

Выключенный модуль, от которого зависит другой, выключает и зависимый:
если перевод по сети отключён, автоперевод тоже считается выключенным.
A disabled module also disables its dependants: with online translation off,
auto-translation is reported as disabled too.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Mapping


@dataclass(frozen=True, slots=True)
class Module:
    """Описание одного модуля / description of one module.

    key          техническое имя / technical key used in code
    title_ru     название для интерфейса (русский) / Russian UI title
    title_en     название для интерфейса (английский) / English UI title
    desc_ru      пояснение (русский) / Russian description
    desc_en      пояснение (английский) / English description
    config_key   ключ в config.json, где хранится флаг / config flag name
    default      состояние при первом запуске / state on the first run
    requires     модули, без которых этот не работает / hard dependencies
    settings_page  раздел настроек, где включается, или None для своего флажка
    """

    key: str
    title_ru: str
    title_en: str
    desc_ru: str
    desc_en: str
    config_key: str
    default: bool = True
    requires: tuple[str, ...] = ()
    settings_page: int | None = None


# Порядок в таблице = порядок в окне настроек.
# Table order is the order shown in the settings window.
MODULES: Final[tuple[Module, ...]] = (
    Module(
        key="translator",
        title_ru="Перевод по сети",
        title_en="Online translation",
        desc_ru="Цепочка сервисов Google, MyMemory, Lingva и LibreTranslate. "
                "Без него работают только встроенные словари.",
        desc_en="The chain of Google, MyMemory, Lingva and LibreTranslate. "
                "Without it only the built-in glossaries work.",
        config_key="translator_enabled",
    ),
    Module(
        key="glossary",
        title_ru="Словарь",
        title_en="Glossary",
        desc_ru="Готовые фразы с русской записью и значениями. Без него фразы "
                "переводятся сервисами, без подсказки «как читается».",
        desc_en="Ready-made phrases with a Russian reading and meanings. Without it "
                "phrases are translated by the services, with no reading hint.",
        config_key="glossary_enabled",
    ),
    Module(
        key="slang",
        title_ru="Сленг и сокращения",
        title_en="Slang and abbreviations",
        desc_ru="brb, afk, gg, спс, мб раскрываются в полные фразы до перевода.",
        desc_en="brb, afk, gg and their Russian counterparts are expanded into "
                "full phrases before translation.",
        config_key="slang",
        settings_page=0,
    ),
    Module(
        key="autotranslate",
        title_ru="Автоперевод",
        title_en="Auto-translation",
        desc_ru="Каждое N-е сообщение переводится само. Требует перевода по сети.",
        desc_en="Every N-th message is translated automatically. Requires online "
                "translation.",
        config_key="auto_mode",
        requires=("translator",),
        settings_page=1,
    ),
    Module(
        key="game_send",
        title_ru="Отправка в игру",
        title_en="Sending into the game",
        desc_ru="Оверлей сам открывает чат игры, вставляет текст и нажимает Enter. "
                "Если выключено — текст только копируется в буфер обмена.",
        desc_en="The overlay opens the game chat, pastes the text and presses Enter. "
                "When off, the text is only copied to the clipboard.",
        config_key="game_send",
        settings_page=2,
    ),
    Module(
        key="dlx",
        title_ru="DeepL рядом (DLX)",
        title_en="DeepL alongside (DLX)",
        desc_ru="Локальный сервис DeepL как первый переводчик. Требует согласия и "
                "около 15 МБ на диске; без него работает обычная цепочка сервисов.",
        desc_en="A local DeepL service used as the first translator. It needs consent "
                "and about 15 MB on disk; without it the regular service chain runs.",
        config_key="dlx_enabled",
        default=False,
        requires=("translator",),
        settings_page=7,
    ),
    Module(
        key="hotkey",
        title_ru="Глобальная клавиша",
        title_en="Global hotkey",
        desc_ru="Вызов оверлея из игры одной клавишей. Без него оверлей "
                "открывается двойным щелчком по значку в трее.",
        desc_en="Opens the overlay from inside the game with one key. Without it the "
                "overlay opens by double-clicking the tray icon.",
        config_key="hotkey_enabled",
    ),
)

BY_KEY: Final[dict[str, Module]] = {m.key: m for m in MODULES}


def get(key: str) -> Module | None:
    """Описание модуля по ключу или None / module by key, or None."""
    return BY_KEY.get(key)


def config_keys() -> dict[str, bool]:
    """Ключи конфигурации и значения по умолчанию / config keys and defaults."""
    return {m.config_key: m.default for m in MODULES}


def _raw_flag(cfg: Mapping[str, Any], module: Module) -> bool:
    """Значение флага из конфигурации без учёта зависимостей / raw flag value."""
    return bool(cfg.get(module.config_key, module.default))


def is_enabled(cfg: Mapping[str, Any], key: str, _seen: frozenset[str] = frozenset()) -> bool:
    """Включён ли модуль (с учётом зависимостей) / is the module active.

    Неизвестный ключ считается выключенным: опечатка в имени не должна
    включать случайную ветку кода.
    An unknown key counts as disabled: a typo must not enable a code path.
    """
    module = BY_KEY.get(key)
    if module is None:
        return False
    if not _raw_flag(cfg, module):
        return False
    for dep in module.requires:
        if dep in _seen:            # защита от циклических зависимостей
            continue            # cycle guard
        if not is_enabled(cfg, dep, _seen | {key}):
            return False
    return True


def disabled(cfg: Mapping[str, Any]) -> list[str]:
    """Ключи выключенных модулей — для журнала и подсказок / disabled module keys."""
    return [m.key for m in MODULES if not is_enabled(cfg, m.key)]


def apply_defaults(cfg: dict[str, Any]) -> dict[str, Any]:
    """Дописывает отсутствующие флаги модулей в конфигурацию / fill missing flags."""
    for module in MODULES:
        cfg.setdefault(module.config_key, module.default)
    return cfg


def summary(cfg: Mapping[str, Any]) -> str:
    """Короткая строка для журнала: какие модули выключены / log summary line."""
    off = disabled(cfg)
    return "модули: все включены" if not off else "выключены: " + ", ".join(off)
