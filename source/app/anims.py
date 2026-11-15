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
from typing import Any, Callable, Iterable, Mapping

from app import morph
from app.config import log

# ---------------------------------------------------------------- режимы чтения
MODE_ALWAYS = 1        # любое сообщение / any message
MODE_EMOTES = 2        # только /me, /ame, /melow, /melong
MODE_ACTIONS = 3       # только текст между *звёздочками* / only *between asterisks*
MODE_MESSAGES = 4      # обычные сообщения и /to, /lto, /l, /s, /w, /wt

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
EMOTE_COMMANDS = ("/me", "/ame", "/melow", "/melong")
# «настоящие сообщения»: обычный текст и эти команды
TALK_COMMANDS = ("/to", "/lto", "/l", "/s", "/w", "/wt")
# у этих команд первым словом идёт получатель, его анализировать нельзя
NICK_COMMANDS = ("/to", "/lto")

# Маркеры отрицания: если такой стоит перед найденным словом, правило молчит.
# Ключ, в котором отрицание уже есть («не открыл зонт»), проверку выключает.
# Negation markers: one of them right before a matched word silences the rule.
# A keyword that already carries a negation switches the check off.
NEG_MARKERS = frozenset({
    "не", "ни", "нет", "нельзя", "нечем", "некого", "нечего", "незачем",
    "никуда", "никто", "ничего", "никогда", "нигде", "никак", "ничуть",
    "not", "never", "nobody", "nothing", "nowhere", "neither", "nor",
})
NEG_LOOKBACK = 3       # сколько слов смотрим перед найденным / words looked back
_PUNCT_RE = re.compile(r"[.,;:!?…—–]")   # граница куска: дальше отрицание не ищем

# 0 мс — особый случай: анимацию не останавливаем вовсе
# 0 ms is a special case: the animation is never stopped
MIN_MS, MAX_MS, DEFAULT_MS = 0, 600000, 3000
MAX_QUEUE = 20           # больше — очередь не растёт, лишнее отбрасывается
# Хвост после анимации: сколько добавить к её собственному времени проигрывания,
# прежде чем запустить следующую из очереди. Отсчёт идёт от отправки `/anim`,
# то есть «проиграла 1500 мс + 50 мс — играет следующая». Задача хвоста — дать
# игре закрыть чат после остановки и серверу принять новую команду.
# The tail after an animation: how much to add to its own play time before the
# next one in the queue starts. The count starts at the `/anim` send, so "played
# 1500 ms + 50 ms, then the next one plays". The tail gives the game time to close
# its chat after the stop and the server time to take the new command.
ANIM_EXTRA_MS = 50
MAX_EXTRA_MS = 10000     # больше ставить бессмысленно / a longer tail makes no sense

_CMD_RE = re.compile(r"^\s*(/\S+)\s*")
_NICK_RE = re.compile(r"\s*\S+\s+")          # получатель в /to и /lto / the recipient
_ACTION_RE = re.compile(r"\*([^*]+)\*")
_WORD_RE = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", re.UNICODE)   # слова с позициями

VAL_EMPTY_KEYWORD = "ключевое слово не задано"
VAL_EMPTY_NAME = "название анимации не задано"
VAL_BAD_NAME = "в названии анимации не должно быть пробелов и косых черт"
VAL_BAD_MS = "длительность должна быть от 0 до 600000 мс"
VAL_BAD_MODE = "такой режим считывания не поддерживается"


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
        body = body[nick.end():]
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


def _with_actions(spans: list[tuple[int, str]], text: str,
                  start: int) -> list[tuple[int, str]]:
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


def keywords_of(text: str) -> list[str]:
    """Ключевые слова правила: запятая, точка с запятой или перевод строки.

    The rule keywords: comma, semicolon or a line break separates them.
    """
    return [part.strip() for part in re.split(r"[,;\n]+", text or "") if part.strip()]


# сколько посторонних слов допускается внутри ключевой фразы: «открыл зонт»
# находит и «открыл чёрный зонт»
# how many foreign words may sit inside a keyword phrase
GAP_WORDS = 1


def _words_of(chunk: str) -> list[tuple[int, int, str]]:
    """Слова куска текста: (начало, конец, слово) / the words of a chunk."""
    return [(match.start(), match.end(), match.group(0))
            for match in _WORD_RE.finditer(chunk)]


def _negated(chunk: str, words: list[tuple[int, int, str]],
             indices: list[int]) -> bool:
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
            if _PUNCT_RE.search(chunk[words[back][1]:words[back + 1][0]]):
                break
            if morph.norm(words[back][2]) in NEG_MARKERS:
                return True
    return False


def _keyword_negated(keyword: str) -> bool:
    """Есть ли отрицание в самом ключе / does the keyword itself negate."""
    return any(morph.norm(word) in NEG_MARKERS for word in _WORD_RE.findall(keyword))


def _phrase_hits(words: list[tuple[int, int, str]], word_keys: list[frozenset[str]],
                 chunk: str, keyword: str, keys: "morph.KeyCache", forms: int,
                 negation: bool = True) -> list[tuple[int, str]]:
    """Совпадения ключевой фразы в куске текста: (смещение, найденный текст).

    Every match of the keyword phrase in a chunk: (offset, the text found).

    Слова фразы ищутся по порядку, между ними допускается не больше
    ``GAP_WORDS`` посторонних слов; на уровне «Точно» — только вплотную.
    ``negation`` включает проверку отрицания (кроме ключей, где оно уже есть).
    The phrase words are matched in order with at most ``GAP_WORDS`` words in
    between (the "Exact" level wants them adjacent). ``negation`` turns the
    negation check on — except for keywords that already negate themselves.
    """
    want = [keys(word, forms) for word in _WORD_RE.findall(keyword)]
    if not want:
        return []
    check = negation and not _keyword_negated(keyword)
    gap = 0 if forms == morph.FORMS_EXACT else GAP_WORDS
    found: list[tuple[int, str]] = []
    for index in range(len(words)):
        if not word_keys[index] & want[0]:
            continue
        previous = index
        matched = [index]
        for need in want[1:]:
            step = previous + 1
            last = previous + 1 + gap
            while step <= last and step < len(words) and not word_keys[step] & need:
                step += 1
            if step >= len(words) or not word_keys[step] & need:
                previous = -1
                break
            previous = step
            matched.append(step)
        if previous < 0:
            continue
        if check and _negated(chunk, words, matched):
            log.info("Анимации: «%s» найдено, но отрицание — пропуск",
                     chunk[words[index][0]:words[previous][1]])
            continue
        start, end = words[index][0], words[previous][1]
        found.append((start, chunk[start:end].strip()))
    return found


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
    _phrases: dict[str, list[tuple[int, int, str]]] = field(default_factory=dict,
                                                           repr=False)

    def key_of(self, phrase: str) -> str:
        """Ключ словаря для фразы; пусто — фразы нет в словаре."""
        if self.equivalent is None:
            return ""
        try:
            return str(self.equivalent(phrase) or "")
        except Exception:
            return ""

    def phrases(self, chunk: str) -> list[tuple[int, int, str]]:
        """Фразы словаря в куске текста, с кэшем на сообщение."""
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
class Rule:
    """Правило анимации / one animation rule."""

    keywords: str = ""
    name: str = ""                       # название для /anim
    mode: int = MODE_ALWAYS
    forms: int = morph.FORMS_DEFAULT     # как сравнивать словоформы / word forms
    duration_ms: int = DEFAULT_MS
    loop: bool = False
    enabled: bool = True
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    # --- проверка ---
    def problem(self) -> str:
        """Что не так с правилом; пустая строка — всё в порядке.

        What is wrong with the rule; an empty string means it is fine.
        """
        if not keywords_of(self.keywords):
            return VAL_EMPTY_KEYWORD
        name = self.name.strip()
        if not name:
            return VAL_EMPTY_NAME
        if re.search(r"[\s/]", name):
            return VAL_BAD_NAME
        if not isinstance(self.duration_ms, int) or not MIN_MS <= self.duration_ms <= MAX_MS:
            return VAL_BAD_MS
        if self.mode not in MODES:
            return VAL_BAD_MODE
        return ""

    def ready(self) -> bool:
        """Правило можно исполнять / the rule can actually run."""
        return self.enabled and not self.problem()

    # --- сопоставление ---
    def scan(self, text: str, ctx: "Context | None" = None
             ) -> tuple[list[str], list[int]]:
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

    def hits(self, text: str, ctx: "Context | None" = None
             ) -> list[tuple[int, str]]:
        """Срабатывания правила по порядку: (место в тексте, найденный текст).

        Два разных ключа в одном сообщении дают два срабатывания, повтор того
        же слова — одно.
        The hits of the rule in order: (position, the text found). Two different
        keywords in one message give two hits, a repeated word gives one.
        """
        if not self.enabled:
            return [], []
        keywords = keywords_of(self.keywords)
        if not keywords:
            return [], []
        ctx = ctx or Context()
        hits: list[tuple[int, str]] = []
        for start, chunk in analysed_spans(text, self.mode):
            words = _words_of(chunk)
            word_keys = [ctx.keys(word, self.forms) for _, _, word in words]
            phrases = ctx.phrases(chunk)
            claimed: list[tuple[int, int]] = []      # уже занятые места в куске
            for keyword in keywords:
                here: list[tuple[int, str]] = list(
                    _phrase_hits(words, word_keys, chunk, keyword, ctx.keys,
                                 self.forms, ctx.negation))
                key = ctx.key_of(keyword)
                # синонимы подключаются, только если самого ключа в тексте нет
                # synonyms only step in when the keyword itself is absent
                if key and not here:
                    for offset, end, phrase_key in phrases:
                        if phrase_key != key:
                            continue
                        index = next((i for i, word in enumerate(words)
                                      if word[0] >= offset), None)
                        if index is None:
                            continue
                        if (ctx.negation and not _keyword_negated(keyword)
                                and _negated(chunk, words, [index])):
                            log.info("Анимации: «%s» найдено, но отрицание — пропуск",
                                     chunk[offset:end])
                            continue
                        here.append((offset, chunk[offset:end].strip()))
                if not here:
                    continue
                here.sort(key=lambda item: item[0])
                # одно срабатывание на ключ: повтор того же слова второй раз не
                # играет, а место берётся первое, ещё никем не занятое —
                # так «да ну» и «да брось» в одной фразе дают два срабатывания
                # one hit per keyword: a repeated word plays once, and the place
                # is the first still free one, so «да ну» plus «да брось» in one
                # phrase fire twice
                span = None
                for offset, form in here:
                    candidate = (offset, offset + len(form))
                    if any(candidate[0] < other_end and other_start < candidate[1]
                           for other_start, other_end in claimed):
                        continue
                    span = candidate
                    break
                if span is None:
                    continue
                claimed.append(span)
                hits.append((start + span[0], chunk[span[0]:span[1]].strip()))
        hits.sort(key=lambda item: item[0])
        return hits

    def matches(self, text: str, ctx: "Context | None" = None) -> list[str]:
        """Какие слова нашлись в сообщении / which words matched."""
        return self.scan(text, ctx)[0]

    # --- хранение ---
    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "keywords": self.keywords, "name": self.name.strip(),
                "mode": int(self.mode), "forms": int(self.forms),
                "duration_ms": int(self.duration_ms),
                "loop": bool(self.loop), "enabled": bool(self.enabled)}

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
        mode = LEGACY_MODES.get(mode, mode)      # старый режим 5 -> «Всегда»
        if mode not in MODES:
            mode = MODE_ALWAYS
        forms = _int(data.get("forms"), morph.FORMS_DEFAULT)
        if forms not in morph.FORMS:
            forms = morph.FORMS_DEFAULT
        return cls(
            keywords=str(data.get("keywords") or ""),
            name=str(data.get("name") or "").strip().lstrip("/"),
            mode=mode,
            forms=forms,
            duration_ms=min(MAX_MS, max(MIN_MS, _int(data.get("duration_ms"), DEFAULT_MS))),
            loop=bool(data.get("loop")),
            enabled=bool(data.get("enabled", True)),
            id=str(data.get("id") or uuid.uuid4().hex[:8]),
        )


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


# ------------------------------------------------------------------ исполнитель
class Runner:
    """Очередь анимаций: `/anim` -> пауза -> `/sa`, при зацикливании по кругу.

    The animation queue: `/anim` -> wait -> `/sa`, repeating while looping.

    send     функция отправки команды в игру: str -> (успех, сообщение);
             a function that sends a command to the game: str -> (ok, message)
    on_event колбэк (вид, текст): «error», «playing», «done», «stopped»;
             a callback (kind, text) for the interface and the player
    """

    def __init__(self, cfg: Mapping[str, Any] | None = None,
                 send: Callable[[str], tuple[bool, str]] | None = None,
                 on_event: Callable[[str, str], None] | None = None,
                 equivalent: Callable[[str], str] | None = None,
                 press_key: Callable[[str], tuple[bool, str]] | None = None,
                 text_keys: Callable[[str], list[tuple[int, int, str]]] | None = None
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
        """
        self.cfg: Mapping[str, Any] = cfg or {}
        self.send = send or (lambda command: (False, "отправка недоступна"))
        self.on_event = on_event
        self.equivalent = equivalent
        self.press_key = press_key
        self.text_keys = text_keys
        self._rules: list[Rule] = rules_from_cfg(self.cfg)
        self._queue: deque[Rule] = deque()
        self._lock = threading.RLock()
        self._cv = threading.Condition(self._lock)
        self._thread: threading.Thread | None = None
        self._done = threading.Event()
        self._end_at = 0.0                      # конец проигрывания, monotonic
        self._quiet_off = False                 # про выключенный модуль пишем раз
        self._stop_run = threading.Event()      # прервать текущий цикл / abort the run
        self._current: Rule | None = None
        self._last_error = ""
        self._last_trigger = ""
        self._reset_pending = False     # после остановки игроком отправить /sa
                                        # send /sa after a stop by the player

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
        if not (text or "").strip():
            return []
        self._quiet_off = False
        ctx = Context(equivalent=self.equivalent, text_keys=self.text_keys,
                      negation=self.negation())
        hits: list[tuple[int, int, Rule]] = []
        for index, rule in enumerate(self.rules()):
            if not rule.ready():
                continue
            found, positions = rule.scan(text, ctx)
            if not positions:
                continue
            # одно срабатывание на каждое ключевое слово правила: разные ключи
            # играют подряд, повтор того же слова — только раз
            # one hit per keyword of the rule: different keywords play in turn,
            # a repeated word plays once
            log.info("Анимации: «%s» по правилу «%s» (%s) -> /anim %s, "
                     "срабатываний: %d",
                     text[:60], rule.keywords[:40], ", ".join(found), rule.name,
                     len(positions))
            for position in positions:
                hits.append((position, index, rule))
        hits.sort(key=lambda item: (item[0], item[1]))     # позиция, потом таблица
        log.info("Анимации: в очередь %s", " -> ".join("/anim " + rule.name
                                                       for _, _, rule in hits))
        for _, _, rule in hits:
            self._enqueue(rule)
        return [rule for _, _, rule in hits]

    def _enqueue(self, rule: Rule) -> None:
        copy = Rule.from_dict(rule.to_dict())      # снимок на момент срабатывания
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
            log.info("Анимации: очередь снята (%s)", ", ".join("/anim " + name
                                                              for name in dropped))
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
            return {"enabled": self.enabled(), "rules": len(self._rules),
                    "current": self._current.name if self._current else "",
                    "loop": bool(self._current and self._current.loop),
                    "queued": len(self._queue), "error": self._last_error,
                    "trigger": self._last_trigger}

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
                log.warning("Анимации: клавиша «%s» не нажалась — %s", spec,
                            self._last_error)

    def _play(self, rule: Rule) -> None:
        """Один заход правила: /anim -> пауза -> остановка или снова /anim.

        One rule run: /anim -> wait -> stop, or /anim again while looping.

        Длительность 0 мс означает «не останавливать»: уходит только `/anim`.
        A duration of 0 ms means "never stop": only `/anim` is sent.
        """
        self._stop_run.clear()
        with self._lock:
            self._current = rule
        self._emit("playing", rule.name)
        # время проигрывания считается от отправки `/anim`: сама отправка тоже
        # занимает время (фокус в игру, чат, вставка, Enter), и оно входит в
        # длительность, иначе каждая пауза незаметно удлинялась бы на полсекунды
        # the play time counts from the `/anim` send: the send itself takes time
        # (focus, game chat, paste, Enter), and it belongs to the duration —
        # otherwise every pause would quietly grow by half a second
        started = time.monotonic()
        if not self._send(f"/anim {rule.name}", rule):
            self._end_at = started
            return
        if rule.duration_ms <= 0:
            # 0 мс: анимацию не останавливаем — ни /sa, ни клавишей
            # 0 ms: the animation is not stopped at all
            self._end_at = started
            self._emit("done", rule.name)
            return
        deadline = started + rule.duration_ms / 1000.0
        while True:
            if self._wait(max(0.0, deadline - time.monotonic())):
                # анимацию остановили клавишей игрока: гасим её выбранным способом
                # the player stopped the animation: put it out the chosen way
                if self._reset_pending:
                    self._reset_pending = False
                    self._stop_animation(rule)
                self._end_at = time.monotonic()
                return
            if rule.loop:
                # при зацикливании остановки нет: анимация просто запускается
                # снова по таймеру, ровно через свою длительность
                # with looping on nothing stops: the animation simply starts
                # again by the timer, exactly one duration later
                deadline += rule.duration_ms / 1000.0
                if not self._send(f"/anim {rule.name}", rule, quiet=True):
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
            self._emit("done", rule.name)
            return

    def _wait(self, seconds: float) -> bool:
        """Пауза с возможностью прервать; True — прервали.

        A pause that can be interrupted; True means it was.
        """
        return self._stop_run.wait(max(0.0, seconds))

    def _send(self, command: str, rule: Rule, quiet: bool = False) -> bool:
        """Отправить команду и запомнить причину отказа.

        Send the command and remember the reason of a failure. ``quiet`` keeps a
        failed repeat in a loop from flooding the player with messages.
        """
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

    POLL = 0.04        # 25 раз в секунду / 25 times a second

    def __init__(self, spec: str, callback: Callable[[], None],
                 active_fn: Callable[[], bool] | None = None) -> None:
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
            log.warning("Анимации: клавиша остановки «%s» не разобрана (%s)",
                        self.spec, error)
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
        pairs = ((MODS["alt"], 0x12), (MODS["ctrl"], 0x11),
                 (MODS["shift"], 0x10), (MODS["win"], 0x5B))
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
STOP_KEY_NAMED = ("space", "tab", "insert", "delete", "home", "end", "pageup",
                  "pagedown", "pause", "`")
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
