"""Animation-rule models, message matching and config serialization.

This module owns the deterministic domain logic. It has no GUI or runtime
scheduler dependencies, so it can be tested and maintained independently from
the animation playback engine in :mod:`app.anims`.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Callable, Iterable, Mapping

from app import morph
from app.config import log

# Rule modes, parsing, matching, models and config conversion.

MODE_ALWAYS = 1  # любое сообщение / any message
MODE_EMOTES = 2  # только /me, /ame, /melow, /melong
MODE_ACTIONS = 3  # только текст между *звёздочками* / only *between asterisks*
MODE_MESSAGES = 4  # обычные сообщения и /to, /lto, /l, /s, /w, /wt

MODES: tuple[int, ...] = (MODE_ALWAYS, MODE_EMOTES, MODE_ACTIONS, MODE_MESSAGES)

# Режим 5 («Команды и сообщения») убран как лишний: он целиком покрывается
# режимом 1 «Всегда», и старые правила переводятся туда.
# Mode 5 ("Commands and messages") is gone as redundant: mode 1 "Always" covers
# it entirely, and old rules are migrated there.
LEGACY_MODES: dict[int, int] = {5: MODE_ALWAYS}

# Короткие названия идут в выпадающий список: они должны умещаться в столбце
# даже на узком окне. Полное объяснение — в подсказке поля.
# Short titles go into the combo box: they must fit the column even in a narrow
# window. The full explanation lives in the field tooltip.
MODE_TITLES_RU: dict[int, str] = {
    MODE_ALWAYS: "Всегда",
    MODE_EMOTES: "Действия: /me и *…*",
    MODE_ACTIONS: "Только *…*",
    MODE_MESSAGES: "Сообщения и /to, /l",
}

MODE_TITLES_EN: dict[int, str] = {
    MODE_ALWAYS: "Always",
    MODE_EMOTES: "Actions: /me and *…*",
    MODE_ACTIONS: "Only *…*",
    MODE_MESSAGES: "Messages and /to, /l",
}

# Полные объяснения режимов — для подсказки поля «Режим».
# Full explanations of the modes — for the "Mode" field tooltip.
MODE_HINTS_RU: dict[int, str] = {
    MODE_ALWAYS: "Любое сообщение целиком: и обычное, и команда, и *действия*.",
    MODE_EMOTES: "Действия: команды /me, /ame, /melow, /melong и текст между "
    "*звёздочками* в любом сообщении.",
    MODE_ACTIONS: "Только текст между *звёздочками*; обычные слова не считаются.",
    MODE_MESSAGES: "Обычные сообщения (вместе с *действиями* внутри них) и команды "
    "/to, /lto, /l, /s, /w, /wt. Команды /me не считаются.",
}

MODE_HINTS_EN: dict[int, str] = {
    MODE_ALWAYS: "The whole message: plain text, commands and *actions* alike.",
    MODE_EMOTES: "Actions: the /me, /ame, /melow, /melong commands and any text "
    "*between asterisks*.",
    MODE_ACTIONS: "Only the text between *asterisks*; plain words do not count.",
    MODE_MESSAGES: "Plain messages (with the *actions* inside them) and the /to, "
    "/lto, /l, /s, /w, /wt commands. /me commands do not count.",
}

# команды, где текст идёт после самой команды
# commands whose text follows the command itself
EMOTE_COMMANDS = ("/me", "/ame", "/melow", "/melong")
# «настоящие сообщения»: обычный текст и эти команды
# "real messages": plain text and these commands
TALK_COMMANDS = ("/to", "/lto", "/l", "/s", "/w", "/wt")
# у этих команд первым словом идёт получатель, его анализировать нельзя
# these commands start with a recipient, which must not be analysed
NICK_COMMANDS = ("/to", "/lto")

# Маркеры отрицания: если такой стоит перед найденным словом, правило молчит.
# Ключ, в котором отрицание уже есть («не открыл зонт»), проверку выключает.
# Negation markers: one of them right before a matched word silences the rule.
# A keyword that already carries a negation switches the check off.
NEG_MARKERS = frozenset(
    {
        "не",
        "ни",
        "нет",
        "нельзя",
        "нечем",
        "некого",
        "нечего",
        "незачем",
        "никуда",
        "никто",
        "ничего",
        "никогда",
        "нигде",
        "никак",
        "ничуть",
        "not",
        "never",
        "nobody",
        "nothing",
        "nowhere",
        "neither",
        "nor",
    }
)
NEG_LOOKBACK = 3  # сколько слов смотрим перед найденным / words looked back
_PUNCT_RE = re.compile(r"[.,;:!?…—–]")  # граница куска: дальше отрицание не ищем

# 0 мс — особый случай: анимацию не останавливаем вовсе
# 0 ms is a special case: the animation is never stopped
MIN_MS, MAX_MS, DEFAULT_MS = 0, 600000, 3000
MAX_QUEUE = 20  # больше — очередь не растёт, лишнее отбрасывается
# Хвост после анимации: сколько добавить к её собственному времени проигрывания,
# прежде чем запустить следующую из очереди. Отсчёт идёт от отправки `/anim`,
# то есть «проиграла 1500 мс + 50 мс — играет следующая». Задача хвоста — дать
# игре закрыть чат после остановки и серверу принять новую команду.
# The tail after an animation: how much to add to its own play time before the
# next one in the queue starts. The count starts at the `/anim` send, so "played
# 1500 ms + 50 ms, then the next one plays". The tail gives the game time to close
# its chat after the stop and the server time to take the new command.
ANIM_EXTRA_MS = 50
MAX_EXTRA_MS = 10000  # больше ставить бессмысленно / a longer tail makes no sense

_CMD_RE = re.compile(r"^\s*(/\S+)\s*")
_NICK_RE = re.compile(r"\s*\S+\s+")  # получатель в /to и /lto / the recipient
_ACTION_RE = re.compile(r"\*([^*]+)\*")
_WORD_RE = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", re.UNICODE)  # слова с позициями

# Варианты одной анимации: ключ один, а /anim из него — несколько.
# Названия и описания задаются в интерфейсе (ПКМ по правилу) и нужны для
# оверлея выбора: игрок видит не «anim_counterleanbar», а «Опёрся на стойку —
# Стоит, опершись локтями на барную стойку».
# Variants of one animation: one keyword, several /anim commands. The titles and
# descriptions are set in the interface (right-click a rule) and feed the chooser
# overlay, so the player sees a human name instead of «anim_counterleanbar».
MAX_CHOICES = 12  # больше вариантов в оверлее не поместится / the chooser fits no more
MAX_TITLE = 60  # длина названия варианта / the variant title length
MAX_DESC = 300  # длина описания варианта / the variant description length
# разделители ключевых слов правила / the rule keyword separators
_KEYWORD_SPLIT_RE = re.compile(r"[,;\n]+")

MAX_GROUP = 40  # длина названия группы / the group title length

VAL_EMPTY_KEYWORD = "ключевое слово не задано"
VAL_EMPTY_NAME = "название анимации не задано"
VAL_BAD_NAME = "в названии анимации не должно быть пробелов и косых черт"
VAL_BAD_MS = "длительность должна быть от 0 до 600000 мс"
VAL_BAD_MODE = "такой режим считывания не поддерживается"
VAL_TOO_MANY_CHOICES = f"вариантов анимации не может быть больше {MAX_CHOICES}"
# в словаре перевода ключ — ровно эта строка с числом
# the translation key is exactly this string, the number included


# ------------------------------------------------------------------- разбор
def parse_message_span(text: str) -> tuple[str, str, int]:
    """Команда, её текст и смещение текста в сообщении.

    The command, its text and the offset of that text inside the message.

    У `/to` и `/lto` первым словом идёт получатель — он отбрасывается, как это
    уже делает движок перевода. Смещение нужно, чтобы сравнивать позиции слов из
    разных сообщений и команд.
    With `/to` and `/lto` the first word is the recipient, which is dropped just
    like the translation engine does. The offset makes positions comparable
    between plain messages and commands.
    """
    source = text or ""
    match = _CMD_RE.match(source)
    if not match:
        return "", source, 0
    command = match.group(1).lower()
    start = match.end()
    body = source[start:]
    if command in NICK_COMMANDS:
        nick = _NICK_RE.match(body)
        if nick is None:
            return command, "", len(source)
        start += nick.end()
        body = body[nick.end() :]
    return command, body, start


def action_spans(text: str, shift: int = 0) -> list[tuple[int, str]]:
    """Куски между звёздочками и их смещения: «*машет* и *уходит*» -> два.

    The pieces between asterisks and their offsets: «*машет* и *уходит*» -> two.
    """
    spans = []
    for match in _ACTION_RE.finditer(text or ""):
        raw = match.group(1)
        lead = len(raw) - len(raw.lstrip())
        spans.append((shift + match.start(1) + lead, raw.strip()))
    return spans


def _with_actions(spans: list[tuple[int, str]], text: str, start: int) -> list[tuple[int, str]]:
    """Текст сообщения плюс всё, что стоит между звёздочками, со смещениями.

    The message text plus everything *between asterisks*, with offsets. Действия
    в ролевой игре — такая же часть сообщения, поэтому в режимах «действий» и
    «сообщений» они читаются вместе с обычными словами.
    Actions are just another part of an RP message, so the action and message
    modes read them together with the plain words.
    """
    chunks = [(offset, part) for offset, part in spans if (part or "").strip()]
    chunks.extend(action_spans(text, start))
    return chunks


def analysed_spans(text: str, mode: int) -> list[tuple[int, str]]:
    """Что проверять в этом режиме и где это стоит в сообщении.

    Which pieces to check in this mode and where they sit in the message.

    Смещение — то, что ставит анимации в порядок слов: сначала срабатывает
    правило, чьё ключевое слово встретилось раньше.
    The offset is what puts animations in word order: the rule whose keyword
    appears earlier plays first.
    """
    source = text or ""
    command, body, start = parse_message_span(source)
    if mode == MODE_ALWAYS:
        return [(0, source)]
    if mode == MODE_ACTIONS:
        return action_spans(source)
    if mode == MODE_EMOTES:
        # режим 2: команды-эмоции и *действия* в любом сообщении
        # mode 2: emote commands and *actions* in almost any message
        if command in EMOTE_COMMANDS:
            return _with_actions([(start, body)], body, start)
        return action_spans(source)
    if mode == MODE_MESSAGES:
        if not command:
            return _with_actions([(0, source)], source, 0)
        if command in TALK_COMMANDS:
            return _with_actions([(start, body)], body, start)
        return []
    return []


@lru_cache(maxsize=512)
def _split_keywords(text: str) -> tuple[str, ...]:
    """Разбор строки ключевых слов с кэшем / keyword parsing, cached."""
    return tuple(part.strip() for part in _KEYWORD_SPLIT_RE.split(text) if part.strip())


def keywords_of(text: str) -> list[str]:
    """Ключевые слова правила: запятая, точка с запятой или перевод строки.

    The rule keywords: comma, semicolon or a line break separates them.

    Разбор кэшируется: ``candidates()`` зовёт это для каждого правила на каждое
    сообщение, а строка ключевых слов у правила не меняется между сообщениями.
    Кэш ограничен, поэтому переименование правил в настройках его не раздувает.
    The parsing is cached: ``candidates()`` calls it for every rule on every
    message, while a rule's keyword string does not change between messages. The
    cache is bounded, so renaming rules in the settings does not grow it.
    """
    return list(_split_keywords(text or ""))


# сколько посторонних слов допускается внутри ключевой фразы: «открыл зонт»
# находит и «открыл чёрный зонт»
# how many foreign words may sit inside a keyword phrase
GAP_WORDS = 1


def _words_of(chunk: str) -> list[tuple[int, int, str]]:
    """Слова куска текста: (начало, конец, слово) / the words of a chunk."""
    return [(match.start(), match.end(), match.group(0)) for match in _WORD_RE.finditer(chunk)]


def _negated(chunk: str, words: list[tuple[int, int, str]], indices: list[int]) -> bool:
    """Стоит ли отрицание перед одним из найденных слов.

    Is there a negation marker before one of the matched words. Смотрим до
    ``NEG_LOOKBACK`` слов назад, но не перешагиваем знаки препинания: «Не
    открыл зонт» — отрицание, а «Не открыл зонт, да ну» — уже два разных куска.
    Up to ``NEG_LOOKBACK`` words back are checked, and punctuation stops the
    lookback: «Не открыл зонт» is negated, «Не открыл зонт, да ну» is not — that
    is a different clause already.
    """
    for index in indices:
        for back in range(index - 1, max(-1, index - NEG_LOOKBACK - 1), -1):
            if _PUNCT_RE.search(chunk[words[back][1] : words[back + 1][0]]):
                break
            if morph.norm(words[back][2]) in NEG_MARKERS:
                return True
    return False


def _keyword_negated(keyword: str) -> bool:
    """Есть ли отрицание в самом ключе / does the keyword itself negate."""
    return any(morph.norm(word) in NEG_MARKERS for word in _WORD_RE.findall(keyword))


def _phrase_hits(
    words: list[tuple[int, int, str]],
    word_keys: list[frozenset[str]],
    chunk: str,
    keyword: str,
    keys: "morph.KeyCache",
    forms: int,
    negation: bool = True,
) -> list[tuple[int, int]]:
    """Совпадения ключевой фразы в куске текста: (начало, конец).

    Every match of the keyword phrase in a chunk: (start, end).

    Слова фразы ищутся по порядку, между ними допускается не больше
    ``GAP_WORDS`` посторонних слов; на уровне «Точно» — только вплотную.
    ``negation`` включает проверку отрицания (кроме ключей, где оно уже есть).
    Возвращаются границы найденного, а не текст: по границам потом видно,
    какое совпадение длиннее и какое лежит внутри другого.
    The phrase words are matched in order with at most ``GAP_WORDS`` words in
    between (the "Exact" level wants them adjacent). ``negation`` turns the
    negation check on — except for keywords that already negate themselves.
    The span is returned rather than the text: the spans show which match is
    longer and which one sits inside another.
    """
    want = [keys(word, forms) for word in _WORD_RE.findall(keyword)]
    if not want:
        return []
    check = negation and not _keyword_negated(keyword)
    gap = 0 if forms == morph.FORMS_EXACT else GAP_WORDS
    found: list[tuple[int, int]] = []
    for index in range(len(words)):
        if not word_keys[index] & want[0]:
            continue
        previous = index
        matched = [index]
        for need in want[1:]:
            step = previous + 1
            last = previous + 1 + gap  # не больше ``gap`` слов между словами
            while step <= last and step < len(words) and not word_keys[step] & need:
                step += 1
            if step > last or step >= len(words) or not word_keys[step] & need:
                previous = -1
                break
            previous = step
            matched.append(step)
        if previous < 0:
            continue
        if check and _negated(chunk, words, matched):
            log.info(
                "Анимации: совпадение с отрицанием пропущено (длина=%d)",
                words[previous][1] - words[index][0],
            )
            continue
        found.append((words[index][0], words[previous][1]))
    return found


def _inside(inner: tuple[int, int], outer: tuple[int, int]) -> bool:
    """Лежит ли ``inner`` внутри ``outer`` и короче ли он.

    Does ``inner`` sit inside ``outer``, and is it shorter.

    Нужно для вложенных ключей: «сел» находится внутри «сел откинувшись», и
    играть должно не оба, а только более точное — длинное — совпадение.
    Совпадение той же длины вложенным не считается: два правила с одинаковым
    ключом — осознанный выбор игрока, и оба срабатывают.
    This is for nested keywords: «сел» is found inside «сел откинувшись», and only
    the more precise, longer match must play — never both. A match of the same
    length is not nested: two rules with an identical keyword are the player's
    deliberate choice, and both fire.
    """
    return (
        outer[0] <= inner[0]
        and inner[1] <= outer[1]
        and (outer[1] - outer[0]) > (inner[1] - inner[0])
    )


def select_spans(candidates: Iterable[tuple[int, int, object]]) -> list[tuple[int, int, object]]:
    """Какие совпадения играют: длинное забирает своё, короткое отступает.

    Which matches play: the long one takes its place and the short one steps
    aside.

    ``candidates`` — (начало, конец, метка ключа) по всем правилам сразу.
    Метка — это (правило, номер ключевого слова): по ней видно, какое срабатывание
    чьё, ведь у каждого правила свои ключи.
    ``candidates`` are (start, end, a keyword label) for every rule at once. The
    label is (rule, keyword number): it tells whose hit is whose, as every rule
    has keywords of its own.
    Порядок разбора такой:
    The selection goes like this:

    1. Совпадения покороче отбрасываются, если лежат внутри более длинного:
       «сел» внутри «сел откинувшись» — это та же мысль, только короче.
       Shorter matches are dropped when they sit inside a longer one: «сел»
       inside «сел откинувшись» says the same thing in fewer words.
    2. Один ключ играет один раз: повтор того же слова второй раз молчит.
       Два разных ключа одного правила, стоящие рядом («да ну да брось»), —
       это два срабатывания, поэтому метки у них разные.
       One keyword plays once: a repeated word stays quiet the second time. Two
       different keywords of one rule side by side («да ну да брось») are two
       hits, which is why their labels differ.
    """
    items = sorted(candidates, key=lambda item: (-(item[1] - item[0]), item[0], repr(item[2])))
    # 1: короткое внутри длинного — не отдельное срабатывание
    # 1: a short match inside a long one is not a hit of its own
    #
    # Каждый кандидат сравнивается с каждым: проверка «лежит ли внутри» — это
    # двумерный запрос (начало не раньше И конец не позже), и упростить его до
    # одного сравнения нельзя, не поменяв поведение. Кандидатов на сообщение
    # десятки, так что квадрат здесь дешевле любой структуры данных — а главное,
    # так поведение остаётся ровно тем же.
    # Every candidate is compared with every other: "sits inside" is a 2-D query
    # (starts no earlier AND ends no later) and cannot be reduced to a single
    # comparison without changing behaviour. A message yields a few dozen
    # candidates, so the square is cheaper than any data structure — and, more
    # importantly, the behaviour stays exactly the same.
    outer = [(begin, end) for begin, end, _ in items]
    alive = [
        item
        for index, item in enumerate(items)
        if not any(
            _inside((item[0], item[1]), other)
            for other_index, other in enumerate(outer)
            if other_index != index
        )
    ]
    # 2: один ключ играет один раз
    # 2: one keyword plays once
    picked: list[tuple[int, int, object]] = []
    taken: set[object] = set()
    for begin, end, label in alive:
        if label in taken:
            continue
        taken.add(label)
        picked.append((begin, end, label))
    picked.sort(key=lambda item: (item[0], item[1]))
    return picked


# -------------------------------------------------------------- контекст поиска
@dataclass
class Context:
    """Всё, что нужно правилу для поиска в одном сообщении.

    Everything a rule needs to search one message.

    equivalent  «фраза -> ключ словаря»: так находятся слова-синонимы
    text_keys   «текст -> [(начало, конец, ключ)]»: фразы словаря в сообщении
    keys        кэш словоформ, чтобы словарь морфологии не спрашивали дважды
    negation    не срабатывать на отрицание
    """

    equivalent: Callable[[str], str] | None = None
    text_keys: Callable[[str], list[tuple[int, int, str]]] | None = None
    keys: "morph.KeyCache" = field(default_factory=morph.KeyCache)
    negation: bool = True
    _phrases: dict[str, list[tuple[int, int, str]]] = field(default_factory=dict, repr=False)

    def key_of(self, phrase: str) -> str:
        """Ключ словаря для фразы; пусто — фразы нет в словаре.

        The glossary key of a phrase; empty when the glossary does not know it.
        """
        if self.equivalent is None:
            return ""
        try:
            return str(self.equivalent(phrase) or "")
        except Exception:
            return ""

    def phrases(self, chunk: str) -> list[tuple[int, int, str]]:
        """Фразы словаря в куске текста, с кэшем на сообщение.

        Glossary phrases inside a chunk of text, cached per message.
        """
        if self.text_keys is None:
            return []
        cached = self._phrases.get(chunk)
        if cached is None:
            try:
                cached = list(self.text_keys(chunk) or [])
            except Exception:
                cached = []
            self._phrases[chunk] = cached
        return cached


# -------------------------------------------------------------------- правило
@dataclass
class Choice:
    """Один вариант анимации: имя для /anim плюс подпись и описание.

    One animation variant: the /anim name plus a title and a description.
    """

    name: str = ""  # имя для /anim / the /anim name
    title: str = ""  # как назвать игроку / the name shown to the player
    description: str = ""  # объяснение в оверлее выбора / the chooser description
    # Группа в меню выбора: варианты одной группы идут подряд под её названием,
    # разные группы разделены чертой. Пусто — вариант без группы.
    # The group in the chooser: variants of one group sit together under its
    # title, and different groups are separated by a rule. Empty means no group.
    group: str = ""

    def label(self) -> str:
        """Как вариант подписан: название, а без него — имя команды.

        How the variant is labelled: its title, or the command name without one.
        """
        return (self.title or "").strip() or (self.name or "").strip()

    def problem(self) -> str:
        """Что не так с вариантом; пустая строка — всё в порядке.

        What is wrong with the variant; an empty string means it is fine.
        """
        if not (self.name or "").strip():
            return VAL_EMPTY_NAME
        if re.search(r"[\s/]", self.name.strip()):
            return VAL_BAD_NAME
        return ""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"name": self.name.strip().lstrip("/")}
        if (self.title or "").strip():
            data["title"] = self.title.strip()[:MAX_TITLE]
        if (self.description or "").strip():
            data["description"] = self.description.strip()[:MAX_DESC]
        if (self.group or "").strip():
            data["group"] = self.group.strip()[:MAX_GROUP]
        return data

    @classmethod
    def from_dict(cls, data: Any) -> "Choice | None":
        """Вариант из config.json; пустой или мусор — None.

        A variant from config.json; an empty or junk one is None.
        Можно писать просто строкой: ``"anim_leanrail"`` — тогда ни названия,
        ни описания у варианта нет.
        A bare string works too: ``"anim_leanrail"`` gives a variant with neither
        a title nor a description.
        """
        if isinstance(data, str):
            name = data.strip().lstrip("/")
            return cls(name=name) if name else None
        if not isinstance(data, Mapping):
            return None
        name = str(data.get("name") or "").strip().lstrip("/")
        if not name:
            return None
        return cls(
            name=name,
            title=str(data.get("title") or "").strip()[:MAX_TITLE],
            description=str(data.get("description") or "").strip()[:MAX_DESC],
            group=str(data.get("group") or "").strip()[:MAX_GROUP],
        )


def _same_rule(one: "Rule", other: "Rule") -> bool:
    """Это срабатывания одного правила / do both come from the same rule."""
    return getattr(one, "id", None) == getattr(other, "id", None) and one.keywords == other.keywords


@dataclass
class Rule:
    """Правило анимации / one animation rule."""

    keywords: str = ""
    name: str = ""  # название для /anim
    mode: int = MODE_ALWAYS
    forms: int = morph.FORMS_DEFAULT  # как сравнивать словоформы / word forms
    duration_ms: int = DEFAULT_MS
    loop: bool = False
    enabled: bool = True
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    # варианты: два и больше — в игре открывается оверлей выбора
    # variants: two or more make the game show the chooser overlay
    choices: list[Choice] = field(default_factory=list)

    # --- проверка ---
    def problem(self) -> str:
        """Что не так с правилом; пустая строка — всё в порядке.

        What is wrong with the rule; an empty string means it is fine.
        """
        if not keywords_of(self.keywords):
            return VAL_EMPTY_KEYWORD
        name = self.name.strip()
        if not name and not self.choices:
            return VAL_EMPTY_NAME
        if name and re.search(r"[\s/]", name):
            return VAL_BAD_NAME
        if len(self.choices) > MAX_CHOICES:
            return VAL_TOO_MANY_CHOICES
        for choice in self.choices:
            problem = choice.problem()
            if problem:
                return problem
        if not isinstance(self.duration_ms, int) or not MIN_MS <= self.duration_ms <= MAX_MS:
            return VAL_BAD_MS
        if self.mode not in MODES:
            return VAL_BAD_MODE
        return ""

    def ready(self) -> bool:
        """Правило можно исполнять / the rule can actually run."""
        return self.enabled and not self.problem()

    # --- варианты ---
    def variant_list(self) -> list["Choice"]:
        """Что игрок выберет: варианты, а без них — само правило.

        What the player chooses from: the variants, or the rule itself when it
        has none. Одно правило без вариантов ведёт себя как раньше — сразу
        играет, без оверлея.
        A rule without variants behaves as before: it plays at once, no overlay.
        """
        if self.choices:
            return list(self.choices)
        name = self.name.strip()
        return [Choice(name=name)] if name else []

    def needs_choice(self) -> bool:
        """Нужен ли оверлей выбора: вариантов два и больше.

        Is the chooser needed: two or more variants. Один вариант — это обычное
        правило, выбор из одного ничего не решает.
        One variant is an ordinary rule: choosing from one option decides nothing.
        """
        return len(self.choices) > 1

    # --- сопоставление ---
    def scan(self, text: str, ctx: "Context | None" = None) -> tuple[list[str], list[int]]:
        """Найденные ключевые слова и их места в сообщении.

        Одно срабатывание на каждое ключевое слово правила.
        The keywords found in the message, with their positions — one hit per
        keyword of the rule.
        """
        hits = self.hits(text, ctx)
        found: list[str] = []
        for _, form in hits:
            if form not in found:
                found.append(form)
        return found, [position for position, _ in hits]

    def hits(self, text: str, ctx: "Context | None" = None) -> list[tuple[int, str]]:
        """Срабатывания правила по порядку: (место в тексте, найденный текст).

        Два разных ключа в одном сообщении дают два срабатывания, повтор того
        же слова — одно.
        The hits of the rule in order: (position, the text found). Two different
        keywords in one message give two hits, a repeated word gives one.
        """
        return [(start, form) for start, _, form in self.spans(text, ctx)]

    def spans(self, text: str, ctx: "Context | None" = None) -> list[tuple[int, int, str]]:
        """Срабатывания правила с границами: (начало, конец, найденный текст).

        Свои совпадения правило разбирает само — тем же правилом «длинное
        побеждает вложенное», что и в работе: два ключа одного правила, один из
        которых вложен в другой, дают одно срабатывание, а не два.
        The hits of the rule with their bounds: (start, end, the text found). The
        rule resolves its own matches with the same "the longer one wins" rule
        used at run time: two keywords of one rule, one nested in the other, give
        one hit, not two.
        """
        picked = select_spans(self.candidates(text, ctx))
        return [(begin, end, text[begin:end].strip()) for begin, end, _label in picked]

    def candidates(self, text: str, ctx: "Context | None" = None) -> list[tuple[int, int, int]]:
        """Все совпадения правила без разбора: (начало, конец, номер ключа).

        Отдаются и вложенные совпадения: короткое слово внутри длинной фразы —
        это тоже находка, просто её потом отбросит отбор. Нужно это затем, что
        решать, какое совпадение лишнее, приходится сразу для **всех** правил:
        «сел» и «сел откинувшись» могут жить в двух разных правилах.
        Every match of the rule, nested ones included: (start, end, keyword
        number). A short word inside a long phrase is a find too, it is just
        dropped later. The selection has to happen across **all** rules at once,
        because «сел» and «сел откинувшись» may live in two different rules.
        """
        if not self.enabled:
            return []
        keywords = keywords_of(self.keywords)
        if not keywords:
            return []
        ctx = ctx or Context()
        found: list[tuple[int, int, int]] = []
        for start, chunk in analysed_spans(text, self.mode):
            words = _words_of(chunk)
            word_keys = [ctx.keys(word, self.forms) for _, _, word in words]
            phrases = ctx.phrases(chunk)
            for order, keyword in enumerate(keywords):
                here: list[tuple[int, int]] = list(
                    _phrase_hits(
                        words, word_keys, chunk, keyword, ctx.keys, self.forms, ctx.negation
                    )
                )
                key = ctx.key_of(keyword)
                # синонимы подключаются, только если самого ключа в тексте нет
                # synonyms only step in when the keyword itself is absent
                if key and not here:
                    for offset, end, phrase_key in phrases:
                        if phrase_key != key:
                            continue
                        index = next((i for i, word in enumerate(words) if word[0] >= offset), None)
                        if index is None:
                            continue
                        if (
                            ctx.negation
                            and not _keyword_negated(keyword)
                            and _negated(chunk, words, [index])
                        ):
                            log.info(
                                "Анимации: «%s» найдено, но отрицание — пропуск", chunk[offset:end]
                            )
                            continue
                        here.append((offset, end))
                for begin, end in here:
                    found.append((start + begin, start + end, order))
        found.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2]))
        return found

    def matches(self, text: str, ctx: "Context | None" = None) -> list[str]:
        """Какие слова нашлись в сообщении / which words matched."""
        return self.scan(text, ctx)[0]

    # --- хранение ---
    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "keywords": self.keywords,
            "name": self.name.strip(),
            "mode": int(self.mode),
            "forms": int(self.forms),
            "duration_ms": int(self.duration_ms),
            "loop": bool(self.loop),
            "enabled": bool(self.enabled),
        }
        if self.choices:
            data["choices"] = [choice.to_dict() for choice in self.choices]
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Rule":
        """Правило из config.json; мусор в полях чинится, а не роняет программу.

        A rule from config.json; junk in the fields is repaired instead of
        breaking the program.
        """

        def _int(value: Any, default: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        mode = _int(data.get("mode"), MODE_ALWAYS)
        mode = LEGACY_MODES.get(mode, mode)  # старый режим 5 -> «Всегда»
        if mode not in MODES:
            mode = MODE_ALWAYS
        forms = _int(data.get("forms"), morph.FORMS_DEFAULT)
        if forms not in morph.FORMS:
            forms = morph.FORMS_DEFAULT
        choices: list[Choice] = []
        raw_choices = data.get("choices")
        if isinstance(raw_choices, (list, tuple)):
            for item in raw_choices:
                choice = Choice.from_dict(item)
                if choice is not None:
                    choices.append(choice)
        return cls(
            keywords=str(data.get("keywords") or ""),
            name=str(data.get("name") or "").strip().lstrip("/"),
            mode=mode,
            forms=forms,
            duration_ms=min(MAX_MS, max(MIN_MS, _int(data.get("duration_ms"), DEFAULT_MS))),
            loop=bool(data.get("loop")),
            enabled=bool(data.get("enabled", True)),
            id=str(data.get("id") or uuid.uuid4().hex[:8]),
            choices=choices[:MAX_CHOICES],
        )


def merge_keywords(*texts: str) -> str:
    """Ключевые слова нескольких правил без повторов, по порядку.

    The keywords of several rules, duplicates removed, order kept.

    Повторы схлопываются без учёта регистра и лишних пробелов: «Открыл зонт» и
    «открыл  зонт» — одно и то же слово, и двух строк в правиле ему не нужно.
    Duplicates collapse regardless of case and extra spaces: they are one and the
    same keyword, and the rule does not need it twice.
    """
    seen: set[str] = set()
    out: list[str] = []
    for text in texts:
        for part in keywords_of(text):
            key = " ".join(part.casefold().split())
            if key in seen:
                continue
            seen.add(key)
            out.append(part)
    return ", ".join(out)


def merge_choices(*groups: Iterable["Choice"]) -> list["Choice"]:
    """Варианты нескольких правил без повторов по имени.

    The variants of several rules, duplicates by name removed.

    Совпало имя — остаётся первый вариант: подпись и описание у него уже есть, а
    придумывать за игрока, чьё описание правильнее, не наше дело.
    Same name means the first variant wins: it already has a title and a
    description, and deciding for the player which one is right is not our call.
    """
    seen: set[str] = set()
    out: list[Choice] = []
    for group in groups:
        for choice in group:
            key = (choice.name or "").strip().lstrip("/").casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(choice)
    return out


def merge_rules(left: "Rule", right: "Rule") -> "Rule":
    """Объединить два правила в одно / merge two rules into one.

    Что переносится всегда: ключевые слова (без повторов) и варианты анимации.
    Что переносится, только если совпадает у обоих: задержка, повтор, словоформы
    и режим. Иначе поле остаётся пустым (значение ``None``), и игрок обязан
    задать его сам — угадывать, какая из двух задержек «правильная», программа
    не станет.

    Always carried over: the keywords (deduplicated) and the animation variants.
    Carried over only when both rules agree: the delay, the loop, the word forms
    and the mode. Otherwise the field is left empty (``None``) so that the player
    has to set it: guessing which of two delays is "the right one" is not the
    program's business.

    Сам merge ничего не решает за интерфейс: возвращается правило и список полей,
    которые остались пустыми, чтобы окно могло попросить их заполнить.
    The merge decides nothing on the interface's behalf: it returns the rule plus
    the fields left empty, so the window can ask for them.
    """
    keywords = merge_keywords(left.keywords, right.keywords)
    choices = merge_choices(
        left.choices or left.variant_list(), right.choices or right.variant_list()
    )
    empty: list[str] = []

    duration = left.duration_ms if left.duration_ms == right.duration_ms else None
    if duration is None:
        empty.append("duration_ms")
    loop = left.loop if left.loop == right.loop else None
    if loop is None:
        empty.append("loop")
    forms = left.forms if left.forms == right.forms else None
    if forms is None:
        empty.append("forms")
    mode = left.mode if left.mode == right.mode else None
    if mode is None:
        empty.append("mode")

    merged = Rule(
        keywords=keywords,
        name="",
        mode=mode if mode is not None else MODE_ALWAYS,
        forms=forms if forms is not None else morph.FORMS_DEFAULT,
        duration_ms=duration if duration is not None else 0,
        loop=bool(loop),
        enabled=left.enabled and right.enabled,
        choices=choices[:MAX_CHOICES],
    )
    return merged, empty


def rules_from_cfg(cfg: Mapping[str, Any]) -> list[Rule]:
    """Все правила из настроек / every rule stored in the settings."""
    raw = cfg.get("anim_rules") or []
    rules: list[Rule] = []
    if not isinstance(raw, list):
        return rules
    for item in raw:
        if isinstance(item, Mapping):
            rules.append(Rule.from_dict(item))
        elif isinstance(item, Rule):
            rules.append(item)
    return rules


def rules_to_cfg(rules: Iterable[Rule]) -> list[dict[str, Any]]:
    """Правила для config.json / the rules in a JSON-friendly shape."""
    return [rule.to_dict() for rule in rules]


# ------------------------------------------------------- подсказки в оверлее
# overlay suggestions
#
# Набор возможных ключевых слов зависит от режима: в сообщении «Действия» ключ,
# привязанный к «Только *…*», не сработает, и предлагать его было бы обманом.
# The set of possible keywords depends on the mode: in an "Actions" message a
# keyword tied to "Only *…*" cannot fire, and offering it would be a lie.
