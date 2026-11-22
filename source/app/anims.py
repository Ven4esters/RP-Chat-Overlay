"""Модуль «Анимации»: ключевое слово в сообщении запускает анимацию в игре.

Animations module: a keyword in a message starts an animation in the game.

Как это работает / how it works
------------------------------
1. Игрок пишет сообщение в оверлее (обычное или командой `/me`, `/to` и т. п.).
2. Модуль смотрит на текст по режиму правила и ищет ключевые слова.
3. Совпало — в чат игры уходит `/anim <название>`, а через заданное время
   анимация останавливается: командой `/sa`, симуляцией нажатия клавиши или
   обоими способами, как выбрано в настройках. Длительность 0 мс означает
   «не останавливать вовсе».
4. Если включено зацикливание, по истечении того же времени просто снова уходит
   `/anim <название>`, и так до нажатия клавиши остановки.
1. The player writes a message in the overlay (plain or with /me, /to and so on).
2. The module reads the text according to the rule mode and looks for keywords.
3. A match sends /anim <name>; after the delay the animation is stopped with
   /sa, with a simulated key press or both — whatever the settings say. A
   duration of 0 ms means "never stop".
4. With looping on, /anim <name> is simply sent again after the same delay until
   the stop key is pressed.

Словоформы / word forms
-----------------------
Ключевое слово сравнивается с сообщением на одном из трёх уровней (поле
«Формы»): ровно та форма, что написана; по основе («открыл» = «открывает»);
по словарной лемме, если установлен `pymorphy3`. Подробности — в `app.morph`.
A keyword is compared to the message on one of three levels (the "Forms"
field): the exact written form, by stem («открыл» = «открывает»), or by the
dictionary lemma when `pymorphy3` is installed. See `app.morph`.

Почему очередь / why a queue
----------------------------
Пока одна анимация играет, вторая не начинается: игры не любят два `/anim`
подряд, а `/sa` от второй анимации сбросил бы первую. Поэтому срабатывания
складываются в очередь и играются по одному — в порядке слов сообщения: слово,
которое игрок написал раньше, и запускает анимацию раньше. Правило играет в
сообщении один раз, сколько бы раз ключевое слово ни повторилось.
While one animation plays, the next does not start: games dislike two /anim
calls in a row, and the second animation's /sa would reset the first. So
triggers are queued and played one at a time, in the order of the words in the
message. A rule plays once per message however often its keyword repeats.

Модуль ничего не знает об интерфейсе: он получает текст, отдаёт команды через
переданную функцию и сообщает о состоянии колбэком. Отключается без последствий.
The module knows nothing about the interface: it takes text, hands commands to a
caller-provided function and reports state through a callback. It can be switched
off without consequences.
"""

from __future__ import annotations

import re
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Callable, Iterable, Mapping

from app import morph
from app.config import log

# ---------------------------------------------------------------- режимы чтения
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
                "Анимации: «%s» найдено, но отрицание — пропуск",
                chunk[words[index][0] : words[previous][1]],
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


# ------------------------------------------------------------------ разбор
def plan(
    rules: Iterable["Rule"], text: str, ctx: "Context | None" = None
) -> list[tuple[int, int, "Rule", str]]:
    """Что сыграет и в каком порядке: (место, номер правила, правило, текст).

    What plays, and in which order: (position, rule number, rule, text).

    Это единственное место, где решается судьба вложенных ключей: «сел» и «сел
    откинувшись» — разные правила, и решать приходится сразу за оба. Порядок —
    по месту в сообщении, при равных местах — по таблице правил.
    This is the only place where nested keywords are settled: «сел» and «сел
    откинувшись» are separate rules, so the decision has to cover both at once.
    The order follows the message, ties follow the rule table.
    """
    table = list(rules)
    ctx = ctx or Context()
    candidates: list[tuple[int, int, int, int, str]] = []
    for index, rule in enumerate(table):
        for begin, end, order in rule.candidates(text, ctx):
            candidates.append((begin, end, index, order, text[begin:end]))
    if not candidates:
        return []
    picked = select_spans(
        (begin, end, (index, order)) for begin, end, index, order, _ in candidates
    )
    chosen = {(begin, end) for begin, end, _ in picked}
    # что не сыграло и почему — видно в журнале
    # what did not play, and why, is visible in the log
    for begin, end, index, _order, form in candidates:
        if (begin, end) in chosen:
            continue
        if any(
            other_begin <= begin and end <= other_end and (other_end - other_begin) > (end - begin)
            for other_begin, other_end, _label in picked
        ):
            log.info(
                "Анимации: «%s» входит в более длинное совпадение — правило «%s» пропущено",
                form,
                table[index].keywords[:40],
            )
    # одно правило в одном месте срабатывает один раз, а разные правила на одном
    # и том же слове — оба, как было и раньше
    # a rule fires once at one place; different rules on the same word both fire,
    # exactly as before
    per_rule_span: dict[tuple[int, int, int], None] = {}
    for begin, end, (index, _order) in picked:
        per_rule_span[(begin, end, index)] = None
    result = [
        (begin, index, table[index], text[begin:end])
        for begin, end, index in sorted(per_rule_span, key=lambda item: item[:2])
    ]
    for index, rule in enumerate(table):
        forms: list[str] = []
        played = 0
        for begin, end, hit_index, _order, form in candidates:
            if hit_index != index:
                continue
            if form not in forms:
                forms.append(form)
            if (begin, end) in chosen:
                played += 1
        if not forms:
            continue
        # одно срабатывание на каждое ключевое слово правила: разные ключи
        # играют подряд, повтор того же слова — только раз
        # one hit per keyword of the rule: different keywords play in turn, a
        # repeated word plays once
        log.info(
            "Анимации: «%s» по правилу «%s» (%s) -> /anim %s, срабатываний: %d",
            text[:60],
            rule.keywords[:40],
            ", ".join(forms),
            rule.name,
            played,
        )
    return result


# ------------------------------------------------------------------ исполнитель
class Runner:
    """Очередь анимаций: `/anim` -> пауза -> `/sa`, при зацикливании по кругу.

    The animation queue: `/anim` -> wait -> `/sa`, repeating while looping.

    send     функция отправки команды в игру: str -> (успех, сообщение);
             a function that sends a command to the game: str -> (ok, message)
    on_event колбэк (вид, текст): «error», «playing», «done», «stopped»;
             a callback (kind, text) for the interface and the player
    """

    def __init__(
        self,
        cfg: Mapping[str, Any] | None = None,
        send: Callable[[str], tuple[bool, str]] | None = None,
        on_event: Callable[[str, str], None] | None = None,
        equivalent: Callable[[str], str] | None = None,
        press_key: Callable[[str], tuple[bool, str]] | None = None,
        text_keys: Callable[[str], list[tuple[int, int, str]]] | None = None,
        chooser: Callable[["Rule"], "Choice | None"] | None = None,
    ) -> None:
        """equivalent — «фраза -> ключ словаря» для слов-синонимов.

        equivalent is the "phrase -> glossary key" function used for synonyms.

        text_keys — «текст -> [(начало, конец, ключ)]»: какие фразы словаря есть
        в сообщении. Без неё синонимами считаются только отдельные слова.
        text_keys tells which glossary phrases sit in the text; without it only
        single words count as synonyms.

        press_key — нажать клавишу в игре (симуляция нажатия) для остановки
        анимации клавишей вместо команды `/sa`.
        press_key presses a key in the game (a simulated press) so an animation
        can be stopped by a key instead of the /sa command.

        chooser — спросить игрока, какой из вариантов играть. Вызывается из
        потока очереди и должен вернуть выбранный ``Choice`` или None, если
        игрок отказался (или оверлей показать не удалось) — тогда правило
        пропускается целиком. Без неё правило с вариантами играет первый.
        chooser asks the player which variant to play. It is called from the
        queue thread and must return the chosen ``Choice``, or None when the
        player backed out (or the overlay could not be shown) — the rule is then
        skipped entirely. Without it a rule with variants plays the first one.
        """
        self.cfg: Mapping[str, Any] = cfg or {}
        self.send = send or (lambda command: (False, "отправка недоступна"))
        self.on_event = on_event
        self.equivalent = equivalent
        self.press_key = press_key
        self.text_keys = text_keys
        self.chooser = chooser
        self._rules: list[Rule] = rules_from_cfg(self.cfg)
        self._queue: deque[Rule] = deque()
        self._lock = threading.RLock()
        self._cv = threading.Condition(self._lock)
        self._thread: threading.Thread | None = None
        self._done = threading.Event()
        self._end_at = 0.0  # конец проигрывания, monotonic
        # Смена анимации на ходу: окно выбора остаётся открытым, и новый выбор
        # приходит сюда, а не в очередь.
        # Swapping the animation on the fly: the chooser stays open, and a new pick
        # arrives here instead of the queue.
        self._swap_choice = None  # какой вариант просят играть
        self._play_token = 0  # номер текущего захода правила
        self._quiet_off = False  # про выключенный модуль пишем раз
        self._stop_run = threading.Event()  # прервать текущий цикл / abort the run
        self._current: Rule | None = None
        self._last_error = ""
        self._last_trigger = ""
        self._reset_pending = False  # после остановки игроком отправить /sa
        # send /sa after a stop by the player
        # Режим «В машине»: пока он включён, ни одна команда в игру не уходит.
        # Признак приходит снаружи (галочка в настройках, пункт меню трея),
        # потому что состояние игры программе недоступно.
        # The "In a vehicle" mode: while it is on, no command leaves for the game.
        # The flag comes from outside (a checkbox in the settings, a tray menu
        # item), because the game state is not available to the program.
        self._vehicle = False
        self._vehicle_note = ""

    # ------------------------------------------------------------ настройки
    def reload(self, cfg: Mapping[str, Any]) -> None:
        """Перечитать правила из настроек / reload the rules from the settings."""
        self.cfg = cfg or {}
        with self._lock:
            self._rules = rules_from_cfg(self.cfg)
        if not self.enabled():
            self.clear("модуль выключен")

    def enabled(self) -> bool:
        """Включён ли модуль / is the module switched on."""
        return bool(self.cfg.get("anims_enabled", False))

    # ------------------------------------------------------ режим «В машине»
    def vehicle(self) -> bool:
        """Включён ли режим «В машине» / is the "In a vehicle" mode on."""
        return bool(self._vehicle)

    def set_vehicle(self, on: bool, reason: str = "") -> bool:
        """Включить или выключить режим «В машине» / turn the vehicle mode on or off.

        Включение — это команда «больше ничего не запускать», поэтому оно сразу
        делает три вещи: снимает очередь, гасит зацикливание и отправляет ровно
        один `/sa`, чтобы в игре не осталось кривой позы. Дальше — тишина: пока
        режим включён, ни `/anim`, ни `/sa` в игру не уходят.
        Второй `/sa` здесь был бы вреден: первый же и убирает анимацию, а лишняя
        команда в машине снова дёргает персонажа.
        Turning it on means "start nothing else", so it does three things at
        once: drops the queue, breaks the loop and sends exactly one `/sa` so that
        no crooked pose is left in the game. After that comes silence: while the
        mode is on, neither `/anim` nor `/sa` leaves for the game.
        A second `/sa` would only hurt here: the first one already removes the
        animation, and an extra command in a vehicle jerks the character again.

        ``reason`` — что написать игроку и в журнал; по умолчанию «в машине».
        ``reason`` is shown to the player and written to the log; "in a vehicle"
        by default.
        """
        reason = reason or "в машине"
        was = bool(self._vehicle)
        self._vehicle = bool(on)
        self._vehicle_note = reason if on else ""
        if not on:
            # Режим выключили: очередь, снятая при включении, не возвращается —
            # сообщения, которые её наполнили, уже старые. Игрок напишет новое.
            # The mode is off: the queue dropped on the way in does not come
            # back — the messages that filled it are stale by now.
            if was:
                log.info("Анимации: режим «в машине» выключен")
            self._emit("vehicle", "режим «в машине» выключен")
            return True
        if was:
            # повторное включение ничего не отправляет: режим уже держит тишину
            # turning it on again sends nothing: the mode already keeps silence
            return True
        log.info("Анимации: режим «в машине» включён — анимации остановлены")
        self._drop_choice_window(close=True)
        with self._cv:
            dropped = [rule.name for rule in self._queue]
            self._queue.clear()
            self._stop_run.set()
            self._cv.notify_all()
        if dropped:
            log.info("Анимации: очередь снята (%s)", ", ".join("/anim " + name for name in dropped))
        current = self._current
        if current is not None:
            # ровно одна остановка, и только если что-то играло
            # exactly one stop, and only when something was playing
            try:
                # единственная команда, которой режим пропускает: она и убирает
                # анимацию, из-за которой персонаж в машине сидит криво
                # the only command the mode lets through: it removes the
                # animation that makes the character sit crooked in a vehicle
                self._send("/sa", current, quiet=True, force=True)
            except Exception:
                log.exception("Анимации: не удалось отправить /sa при входе в машину")
            self._emit("stopped", "остановлено перед машиной")
        self._emit("vehicle", "режим «в машине» включён")
        return True

    def guard_quiet(self) -> bool:
        """Пускать ли текущее действие в игру / may the current action reach the game.

        Единственное место, где решается «молчать или отправлять»: пока режим
        включён, ни одна команда не уходит. Ошибку пишем один раз, чтобы журнал
        не забивался одинаковыми строками.
        The only place that decides "silent or send": while the mode is on no
        command leaves. The log line is written once, so it does not fill up.
        """
        if not self._vehicle:
            return True
        if not self._quiet_off:
            self._quiet_off = True
            log.info("Анимации: режим «в машине» — команды в игру не отправляются")
        return False

    def rules(self) -> list[Rule]:
        with self._lock:
            return list(self._rules)

    # ------------------------------------------------------------ сообщения
    def feed(self, text: str) -> list[Rule]:
        """Проверить сообщение и поставить срабатывания в очередь.

        Check a message and queue every hit.

        Порядок — как в самом сообщении: сначала то, что игрок написал раньше.
        Правило играет в сообщении **один раз**, даже если ключевое слово
        повторилось: «чёрт, чёрт» даёт одну анимацию, а место в очереди берётся
        по первому совпадению. Слова-синонимы, которые переводятся так же, как
        ключевое, тоже срабатывают — если передана функция ``equivalent``.
        The order follows the message itself: whatever was written first plays
        first. A rule plays **once per message** even when its keyword repeats:
        «чёрт, чёрт» gives one animation, and the place in the queue is taken from
        the first match. Synonyms that translate like the keyword fire too when an
        ``equivalent`` function is provided.
        """
        if not self.enabled():
            if not self._quiet_off:
                self._quiet_off = True
                log.info("Анимации: модуль выключен — правила не проверяются")
            return []
        if self._vehicle:
            # В машине ни правила не проверяем, ни очередь не трогаем: игрок
            # не должен удивиться, когда после выхода из машины вдруг сыграет
            # то, что он написал десять минут назад на ходу.
            # In a vehicle neither the rules nor the queue are touched: the
            # player must not be surprised by something written ten minutes ago
            # suddenly playing after getting out.
            if not self._quiet_off:
                self._quiet_off = True
                log.info("Анимации: режим «в машине» — правила не проверяются")
            return []
        if not (text or "").strip():
            return []
        self._quiet_off = False  # снова говорим, если что-то не так
        ctx = Context(
            equivalent=self.equivalent, text_keys=self.text_keys, negation=self.negation()
        )
        rules = [rule for rule in self.rules() if rule.ready()]
        hits = plan(rules, text, ctx)
        log.info(
            "Анимации: в очередь %s", " -> ".join("/anim " + rule.name for _, _, rule, _ in hits)
        )
        for _, _, rule, _ in hits:
            # Меню этого правила ещё висит в очереди выбора — возвращаем его,
            # а не открываем второе такое же: игрок как раз хочет поменять
            # анимацию по этому ключу.
            # This rule's menu is still waiting in the choice queue: it is brought
            # back instead of opening a second one — the player wants to change the
            # animation for that keyword.
            focus = getattr(self.chooser, "focus_menu_for", None)
            if callable(focus) and rule.needs_choice():
                try:
                    if focus(rule):
                        log.info(
                            "Анимации: меню «%s» поднято из очереди выбора", rule.keywords[:40]
                        )
                        continue
                except Exception:
                    log.exception("Анимации: не удалось вернуть меню выбора")
            self._enqueue(rule)
        return [rule for _, _, rule, _ in hits]

    def _enqueue(self, rule: Rule) -> None:
        # Страховка: в машине очередь не наполняется даже в обход feed.
        # A safeguard: in a vehicle the queue does not fill up even around feed.
        if self._vehicle:
            return
        copy = Rule.from_dict(rule.to_dict())  # снимок на момент срабатывания
        with self._cv:
            if len(self._queue) >= MAX_QUEUE:
                log.warning("Анимации: очередь переполнена, «%s» отброшено", rule.name)
                self._last_error = "очередь переполнена"
                return
            self._queue.append(copy)
            self._last_trigger = rule.keywords
            self._ensure_thread()
            self._cv.notify_all()

    # ----------------------------------------------------------- управление
    def stop_user(self) -> bool:
        """Остановить текущую анимацию (горячая клавиша), очередь не трогать.

        Stop the animation playing right now (the stop hotkey) and keep the queue.
        Очередь остаётся: остальные срабатывания пришли из того же сообщения и
        должны сыграть. Снять очередь целиком может только полная остановка —
        ``stop()`` или ``clear()``.
        The queue stays: the other hits came from the same message and must still
        play. Only a full stop — ``stop()`` or ``clear()`` — drops it.
        """
        self._reset_pending = True
        # Меню остановленного правила больше не живое: следующий тот же ключ
        # должен открыть свежее меню, а не вернуть старое с отмеченным вариантом.
        # Само окно остаётся на экране — игрок может выбрать другой вариант.
        # The stopped rule's menu is no longer live: the next hit of the same
        # keyword must open a fresh menu, not bring back the old one with a marked
        # variant. The window itself stays — the player may pick another variant.
        self._chooser_stopped(self._current)
        self._drop_choice_window()
        with self._cv:
            queued = len(self._queue)
            if not self._current and not queued:
                return False
            self._stop_run.set()
            self._cv.notify_all()
        log.info("Анимации: остановлено игроком, в очереди остаётся: %d", queued)
        self._emit("stopped", "остановлено игроком")
        return True

    def stop(self, reason: str = "") -> bool:
        """Прервать текущий цикл и очистить очередь / abort the run and the queue."""
        stopped = bool(self._current) or bool(self._queue)
        # полная остановка убирает окно совсем; клавиша остановки его оставляет
        # a full stop removes the window for good; the stop key keeps it
        self._drop_choice_window(close=True)
        if reason and reason != "остановлено игроком":
            self._reset_pending = False
        with self._cv:
            dropped = [rule.name for rule in self._queue]
            self._queue.clear()
            self._stop_run.set()
            self._cv.notify_all()
        if dropped:
            # очередь снята целиком — в журнале видно, что именно не сыграет
            # the whole queue is dropped — the log shows what will not play
            log.info("Анимации: очередь снята (%s)", ", ".join("/anim " + name for name in dropped))
        if stopped:
            log.info("Анимации: %s", reason or "остановлено")
            self._emit("stopped", reason or "остановлено")
        return stopped

    def clear(self, reason: str = "") -> None:
        """Полная остановка: очередь, текущая анимация и рабочий поток.

        A full stop: the queue, the running animation and the worker thread.
        """
        self.stop(reason)
        self._done.set()
        with self._cv:
            self._cv.notify_all()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)
        self._thread = None
        self._done.clear()

    def shutdown(self) -> None:
        """Гашение при выходе программы / the shutdown hook."""
        try:
            self.clear("программа закрывается")
        except Exception:
            log.exception("Анимации: сбой при остановке")

    # --------------------------------------------------------------- состояние
    def state(self) -> dict[str, Any]:
        """Что показать в настройках / what the settings page shows."""
        with self._lock:
            return {
                "enabled": self.enabled(),
                "rules": len(self._rules),
                "current": self._current.name if self._current else "",
                "loop": bool(self._current and self._current.loop),
                "queued": len(self._queue),
                "error": self._last_error,
                "trigger": self._last_trigger,
                "vehicle": bool(self._vehicle),
            }

    def _emit(self, kind: str, text: str) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(kind, text)
        except Exception:
            log.exception("Анимации: колбэк состояния упал")

    # ------------------------------------------------------------ исполнение
    def _ensure_thread(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._done.clear()
        self._thread = threading.Thread(target=self._loop, name="anims", daemon=True)
        self._thread.start()

    def _next(self) -> Rule | None:
        with self._cv:
            while not self._queue and not self._done.is_set():
                self._cv.wait(0.25)
            if self._done.is_set() or not self._queue:
                return None
            return self._queue.popleft()

    def _loop(self) -> None:
        """Очередь: анимация проигрывает своё время, хвост — и следующая.

        The queue: an animation plays its own time, then the tail, then the next.
        Хвост (``anim_extra_ms``, по умолчанию 50 мс) отмеряется от конца
        проигрывания: 1500 мс анимации + 50 мс — играет следующая. Он же даёт
        игре закрыть чат после остановки и серверу принять новую команду.
        The tail (``anim_extra_ms``, 50 ms by default) starts at the end of the
        play: 1500 ms of animation + 50 ms — the next one plays. It also gives
        the game time to close its chat after the stop and the server time to
        take the new command.
        """
        while not self._done.is_set():
            rule = self._next()
            if rule is None:
                return
            if self._vehicle:
                # Режим включили, пока правило ждало очереди: не играем.
                # The mode was turned on while the rule waited: do not play it.
                log.info("Анимации: «%s» снято — включён режим «в машине»", rule.name)
                with self._lock:
                    self._current = None
                continue
            try:
                self._play(rule)
            except Exception:
                log.exception("Анимации: сбой при проигрывании «%s»", rule.name)
                self._last_error = "сбой при отправке"
                self._end_at = time.monotonic()
            finally:
                with self._lock:
                    self._current = None
            extra = self.extra()
            if extra:
                left = self._end_at + extra - time.monotonic()
                if left > 0:
                    # флаг остановки от прошлой анимации сюда не относится
                    # a stop flag left over from the previous animation is not
                    # about this one
                    self._stop_run.clear()
                    if self._stop_run.wait(left):
                        # остановили во время хвоста: следующую не играем
                        # stopped during the tail: the next one is dropped
                        self._stop_run.clear()

    def negation(self) -> bool:
        """Не срабатывать на отрицание? / should negation silence a rule."""
        return bool(self.cfg.get("anim_skip_negation", True))

    def extra(self) -> float:
        """Хвост после анимации в секундах / the tail after an animation.

        Сколько добавить к времени проигрывания, прежде чем запускать следующую
        анимацию из очереди: 1500 мс анимации + 50 мс хвоста — играет следующая.
        Настройка ``anim_extra_ms`` (по умолчанию ``ANIM_EXTRA_MS``); старое поле
        ``anim_gap_ms`` читается как она же, чтобы настройки не потерялись.
        How much to add to the play time before the next animation starts:
        1500 ms of animation + 50 ms of tail — the next one plays. The setting is
        ``anim_extra_ms`` (``ANIM_EXTRA_MS`` by default); the old ``anim_gap_ms``
        is read as the same value so the settings are not lost.
        """
        raw = self.cfg.get("anim_extra_ms")
        if raw is None:
            raw = self.cfg.get("anim_gap_ms", ANIM_EXTRA_MS)
        try:
            ms = int(raw)
        except (TypeError, ValueError):
            ms = ANIM_EXTRA_MS
        return min(MAX_EXTRA_MS, max(0, ms)) / 1000.0

    def stop_methods(self) -> tuple[bool, bool]:
        """Как останавливать анимацию: (командой /sa, клавишей).

        How to stop an animation: (with the /sa command, with the key).
        """
        by_sa = bool(self.cfg.get("anim_stop_by_sa", True))
        by_key = bool(self.cfg.get("anim_stop_by_key", False))
        return by_sa, by_key

    def _stop_animation(self, rule: Rule) -> None:
        """Остановить анимацию выбранными способами / stop it the chosen ways.

        Настройки дают два независимых способа: команда `/sa` и симуляция
        нажатия клавиши (по умолчанию F — та же, что прекращает анимацию в игре).
        Включены оба — применяются оба; выключены оба — анимация не
        останавливается совсем.
        The settings offer two independent ways: the `/sa` command and a
        simulated key press (F by default, the key the game itself uses). Both on
        means both are used; both off means the animation is not stopped at all.
        """
        if not self.guard_quiet():
            return
        by_sa, by_key = self.stop_methods()
        if by_sa:
            self._send("/sa", rule, quiet=True)
        if by_key:
            spec = str(self.cfg.get("anim_stop_key", "f") or "f")
            if self.press_key is None:
                log.warning("Анимации: нажатие клавиши «%s» недоступно", spec)
                return
            try:
                ok, message = self.press_key(spec)
            except Exception as error:
                log.exception("Анимации: не удалось нажать «%s»", spec)
                ok, message = False, str(error)[:120]
            if ok:
                log.info("Анимации: нажата клавиша «%s»", spec)
            else:
                self._last_error = message or "клавиша не нажалась"
                log.warning("Анимации: клавиша «%s» не нажалась — %s", spec, self._last_error)

    def _play(self, rule: Rule) -> None:
        """Один заход правила: /anim -> пауза -> остановка или снова /anim.

        One rule run: /anim -> wait -> stop, or /anim again while looping.

        Длительность 0 мс означает «не останавливать»: уходит только `/anim`.
        A duration of 0 ms means "never stop": only `/anim` is sent.
        """
        self._stop_run.clear()
        with self._lock:
            self._current = rule
            self._play_token += 1
            token = self._play_token
            self._swap_choice = None
        # выбор варианта — до первого /anim: пока игрок думает, в игре ничего
        # не играет, и очередь стоит. Окно после выбора не закрывается, и выбор
        # другого варианта меняет анимацию на ходу.
        # the variant is chosen before the first /anim: nothing plays in the game
        # while the player picks, and the queue waits. The window stays open after
        # the pick, and picking another variant swaps the animation on the fly.
        variant = self._choose(rule, token)
        if variant is None:
            # игрок отказался или оверлей не показать: правило пропускаем целиком,
            # иначе в чат уйдёт не то, что он ждал
            # the player backed out or the overlay could not be shown: the whole
            # rule is skipped, otherwise the game plays what he did not pick
            self._end_at = time.monotonic()
            self._withdraw_choice(token)
            return
        self._emit("playing", variant.label() if rule.needs_choice() else rule.name)
        # время проигрывания считается от отправки `/anim`: сама отправка тоже
        # занимает время (фокус в игру, чат, вставка, Enter), и оно входит в
        # длительность, иначе каждая пауза незаметно удлинялась бы на полсекунды
        # the play time counts from the `/anim` send: the send itself takes time
        # (focus, game chat, paste, Enter), and it belongs to the duration —
        # otherwise every pause would quietly grow by half a second
        started = time.monotonic()
        if not self._send(f"/anim {variant.name}", rule):
            self._end_at = started
            return
        if rule.duration_ms <= 0:
            # 0 мс: анимацию не останавливаем — ни /sa, ни клавишей
            # 0 ms: the animation is not stopped at all
            self._end_at = started
            self._emit("done", variant.name)
            return
        deadline = started + rule.duration_ms / 1000.0
        while True:
            # Смена варианта проверяется ДО решения о конце: за время ожидания
            # игрок мог нажать другой вариант, и тогда правило не заканчивается,
            # а играет выбранное — при зацикливании и без него одинаково.
            # The swap is checked BEFORE deciding the run is over: while waiting the
            # player may have picked another variant, and then the rule does not
            # end but plays the pick — with looping and without it alike.
            swapped = self._take_swap(token)
            if swapped is not None and swapped.name != variant.name:
                log.info("Анимации: смена варианта %s -> %s", variant.name, swapped.name)
                self._stop_animation(rule)
                variant = swapped
                self._emit("playing", variant.label())
                started = time.monotonic()
                if not self._send(f"/anim {variant.name}", rule):
                    self._end_at = started
                    return
                if rule.duration_ms <= 0:
                    self._end_at = started
                    self._emit("done", variant.name)
                    return
                deadline = started + rule.duration_ms / 1000.0
                continue
            if time.monotonic() < deadline:
                # Ждём короткими шагами, чтобы не проспать смену варианта.
                # Wait in short steps so a variant swap is not slept through.
                left = deadline - time.monotonic()
                if self._stop_run.wait(min(left, 0.08)):
                    # анимацию остановили клавишей игрока: гасим её выбранным
                    # способом
                    # the player stopped the animation: put it out the chosen way
                    if self._reset_pending:
                        self._reset_pending = False
                        self._stop_animation(rule)
                    self._end_at = time.monotonic()
                    self._withdraw_choice(token)
                    self._notify_rule_done(rule)
                    return
                continue
            if rule.loop:
                # при зацикливании остановки нет: анимация просто запускается
                # снова по таймеру, ровно через свою длительность
                # with looping on nothing stops: the animation simply starts
                # again by the timer, exactly one duration later
                deadline += rule.duration_ms / 1000.0
                if not self._send(f"/anim {variant.name}", rule, quiet=True):
                    self._end_at = deadline
                    return
                continue
            # без зацикливания пора останавливать — так, как выбрано в настройках
            # without looping it is time to stop, the way the settings say
            self._stop_animation(rule)
            # следующая анимация пойдёт через хвост после КОНЦА проигрывания, а
            # потраченное на остановку время из этого хвоста вычитается
            # the next animation starts one tail after the END of the play, and
            # the time spent stopping is taken out of that tail
            self._end_at = deadline
            # подписку не снимаем: меню ещё висит, и игрок может поменять
            # анимацию — тогда она сыграет заново (push_swap)
            # the subscription stays: the menu is still up, and the player may swap
            # the animation — then it plays again (push_swap)
            self._notify_rule_done(rule)
            self._emit("done", variant.name)
            return

    def _choose(self, rule: Rule, token: int = 0) -> "Choice | None":
        """Какой вариант играть / which variant to play.

        Три случая:
        Three cases:

        * вариантов нет или он один — играем его, оверлей не нужен;
          no variants or just one — it plays, no overlay needed;
        * вариантов два и больше, но спросить некого — играем первый, о чём
          честно пишем в журнал;
          two or more variants but nobody to ask — the first plays, and the log
          says so honestly;
        * есть ``chooser`` — спрашиваем игрока; None от него означает отказ, и
          тогда правило пропускается.
          a ``chooser`` is set — the player is asked; None means he backed out and
          the rule is skipped.
        """
        variants = rule.variant_list()
        if not variants:
            log.warning(
                "Анимации: у правила «%s» нет ни названия, ни вариантов", rule.keywords[:40]
            )
            return None
        if not rule.needs_choice():
            return variants[0]
        if self.chooser is None:
            log.warning(
                "Анимации: у правила «%s» %d варианта(ов), но выбрать негде — играю первый (%s)",
                rule.keywords[:40],
                len(variants),
                variants[0].name,
            )
            return variants[0]

        # выбор блокирует очередь: пока оверлей открыт, следующее правило ждёт
        # the choice blocks the queue: while the overlay is open the next rule
        # waits
        # Окно выбора не закрывается после ответа: игрок может передумать и
        # нажать другой вариант, и тогда анимация меняется на ходу.
        # The chooser does not close after the answer: the player may change his
        # mind and press another variant, and then the animation swaps on the fly.
        def on_change(choice):
            # Правило уже не играет — меню всё ещё открыто, и выбор должен
            # сыграть заново, а не пропасть. Это бывает в трёх случаях: правило
            # доиграло само, его остановил игрок (F) или очередь ушла дальше и
            # текущим стало другое правило.
            # The rule is not playing any more — the menu is still up and the pick
            # must replay instead of vanishing. That happens in three cases: the
            # rule ended by itself, the player stopped it (F), or the queue moved
            # on and another rule is current now.
            current = self._current
            if (
                (token and token != self._play_token)
                or current is None
                or not _same_rule(current, rule)
            ):
                self.push_swap(rule, choice)
                return
            with self._lock:
                self._swap_choice = choice

        attach = getattr(self.chooser, "attach", None)
        if callable(attach):
            # меню запоминает, чем сыграть выбор после конца правила
            # the menu remembers what to play a pick with after the rule ends
            attach(rule, lambda choice: self.push_swap(rule, choice))
        try:
            try:
                picked = self.chooser(rule, on_change=on_change)
            except TypeError:
                # заглушка без второго аргумента — обычная функция
                # a stub without the second argument is a plain function
                picked = self.chooser(rule)
        except Exception:
            log.exception("Анимации: выбор варианта не удался")
            return variants[0]
        if picked is None:
            log.info(
                "Анимации: выбор варианта для «%s» отменён — правило пропущено", rule.keywords[:40]
            )
            return None
        log.info(
            "Анимации: выбран вариант «%s» (%s) по правилу «%s»",
            picked.label(),
            picked.name,
            rule.keywords[:40],
        )
        return picked

    def _notify_rule_done(self, rule: "Rule | None" = None) -> None:
        """Сказать окну выбора, что правило доиграло.

        Tell the chooser window that the rule has finished.

        Окно остаётся открытым (закрывает его только игрок), но пометку «играет»
        снимаем: анимация больше не идёт.
        The window stays open (only the player closes it), but the "playing" mark
        is cleared: the animation is not running any more.
        """
        finished = getattr(self.chooser, "rule_finished", None)
        if callable(finished):
            try:
                try:
                    finished(rule)
                except TypeError:
                    # заглушка без параметра / a stub without the parameter
                    finished()
            except Exception:
                log.exception("Анимации: не удалось снять пометку в окне выбора")

    def push_swap(self, rule, choice) -> bool:
        """Меню открыто, а его правило уже доиграло: сыграть выбор заново.

        The menu is still open but its rule has finished: play the pick again.

        Иначе выбор по первому ключу пропадал бы, как только доиграет его
        анимация, — а игрок как раз может вернуться к нему и передумать.
        ``choice is None`` означает «закрыть»: поставленная в очередь анимация
        этого правила снимается, если ещё не началась.
        Otherwise a pick for the first keyword would be lost the moment its
        animation ends — while the player may well come back and change his mind.
        ``choice is None`` means "close": a queued animation of that rule is
        dropped if it has not started yet.
        """
        if choice is None:
            with self._cv:
                self._queue = deque(item for item in self._queue if not _same_rule(item, rule))
                if self._current is not None and _same_rule(self._current, rule):
                    self._stop_run.set()
                self._cv.notify_all()
            return True
        with self._cv:
            self._queue = deque(item for item in self._queue if not _same_rule(item, rule))
            copy = Rule.from_dict(rule.to_dict())
            copy.choices = [choice]
            copy.name = choice.name
            self._queue.appendleft(copy)
            self._ensure_thread()
            self._cv.notify_all()
        log.info("Анимации: выбор по «%s» играет заново (%s)", rule.keywords[:40], choice.name)
        return True

    def _take_swap(self, token: int) -> "Choice | None":
        """Забрать запрошенную смену варианта для этого захода правила.

        Take the requested variant swap for this rule run.
        """
        with self._lock:
            if token != self._play_token:
                return None
            choice, self._swap_choice = self._swap_choice, None
            return choice

    def _withdraw_choice(self, token: int) -> None:
        """Снять подписку на смену варианта: правило доиграло.

        Drop the variant-swap subscription: the rule has finished.
        """
        with self._lock:
            if token == self._play_token:
                self._swap_choice = None

    def _chooser_stopped(self, rule: "Rule | None" = None) -> None:
        """Сказать окну выбора, что анимацию остановили.

        Tell the chooser that the animation was stopped.

        Отдельно от ``_notify_rule_done``: там правило доиграло само, а здесь его
        прервали, и меню по нему отвечать больше не должно.
        Separate from ``_notify_rule_done``: there the rule ended by itself, while
        here it was cut short and its menu must not be answered any more.
        """
        stopped = getattr(self.chooser, "rule_stopped", None)
        if callable(stopped):
            try:
                stopped(rule)
            except TypeError:
                # заглушка без параметра / a stub without the parameter
                stopped()
            except Exception:
                log.exception("Анимации: не удалось снять меню остановленного правила")

    def _drop_choice_window(self, close: bool = False) -> None:
        """Закрыть открытый оверлей выбора, если он есть.

        Close the open chooser window, if any.

        chooser — это функция, но у настоящего оверлея есть ещё и ``cancel``:
        проверяем по наличию метода, чтобы заглушки в проверках оставались
        простыми функциями.
        chooser is a function, but the real overlay also has ``cancel``: it is
        looked up by the method's presence, so plain function stubs stay valid.
        """
        cancel = getattr(self.chooser, "cancel", None)
        if callable(cancel):
            try:
                cancel(close=close)
            except TypeError:
                # заглушка без параметра / a stub without the parameter
                cancel()
            except Exception:
                log.exception("Анимации: не удалось закрыть окно выбора")

    def _send(self, command: str, rule: Rule, quiet: bool = False, force: bool = False) -> bool:
        """Отправить команду и запомнить причину отказа.

        Send the command and remember the reason of a failure. ``quiet`` keeps a
        failed repeat in a loop from flooding the player with messages.

        Здесь же стоят ворота режима «В машине»: пока он включён, команда не
        уходит вовсе — ни `/anim`, ни `/sa`, ни нажатие клавиши (клавиша идёт
        мимо этой функции, поэтому её проверяют отдельно).
        This is also where the "In a vehicle" gate sits: while the mode is on no
        command leaves at all — neither `/anim` nor `/sa`; the key press bypasses
        this function, so it is checked on its own. ``force`` is the one exception:
        the single `/sa` that turns the mode on has to get through, or the pose
        left in the game would be the crooked one.
        """
        if not force and not self.guard_quiet():
            return False
        try:
            ok, message = self.send(command)
        except Exception as error:
            log.exception("Анимации: не удалось отправить %s", command)
            ok, message = False, str(error)[:120]
        if ok:
            log.info("Анимации: отправлено %s", command)
            return True
        self._last_error = message or "команда не отправилась"
        log.warning("Анимации: %s не отправлено — %s", command, self._last_error)
        if not quiet:
            self._emit("error", f"{command}: {self._last_error}")
        return False


# ------------------------------------------------------- клавиша остановки
class StopWatcher(threading.Thread):
    """Следит за клавишей остановки, не забирая её у игры.

    Watches the stop key without taking it away from the game.

    RegisterHotKey перехватил бы клавишу целиком, а остановка анимации в игре —
    это обычная игровая клавиша (по умолчанию F). Поэтому состояние клавиши
    читается через GetAsyncKeyState: игра получает нажатие как обычно, а модуль
    узнаёт о нём со стороны.
    RegisterHotKey would swallow the key, while the in-game animation stop is an
    ordinary game key (F by default). So the key state is read through
    GetAsyncKeyState: the game gets the press as usual and the module notices it
    from the side.
    """

    POLL = 0.04  # 25 раз в секунду / 25 times a second

    def __init__(
        self, spec: str, callback: Callable[[], None], active_fn: Callable[[], bool] | None = None
    ) -> None:
        super().__init__(name="anims-stop", daemon=True)
        self.spec = spec or ""
        self.callback = callback
        self.active_fn = active_fn
        self._stop_flag = threading.Event()
        self._pressed = False
        self._vk = 0
        self._mods = 0
        self._ok = self._prepare()

    # --- подготовка ---
    def _prepare(self) -> bool:
        """Разобрать клавишу и взять функции Windows / parse the key, load Win32."""
        if sys.platform != "win32" or not self.spec.strip():
            return False
        try:
            from app.hotkey import parse_hotkey

            self._mods, self._vk = parse_hotkey(self.spec)
        except Exception as error:
            log.warning("Анимации: клавиша остановки «%s» не разобрана (%s)", self.spec, error)
            return False
        return self._vk > 0

    def _down(self, vk: int) -> bool:
        """Нажата ли клавиша прямо сейчас / is the key down right now."""
        try:
            import ctypes

            return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
        except Exception:
            return False

    def _mods_down(self) -> bool:
        from app.hotkey import MODS

        if not self._mods:
            return True
        pairs = (
            (MODS["alt"], 0x12),
            (MODS["ctrl"], 0x11),
            (MODS["shift"], 0x10),
            (MODS["win"], 0x5B),
        )
        return all(self._down(vk) for mask, vk in pairs if self._mods & mask)

    # --- работа ---
    def stop(self) -> None:
        self._stop_flag.set()

    def run(self) -> None:
        """Опрос клавиши; колбэк — на передний фронт нажатия.

        Poll the key; the callback fires on the rising edge only, so holding the
        key does not repeat the stop over and over.
        """
        if not self._ok:
            return
        while not self._stop_flag.wait(self.POLL):
            try:
                down = self._down(self._vk) and self._mods_down()
                if down and not self._pressed:
                    if self.active_fn is None or self.active_fn():
                        self.callback()
                self._pressed = down
            except Exception:
                log.exception("Анимации: сбой опроса клавиши остановки")
                return


# клавиша остановки: одна клавиша и, при желании, модификаторы
# the stop key: one key and, optionally, modifiers
STOP_KEY_MODS = ("ctrl", "alt", "shift", "win")
STOP_KEY_NAMED = (
    "space",
    "tab",
    "insert",
    "delete",
    "home",
    "end",
    "pageup",
    "pagedown",
    "pause",
    "`",
)
VAL_EMPTY_STOP_KEY = "клавиша остановки не задана"
VAL_BAD_STOP_KEY = "нужна ровно одна клавиша: буква, цифра, F1–F24 или Space"
VAL_UNKNOWN_STOP_KEY = "такая клавиша не поддерживается"


def stop_key_problem(spec: str) -> str:
    """Проверка клавиши остановки; пустая строка — всё в порядке.

    Validation of the stop key; an empty string means it is fine.

    Одиночная буква здесь разрешена: в игре анимацию прекращает обычная клавиша
    (по умолчанию F), и забирать её у игры нельзя.
    A single letter is allowed here: in the game an ordinary key (F by default)
    stops the animation, and the module must not take it away from the game.
    """
    parts = [part.strip().lower() for part in str(spec or "").split("+") if part.strip()]
    if not parts:
        return VAL_EMPTY_STOP_KEY
    keys = [part for part in parts if part not in STOP_KEY_MODS]
    if len(keys) != 1:
        return VAL_BAD_STOP_KEY
    key = keys[0]
    letter = len(key) == 1 and key.isascii() and key.isalnum()
    function = key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24
    if not (letter or function or key in STOP_KEY_NAMED):
        return VAL_UNKNOWN_STOP_KEY
    return ""


def describe_mode(mode: int, english: bool = False) -> str:
    """Короткое название режима для списка / the short mode title for the list."""
    table = MODE_TITLES_EN if english else MODE_TITLES_RU
    return table.get(int(mode), table[MODE_ALWAYS])


def describe_mode_hint(mode: int, english: bool = False) -> str:
    """Полное объяснение режима для подсказки / the full mode explanation."""
    table = MODE_HINTS_EN if english else MODE_HINTS_RU
    return table.get(int(mode), table[MODE_ALWAYS])
