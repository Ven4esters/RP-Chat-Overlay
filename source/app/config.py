"""Пути, журнал и конфигурация программы / paths, logging and configuration.

Здесь собрано всё, что зависит от места запуска: папка данных, файлы журнала,
чтение и запись JSON, набор настроек по умолчанию.
This module owns everything that depends on where the program runs: the data
folder, log files, JSON reading and writing, and the default settings.

Правила / rules:
  * пользовательские данные никогда не перезаписываются молча: сначала
    создаётся временный файл, затем он подменяет старый (атомарная запись);
    user data is never overwritten silently: a temporary file is written first
    and then swapped in (atomic write);
  * если папка программы недоступна для записи, данные уходят в %LOCALAPPDATA%.
    if the program folder is read-only, data goes to %LOCALAPPDATA%.
"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from pathlib import Path
from typing import Any, Final, Mapping

from app import APP_NAME, modules


# --------------------------------------------------------------------------- пути
def _local_fallback_root(appdata: Path) -> Path:
    """Choose the legacy data folder when present, or the new folder on a fresh install."""
    legacy = appdata / "RPChatOverlay"
    return legacy if legacy.is_dir() else appdata / "FiveMChatOverlay"


def _root() -> Path:
    """Папка программы: рядом с .exe (сборка) или с исходниками.

    Program folder: next to the .exe in a build, or the source folder otherwise.
    Если писать в неё нельзя (например, Program Files), данные переезжают
    в %LOCALAPPDATA%\\FiveMChatOverlay — программа работает и оттуда. Папка
    %LOCALAPPDATA%\\RPChatOverlay остаётся совместимой с предыдущим названием.
    If the folder is not writable (Program Files, for example), data moves to
    %LOCALAPPDATA%\\FiveMChatOverlay. Existing %LOCALAPPDATA%\\RPChatOverlay
    data remains supported for users upgrading from the previous app name.
    """
    base = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent.parent
    )
    try:
        (base / "data").mkdir(parents=True, exist_ok=True)
        probe = base / "data" / ".writable"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return base
    except OSError:
        appdata = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home())
        # Keep reading and writing the old location if it already contains a
        # user's settings/logs. Fresh installs use the new branded directory.
        fallback = _local_fallback_root(appdata)
        try:
            fallback.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass  # работаем без сохранения / continue without persistence
        return fallback


ROOT: Path = _root()
DATA: Path = ROOT / "data"
LOGS: Path = ROOT / "logs"


def resource_path(name: str) -> Path:
    """Файл из комплекта программы: иконка, словари, картинки.

    A file shipped with the program: the icon, the glossaries, the images.
    В сборке PyInstaller распаковывает их в ``sys._MEIPASS``, в исходниках они
    лежат рядом с ``main.py``; папка данных (%LOCALAPPDATA%) проверяется тоже —
    на случай, если программу распаковали только частично.
    PyInstaller unpacks them into ``sys._MEIPASS``; in the sources they sit next
    to ``main.py``. The data folder (%LOCALAPPDATA%) is checked too, in case the
    program was unpacked only partly.
    """
    candidates = []
    bundle = getattr(sys, "_MEIPASS", "")
    if bundle:
        candidates.append(Path(bundle) / name)
    candidates.append(ROOT / name)
    candidates.append(Path(__file__).resolve().parent.parent / name)
    for path in candidates:
        if path.is_file():
            return path
    return candidates[-1]


CONFIG_PATH: Path = DATA / "config.json"
CACHE_PATH: Path = DATA / "cache.json"
SLANG_PATH: Path = DATA / "slang.json"  # свои сокращения игрока / user abbreviations
GLOSSARY_DIR: Path = DATA / "glossaries"  # по файлу на язык / one file per language
GLOSSARY_PATH: Path = DATA / "glossary.json"  # старый единый словарь / legacy single glossary
LOG_PATH: Path = LOGS / "app.log"

log: logging.Logger = logging.getLogger("app")

# ----------------------------------------------------------------- настройки
# Ключ -> значение по умолчанию. Каждый ключ прокомментирован по-русски и
# по-английски; новых ключей достаточно добавить только здесь.
# Key -> default value, commented in both languages; new keys belong here only.
DEFAULT_CONFIG: dict[str, Any] = {
    # --- язык и направление / language and direction ---
    "target_lang": "it",  # язык перевода / target language code
    # "reading" = русская запись, "native" = текст на языке
    # "reading" sends the Russian reading, "native" the foreign text
    "send_mode": "reading",
    # Режим перевода — один ключ на три режима. Старый "direction" читается
    # как раньше: "in" — это режим 3, "out" — частичный (режим 2).
    # One key for three modes. The old "direction" key is still honoured:
    # "in" means mode 3, "out" means partial (mode 2).
    "mode": "partial",  # "full" | "partial" | "to_ru"
    "direction": "out",  # устаревший дубль режима / legacy copy of mode
    # "out" = русский → язык, "in" = любой язык → русский
    # --- интерфейс / interface ---
    "ui_lang": "ru",  # язык интерфейса: "ru" | "en" / UI language
    "ui_lang_chosen": False,  # игрок уже выбирал язык / language already picked
    "show_settings_on_start": True,  # показывать настройки при запуске / open settings on start
    "setup_done": False,  # первый запуск пройден / first run completed
    "cache_cleanup_interval": "off",  # off | daily | weekly | monthly
    "cache_last_cleaned": "",  # время последней очистки кэша, UTC ISO / last cache cleanup
    "usage_report_enabled": False,  # локальный отчёт производительности / opt-in diagnostics
    "ui_scale": 1.0,  # масштаб интерфейса / interface scale
    "always_on_top": True,  # оверлей поверх игры / overlay above the game
    # --- вспомогательные модули / optional modules ---
    "translator_enabled": True,  # перевод по сети / online translation
    "glossary_enabled": True,  # словарь / glossary
    "hotkey_enabled": True,  # глобальная клавиша / global hotkey
    "dlx_enabled": False,  # DeepL рядом (DLX) / local DeepL service
    "dlx_asked": False,  # предупреждение уже показано / consent shown
    "dlx_port": 0,  # 0 — выбрать свободный / 0 means auto
    "dlx_autostart": True,  # поднимать вместе с программой / start with app
    "dlx_auto_update": True,  # проверять обновления / check for updates
    "dlx_proxy": "",  # HTTP-прокси для DeepL / HTTP proxy for DeepL
    "dlx_use_system_proxy": True,  # брать прокси из настроек Windows / use the Windows proxy
    "dlx_url": "",  # свой адрес сервиса вместо dlx.exe / own service URL
    "dlx_url_token": "",  # токен своего сервиса / token of that service
    "dlx_pro_token": "",  # токен DeepL Pro (OAuth) / DeepL Pro OAuth token
    "slang": True,  # сленг и сокращения / slang and abbreviations
    # Язык таблицы сокращений. Пусто — следовать за языком перевода: на немецком
    # сервере первой работает немецкая таблица, а итальянский (своей таблицы у
    # него нет) берёт английскую.
    # The abbreviation table's language. Empty means "follow the translation
    # language": a German server uses the German table first, and Italian, which
    # has no table of its own, falls back to English.
    "slang_lang": "",
    # --- текст и маркеры / text and markers ---
    "marker_open": "+",  # маркер «переведи это» / "translate this" marker
    "marker_close": "+",
    "max_chars": 256,  # предел длины сообщения / message length limit
    "debounce_ms": 450,  # пауза после ввода / typing pause before translating
    "filler_always": True,  # слова-паразиты в каждом сообщении
    # fillers in every message
    # --- автоперевод / auto-translation ---
    "auto_mode": False,  # включён ли автоперевод / auto-translation on
    "auto_every": 4,  # каждое N-е сообщение / every N-th message
    "auto_position": "last",  # "last" | "first" | "random" | номер 1..N
    "auto_fragments": 1,  # сколько фрагментов переводить / fragments per message
    "auto_min_words": 1,  # длина фрагмента: от / fragment length, min
    "auto_max_words": 3,  # ... и до / fragment length, max
    "auto_prefer_glossary": True,  # сначала фразы из словаря / prefer glossary phrases
    # --- отправка в игру / sending into the game ---
    "game_send": True,  # отправлять в игру / send into the game
    "game_press_enter": False,  # нажимать Enter после вставки / press Enter after pasting
    "game_submit": True,  # отправлять сообщение / submit the message
    "game_chat_key": "t",  # клавиша чата в игре / in-game chat key
    "game_open_chat_first": True,  # сначала открыть чат игры / open the game chat first
    "game_open_delay_ms": 300,  # пауза после открытия чата / pause after opening
    "game_paste_delay_ms": 150,  # пауза перед вставкой / pause before pasting
    "game_focus_delay_ms": 150,  # пауза перед возвратом фокуса / pause before refocusing
    "game_input_mode": "paste",  # "paste" = Ctrl+V, "type" = посимвольный ввод / typed input
    "game_window_class": "grcWindow",  # класс окна игры / game window class
    "game_extra_exes": [],  # дополнительные процессы игры / extra game processes
    # --- анимации / animations ---
    "slang_order": [],  # свой порядок сокращений / the user's order
    "anims_enabled": False,  # модуль «Анимации» / the animation module
    "anim_rules": [],  # правила: слово -> /anim / rules: keyword -> /anim
    "anim_stop_key": "f",  # клавиша остановки / the stop key
    "anim_stop_by_sa": True,  # останавливать командой /sa / stop with /sa
    "anim_stop_by_key": False,
    "anim_skip_negation": True,  # останавливать нажатием клавиши / stop with the key
    "anim_extra_ms": 50,  # добавка к длительности анимации / tail after it
    # Режим «В машине»: пока включён, анимации не играют и /sa не уходит.
    # Флаг сохраняется, чтобы после перезапуска игры на парковке не сработало
    # то, что игрок выключил нарочно.
    # The "In a vehicle" mode: while on, no animation plays and no /sa is sent.
    # The flag is saved so that a restart in the middle of a ride does not bring
    # back what the player switched off on purpose.
    "anim_in_vehicle": False,
    # подсказки ключевых слов в оверлее: список слов, подходящих под набранное,
    # и пролистывание по Tab / keyword hints in the overlay: the words that fit
    # what is typed, walkable with Tab
    "anim_hints": True,
    "anim_hints_max": 8,
    # высота строки таблицы правил: длинные фразы в пятнадцать пикселей не
    # читаются / the rules table row height: long phrases do not read at fifteen
    "anim_row_height": 34,
    # --- горячая клавиша и окно / hotkey and window ---
    "hotkey": "F6",
    "overlay_pos": [0.01, 0.28],  # положение окна в долях окна игры / position as a fraction
    "overlay_width": 560,  # ширина оверлея, px / overlay width in pixels
}


# --------------------------------------------------------------------- журнал
def setup_logging() -> None:
    """Создаёт папки данных и включает запись журнала в logs/app.log.

    Creates the data folders and starts logging into logs/app.log.
    Необработанные исключения тоже попадают в журнал — по нему видно, что
    именно случилось у игрока.
    Unhandled exceptions are logged as well, so a player's report can be traced.
    """
    DATA.mkdir(exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    GLOSSARY_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        handlers=[
            RotatingFileHandler(
                LOG_PATH,
                maxBytes=2 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
        ],
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    sys.excepthook = lambda exc_type, exc, tb: log.critical(
        "Необработанная ошибка", exc_info=(exc_type, exc, tb)
    )
    # перехватчики ошибок: исключения, потоки, Qt и аварийные падения
    # error hooks: exceptions, threads, Qt and hard crashes
    try:
        from app import errorlog

        errorlog.install()
        log.info("Журналы приложения и ошибок включены")
    except Exception:
        log.exception("Не удалось включить журнал ошибок")
    log.info("=== Запуск %s, Python %s ===", APP_NAME, sys.version.split()[0])


# ----------------------------------------------------------------------- JSON
def read_json(path: str | Path, default: Any = None) -> Any:
    """Читает JSON-файл; при любой ошибке возвращает default и пишет в журнал.

    Reads a JSON file; on any error returns `default` and logs the problem.
    """
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default
    except (OSError, ValueError):
        log.exception("Не удалось прочитать %s", path)
        return default


def write_json(path: str | Path, data: Any, compact: bool = False) -> None:
    """Атомарно записывает JSON: сначала .tmp, потом подмена файла.

    Writes JSON atomically: a .tmp file first, then an atomic replace.

    compact=True — без отступов: файл кэша переводов переписывается на каждой
    новой фразе, и отступы в две тысячи записей стоили лишних сотен килобайт
    записи на диск во время игры.
    compact=True drops indentation: the translation cache file is rewritten on
    every new phrase, and indenting two thousand entries meant hundreds of extra
    kilobytes written to disk while the game runs.
    """
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        if compact:
            json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# -------------------------------------------------------------------- конфиг
def load_config() -> dict[str, Any]:
    """Читает config.json, дополняет его значениями по умолчанию и сохраняет.

    Reads config.json, fills in the defaults and writes the file back, so a new
    build always sees the keys it needs.
    """
    cfg: dict[str, Any] = dict(DEFAULT_CONFIG)
    saved = read_json(CONFIG_PATH, {})
    if isinstance(saved, dict):
        cfg.update(saved)
    for key in ("marker_open", "marker_close"):
        if not isinstance(cfg.get(key), str) or not cfg[key]:
            cfg[key] = DEFAULT_CONFIG[key]
    modules.apply_defaults(cfg)
    cfg["mode"] = _mode_of(cfg)
    cfg["direction"] = "in" if cfg["mode"] == "to_ru" else "out"
    save_config(cfg)
    return cfg


MODES: Final[dict[str, str]] = {"full": "full", "partial": "partial", "to_ru": "to_ru"}


def _mode_of(cfg: Mapping[str, Any]) -> str:
    """Режим перевода из конфигурации, с оглядкой на старый ключ.

    The translation mode from the configuration, honouring the legacy key.

    Старый ``direction`` читается только если файл пришёл без ``mode``:
    иначе два ключа начнут спорить, и меню трея разойдётся с настройками.
    The legacy ``direction`` is only read when the file has no ``mode``;
    otherwise the two keys argue and the tray menu disagrees with the settings.
    """
    mode = cfg.get("mode")
    if mode in MODES:
        return mode
    return "to_ru" if str(cfg.get("direction") or "").lower() in ("in", "reverse") else "partial"


def save_config(cfg: dict[str, Any]) -> bool:
    """Сохраняет конфигурацию, не роняя программу при ошибке записи.

    Saves the configuration; a write error is logged instead of raised.
    """
    try:
        write_json(CONFIG_PATH, cfg)
        return True
    except OSError:
        log.exception("Не удалось сохранить config.json")
        return False
