"""Autocomplete suggestions for animation keywords.

Contains message-family filtering, suggestion ranking and text completion,
separate from the animation playback runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app import morph
from app.anims_rules import (
    MODE_ACTIONS,
    MODE_ALWAYS,
    MODE_EMOTES,
    Rule,
    _WORD_RE,
    _words_of,
    keywords_of,
)

# ---------------------------------------------------------------- режимы чтения
MODE_FAMILY_ALWAYS = "always"
MODE_FAMILY_EMOTES = "emotes"
MODE_FAMILY_ACTIONS = "actions"
MODE_FAMILY_MESSAGES = "messages"


def message_family(text: str) -> str:
    """Какой вид сообщения набирает игрок: обычное, /me или между звёздочками.

    What kind of message the player is typing: plain, /me, or between asterisks.

    Смотрится только начало строки и незакрытая звёздочка — этого хватает,
    чтобы подсказывать только те ключи, которые в таком сообщении сработают.
    Only the start of the line and an unclosed asterisk are looked at — enough to
    suggest only the keywords that would fire in that kind of message.
    """
    low = (text or "").lstrip().casefold()
    if low.startswith(("/me", "/ame", "/melow", "/melong")):
        return MODE_FAMILY_EMOTES
    if (text or "").count("*") % 2 == 1:
        return MODE_FAMILY_ACTIONS
    return MODE_FAMILY_MESSAGES


def family_of_mode(mode: int) -> str:
    """Режим правила -> вид сообщения / a rule mode -> the message family."""
    mode = int(mode)
    if mode == MODE_ALWAYS:
        return MODE_FAMILY_ALWAYS
    if mode == MODE_EMOTES:
        return MODE_FAMILY_EMOTES
    if mode == MODE_ACTIONS:
        return MODE_FAMILY_ACTIONS
    return MODE_FAMILY_MESSAGES


def family_hits(mode: int, family: str, has_action: bool = False) -> bool:
    """Сработает ли правило такого режима в сообщении такого вида.

    Would a rule of that mode fire in a message of that family.

    Если в тексте есть действие *...* (или незакрытая звёздочка), подходят и
    обычные, и «только *…*» правила: слово между звёздочками считается и там,
    и там. Если звёзд нет — «только *…*» не срабатывает на обычные слова.
    If the text contains an action *...* (or an unclosed asterisk), both plain
    and "only *…*" rules fit: a word between asterisks counts there as well.
    Without asterisks, "only *…*" does not fire on plain words.
    """
    rule_family = family_of_mode(mode)
    if rule_family == MODE_FAMILY_ALWAYS:
        return True
    if rule_family == family:
        return True
    if has_action and rule_family in (MODE_FAMILY_ACTIONS, MODE_FAMILY_MESSAGES):
        return True
    return False


@dataclass
class Hint:
    """Одно предложение подсказки / one suggestion.

    ``keyword`` — что подставляется в текст, ``rule`` — чьё это слово,
    ``label`` — как это назвать игроку (название анимации).
    ``keyword`` is what goes into the text, ``rule`` is its owner and ``label``
    is how the animation is called for the player.
    """

    keyword: str
    rule: "Rule"
    label: str = ""
    playing: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "keyword": self.keyword,
            "label": self.label,
            "name": self.rule.name,
            "playing": self.playing,
        }


def current_word(text: str) -> str:
    """Слово, которое набирается прямо сейчас (после последней границы).

    The word being typed right now (everything after the last boundary).
    """
    tail = ""
    for match in _WORD_RE.finditer(text or ""):
        tail = match.group(0)
    return tail


def _stem_word(word: str) -> str:
    """Основа набранного слова: «опёрся» и «опёрлась» должны совпасть.

    The stem of the typed word: «опёрся» and «опёрлась» have to meet.
    """
    return morph.stem(morph.norm(word)) if word else ""


def suggestions(rules: Iterable["Rule"], text: str, limit: int = 8) -> list[Hint]:
    """Подсказки ключевых слов по тому, что игрок уже набрал.

    Keyword suggestions for what the player has typed so far.

    Совпадение считается по началу слова, а не по содержанию: игрок набирает
    ключ с начала, и «опё» должно предлагать «опёрся», а не «приопёрся».
    Сначала идут ключи, которые начинаются с набранного, потом — те, у которых
    совпала основа («опёрлась» при наборе «опёрся»). Внутри группы порядок —
    как в таблице правил, то есть как игрок сам его расставил.

    Matching is by the start of a word, not by containment: the player types a
    keyword from its beginning, so «опё» must offer «опёрся», never «приопёрся».
    Keywords starting with what is typed come first, then those whose stem
    matches («опёрлась» while typing «опёрся»). Inside a group the order follows
    the rule table — the order the player arranged.
    """
    tail = current_word(text)
    need = morph.norm(tail)
    if not need:
        return []
    family = message_family(text)
    # есть действие *...* — и обычные, и «только *…*» правила могут сработать
    # there's an action *...* — both plain and "only *…*" rules can fire
    has_action = "*" in (text or "")
    stem_need = _stem_word(tail)
    starts: list[Hint] = []
    stems: list[Hint] = []
    seen: set[str] = set()
    for rule in rules:
        if not rule.ready():
            continue
        if not family_hits(rule.mode, family, has_action):
            continue
        names = [choice.label() for choice in rule.variant_list()] or [rule.name]
        label = " / ".join(name for name in names if name)[:60]
        for keyword in keywords_of(rule.keywords):
            low = " ".join(keyword.casefold().split())
            if not low or low in seen:
                continue
            first = _words_of(keyword)
            if not first:
                continue
            word = first[0][2]
            here = morph.norm(word)
            if here.startswith(need):
                seen.add(low)
                starts.append(Hint(keyword, rule, label))
            elif stem_need and _stem_word(word) == stem_need and len(need) >= 3:
                seen.add(low)
                stems.append(Hint(keyword, rule, label))
    found = starts + stems
    return found[: max(1, int(limit))]


def complete(text: str, hint: "Hint | None") -> tuple[str, int]:
    """Дописать текст выбранной подсказкой; вернуть текст и новую каретку.

    Finish the text with the chosen suggestion; return the text and the caret.

    Меняется только последнее набираемое слово, всё, что было до него, остаётся
    как есть. Если ключ уже набран целиком, текст не меняется — Enter отправит
    его как обычно.
    Only the word being typed is replaced; everything before it stays as it was.
    If the keyword is already complete the text is left alone, and Enter sends it
    as usual.
    """
    source = text or ""
    if hint is None:
        return source, len(source)
    matches = list(_WORD_RE.finditer(source))
    begin = matches[-1].start() if matches else len(source)
    # кавычки и звёздочки перед словом не съедаем: «*опёр» -> «*опёрся»
    # the quotes and asterisks before the word stay: «*опёр» -> «*опёрся»
    done = source[:begin] + hint.keyword
    return done, len(done)
