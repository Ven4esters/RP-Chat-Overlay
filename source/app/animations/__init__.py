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

from app.animations.runtime import Runner as Runner, plan as plan


from app.animations.stop import (
    StopWatcher as StopWatcher,
    STOP_KEY_MODS as STOP_KEY_MODS,
    STOP_KEY_NAMED as STOP_KEY_NAMED,
    VAL_BAD_STOP_KEY as VAL_BAD_STOP_KEY,
    VAL_EMPTY_STOP_KEY as VAL_EMPTY_STOP_KEY,
    VAL_UNKNOWN_STOP_KEY as VAL_UNKNOWN_STOP_KEY,
    stop_key_problem as stop_key_problem,
)


from app.animations.hints import (
    MODE_FAMILY_ACTIONS as MODE_FAMILY_ACTIONS,
    MODE_FAMILY_ALWAYS as MODE_FAMILY_ALWAYS,
    MODE_FAMILY_EMOTES as MODE_FAMILY_EMOTES,
    MODE_FAMILY_MESSAGES as MODE_FAMILY_MESSAGES,
    Hint as Hint,
    complete as complete,
    current_word as current_word,
    family_hits as family_hits,
    family_of_mode as family_of_mode,
    message_family as message_family,
    suggestions as suggestions,
)


from app.animations.rules import (
    ANIM_EXTRA_MS as ANIM_EXTRA_MS,
    Choice as Choice,
    Context as Context,
    DEFAULT_MS as DEFAULT_MS,
    EMOTE_COMMANDS as EMOTE_COMMANDS,
    GAP_WORDS as GAP_WORDS,
    LEGACY_MODES as LEGACY_MODES,
    MAX_CHOICES as MAX_CHOICES,
    MAX_DESC as MAX_DESC,
    MAX_EXTRA_MS as MAX_EXTRA_MS,
    MAX_GROUP as MAX_GROUP,
    MAX_MS as MAX_MS,
    MAX_QUEUE as MAX_QUEUE,
    MAX_TITLE as MAX_TITLE,
    MIN_MS as MIN_MS,
    MODES as MODES,
    MODE_ACTIONS as MODE_ACTIONS,
    MODE_ALWAYS as MODE_ALWAYS,
    MODE_EMOTES as MODE_EMOTES,
    MODE_HINTS_EN as MODE_HINTS_EN,
    MODE_HINTS_RU as MODE_HINTS_RU,
    MODE_MESSAGES as MODE_MESSAGES,
    MODE_TITLES_EN as MODE_TITLES_EN,
    MODE_TITLES_RU as MODE_TITLES_RU,
    NEG_LOOKBACK as NEG_LOOKBACK,
    NEG_MARKERS as NEG_MARKERS,
    NICK_COMMANDS as NICK_COMMANDS,
    Rule as Rule,
    TALK_COMMANDS as TALK_COMMANDS,
    VAL_BAD_MODE as VAL_BAD_MODE,
    VAL_BAD_MS as VAL_BAD_MS,
    VAL_BAD_NAME as VAL_BAD_NAME,
    VAL_EMPTY_KEYWORD as VAL_EMPTY_KEYWORD,
    VAL_EMPTY_NAME as VAL_EMPTY_NAME,
    VAL_TOO_MANY_CHOICES as VAL_TOO_MANY_CHOICES,
    action_spans as action_spans,
    analysed_spans as analysed_spans,
    keywords_of as keywords_of,
    merge_choices as merge_choices,
    merge_keywords as merge_keywords,
    merge_rules as merge_rules,
    parse_message_span as parse_message_span,
    rules_from_cfg as rules_from_cfg,
    rules_to_cfg as rules_to_cfg,
    select_spans as select_spans,
)


def describe_mode(mode: int, english: bool = False) -> str:
    """Короткое название режима для списка / the short mode title for the list."""
    table = MODE_TITLES_EN if english else MODE_TITLES_RU
    return table.get(int(mode), table[MODE_ALWAYS])


def describe_mode_hint(mode: int, english: bool = False) -> str:
    """Полное объяснение режима для подсказки / the full mode explanation."""
    table = MODE_HINTS_EN if english else MODE_HINTS_RU
    return table.get(int(mode), table[MODE_ALWAYS])


__all__ = [name for name in globals() if not name.startswith("_")]
