"""Точка входа / entry point.

Запуск приложения и служебные режимы командной строки.
Application startup and command line service modes.

Ключи / flags:
    --settings    сразу открыть окно настроек / open the settings window
    --selftest    прогон перевода и словарей без сети / offline self-check
    --langs       список языков и встроенных словарей / language and pack list
    --find-game   окна, похожие на игру / windows that look like the game
    --version     версия программы / program version

Примеры / examples:
    python main.py --selftest
    RPChatOverlay.exe --find-game
"""

from __future__ import annotations

import ctypes
import os
import sys

from app import APP_NAME, MUTEX_NAME, VERSION, i18n, modules
from app.config import log, load_config, setup_logging


# --------------------------------------------------------------------- служебное
def _silence_stdout() -> None:
    """В оконной сборке консоли нет: print() должен молча писать в никуда.

    A windowed build has no console; print() goes to a bit bucket instead of
    raising on a missing stdout.
    """
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def single_instance() -> tuple[int, bool]:
    """Мьютекс одиночного запуска / single-instance mutex.

    Возвращает (дескриптор, первый_ли_запуск).
    Returns (handle, is_first_instance).
    """
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    error_already_exists = 183
    return handle, ctypes.get_last_error() != error_already_exists


# ------------------------------------------------------------------ selftest
def _offline_translator():
    """Переводчик-заглушка: сеть в самопроверке не нужна / offline stub."""

    class Offline:
        def translate(self, text: str) -> str:
            raise RuntimeError("в selftest сеть не используется")

    return Offline()


def _reverse_translator():
    """Переводчик-заглушка для режима «ваш язык → русский» / stub for reverse mode."""

    class Reverse:
        _known = {
            "Ciao, fratello": "Привет, брат",
            "Senti, aspetta": "Слушай, подожди",
            "машет рукой": "машет рукой",
            "/to Ivan Ciao, fratello Ivan": "Привет, брат",
        }

        def translate(self, text: str) -> str:
            return self._known.get(text, f"[пер.: {text}]")

    return Reverse()


def selftest(cfg: dict) -> None:
    """Проверка перевода и словарей без обращения к сети / offline self-check."""
    from app import langs, slang
    from app.engine import Engine, has_fillers, is_counted_command, load_glossary

    samples = {
        "it": ["Слушай, брат, подожди", "Ну что ты, я же говорил", "Потихоньку идём",
               "/to Ivan слушай, брат"],
        "es": ["Слушай, брат, подожди", "Ну что ты, я же говорил", "/l слушай сюда"],
        "es-MX": ["Слушай, брат", "Ну что ты, я же говорил"],
        "pt-BR": ["Слушай, брат, подожди", "Ну что ты"],
        "zh-CN": ["Слушай, брат", "Ну что ты, я же говорил"],
        "ja": ["Слушай, брат", "А что поделаешь"],
    }
    for code, phrases in samples.items():
        glossary = load_glossary(code, cfg)
        engine = Engine(cfg, glossary, _offline_translator())
        print(f"\n=== {langs.label(code)} ({code}) — фраз в словаре: {len(glossary.phrases)}, "
              f"паразитов: {len(glossary.fillers)} ===")
        for phrase in phrases:
            result = engine.process(phrase)
            flag = " [команда]" if is_counted_command(phrase) else ""
            print(f"  {phrase!r}{flag}\n     -> {result.text!r} | чтение: {result.native!r} | "
                  f"переведено: {result.translated} | паразит: {has_fillers(phrase, cfg, glossary)}")

    engine = Engine(cfg, load_glossary("it", cfg), _reverse_translator())
    print("\nРежим переводчика (язык сервера → русский):")
    for phrase in ("Ciao, fratello", "*машет рукой* Ciao, fratello",
                   "/me *машет рукой* и говорит Ciao, fratello"):
        result = engine.process_in(phrase)
        print(f"  {phrase!r}\n     -> перевод: {result.text!r} | оригинал: {result.native!r} | "
              f"переведено: {result.translated}")

    print("\nСленг и сокращения (раскрытие до перевода и русская подстраховка):")
    for source in ("brb", "afk 5 min", "I'm afk", "ty, np", "gg wp", "looool, ez",
                   "idk man, wdym", "спс, мб завтра"):
        is_russian = slang.is_russian_token(source)
        expanded = (slang.expand_russian(source) if is_russian else slang.expand_foreign(source))[0]
        print(f"  {source!r} -> {expanded!r}")
    for source in ("ахах gg", "я afk", "lol, это было ez"):
        print(f"  подстраховка: {source!r} -> {slang.restore_russian(source)[0]!r}")
    print(f"  в таблицах: {slang.known()}")

    print("\nАвтоперевод (разные seed выбирают разные фрагменты):")
    for seed in (1, 2, 3):
        try:
            result = engine.process("мне срочно нужна помощь, не знаю что делать",
                                    auto=True, seed=seed)
            print(f"   seed {seed}: {result.text}")
        except Exception as error:                      # фрагмент вне словаря
            print(f"   seed {seed}: фрагмент вне словаря, нужна сеть ({error})")


def list_langs() -> None:
    """Список языков и наличие встроенного словаря / language and pack list."""
    from app import langs
    from app.langpacks import has_pack

    for language in langs.LANGUAGES:
        code = language["code"]
        pack_state = "встроен" if has_pack(code) else "нет (загружается вручную)"
        reading = "" if langs.reading(code) else " · без русской записи"
        print(f"{code:<7} {langs.label(code, native=True):<32} словарь: {pack_state}{reading}")


def find_game(cfg: dict) -> None:
    """Печатает окна Windows и отмечает то, что похоже на игру / list windows."""
    from app import gamesend

    for window in gamesend.list_windows():
        if window.w > 100 and window.h > 100:
            mark = ">>" if gamesend.is_game(window, cfg) else "  "
            print(f"{mark} {window.hwnd:>10}  {window.exe or '?':<28} {window.cls:<28} "
                  f"{window.w}x{window.h}  {window.title[:40]}")


# ---------------------------------------------------------------------- запуск
def main() -> int:
    """Запуск программы / program entry point."""
    _silence_stdout()
    setup_logging()

    if "--version" in sys.argv:
        print(f"{APP_NAME} {VERSION}")
        return 0

    cfg = load_config()
    i18n.set_lang(cfg.get("ui_lang", "ru"))      # журнал и консоль на языке игрока

    if "--selftest" in sys.argv:
        selftest(cfg)
        return 0
    if "--find-game" in sys.argv:
        find_game(cfg)
        return 0
    if "--langs" in sys.argv:
        list_langs()
        return 0

    log.info("Модули: %s", modules.summary(cfg))
    handle, is_first = single_instance()
    if not is_first:
        print(i18n.t("Оверлей уже запущен (значок в трее)."))
        return 1
    del handle                      # мьютекс живёт до выхода из процесса

    try:
        from app.overlay import run_gui
        return run_gui(cfg, open_settings_on_start="--settings" in sys.argv)
    except Exception:
        log.exception("Критическая ошибка")
        raise


if __name__ == "__main__":
    sys.exit(main())
