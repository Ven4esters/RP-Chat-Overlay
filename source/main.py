"""main.py — запуск оверлея. Ключи: --settings, --selftest, --find-game, --langs."""
import ctypes
import os
import sys

from common import load_config, log, save_config, setup_logging

EXTRA = {
    "hotkey": "F6",
    "game_submit": True,          # после вставки нажимать Enter в игре
    "game_open_chat_first": True, # сначала открыть чат игры (T), потом оверлей
    "filler_always": True,        # слова-паразиты переводить в КАЖДОМ сообщении
    "game_focus_delay_ms": 150,
    "game_input_mode": "paste",   # "paste" = Ctrl+V, "type" = посимвольный ввод
    "overlay_pos": [0.01, 0.28],  # положение окна относительно окна игры (доли ширины и высоты)
    "overlay_width": 560,
    # --- автоперевод (auto_mode и auto_every лежат в основном конфиге) ---
    "auto_position": "last",      # какое сообщение в серии: "last" | "first" | "random" | число 1..N
    "auto_fragments": 1,          # сколько фрагментов переводить в сообщении
    "auto_min_words": 1,          # длина фрагмента: от скольких слов
    "auto_max_words": 3,          # ... и до скольких
    "auto_prefer_glossary": True, # сначала брать фразы, которые есть в словаре
}


def prepare_config():
    cfg = load_config()
    for k, v in EXTRA.items():
        cfg.setdefault(k, v)
    save_config(cfg)
    return cfg


def selftest(cfg):
    """Проверка перевода по нескольким языкам без обращения к сети."""
    import langs
    from engine import Engine, has_fillers, is_counted_command, load_glossary

    class NoNet:
        def translate(self, text):
            raise RuntimeError("в selftest сеть не используется")

    samples = {
        "it": ["Слушай, брат, подожди", "Ну что ты, я же говорил", "Потихоньку идём",
               "/to Ivan слушай, брат"],
        "es": ["Слушай, брат, подожди", "Ну что ты, я же говорил", "/l слушай сюда"],
        "es-MX": ["Слушай, брат", "Ну что ты, я же говорил"],
        "pt-BR": ["Слушай, брат, подожди", "Ну что ты"],
        "zh-CN": ["Слушай, брат", "Ну что ты, я же говорил"],
        "ja": ["Слушай, брат", "А что поделаешь"],
    }
    for code in samples:
        gl = load_glossary(code)
        eng = Engine(cfg, gl, NoNet())
        print(f"\n=== {langs.label(code)} ({code}) — фраз в словаре: {len(gl.phrases)}, "
              f"паразитов: {len(gl.fillers)} ===")
        for s in samples[code]:
            r = eng.process(s)
            flag = " [команда]" if is_counted_command(s) else ""
            print(f"  {s!r}{flag}\n     -> {r.text!r} | чтение: {r.italian!r} | "
                  f"переведено: {r.translated} | паразит: {has_fillers(s, cfg, gl)}")
    gl = load_glossary("it")
    eng = Engine(cfg, gl, NoNet())
    print("\nАвтоперевод (разные seed выбирают разные фрагменты):")
    for seed in (1, 2, 3):
        try:
            r = eng.process("мне срочно нужна помощь, не знаю что делать",
                            auto=True, seed=seed)
            print(f"   seed {seed}: {r.text}")
        except Exception as e:
            print(f"   seed {seed}: фрагмент вне словаря, нужна сеть ({e})")


def list_langs():
    """Список языков и наличие встроенного словаря."""
    import langs
    from langpacks import has_pack
    for x in langs.LANGUAGES:
        print(f"{x['code']:<7} {langs.label(x['code'], native=True):<32} "
              f"словарь: {'встроен' if has_pack(x['code']) else 'нет (загружается вручную)'}"
              f"{'' if langs.reading(x['code']) else ' · без русской записи'}")


def find_game(cfg):
    import gamesend as gs
    for w in gs.list_windows():
        if w.w > 100 and w.h > 100:
            mark = ">>" if gs.is_game(w, cfg) else "  "
            print(f"{mark} {w.hwnd:>10}  {w.exe or '?':<28} {w.cls:<28} {w.w}x{w.h}  {w.title[:40]}")


def single_instance():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    k.CreateMutexW.restype = ctypes.c_void_p
    handle = k.CreateMutexW(None, False, "Local\\ItalianOverlayMutex")
    return handle, ctypes.get_last_error() != 183      # 183 = уже запущено


def main():
    # в оконной сборке (.exe) консоли нет — print() не должен падать
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    setup_logging()
    cfg = prepare_config()
    if "--selftest" in sys.argv:
        return selftest(cfg)
    if "--find-game" in sys.argv:
        return find_game(cfg)
    if "--langs" in sys.argv:
        return list_langs()
    handle, first = single_instance()
    if not first:
        print("Оверлей уже запущен (иконка «IT» в трее).")
        return
    try:
        from overlay import run_gui
        sys.exit(run_gui(cfg, open_settings_on_start="--settings" in sys.argv))
    except Exception:
        log.exception("Критическая ошибка")
        raise


if __name__ == "__main__":
    main()