"""Deterministic coverage for message parsing, glossary logic, and engine modes."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import engine as engine_module  # noqa: E402
from app.engine import (  # noqa: E402
    Engine,
    Glossary,
    Result,
    _filler_key,
    _filler_spans,
    _inject_fillers,
    _normalize_sections,
    _pack_default,
    _phrase_parts,
    auto_wrap,
    get_command,
    has_fillers,
    has_markers,
    hide_actions,
    is_counted_command,
    keep_edges,
    load_glossary,
    load_glossary_data,
    merge_defaults,
    norm,
    reset_glossary,
    restore_actions,
    save_glossary_data,
    split_prefix,
    split_tail,
    strip_markers,
    up_first,
    wrap_fillers,
)


CFG = {
    "marker_open": "+",
    "marker_close": "+",
    "filler_always": False,
    "auto_min_words": 1,
    "auto_max_words": 2,
    "auto_fragments": 1,
    "auto_prefer_glossary": True,
}

PACK = {
    "code": "it",
    "version": 2,
    "phrases": {
        "ciao": "чао | привет",
        "buongiorno": "буонджорно | доброе утро",
        "buona sera": "буона сера | добрый вечер",
        "gatto": "гатто | кот",
        "amico": "амико | друг",
        "ma dai": "ма дай | ну давай",
    },
    "fillers": [{"target": "ma dai", "reading": "ма дай", "ru": ["ну давай"]}],
    "replace": {"caro": "amico"},
    "exceptions": {"readme": "ридми"},
}


class TranslatorStub:
    def __init__(self, result=None):
        self.result = result
        self.calls = []
        self.directions = []

    def translate(self, text):
        self.calls.append(text)
        return self.result(text) if callable(self.result) else self.result or f"tr:{text}"

    def set_direction(self, direction):
        self.directions.append(direction)


def glossary(data=None, lang="it"):
    data = data or {
        "phrases": dict(PACK["phrases"]),
        "replace": dict(PACK["replace"]),
        "exceptions": dict(PACK["exceptions"]),
        "_fillers": [dict(item) for item in PACK["fillers"]],
    }
    return Glossary(data, lang)


def make_engine(cfg=None, data=None, translator=None, lang="it"):
    cfg = {**CFG, **(cfg or {})}
    translator = translator or TranslatorStub()
    return Engine(cfg, glossary(data, lang), translator), translator


def test_command_helpers_keep_supported_chat_commands_and_nicknames():
    assert get_command("  /TO Alice hi") == "/to"
    assert get_command("hello") == ""
    assert get_command("") == ""
    assert is_counted_command("/wt hello") is True
    assert is_counted_command("/me hello") is False
    assert split_prefix("hello") == ("", "hello", False, False)
    assert split_prefix("/to Alice hello") == ("/to Alice ", "hello", True, True)
    assert split_prefix("/lto Bob") == ("/lto Bob", "", True, True)
    assert split_prefix("/l hello") == ("/l ", "hello", True, True)
    assert split_prefix("/me hello") == ("/me ", "hello", True, False)
    assert split_prefix("/me") == ("/me", "", True, False)


def test_text_helpers_preserve_edges_actions_and_sentence_case():
    assert norm("  ÉCOLE, Йод! ") == "ecole, иод"
    assert keep_edges("  hello  ", "hola") == "  hola  "
    assert keep_edges("  hello  ", "  ") == "  hello  "
    hidden, actions = hide_actions("Hi *waves* and *smiles")
    assert hidden == "Hi \ue0000\ue000 and \ue0001\ue000"
    assert restore_actions(hidden, actions) == "Hi *waves* and *smiles"
    assert split_tail("Hello?!...") == ("Hello", "?!...")
    assert split_tail("no tail") == ("no tail", "")
    assert up_first("...hello") == "...Hello"
    assert up_first("123") == "123"


def test_marker_helpers_escape_custom_delimiters_and_leave_actions_untouched():
    cfg = {"marker_open": "[+", "marker_close": "+]"}
    text = "hello [+translate me+] *[+not a marker+]"
    assert has_markers(text, cfg) is True
    assert strip_markers(text, cfg) == "hello translate me *[+not a marker+]"
    assert has_markers("just words", cfg) is False
    assert strip_markers("nothing marked", cfg) == "nothing marked"


def test_filler_matching_prefers_longest_words_and_skips_punctuation_and_actions():
    g = glossary()
    assert _filler_key("  НУ, ДАВАЙ! ") == "ну даваи"
    assert _filler_spans("ну, давай ну", g) == [(0, 9)]
    assert _filler_spans("ну — давай", g) == []
    assert has_fillers("ну, давай", CFG, g) is True
    assert has_fillers("/me ну давай", CFG, g) is False
    assert has_fillers("*ну давай*", CFG, g) is False
    assert has_fillers("обычный текст", CFG, g) is False


def test_wrap_fillers_does_not_rewrite_existing_markers_or_actions():
    g = glossary()
    text = "ну давай, [+ну давай+] *ну давай*"
    cfg = {"marker_open": "[+", "marker_close": "+]"}
    assert wrap_fillers(text, cfg, g) == "[+ну давай+], [+ну давай+] *ну давай*"
    assert wrap_fillers("ну давай", CFG, g) == "+ну давай+"


def test_auto_wrap_is_stable_and_honors_word_count_stopwords_and_fragment_count():
    g = glossary()
    text = "привет мой хороший друг"
    first = auto_wrap(text, CFG, g, seed=23)
    assert first == auto_wrap(text, CFG, g, seed=23)
    assert first.count("+") == 2
    assert auto_wrap("и в на", CFG, g, seed=23) == "и в на"
    cfg = {**CFG, "auto_min_words": "broken", "auto_max_words": None, "auto_fragments": -2}
    assert auto_wrap("привет мир", cfg, g, seed=1).count("+") == 2
    assert auto_wrap("", CFG, g, seed=1) == ""


def test_glossary_format_helpers_and_user_selected_filler_list():
    assert _pack_default({"version": "3", "phrases": {"a": "b"}}) == {
        "_version": 3,
        "phrases": {"a": "b"},
        "replace": {},
        "exceptions": {},
    }
    assert _phrase_parts("  чтение | привет; здравствуй ; ") == (
        "чтение",
        ["привет", "здравствуй"],
    )
    data = {"phrases": {"ma dai": "модернизированное | ну давай"}, "_fillers": []}
    result = _inject_fillers(data, PACK)
    assert result["phrases"]["ma dai"] == "модернизированное | ну давай"
    assert result["_fillers"] == [{"target": "ma dai", "ru": ["ну давай"]}]

    custom = {
        "phrases": {},
        "_fillers_user": True,
        "_fillers": [
            {"target": "ma dai", "ru": ["мой вариант"]},
            {"target": "", "ru": ["invalid"]},
            "not an entry",
        ],
    }
    _inject_fillers(custom, PACK)
    assert custom["_fillers"] == [{"target": "ma dai", "ru": ["мой вариант"]}]


def test_glossary_migration_normalization_and_preserving_user_edits():
    user = {
        "_version": 1,
        "phrases": {"CIAO": "своё чтение | привет", "custom": "кастом | своё"},
        "it_replace": {"mine": "custom"},
    }
    default = {
        "_version": 2,
        "phrases": {"ciao": "чао | привет; здравствуй", "gatto": "гатто | кот"},
        "replace": {"mine": "gatto", "new": "ciao"},
        "exceptions": {"word": "ворд"},
    }
    merged = merge_defaults(user, default)
    assert merged["phrases"]["CIAO"] == "своё чтение | привет; здравствуй"
    assert merged["phrases"]["gatto"] == "гатто | кот"
    assert merged["replace"] == {"mine": "custom", "new": "ciao"}
    old = {"it_replace": {"old": "new"}, "translit_exceptions": {"x": "икс"}}
    assert _normalize_sections(old) == {
        "replace": {"old": "new"},
        "exceptions": {"x": "икс"},
    }


def test_glossary_normalizes_legacy_data_and_resolves_variants():
    g = Glossary(
        {
            "ciao": "чао | привет; здравствуй",
            "gatto": "гатто | кот",
            "ma dai": "ма дай | ну давай",
            "broken": 7,
            "replace": {"caro": "gatto"},
            "exceptions": {"readme": "ридми"},
            "_fillers": [{"target": "ma dai", "ru": ["ну давай"]}],
        },
        "Italian",
    )
    assert g.lang == "it"
    assert g.reading is True
    assert g.find_meaning("Привёт!") == norm("ciao")
    assert g.find_meaning("здравствуй") == norm("ciao")
    assert g.find_meaning("ну, давай") == norm("ma dai")
    assert g.find_meaning("приветте") == norm("ciao")
    assert g.find_meaning("неизвестно") is None
    assert g.phrase_keys("привет и кот") == [(0, 6, norm("ciao")), (9, 12, norm("gatto"))]
    assert g.phrase_keys("ну давай") == [(0, 8, norm("ma dai"))]


def test_glossary_to_ru_uses_phrases_dialect_replacements_and_exceptions(monkeypatch):
    g = glossary()
    monkeypatch.setattr(engine_module, "translit_word", lambda word, _lang: f"<${word}>")
    assert g.to_ru("ciao, GATTO!") == "чао, гатто!"
    assert g.to_ru("caro", dialect=True) == "амико"
    assert g.to_ru("caro", dialect=False) == "<$caro>"
    assert g.to_ru("readme") == "ридми"
    assert g.to_ru("mystery") == "<$mystery>"
    assert g.to_ru("ma dai") == "ма дай"
    no_reading = Glossary({"phrases": {}}, "ja")
    assert no_reading.reading is False
    assert no_reading.to_ru("こんにちは") == "こんにちは"


def test_glossary_phrase_lookup_longest_match_and_plural_fallback():
    g = glossary(
        {
            "phrases": {
                "buona": "буона | хорошо",
                "buona sera": "буона сера | добрый вечер",
                "hello": "хелло | привет",
            }
        }
    )
    assert g.phrase_keys("добрый вечер привет") == [
        (0, 12, norm("buona sera")),
        (13, 19, norm("hello")),
    ]
    assert g.find_meaning("приветте") == norm("hello")
    assert g.find_meaning("неизвестно") is None


def test_load_glossary_data_creates_defaults_and_backs_up_corrupt_files(tmp_path, monkeypatch):
    directory = tmp_path / "glossaries"
    monkeypatch.setattr(engine_module, "GLOSSARY_DIR", directory)
    monkeypatch.setattr(engine_module, "GLOSSARY_PATH", tmp_path / "glossary.json")
    monkeypatch.setattr(engine_module, "get_pack", lambda _lang: PACK)
    path = directory / "it.json"

    first = load_glossary_data("it")
    assert first["_lang"] == "it"
    assert first["_version"] == 2
    assert first["_fillers"] == [{"target": "ma dai", "ru": ["ну давай"]}]
    assert json.loads(path.read_text(encoding="utf-8"))["_lang"] == "it"

    path.write_text("not-json", encoding="utf-8")
    recovered = load_glossary_data("it")
    assert recovered["phrases"]["ciao"] == PACK["phrases"]["ciao"]
    assert (directory / "it.bak.json").read_text(encoding="utf-8") == "not-json"


def test_load_glossary_data_migrates_old_versions_and_section_names(tmp_path, monkeypatch):
    directory = tmp_path / "glossaries"
    directory.mkdir()
    monkeypatch.setattr(engine_module, "GLOSSARY_DIR", directory)
    monkeypatch.setattr(engine_module, "GLOSSARY_PATH", tmp_path / "legacy.json")
    monkeypatch.setattr(engine_module, "get_pack", lambda _lang: PACK)
    monkeypatch.setattr(engine_module, "_migrate_old_glossary", lambda: None)
    path = directory / "it.json"
    path.write_text(
        json.dumps(
            {
                "_version": 1,
                "phrases": {"ciao": "моё чтение | привет"},
                "it_replace": {"my": "ciao"},
            }
        ),
        encoding="utf-8",
    )

    loaded = load_glossary_data("it")
    assert loaded["phrases"]["ciao"] == "моё чтение | привет"
    assert loaded["phrases"]["gatto"] == PACK["phrases"]["gatto"]
    assert loaded["replace"]["my"] == "ciao"
    assert (directory / "it.v1.bak.json").exists()


def test_glossary_migration_save_reset_and_disabled_module(tmp_path, monkeypatch):
    directory = tmp_path / "glossaries"
    legacy = tmp_path / "glossary.json"
    legacy.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(engine_module, "GLOSSARY_DIR", directory)
    monkeypatch.setattr(engine_module, "GLOSSARY_PATH", legacy)
    monkeypatch.setattr(engine_module, "get_pack", lambda _lang: PACK)
    engine_module._migrate_old_glossary()
    assert (directory / "it.json").read_text(encoding="utf-8") == "{}"
    engine_module._migrate_old_glossary()
    assert (directory / "it.json").read_text(encoding="utf-8") == "{}"

    data = reset_glossary("it")
    assert data["_lang"] == "it"
    assert data["_fillers"] == [{"target": "ma dai", "ru": ["ну давай"]}]
    assert save_glossary_data("it", {"phrases": {"ciao": "ok"}}) is True
    assert json.loads((directory / "it.json").read_text(encoding="utf-8"))["_lang"] == "it"
    monkeypatch.setattr(engine_module.modules, "is_enabled", lambda *_args: False)
    empty = load_glossary("it", cfg={})
    assert empty.phrases == {}


def test_save_glossary_reports_oserror_and_migration_tolerates_read_only_paths(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setattr(engine_module, "GLOSSARY_DIR", tmp_path / "glossaries")
    monkeypatch.setattr(
        engine_module, "write_json", lambda *_args: (_ for _ in ()).throw(OSError("no disk"))
    )
    assert save_glossary_data("it", {}) is False
    assert "Не удалось сохранить словарь" in caplog.text

    class BrokenPath:
        def mkdir(self, **_kwargs):
            raise OSError("read only")

    monkeypatch.setattr(engine_module, "GLOSSARY_DIR", BrokenPath())
    engine_module._migrate_old_glossary()


def test_engine_syncs_directions_guards_modules_and_segments_glossary_text(monkeypatch):
    engine, translator = make_engine()
    monkeypatch.setattr(engine_module.modules, "is_enabled", lambda _cfg, key: key != "translator")
    engine._sync_direction(False)
    engine._sync_direction(True)
    assert translator.directions == ["out", "in"]
    assert engine._translate("private") == "private"
    assert engine._slang_on() is True

    assert engine.segment("привет", cap=True) == ("Чао", "ciao")
    assert engine.segment("ciao!", cap=False) == ("чао!", "ciao!")


def test_engine_segment_translates_russian_and_uses_dictionary_meaning(monkeypatch):
    engine, translator = make_engine(translator=TranslatorStub(lambda text: f"ciao {text}"))
    monkeypatch.setattr(engine_module.modules, "is_enabled", lambda _cfg, key: key != "slang")
    monkeypatch.setattr(engine.g, "to_ru", lambda text, dialect=False: f"ru:{text}")
    assert engine.segment("  незнакомо! ") == ("ru:ciao незнакомо!", "ciao незнакомо!")
    assert translator.calls == ["незнакомо"]
    assert engine.segment("доброе утро") == ("буонджорно", "buongiorno")
    assert engine.segment(", , ") == ("", "")


def test_engine_process_handles_markers_actions_auto_and_nonmessage_commands(monkeypatch):
    engine, translator = make_engine()
    monkeypatch.setattr(engine, "segment", lambda text, cap=False: (f"RU({text})", f"IT({text})"))
    monkeypatch.setattr(engine_module.modules, "is_enabled", lambda _cfg, _key: False)

    marked = engine.process("/to Alex +hello+ *waves*", auto=True, seed=2)
    assert marked == Result("/to Alex RU(hello) *waves*", "/to Alex IT(hello) *waves*", True)
    assert translator.directions == ["out"]

    service = engine.process("/me *waves* hello", auto=True)
    assert service.translated is False
    assert service.text == "/me *waves* hello"
    assert engine.process("no translation", auto=False).translated is False


def test_engine_process_applies_automatic_markers_and_filler_behavior(monkeypatch):
    engine, _translator = make_engine()
    monkeypatch.setattr(engine, "segment", lambda text, cap=False: ("R", "T"))
    monkeypatch.setattr(engine_module.modules, "is_enabled", lambda _cfg, _key: False)
    result = engine.process("привет мир", auto=True, seed=0.5)
    assert result.translated is True
    assert result.text.count("R") == 1
    assert result.native.count("T") == 1

    cfg = {**CFG, "filler_always": True}
    engine, _ = make_engine(cfg=cfg)
    monkeypatch.setattr(engine, "segment", lambda text, cap=False: (f"RU:{text}", f"IT:{text}"))
    filler = engine.process("ну давай")
    assert filler.translated is True
    assert "RU:ну давай" in filler.text

    with_action = engine.process("*ну давай* ну давай")
    assert with_action.text == "*ну давай* RU:ну давай"
    assert with_action.native == "*ну давай* IT:ну давай"


def test_engine_full_mode_translates_commands_and_preserves_target_prefix(monkeypatch):
    engine, translator = make_engine(translator=TranslatorStub(lambda text: f"it:{text}"))
    monkeypatch.setattr(engine_module.modules, "is_enabled", lambda _cfg, key: key != "glossary")
    result = engine.process_full("/to Alex  hello  ")
    assert result == Result("/to Alex  it:hello", "/to Alex  it:hello", True)
    assert translator.calls == ["hello"]
    assert engine.process_full("  ") == Result("", "", False)


def test_full_part_preserves_known_phrases_spacing_and_untranslated_unicode(monkeypatch):
    engine, translator = make_engine(translator=TranslatorStub(lambda text: f"it:{text.strip()}"))
    monkeypatch.setattr(
        engine_module.modules,
        "is_enabled",
        lambda _cfg, key: key in {"glossary", "translator"},
    )
    assert (
        engine._full_part(" привет добрый вечер мир ", slang_on=False) == " ciao buona sera it:мир "
    )
    assert engine._full_part(" 你好 ", slang_on=False) == "it:你好"
    assert engine._full_part("  ", slang_on=False) == "  "
    assert translator.calls == [" мир ", " 你好 "]


def test_full_part_uses_slang_and_bypasses_glossary_when_disabled(monkeypatch):
    engine, translator = make_engine()
    monkeypatch.setattr(engine_module.modules, "is_enabled", lambda _cfg, key: key == "translator")
    monkeypatch.setattr(
        engine_module.slang, "expand_russian", lambda text: (f"expanded:{text}", [])
    )
    assert engine._full_part("слово", slang_on=True) == "tr:expanded:слово"
    assert engine._full_part("word", slang_on=False) == "tr:word"
    assert engine._full_part("   ", slang_on=True) == "   "


def test_process_in_keeps_commands_translates_actions_and_restores_slang(monkeypatch):
    translator = TranslatorStub(
        lambda text: {"hello": "hola", "wave": "saluda", "again": "otra"}.get(text.strip(), "")
    )
    engine, _ = make_engine(translator=translator)
    monkeypatch.setattr(engine_module.modules, "is_enabled", lambda _cfg, key: key == "translator")
    monkeypatch.setattr(
        engine_module.slang, "expand_any", lambda text: (text.replace("brb", "be right back"), [])
    )
    monkeypatch.setattr(
        engine_module.slang, "restore_any", lambda text: (text.replace("gg", "bien jugado"), [])
    )

    result = engine.process_in("/to Alice hello *wave* again")
    assert result.text == "/to Alice hola *saluda* otra"
    assert result.native == "hello *wave* again"
    assert translator.directions[-1] == "in"
    assert translator.calls == ["hello ", "wave", " again"]
    assert engine.process_in("") == Result("", "", False)


def test_direction_setter_errors_are_logged_and_do_not_interrupt(caplog):
    class BadDirection:
        def set_direction(self, _direction):
            raise RuntimeError("not available")

    engine = Engine(CFG, glossary(), BadDirection())
    engine._sync_direction(True)
    assert "Не удалось переключить направление" in caplog.text
