"""Focused tests for animation rule parsing, validation, matching, and storage."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import morph  # noqa: E402
from app.anims_rules import (  # noqa: E402
    MAX_CHOICES,
    MODE_ACTIONS,
    MODE_ALWAYS,
    MODE_EMOTES,
    MODE_MESSAGES,
    VAL_BAD_MODE,
    VAL_BAD_MS,
    VAL_BAD_NAME,
    VAL_EMPTY_KEYWORD,
    VAL_EMPTY_NAME,
    VAL_TOO_MANY_CHOICES,
    Choice,
    Context,
    Rule,
    _same_rule,
    action_spans,
    analysed_spans,
    keywords_of,
    merge_choices,
    merge_keywords,
    merge_rules,
    parse_message_span,
    rules_from_cfg,
    rules_to_cfg,
    select_spans,
)


def test_message_command_parsing_keeps_offsets_and_drops_recipients():
    assert parse_message_span("hello world") == ("", "hello world", 0)
    command, body, offset = parse_message_span("/TO Alice hello")
    assert command == "/to"
    assert body == "hello"
    assert offset == len("/TO Alice ")
    assert parse_message_span("/to")[1:] == ("", len("/to"))


def test_action_spans_trim_content_and_keep_original_offsets():
    assert action_spans("before * waves * after *leaves*", shift=4) == [
        (13, "waves"),
        (28, "leaves"),
    ]


def test_analyzed_spans_respect_each_message_mode():
    assert analysed_spans("hello", MODE_ALWAYS) == [(0, "hello")]
    assert analysed_spans("hello *waves*", MODE_ACTIONS) == [(7, "waves")]
    assert analysed_spans("/me waves *smiles*", MODE_EMOTES) == [
        (4, "waves *smiles*"),
        (11, "smiles"),
    ]
    assert analysed_spans("hello *waves*", MODE_MESSAGES) == [
        (0, "hello *waves*"),
        (7, "waves"),
    ]
    assert analysed_spans("/me hello", MODE_MESSAGES) == []
    assert analysed_spans("/to Bob hello", MODE_MESSAGES) == [(8, "hello")]
    assert analysed_spans("hello", MODE_EMOTES) == []
    assert analysed_spans("hello", 999) == []


def test_keywords_split_on_separators_and_ignore_empty_parts():
    assert keywords_of("  first ; second,,\n third ") == ["first", "second", "third"]
    assert keywords_of(" ; , \n ") == []
    assert keywords_of(None) == []


def test_selection_removes_nested_spans_and_duplicate_keyword_hits():
    candidates = [
        (0, 4, (0, 0)),
        (0, 10, (1, 0)),
        (20, 25, (0, 1)),
        (30, 34, (0, 0)),
        (31, 33, (3, 0)),
        (40, 43, (2, 0)),
        (50, 53, (2, 0)),
    ]
    assert select_spans(candidates) == [
        (0, 10, (1, 0)),
        (20, 25, (0, 1)),
        (30, 34, (0, 0)),
        (40, 43, (2, 0)),
    ]


def test_context_equivalence_and_phrase_cache_are_failure_safe():
    calls = []
    context = Context(
        equivalent=lambda phrase: calls.append(phrase) or 17,
        text_keys=lambda text: [(0, len(text), "key")],
    )
    assert context.key_of("term") == "17"
    assert context.phrases("sample") == [(0, 6, "key")]
    assert context.phrases("sample") == [(0, 6, "key")]
    assert calls == ["term"]

    broken_equivalent = Context(equivalent=lambda _phrase: 1 / 0)
    broken_phrases = Context(text_keys=lambda _text: 1 / 0)
    assert broken_equivalent.key_of("x") == ""
    assert broken_phrases.phrases("x") == []
    assert broken_phrases.phrases("x") == []


def test_choice_label_validation_and_config_round_trip():
    assert Choice(name=" anim_wave ").label() == "anim_wave"
    assert Choice(title=" Wave ", name="anim_wave").label() == "Wave"
    assert Choice().problem() == VAL_EMPTY_NAME
    assert Choice(name="bad/name").problem() == VAL_BAD_NAME

    choice = Choice.from_dict(
        {
            "name": "/anim_wave",
            "title": " Wave ",
            "description": " Description ",
            "group": " Standing ",
        }
    )
    assert choice == Choice("anim_wave", "Wave", "Description", "Standing")
    assert Choice.from_dict(" /anim_idle ") == Choice(name="anim_idle")
    assert Choice.from_dict("  ") is None
    assert Choice.from_dict(None) is None
    assert Choice.from_dict({"title": "orphan"}) is None
    assert choice.to_dict() == {
        "name": "anim_wave",
        "title": "Wave",
        "description": "Description",
        "group": "Standing",
    }


def test_rule_validation_checks_fields_in_order_and_accepts_valid_choice_rule():
    assert Rule().problem() == VAL_EMPTY_KEYWORD
    assert Rule(keywords="hello").problem() == VAL_EMPTY_NAME
    assert Rule(keywords="hello", name="two words").problem() == VAL_BAD_NAME
    assert Rule(keywords="hello", name="wave", duration_ms=-1).problem() == VAL_BAD_MS
    assert Rule(keywords="hello", name="wave", duration_ms=1.5).problem() == VAL_BAD_MS
    assert Rule(keywords="hello", name="wave", mode=999).problem() == VAL_BAD_MODE
    assert Rule(keywords="hello", choices=[Choice()]).problem() == VAL_EMPTY_NAME

    too_many = [Choice(name=f"anim_{index}") for index in range(MAX_CHOICES + 1)]
    assert Rule(keywords="hello", choices=too_many).problem() == VAL_TOO_MANY_CHOICES
    assert Rule(keywords="hello", choices=[Choice(name="anim_wave")]).problem() == ""
    assert Rule(keywords="hello", name="wave").ready() is True
    assert Rule(keywords="hello", name="wave", enabled=False).ready() is False


def test_rule_variants_and_choice_requirement():
    plain = Rule(keywords="hello", name=" wave ")
    assert plain.variant_list() == [Choice(name="wave")]
    assert plain.needs_choice() is False
    assert Rule().variant_list() == []

    variants = [Choice(name="anim_one"), Choice(name="anim_two")]
    rule = Rule(keywords="hello", choices=variants)
    assert rule.variant_list() == variants
    assert rule.variant_list() is not variants
    assert rule.needs_choice() is True


def test_rule_candidates_skip_disabled_empty_and_non_word_keywords():
    assert Rule(keywords="hello", name="wave", enabled=False).candidates("hello") == []
    assert Rule(keywords=" ; ", name="wave").candidates("hello") == []
    assert Rule(keywords="***", name="wave").candidates("hello") == []


def test_rule_hits_deduplicate_each_keyword_but_keep_distinct_keywords():
    rule = Rule(keywords="hello; bye", name="wave", forms=morph.FORMS_EXACT)
    assert rule.candidates("hello") == [(0, 5, 0)]
    assert rule.hits("bye then hello, hello") == [(0, "bye"), (9, "hello")]
    assert rule.scan("bye then hello, hello") == (["bye", "hello"], [0, 9])
    assert rule.matches("none here") == []


def test_rule_selection_prefers_long_phrase_and_respects_exact_form():
    rule = Rule(keywords="stand; stand up", name="wave", forms=morph.FORMS_EXACT)
    assert rule.spans("stand up") == [(0, 8, "stand up")]
    assert rule.spans("stand very up") == [(0, 5, "stand")]


def test_negation_is_limited_by_punctuation_and_keyword_can_contain_negation():
    rule = Rule(keywords="open", name="wave", forms=morph.FORMS_EXACT)
    assert rule.matches("not open") == []
    assert rule.matches("not, open") == ["open"]
    assert Rule(keywords="not open", name="wave", forms=morph.FORMS_EXACT).matches("not open") == [
        "not open"
    ]
    assert Rule(keywords="open", name="wave", forms=morph.FORMS_EXACT).matches(
        "not open", Context(negation=False)
    ) == ["open"]


def test_rule_synonym_matching_and_context_caching():
    phrase_calls = []
    context = Context(
        equivalent=lambda phrase: "hello-key" if phrase == "hello" else "",
        text_keys=lambda text: phrase_calls.append(text) or [(0, 2, "hello-key")],
    )
    rule = Rule(keywords="hello", name="wave", forms=morph.FORMS_EXACT)
    assert rule.spans("hi", context) == [(0, 2, "hi")]
    assert rule.spans("hi", context) == [(0, 2, "hi")]
    assert phrase_calls == ["hi"]
    assert rule.matches("hello", context) == ["hello"]


def test_synonym_offsets_and_negation_are_respected():
    rule = Rule(keywords="hello", name="wave", forms=morph.FORMS_EXACT)
    mismatched_key = Context(
        equivalent=lambda _phrase: "wanted",
        text_keys=lambda text: [(0, len(text), "other")],
    )
    missing_offset = Context(
        equivalent=lambda _phrase: "wanted",
        text_keys=lambda text: [(len(text) + 1, len(text) + 2, "wanted")],
    )
    negated = Context(
        equivalent=lambda _phrase: "wanted",
        text_keys=lambda _text: [(4, 6, "wanted")],
    )

    assert rule.matches("hi", mismatched_key) == []
    assert rule.matches("hi", missing_offset) == []
    assert rule.matches("not hi", negated) == []


def test_rule_serialization_repairs_invalid_legacy_values_and_round_trips():
    legacy = Rule.from_dict(
        {
            "keywords": " hello ",
            "name": "/anim_wave",
            "mode": 5,
            "forms": "bad",
            "duration_ms": "bad",
            "choices": ["anim_one", None, {"name": "anim_two", "title": "Two"}],
        }
    )
    assert legacy.mode == MODE_ALWAYS
    assert legacy.name == "anim_wave"
    assert legacy.forms == morph.FORMS_DEFAULT
    assert legacy.duration_ms == 3000
    assert [choice.name for choice in legacy.choices] == ["anim_one", "anim_two"]
    assert Rule.from_dict({"mode": 999, "forms": 999, "duration_ms": 999999}).mode == MODE_ALWAYS
    assert Rule.from_dict({"mode": 999, "forms": 999, "duration_ms": 999999}).duration_ms == 600000

    encoded = legacy.to_dict()
    assert Rule.from_dict(encoded) == legacy
    assert rules_to_cfg([legacy]) == [encoded]
    assert [rule.name for rule in rules_from_cfg({"anim_rules": [encoded, legacy, "bad"]})] == [
        "anim_wave",
        "anim_wave",
    ]
    assert rules_from_cfg({"anim_rules": "not a list"}) == []


def test_same_rule_requires_matching_identifier_and_keywords():
    first = Rule(keywords="hello", name="wave", id="stable")
    same = Rule(keywords="hello", name="other", id="stable")
    changed = Rule(keywords="bye", name="wave", id="stable")
    different = Rule(keywords="hello", name="wave", id="different")

    assert _same_rule(first, same) is True
    assert _same_rule(first, changed) is False
    assert _same_rule(first, different) is False


def test_merge_helpers_deduplicate_and_report_disagreements():
    assert merge_keywords("Hello, Bye", "hello;  bye; Again") == "Hello, Bye, Again"
    merged_choices = merge_choices(
        [Choice(name="/anim_one"), Choice(name="anim_one", title="ignored")],
        [Choice(name="anim_two"), Choice()],
    )
    assert [choice.name for choice in merged_choices] == ["/anim_one", "anim_two"]

    first = Rule(
        keywords="hello; bye",
        name="wave",
        duration_ms=1000,
        loop=True,
        mode=MODE_MESSAGES,
        choices=[Choice(name="anim_one")],
    )
    second = Rule(
        keywords="HELLO; again",
        name="wave2",
        duration_ms=2000,
        loop=False,
        mode=MODE_ACTIONS,
        forms=morph.FORMS_EXACT,
        choices=[Choice(name="anim_two")],
        enabled=False,
    )
    merged, unresolved = merge_rules(first, second)
    assert merged.keywords == "hello, bye, again"
    assert merged.duration_ms == 0
    assert merged.loop is False
    assert merged.enabled is False
    assert merged.mode == MODE_ALWAYS
    assert [choice.name for choice in merged.choices] == ["anim_one", "anim_two"]
    assert unresolved == ["duration_ms", "loop", "forms", "mode"]

    same, unresolved_same = merge_rules(first, first)
    assert same.duration_ms == first.duration_ms
    assert same.mode == first.mode
    assert same.loop is True
    assert unresolved_same == []
