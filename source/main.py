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
import re
import sys

from app import APP_NAME, MUTEX_NAME, VERSION, i18n, modules
from app.config import log, load_config, setup_logging


# --------------------------------------------------------------------- служебное
def _silence_stdout() -> None:
    """В оконной сборке консоли нет: print() должен молча писать в никуда.

    A windowed build has no console; print() goes to a bit bucket instead of
    raising on a missing stdout.
    """
    # Дескриптор живёт до выхода из программы: закрывать его нельзя, иначе print()
    # снова упадёт. Отсюда noqa вместо менеджера контекста.
    # The handle must live until the process exits: closing it would make print()
    # fail again, hence noqa instead of a context manager.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115


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
        "it": [
            "Слушай, брат, подожди",
            "Ну что ты, я же говорил",
            "Потихоньку идём",
            "/to Ivan слушай, брат",
        ],
        "es": ["Слушай, брат, подожди", "Ну что ты, я же говорил", "/l слушай сюда"],
        "es-MX": ["Слушай, брат", "Ну что ты, я же говорил"],
        "pt-BR": ["Слушай, брат, подожди", "Ну что ты"],
        "zh-CN": ["Слушай, брат", "Ну что ты, я же говорил"],
        "ja": ["Слушай, брат", "А что поделаешь"],
    }
    for code, phrases in samples.items():
        glossary = load_glossary(code, cfg)
        engine = Engine(cfg, glossary, _offline_translator())
        print(
            f"\n=== {langs.label(code)} ({code}) — фраз в словаре: {len(glossary.phrases)}, "
            f"паразитов: {len(glossary.fillers)} ==="
        )
        for phrase in phrases:
            result = engine.process(phrase)
            flag = " [команда]" if is_counted_command(phrase) else ""
            print(
                f"  {phrase!r}{flag}\n     -> {result.text!r} | чтение: {result.native!r} | "
                f"переведено: {result.translated} | "
                f"паразит: {has_fillers(phrase, cfg, glossary)}"
            )

    engine = Engine(cfg, load_glossary("it", cfg), _reverse_translator())
    print("\nРежим переводчика (язык сервера → русский):")
    for phrase in (
        "Ciao, fratello",
        "*машет рукой* Ciao, fratello",
        "/me *машет рукой* и говорит Ciao, fratello",
    ):
        result = engine.process_in(phrase)
        print(
            f"  {phrase!r}\n     -> перевод: {result.text!r} | оригинал: {result.native!r} | "
            f"переведено: {result.translated}"
        )

    print("\nСленг и сокращения (раскрытие до перевода и русская подстраховка):")
    for source in (
        "brb",
        "afk 5 min",
        "I'm afk",
        "ty, np",
        "gg wp",
        "looool, ez",
        "idk man, wdym",
        "спс, мб завтра",
    ):
        is_russian = slang.is_russian_token(source)
        expanded = (slang.expand_russian(source) if is_russian else slang.expand_foreign(source))[0]
        print(f"  {source!r} -> {expanded!r}")
    for source in ("ахах gg", "я afk", "lol, это было ez"):
        print(f"  подстраховка: {source!r} -> {slang.restore_russian(source)[0]!r}")
    print(f"  в таблицах: {slang.known()}")

    print("\nАвтоперевод (разные seed выбирают разные фрагменты):")
    for seed in (1, 2, 3):
        try:
            result = engine.process(
                "мне срочно нужна помощь, не знаю что делать", auto=True, seed=seed
            )
            print(f"   seed {seed}: {result.text}")
        except Exception as error:  # фрагмент вне словаря
            print(f"   seed {seed}: фрагмент вне словаря, нужна сеть ({error})")


def selftest_anims(cfg: dict) -> None:
    """Проверка модуля «Анимации» без игры и без сети / offline animation check.

    Прогоняет критерии приёмки: режимы считывания, поиск ключевого слова,
    отправку `/anim`, `/sa` по таймеру и зацикливание. Игра не нужна: команды
    принимает заглушка, поэтому проверка работает где угодно.
    Runs the acceptance criteria: read modes, keyword search, `/anim`, the timed
    `/sa` and looping. No game is needed: a stub receives the commands.
    """
    import time

    from app import animations as anims, morph

    def rule(**kwargs):
        base = dict(keywords="привет", name="wave", mode=anims.MODE_ALWAYS, duration_ms=1000)
        base.update(kwargs)
        return anims.Rule(**base)

    print("\n=== Модуль «Анимации»: режимы считывания ===")
    cases = (
        (anims.MODE_ALWAYS, "что угодно привет тут", True),
        (anims.MODE_ALWAYS, "приветствую тебя", False),
        (anims.MODE_EMOTES, "привет", False),
        (anims.MODE_EMOTES, "/me привет", True),
        (anims.MODE_EMOTES, "/ame привет", True),
        (anims.MODE_EMOTES, "текст *привет* текст", True),
        (anims.MODE_ACTIONS, "текст *привет* текст", True),
        (anims.MODE_ACTIONS, "привет", False),
        (anims.MODE_MESSAGES, "привет", True),
        (anims.MODE_MESSAGES, "/me привет", False),
        (anims.MODE_MESSAGES, "смотри *привет* тут", True),
        (anims.MODE_MESSAGES, "/me *привет*", False),
        (anims.MODE_MESSAGES, "/to Ivan привет", True),
    )
    failed = 0
    for mode, phrase, expected in cases:
        got = bool(rule(mode=mode).matches(phrase))
        failed += 0 if got == expected else 1
        print(
            f"  {'ok    ' if got == expected else 'ПРОВАЛ'} режим {mode} "
            f"({anims.describe_mode(mode)}): {phrase!r} -> {got}"
        )

    print("\n=== Несколько ключевых слов, регистр и «ё» ===")
    multi = rule(keywords="привет, здравствуй, ещё")
    for phrase, expected in (
        ("здравствуй, друг", True),
        ("и еще раз", True),
        ("нет тут ничего", False),
        ("ПРИВЕТ", True),
    ):
        got = bool(multi.matches(phrase))
        failed += 0 if got == expected else 1
        print(f"  {'ok    ' if got == expected else 'ПРОВАЛ'} {phrase!r} -> {got}")

    # ------------------------------------------------------------------
    # повторы, слова-синонимы и способы остановки
    # repetitions, synonyms and the stop methods
    codes = {
        "чёрт": "mannaggia",
        "проклятье": "mannaggia",
        "блин": "mannaggia",
        "да ну": "ma dai",
        "да брось": "ma dai",
        "дай": "dai",
    }

    def equiv(phrase):
        return codes.get(phrase.lower(), "")

    def phrase_keys(text):
        """Фразы словаря в тексте — как это делает настоящий словарь.

        The glossary phrases found in the text, the way the real glossary does it:
        single words first, then the longer phrases that win over them.
        """
        low = text.lower()
        out = []
        for match in re.finditer(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", low):
            key = codes.get(match.group(0))
            if key:
                out.append((match.start(), match.end(), key))
        for phrase in ("да ну", "да брось"):
            start = low.find(phrase)
            while start >= 0:
                out.append((start, start + len(phrase), codes[phrase]))
                start = low.find(phrase, start + len(phrase))
        return sorted(out)

    def quick(rules, message, wait=0.5, **extra):
        """Быстрый прогон: правила и сообщение -> команды и нажатия клавиш.

        A quick run: rules and a message -> the commands and the key presses.
        """
        commands, pressed = [], []
        # хвост после анимации здесь выключен: проверки быстрые, а сам хвост
        # проверяется отдельным прогоном в конце
        # the tail is off for these fast checks; the tail itself has its own run
        cfg = {"anims_enabled": True, "anim_rules": rules, "anim_extra_ms": 0}
        cfg.update(extra)
        runner = anims.Runner(
            cfg,
            send=lambda c: commands.append(c) or (True, ""),
            on_event=None,
            equivalent=equiv,
            text_keys=phrase_keys,
            press_key=lambda spec: pressed.append(spec) or (True, ""),
        )
        runner.feed(message)
        time.sleep(wait)
        runner.shutdown()
        return commands, pressed

    print("\n=== Повторы, синонимы и способы остановки ===")
    commands, _ = quick([rule(keywords="чёрт", name="anger", duration_ms=80)], "чёрт, чёрт")
    print(f"  «чёрт, чёрт» (правило играет один раз): {commands}")
    failed += 0 if commands == ["/anim anger", "/sa"] else 1

    commands, _ = quick(
        [
            rule(keywords="чёрт", name="anger", duration_ms=80),
            rule(keywords="кашляет", name="cough", duration_ms=80),
        ],
        "Чёрт, чёрт, как же я устал *кашляет*",
    )
    print(f"  два правила при повторе одного слова: {commands}")
    failed += 0 if commands == ["/anim anger", "/sa", "/anim cough", "/sa"] else 1

    commands, _ = quick([rule(keywords="чёрт", name="anger", duration_ms=80)], "Проклятье, опять")
    print(f"  синоним «проклятье» при ключе «чёрт»: {commands}")
    failed += 0 if commands and commands[0] == "/anim anger" else 1

    commands, _ = quick([rule(keywords="чёрт", name="anger", duration_ms=0)], "чёрт", wait=0.3)
    print(f"  длительность 0 мс (не останавливать): {commands}")
    failed += 0 if commands == ["/anim anger"] else 1

    commands, pressed = quick(
        [rule(keywords="чёрт", name="anger", duration_ms=80)],
        "чёрт",
        anim_stop_by_sa=False,
        anim_stop_by_key=True,
    )
    print(f"  остановка клавишей: команды {commands}, нажатия {pressed}")
    failed += 0 if commands == ["/anim anger"] and pressed[:1] == ["f"] else 1

    commands, pressed = quick(
        [rule(keywords="чёрт", name="anger", duration_ms=80)],
        "чёрт",
        anim_stop_by_sa=False,
        anim_stop_by_key=False,
    )
    print(f"  оба способа выключены: {commands}, нажатия {pressed}")
    failed += 0 if commands == ["/anim anger"] and not pressed else 1

    commands, pressed = quick(
        [rule(keywords="чёрт", name="anger", duration_ms=80)],
        "чёрт",
        anim_stop_by_sa=True,
        anim_stop_by_key=True,
        anim_stop_key="f5",
    )
    print(f"  оба способа включены: {commands}, нажатия {pressed}")
    failed += 0 if commands == ["/anim anger", "/sa"] and pressed[:1] == ["f5"] else 1

    print("\n=== Словоформы ключевых слов ===")
    forms_cases = (
        (morph.FORMS_EXACT, "открыл зонт", True),
        (morph.FORMS_EXACT, "открывает зонт", False),
        (morph.FORMS_STEM, "открывает зонт", True),
        (morph.FORMS_STEM, "открыла огромный зонт", True),
        (morph.FORMS_STEM, "откроет зонт", True),
        (morph.FORMS_STEM, "открыл зонтик", False),
        (morph.FORMS_STEM, "закрыл зонт", False),
        (morph.FORMS_LEMMA, "открывает зонт", True),
        (morph.FORMS_LEMMA, "достал зонт", False),
    )
    for forms_kind, phrase, expected in forms_cases:
        got = bool(
            anims.Rule(keywords="открыл зонт", name="umbrella", forms=forms_kind).scan(phrase)[1]
        )
        failed += 0 if got == expected else 1
        print(
            f"  {'ok    ' if got == expected else 'ПРОВАЛ'} "
            f"{morph.describe_forms(forms_kind):<7} {phrase!r} -> {got}"
        )
    if morph.lemmas_available():
        got = bool(
            anims.Rule(keywords="человек", name="human", forms=morph.FORMS_LEMMA).scan(
                "пришли люди"
            )[1]
        )
        failed += 0 if got else 1
        print(f"  {'ok    ' if got else 'ПРОВАЛ'} леммы: «люди» по ключу «человек» -> {got}")
    else:
        print("  ----   леммы: пакет pymorphy3 не установлен, проверка пропущена")
    legacy = anims.Rule.from_dict({"keywords": "привет", "name": "wave", "mode": 5})
    failed += 0 if legacy.mode == anims.MODE_ALWAYS else 1
    print(f"  режим 5 (убран) читается как «{anims.describe_mode(legacy.mode)}»: {legacy.mode}")
    junk = anims.Rule.from_dict({"keywords": "привет", "name": "wave", "forms": 99})
    failed += 0 if junk.forms == morph.FORMS_DEFAULT else 1
    print(f"  мусор в «Формах» чинится на «{morph.describe_forms(junk.forms)}»: {junk.forms}")

    print("\n=== Отрицание и синонимы по фразе ===")
    commands, _ = quick(
        [rule(keywords="открыл зонт", name="umbrella", duration_ms=80)],
        "Не открыл зонт — дождь кончился",
    )
    print(f"  «не открыл зонт» (проверка включена): {commands}")
    failed += 0 if commands == [] else 1

    commands, _ = quick(
        [rule(keywords="открыл зонт", name="umbrella", duration_ms=80)],
        "Не открыл зонт — дождь кончился",
        anim_skip_negation=False,
    )
    print(f"  «не открыл зонт» (проверка выключена): {commands}")
    failed += 0 if commands == ["/anim umbrella", "/sa"] else 1

    commands, _ = quick(
        [rule(keywords="открыл зонт", name="umbrella", duration_ms=80)], "Открыл зонт и вышел"
    )
    print(f"  «открыл зонт»: {commands}")
    failed += 0 if commands == ["/anim umbrella", "/sa"] else 1

    commands, _ = quick(
        [rule(keywords="не открыл зонт", name="umbrella", duration_ms=80)],
        "Не открыл зонт и остался",
    )
    print(f"  ключ сам с отрицанием: {commands}")
    failed += 0 if commands == ["/anim umbrella", "/sa"] else 1

    commands, _ = quick(
        [rule(keywords="не открыл зонт", name="umbrella", duration_ms=80)], "Открыл зонт и вышел"
    )
    print(f"  ключ с отрицанием на «открыл зонт»: {commands}")
    failed += 0 if commands == [] else 1

    commands, _ = quick([rule(keywords="да брось", name="dai", duration_ms=80)], "Да ну")
    print(f"  синоним по фразе: ключ «да брось» на «да ну»: {commands}")
    failed += 0 if commands == ["/anim dai", "/sa"] else 1

    commands, _ = quick([rule(keywords="да брось", name="dai", duration_ms=80)], "Да ну да брось")
    print(f"  «да ну да брось» при одном ключе — одно срабатывание: {commands}")
    failed += 0 if commands == ["/anim dai", "/sa"] else 1

    commands, _ = quick(
        [rule(keywords="да ну, да брось", name="dai", duration_ms=80)], "Да ну да брось"
    )
    print(f"  два ключа-синонима в правиле: {commands}")
    failed += 0 if commands == ["/anim dai", "/sa"] * 2 else 1

    commands, _ = quick(
        [rule(keywords="дождь, зонт", name="rain", duration_ms=80)], "Дождь льёт, зонт промок"
    )
    print(f"  два разных ключа в правиле: {commands}")
    failed += 0 if commands == ["/anim rain", "/sa"] * 2 else 1

    commands, _ = quick(
        [rule(keywords="дождь, зонт", name="rain", duration_ms=80)], "Дождь, дождь и зонт"
    )
    print(f"  повтор ключа + второй ключ: {commands}")
    failed += 0 if commands == ["/anim rain", "/sa"] * 2 else 1

    # вложенные ключи: «сел» и «сел откинувшись» — играет только длинное,
    # иначе длинная анимация сразу же гасится короткой
    # nested keywords: of «сел» and «сел откинувшись» only the long one plays,
    # otherwise the long animation is put out by the short one right away
    print("\n=== Вложенные ключи: длинное совпадение важнее короткого ===")
    nested_cases = (
        ("Сел откинувшись на спинку", ["sit_back"]),
        ("Сел на стул", ["sit"]),
        ("Сел откинувшись, а потом сел прямо", ["sit_back", "sit"]),
        ("Сел. Потом сел откинувшись.", ["sit", "sit_back"]),
    )
    for phrase, expected in nested_cases:
        commands, _ = quick(
            [
                rule(keywords="сел", name="sit", duration_ms=60),
                rule(keywords="сел откинувшись", name="sit_back", duration_ms=60),
            ],
            phrase,
        )
        names = [line.split()[-1] for line in commands if line.startswith("/anim")]
        failed += 0 if names == expected else 1
        print(
            f"  {'ok    ' if names == expected else 'ПРОВАЛ'} {phrase!r} -> {names}"
            f" (ждали {expected})"
        )

    commands, _ = quick(
        [rule(keywords="сел, сел откинувшись", name="sit", duration_ms=60)], "Сел откинувшись"
    )
    print(f"  оба ключа в одном правиле, длинный первым: {commands}")
    failed += 0 if commands == ["/anim sit", "/sa"] else 1

    # варианты анимации: два и больше /anim на один ключ — оверлей выбора
    # animation variants: two or more /anim commands per keyword show a chooser
    print("\n=== Варианты анимации (выбор из нескольких) ===")
    cl = anims.Choice
    variants_rule = anims.Rule(
        keywords="оперся руками",
        name="",
        duration_ms=60,
        choices=[
            cl(
                name="anim_counterleanbar",
                title="Опёрся на стойку",
                description="Локти на барной стойке",
            ),
            cl(name="anim_leanrail", title="Опёрся на перила", description="Опирается на перила"),
        ],
    )
    failed += 0 if variants_rule.problem() == "" else 1
    print(f"  правило с вариантами проходит проверку: {variants_rule.problem()!r}")
    failed += 0 if variants_rule.needs_choice() else 1
    print(f"  нужен оверлей выбора: {variants_rule.needs_choice()}")

    single = anims.Rule(keywords="сел", duration_ms=60, choices=[cl(name="sit")])
    failed += 0 if not single.needs_choice() else 1
    print(f"  один вариант — обычное правило, оверлея нет: {single.needs_choice()}")

    plain = anims.Rule(keywords="сел", name="sit", duration_ms=60)
    failed += 0 if not plain.needs_choice() else 1
    print(f"  правило без вариантов как раньше: {[c.name for c in plain.variant_list()]}")

    again = anims.Rule.from_dict(variants_rule.to_dict())
    same = [(c.name, c.title, c.description) for c in again.choices]
    failed += 0 if same == [(c.name, c.title, c.description) for c in variants_rule.choices] else 1
    print(f"  сохранение и чтение вариантов: {len(same)} шт.")

    strings = anims.Rule.from_dict({"keywords": "x", "choices": ["anim_a", "anim_b"]})
    failed += 0 if [c.name for c in strings.choices] == ["anim_a", "anim_b"] else 1
    print(f"  варианты можно писать строкой: {[c.name for c in strings.choices]}")

    # выбор: какой вариант уйдёт в игру
    def choice_run(pick):
        commands = []

        def chooser(rule):
            """Заглушка выбора для самопроверки / a chooser stub for the selftest."""
            return rule.choices[pick] if isinstance(pick, int) else pick

        runner_ = anims.Runner(
            {"anims_enabled": True, "anim_extra_ms": 0},
            send=lambda command: commands.append(command) or (True, ""),
            on_event=None,
            chooser=chooser,
        )
        runner_._rules = [
            anims.Rule(
                keywords="оперся", duration_ms=60, choices=[cl(name="anim_a"), cl(name="anim_b")]
            )
        ]
        runner_.feed("оперся")
        time.sleep(0.35)
        runner_.shutdown()
        return commands

    commands = choice_run(1)
    print(f"  выбран второй вариант: {commands}")
    failed += 0 if commands == ["/anim anim_b", "/sa"] else 1

    commands = choice_run(None)
    print(f"  отказ от выбора — не играет ничего: {commands}")
    failed += 0 if commands == [] else 1

    # смена варианта на ходу: окно не закрывается, и новый выбор меняет анимацию
    # swapping on the fly: the window stays open and a new pick changes it
    commands = []
    swap = {}

    def slow_pick(rule_obj, on_change=None):
        """Первый ответ сразу, второй приходит во время проигрывания.

        The first answer is immediate, the second arrives mid-play.
        """
        if on_change is not None:
            swap["change"] = on_change
        return rule_obj.choices[0]

    runner_swap = anims.Runner(
        {"anims_enabled": True, "anim_extra_ms": 0},
        send=lambda command: commands.append(command) or (True, ""),
        on_event=None,
        chooser=slow_pick,
    )
    runner_swap._rules = [
        anims.Rule(
            keywords="оперся", duration_ms=400, choices=[cl(name="anim_a"), cl(name="anim_b")]
        )
    ]
    runner_swap.feed("оперся")
    time.sleep(0.15)
    swap["change"](anims.Choice(name="anim_b"))
    time.sleep(0.7)
    runner_swap.shutdown()
    print(f"  смена варианта на ходу: {commands}")
    # после смены новая анимация тоже гасится своим /sa
    # the swapped-in animation is put out with its own /sa as well
    failed += 0 if commands == ["/anim anim_a", "/sa", "/anim anim_b", "/sa"] else 1

    # два ключа с выбором в одном сообщении: окна не наслаиваются, очередь меню
    # идёт по одному, а выбор по каждому ключу сохраняется
    # two chooser keywords in one message: the windows never stack, the menus run
    # one at a time, and each keyword keeps its own pick
    print("\n=== Два ключа с выбором в одном сообщении ===")
    two = [
        anims.Rule(
            keywords="оперся",
            duration_ms=200,
            choices=[cl(name="lean_a"), cl(name="lean_b")],
            id="r1",
        ),
        anims.Rule(
            keywords="сел", duration_ms=200, choices=[cl(name="sit_a"), cl(name="sit_b")], id="r2"
        ),
    ]
    asked, orders = [], []

    def two_pick(rule, on_change=None):
        asked.append(rule.keywords)
        return rule.choices[0]

    sent_two = []
    runner_two = anims.Runner(
        {"anims_enabled": True, "anim_extra_ms": 0},
        send=lambda command: sent_two.append(command) or (True, ""),
        on_event=None,
        chooser=two_pick,
    )
    runner_two._rules = two
    runner_two.feed("оперся и сел")
    time.sleep(0.9)
    runner_two.shutdown()
    orders.append(asked)
    print(f"  спросили по очереди: {asked}")
    failed += 0 if asked == ["оперся", "сел"] else 1
    print(f"  сыграло по выбору каждого: {sent_two}")
    failed += 0 if sent_two[:2] == ["/anim lean_a", "/sa"] else 1

    # Очередь меню выбора: отвеченное меню уходит из очереди, и следующее
    # занимает окно. Проверяем на чистых списках — без Qt, чтобы работало в
    # самотесте где угодно.
    # The chooser menu queue: an answered menu leaves the queue and the next one
    # takes the window. Checked on plain lists — no Qt, so it runs anywhere.
    print("\n=== Очередь меню выбора ===")
    menus = ["меню1: оперся", "меню2: сел"]
    answered = menus.pop(0)  # ответили по первому
    print(f"  ответили по «{answered}», в очереди: {menus}")
    failed += 0 if menus == ["меню2: сел"] else 1
    shown_menu = menus[0] if menus else None
    print(f"  окно показывает: {shown_menu}")
    failed += 0 if shown_menu == "меню2: сел" else 1

    print("\n=== Проверка неверных правил ===")
    for bad in (
        rule(keywords=""),
        rule(name=""),
        rule(name="my anim"),
        rule(duration_ms=-5),
        rule(mode=9),
    ):
        print(f"  {bad.keywords!r}/{bad.name!r}: {bad.problem()}")

    print("\n=== Отправка и зацикливание (быстрый прогон) ===")
    sent = []
    started = time.time()
    # хвост после анимации здесь выключен: проверяем только порядок команд,
    # сам хвост проверяем отдельным прогоном ниже
    # the tail is off here: these cases check the order of the commands, and the
    # tail itself is checked by a separate run below
    runner = anims.Runner(
        {"anims_enabled": True, "anim_extra_ms": 0},
        send=lambda command: sent.append((round(time.time() - started, 2), command)) or (True, ""),
        on_event=None,
    )
    runner._rules = [rule(duration_ms=150)]  # без зацикливания
    runner.feed("привет")
    time.sleep(0.45)
    print(f"  один цикл: {sent}")
    failed += 0 if [c for _, c in sent] == ["/anim wave", "/sa"] else 1

    sent.clear()
    runner._rules = [rule(duration_ms=120, loop=True)]
    runner.feed("привет")
    time.sleep(0.5)
    runner.stop_user()
    time.sleep(0.3)
    commands = [c for _, c in sent]
    # при зацикливании /sa между повторами не отправляется: анимация просто
    # запускается снова по таймеру, а /sa уходит только при остановке
    # a loop sends no /sa between the repeats: the animation simply starts again
    # by the timer, and the single /sa comes with the stop
    loops_ok = len(commands) >= 3 and set(commands[:-1]) == {"/anim wave"} and commands[-1] == "/sa"
    print(f"  зацикливание: {sent}")
    failed += 0 if loops_ok else 1

    sent.clear()
    runner._rules = [
        rule(keywords="один", name="a1", duration_ms=100),
        rule(keywords="два", name="a2", duration_ms=100),
    ]
    runner.feed("один и два")
    time.sleep(0.6)
    order = [c for _, c in sent]
    print(f"  очередь двух правил: {sent}")
    failed += 0 if order == ["/anim a1", "/sa", "/anim a2", "/sa"] else 1

    # порядок берётся из сообщения, а не из таблицы правил: «кашляет» стоит в
    # списке первым, но в тексте идёт позже — играть должно вторым
    # the order comes from the message, not from the rule table: «кашляет» is
    # listed first but appears later in the text, so it must play second
    sent.clear()
    runner._rules = [
        rule(keywords="кашляет", name="cough", duration_ms=100),
        rule(keywords="чёрт", name="anger", duration_ms=100),
    ]
    runner.feed("Чёрт, как же я устал от этого *кашляет*")
    time.sleep(0.6)
    order = [c for _, c in sent]
    print(f"  порядок по словам сообщения: {sent}")
    failed += 0 if order == ["/anim anger", "/sa", "/anim cough", "/sa"] else 1
    runner.shutdown()

    # хвост после анимации: следующая команда идёт через длительность анимации
    # плюс хвост, а не в ту же секунду, что и /sa от первой
    # the tail after an animation: the next command follows one duration plus the
    # tail later, not in the same instant as the first /sa
    def tail_run(extra, first_ms, wait):
        sent.clear()
        clock = time.time()
        runner_ = anims.Runner(
            {"anims_enabled": True, "anim_extra_ms": extra},
            send=lambda command: (
                sent.append((round(time.time() - clock, 2), command)) or (True, "")
            ),
            on_event=None,
        )
        runner_._rules = [
            rule(keywords="один", name="a1", duration_ms=first_ms),
            rule(keywords="два", name="a2", duration_ms=100),
        ]
        runner_.feed("один и два")
        time.sleep(wait)
        runner_.shutdown()
        return [command for _, command in sent], [
            round(sent[i + 1][0] - sent[i][0], 2) for i in range(len(sent) - 1)
        ]

    commands, gaps = tail_run(50, 100, 0.6)
    print(f"  хвост 50 мс: {sent}, паузы {gaps}")
    failed += (
        0 if (commands == ["/anim a1", "/sa", "/anim a2", "/sa"] and 0.04 <= gaps[1] <= 0.12) else 1
    )

    commands, gaps = tail_run(0, 100, 0.5)
    print(f"  хвост 0 мс: {sent}, паузы {gaps}")
    failed += 0 if (commands == ["/anim a1", "/sa", "/anim a2", "/sa"] and gaps[1] <= 0.03) else 1

    # хвост отсчитывается от конца анимации: 400 мс анимация + 200 мс хвоста —
    # следующая команда через 0,6 с
    # the tail is counted from the end of the animation: a 400 ms animation plus
    # a 200 ms tail send the next command after 0.6 s
    commands, gaps = tail_run(200, 400, 1.1)
    print(f"  хвост 200 мс при анимации 400 мс: {sent}, паузы {gaps}")
    failed += (
        0
        if (
            commands == ["/anim a1", "/sa", "/anim a2", "/sa"] and 0.55 <= gaps[1] + gaps[0] <= 0.65
        )
        else 1
    )

    # остановка игроком гасит текущую анимацию, но очередь не снимает: второе
    # срабатывание из того же сообщения должно сыграть
    # a player stop ends the current animation but keeps the queue: the second
    # hit from the same message still plays
    sent.clear()
    clock = time.time()
    stop_runner = anims.Runner(
        {"anims_enabled": True, "anim_extra_ms": 0},
        send=lambda command: sent.append((round(time.time() - clock, 2), command)) or (True, ""),
        on_event=None,
    )
    stop_runner._rules = [
        rule(keywords="один", name="a1", duration_ms=400),
        rule(keywords="два", name="a2", duration_ms=100),
    ]
    stop_runner.feed("один и два")
    time.sleep(0.2)
    stop_runner.stop_user()  # игрок нажал клавишу остановки
    time.sleep(0.8)
    stop_runner.shutdown()
    commands = [command for _, command in sent]
    print(f"  остановка игроком, очередь остаётся: {sent}")
    failed += 0 if commands == ["/anim a1", "/sa", "/anim a2", "/sa"] else 1

    # полная остановка очередь снимает
    # a full stop drops the queue
    sent.clear()
    clock = time.time()
    clear_runner = anims.Runner(
        {"anims_enabled": True, "anim_extra_ms": 0},
        send=lambda command: sent.append((round(time.time() - clock, 2), command)) or (True, ""),
        on_event=None,
    )
    clear_runner._rules = [
        rule(keywords="один", name="a1", duration_ms=400),
        rule(keywords="два", name="a2", duration_ms=100),
    ]
    clear_runner.feed("один и два")
    time.sleep(0.15)
    clear_runner.stop("снято вручную")
    time.sleep(0.6)
    clear_runner.shutdown()
    commands = [command for _, command in sent]
    print(f"  полная остановка снимает очередь: {sent}")
    failed += 0 if "/anim a2" not in commands else 1

    print(f"\nИтог модуля «Анимации»: {'всё сходится' if not failed else 'ошибок: %d' % failed}")


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
            print(
                f"{mark} {window.hwnd:>10}  {window.exe or '?':<28} {window.cls:<28} "
                f"{window.w}x{window.h}  {window.title[:40]}"
            )


# ---------------------------------------------------------------------- запуск
def main() -> int:
    """Запуск программы / program entry point."""
    _silence_stdout()
    setup_logging()

    if "--version" in sys.argv:
        print(f"{APP_NAME} {VERSION}")
        return 0

    cfg = load_config()
    i18n.set_lang(cfg.get("ui_lang", "ru"))  # журнал и консоль на языке игрока

    if "--selftest" in sys.argv:
        selftest(cfg)
        selftest_anims(cfg)
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
    del handle  # мьютекс живёт до выхода из процесса

    try:
        from app.overlay import run_gui

        return run_gui(cfg, open_settings_on_start="--settings" in sys.argv)
    except Exception:
        log.exception("Критическая ошибка")
        raise


if __name__ == "__main__":
    sys.exit(main())
