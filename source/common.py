"""common.py — пути, логирование, конфиг, JSON."""
import json
import logging
import os
import sys
from pathlib import Path

def _root():
    """Папка программы: рядом с .exe (сборка) или с исходниками.

    Если папка недоступна для записи (например, Program Files), данные уходят
    в %LOCALAPPDATA%\\RPChatOverlay.
    """
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent
    try:
        (base / "data").mkdir(parents=True, exist_ok=True)
        probe = base / "data" / ".writable"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return base
    except OSError:
        alt = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
                   or Path.home()) / "RPChatOverlay"
        try:
            alt.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return alt


ROOT = _root()
DATA = ROOT / "data"
LOGS = ROOT / "logs"
CONFIG_PATH = DATA / "config.json"
GLOSSARY_DIR = DATA / "glossaries"       # по файлу на язык: it.json, es.json, ...
GLOSSARY_PATH = DATA / "glossary.json"   # старый единый словарь (переносится сам)
CACHE_PATH = DATA / "cache.json"
LOG_PATH = LOGS / "app.log"

log = logging.getLogger("app")

DEFAULT_CONFIG = {
    "target_lang": "it",          # язык перевода (см. langs.py)
    "send_mode": "reading",       # "reading" = русская запись, "native" = текст на языке
    "show_settings_on_start": True,  # показывать окно настроек при запуске
    "setup_done": False,          # первый запуск уже пройден
    "ui_scale": 1.0,              # масштаб интерфейса настроек
    "marker_open": "+",
    "marker_close": "+",
    "max_chars": 256,
    "debounce_ms": 450,
    "auto_mode": False,
    "auto_every": 4,
    "filler_always": True,        # слова-паразиты переводить в КАЖДОМ сообщении
    "always_on_top": True,
    "game_send": True,
    "game_press_enter": False,
    "game_chat_key": "t",
    "game_open_chat_first": True, # сначала открыть чат игры (T), потом оверлей
    "game_open_delay_ms": 300,
    "game_paste_delay_ms": 150,
    "game_window_class": "grcWindow",
    "game_extra_exes": [],
}


def setup_logging():
    DATA.mkdir(exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    GLOSSARY_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    sys.excepthook = lambda t, v, tb: log.critical(
        "Необработанная ошибка", exc_info=(t, v, tb)
    )
    log.info("=== Запуск, Python %s ===", sys.version.split()[0])


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception:
        log.exception("Не удалось прочитать %s", path)
        return default


def write_json(path, data):
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    saved = read_json(CONFIG_PATH, {})
    if isinstance(saved, dict):
        cfg.update(saved)
    for k in ("marker_open", "marker_close"):
        if not isinstance(cfg.get(k), str) or not cfg[k]:
            cfg[k] = DEFAULT_CONFIG[k]
    save_config(cfg)
    return cfg


def save_config(cfg):
    try:
        write_json(CONFIG_PATH, cfg)
    except OSError:
        log.exception("Не удалось сохранить config.json")