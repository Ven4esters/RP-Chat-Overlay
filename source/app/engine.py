"""Разбор сообщения и словарь / message parsing and glossary.

Что делает движок / what the engine does
----------------------------------------
Сообщение игрока превращается в две версии: русскую запись (её видно в оверлее)
и текст на языке сервера (он уходит в чат). По дороге разбираются +маркеры+,
*действия*, словарь, слова-паразиты, автоперевод и служебные команды.
A player message turns into two versions: the Russian reading (shown in the
overlay) and the text in the server language (sent to the chat). On the way the
engine handles +markers+, *actions*, the glossary, filler words, auto-translation
and service commands.

Правила, которые нельзя менять / rules that must not change
-----------------------------------------------------------
  * слова-паразиты переводятся в КАЖДОМ сообщении / filler words in every message;
  * команды /to /lto /l /wt /s /st считаются сообщениями, остальные нет;
    /to /lto /l /wt /s /st count as messages, other commands do not;
  * *действия* переводятся, служебные команды и ники — нет;
    *actions* are translated, service commands and nicknames are not;
  * язык берётся из словаря, итальянский нигде не зашит;
    the language comes from the glossary, nothing is hard-coded for Italian.

Модули / modules: словарь (glossary), сокращения (slang) и перевод по сети
(translator) можно выключить — движок продолжит работать в урезанном виде.
The glossary, slang and online translation can be disabled; the engine keeps
working in a reduced form.
"""

from __future__ import annotations

import random
import re
import shutil
from dataclasses import dataclass
from typing import Any, Mapping

from app import modules, morph, slang
from app.config import GLOSSARY_DIR, GLOSSARY_PATH, log, read_json, write_json
from app.langpacks import empty_pack, get_pack
from app.langs import code_of, get as get_lang
from app.translit import apply_case, has_reading, norm as _norm, translit_word
from app.usage_report import measure_call


@dataclass(frozen=True, slots=True)
class Result:
    """Готовый разбор сообщения / one parsed message.

    text        что показываем и отправляем по умолчанию (русская запись или
                русский перевод в обратном режиме) / the main text
    native      вторая сторона: текст на языке сервера (обычный режим) или
                исходное сообщение игрока (обратный режим) / the other side
    translated  перевод действительно был / the text was really translated
    """

    text: str
    native: str
    translated: bool


def norm(text: str) -> str:
    """Ключ сравнения: без регистра, ударений и знаков по краям; е=ё, и=й.

    Comparison key: case, accents and edge punctuation removed; ё=е and й=и.
    """
    return _norm(text).replace("й", "и")


PH_RE = re.compile(r"\ue000(\d+)\ue000")
ACT_RE = re.compile(r"\*[^*]*(?:\*|$)")  # незакрытое действие — до конца строки
CYR_RE = re.compile(r"[А-Яа-яЁё]")
CYR_WORD_RE = re.compile(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*")
WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ’']+")
TAIL_RE = re.compile(r"[.!?…]+$")

# служебные слова: сами по себе (и на краях фрагмента) в автоперевод не берутся
# function words: alone, and at the edges of a fragment, they never
# go into auto-translation
STOP = {
    norm(w)
    for w in (
        "и в во на с со к ко у о об от по за из для при про без до не ни но а да что как это то "
        "я ты он она оно мы вы они мне тебе меня тебя ему ей нам вам их же бы ли вот вон тут там "
        "уж ну же или либо чтобы если когда мой моя моё мои твой твоя твоё твои наш ваш"
    ).split()
}

# ---------- команды, которые считаются сообщениями ----------
# /to, /lto, /l, /wt, /s, /st — это настоящие сообщения другим игрокам,
# поэтому они участвуют в счётчике автоперевода (AutoPlan) наравне с обычным текстом.
# Остальные команды (/me, /do, /b, /g, ...) в счётчик НЕ идут и не автопереводятся.
COUNTED_COMMANDS = {"/to", "/lto", "/l", "/wt", "/s", "/st"}
NICK_COMMANDS = {"/to", "/lto"}  # после команды идёт ник, его переводить нельзя
_CMD_TOKEN_RE = re.compile(r"^\s*(/\S+)")
_CMD_PREFIX_RE = re.compile(r"^\s*/\S+\s*")
_NICK_RE = re.compile(r"\S+\s*")


def get_command(text: str) -> str:
    """Команда в начале сообщения (в нижнем регистре) или "" если её нет.

    The command at the start of a message in lower case, or "" when absent.
    """
    m = _CMD_TOKEN_RE.match(text or "")
    return m.group(1).lower() if m else ""


def is_counted_command(text: str) -> bool:
    """True, если сообщение — одна из команд /to /lto /l /wt /s /st.

    True when the message is one of /to /lto /l /wt /s /st, which count as
    ordinary messages in the auto-translation series.
    """
    return get_command(text) in COUNTED_COMMANDS


def split_prefix(text: str) -> tuple[str, str, bool, bool]:
    """Разбирает команду: (префикс, тело, есть_команда, команда_учитывается).

    Splits a command off: (prefix, body, has_command, command_is_counted).

    Для /to и /lto в префикс входит и ник: "/to Ivan привет" -> ("/to Ivan ", "привет").
    Для остальных команд префикс — только сама команда: "/l привет" -> ("/l ", "привет").
    """
    m = _CMD_PREFIX_RE.match(text or "")
    if not m:
        return "", text or "", False, False
    cmd = get_command(text)
    prefix, body = m.group(0), text[m.end() :]
    if cmd in NICK_COMMANDS:
        nick = _NICK_RE.match(body)
        if nick:
            prefix += nick.group(0)
            body = body[nick.end() :]
    return prefix, body, True, cmd in COUNTED_COMMANDS


# ---------- слова-паразиты: переводятся ВСЕГДА ----------
# Список слов-паразитов хранится в словаре языка (ключ "_fillers"), поэтому
# для каждого языка он свой: итальянские Senti / Ma dai, испанские Oye / No manches,
# китайские 那个 / 没办法 и т.д. Русские формы — то, что пользователь печатает в чате.
# Они переводятся в КАЖДОМ сообщении, вне зависимости от счётчика автоперевода
# (auto_every) и от того, попало ли сообщение в «переводимый» номер серии.


def keep_edges(orig: str, translated: str) -> str:
    """Сохраняет пробелы по краям фрагмента: переводчик их срезает.

    Keeps the leading and trailing spaces the translator strips, so that
    "*машет рукой* ciao" does not glue into "*машет рукой*привет".

    Без этого «*машет рукой* ciao» склеивалось в «*машет рукой*привет».
    """
    if not translated:
        return orig
    lead = orig[: len(orig) - len(orig.lstrip())]
    tail = orig[len(orig.rstrip()) :]
    return lead + translated.strip() + tail


def _filler_key(s):
    """Ключ сравнения паразита: без регистра, ё/й, знаков и лишних пробелов.

    The comparison key of a filler: no case, ё/й, punctuation or extra spaces.
    """
    return " ".join(re.sub(r"[^\w\s]", " ", norm(s)).split())


def _filler_spans(body, g):
    """Находит все вхождения паразитов в body (без учёта уже расставленных маркеров).

    Возвращает список (start, end), отсортированный по началу, без пересечений,
    самые длинные фразы побеждают короткие.
    """
    ms = list(CYR_WORD_RE.finditer(body))
    if not ms:
        return []
    cands = []
    maxw = g.filler_max_words
    for i in range(len(ms)):
        for n in range(min(maxw, len(ms) - i), 0, -1):
            j = i + n - 1
            # слова подряд, между ними только пробелы/запятые (без действий )
            # consecutive words with only spaces or commas between them (no actions)
            ok = True
            for x in range(i, j):
                sep = body[ms[x].end() : ms[x + 1].start()]
                if "\ue000" in sep or sep.strip(" ,") != "":
                    ok = False
                    break
            if not ok:
                continue
            frag = body[ms[i].start() : ms[j].end()]
            # Фраза словаря главнее списка паразитов: «ну, значит» переводится как
            # готовая фраза, а не как два отдельных паразита.
            # A glossary phrase wins over the filler list: it goes as one ready
            # phrase instead of two separate fillers.
            if _filler_key(frag) in g.filler_keys and g.find_meaning(frag) is not None:
                cands.append((ms[i].start(), ms[j].end(), n))
                break  # самая длинная фраза с этой позиции уже найдена
    cands.sort(key=lambda c: (-c[2], c[0]))
    picked = []
    for s, e, _n in cands:
        if all(e <= ps or s >= pe for ps, pe in picked):
            picked.append((s, e))
    return sorted(picked)


def wrap_fillers(body: str, cfg: Mapping[str, Any], glossary: "Glossary") -> str:
    """Оборачивает слова-паразиты в маркеры (только вне +маркеров+ и *действий*).

    Wraps filler words in markers, skipping the text inside +markers+ and
    inside *actions*, which are already handled separately.
    """
    o, c = cfg["marker_open"], cfg["marker_close"]
    rx = _marker_rx(cfg)
    marked = [(m.start(), m.end()) for m in rx.finditer(body)]
    if marked:
        # режем тело на куски вне маркеров и обрабатываем каждый отдельно
        # split the body into the parts outside markers and handle each one
        out, pos = [], 0
        for start, end in marked:
            out.append(_wrap_fillers_plain(body[pos:start], o, c, glossary))
            out.append(body[start:end])
            pos = end
        out.append(_wrap_fillers_plain(body[pos:], o, c, glossary))
        return "".join(out)
    return _wrap_fillers_plain(body, o, c, glossary)


def _wrap_fillers_plain(body, o, c, g):
    for s, e in sorted(_filler_spans(body, g), reverse=True):
        body = body[:s] + o + body[s:e] + c + body[e:]
    return body


def has_fillers(text: str, cfg: Mapping[str, Any], glossary: "Glossary") -> bool:
    """Есть ли в сообщении слово-паразит, которое нужно перевести.

    True when the message contains a filler word that has to be translated.
    """
    _prefix, body, is_cmd, is_counted = split_prefix(text)
    if is_cmd and not is_counted:
        return False
    body, _acts = hide_actions(body)
    return wrap_fillers(body, cfg, glossary) != body


# ---------- действия ----------
def hide_actions(text: str) -> tuple[str, list[str]]:
    """Прячет *действия* за метками, чтобы остальной разбор их не трогал.

    Hides *actions* behind placeholders so the rest of the parsing ignores them.
    """
    acts = []

    def rep(m):
        acts.append(m.group(0))
        return "\ue000%d\ue000" % (len(acts) - 1)

    return ACT_RE.sub(rep, text), acts


def restore_actions(text: str, acts: list[str]) -> str:
    """Возвращает *действия* на место после разбора / puts *actions* back."""
    return PH_RE.sub(lambda m: acts[int(m.group(1))], text)


def split_tail(text: str) -> tuple[str, str]:
    """Отделяет знаки в конце: «Привет!» -> («Привет», «!») / splits the tail."""
    m = TAIL_RE.search(text)
    return (text[: m.start()], m.group(0)) if m else (text, "")


def up_first(text: str) -> str:
    """Поднимает первую букву фразы / capitalises the first letter."""
    for i, ch in enumerate(text):
        if ch.isalpha():
            return text[:i] + ch.upper() + text[i + 1 :]
    return text


def _marker_rx(cfg):
    return re.compile(
        re.escape(cfg["marker_open"]) + r"(.+?)" + re.escape(cfg["marker_close"]), re.S
    )


def has_markers(text: str, cfg: Mapping[str, Any]) -> bool:
    """Есть ли в сообщении свои +маркеры+ / are there any +markers+ in the text."""
    body, _ = hide_actions(text)
    return bool(_marker_rx(cfg).search(body))


def strip_markers(text: str, cfg: Mapping[str, Any]) -> str:
    """Убирает маркеры, оставляя текст внутри (отправка без перевода).

    Removes the markers and keeps the text between them (send without translating).
    """
    body, acts = hide_actions(text)
    return restore_actions(_marker_rx(cfg).sub(r"\1", body), acts)


# ---------- автоперевод: случайный фрагмент ----------
# auto-translation: a random fragment
def _int(cfg, key, default):
    try:
        return int(cfg.get(key, default))
    except (TypeError, ValueError):
        return default


def auto_wrap(body: str, cfg: Mapping[str, Any], glossary: "Glossary", seed: float) -> str:
    """Оборачивает в маркеры один или несколько фрагментов (слово, словосочетание).
    Выбор «случайный», но для одного seed и одного фрагмента всегда одинаковый,
    поэтому результат не прыгает, пока пользователь дописывает текст."""
    o, c = cfg["marker_open"], cfg["marker_close"]
    lo = max(1, _int(cfg, "auto_min_words", 1))
    hi = max(lo, _int(cfg, "auto_max_words", 3))
    count = max(1, _int(cfg, "auto_fragments", 1))
    prefer = bool(cfg.get("auto_prefer_glossary", True))
    ms = list(CYR_WORD_RE.finditer(body))
    cands = []
    for i in range(len(ms)):
        for n in range(lo, hi + 1):
            j = i + n - 1
            if j >= len(ms):
                break
            # слова должны идти подряд, только через пробелы (без знаков и действий между ними)
            # the words must follow each other through spaces only (no punctuation,
            # no actions between them)
            if any(body[ms[x].end() : ms[x + 1].start()].strip() for x in range(i, j)):
                break
            frag = body[ms[i].start() : ms[j].end()]
            words = [norm(ms[x].group()) for x in range(i, j + 1)]
            known = glossary.find_meaning(frag) is not None
            filler = _filler_key(frag) in glossary.filler_keys and known
            if not known and (
                all(w in STOP for w in words) or words[0] in STOP or words[-1] in STOP
            ):
                continue
            score = random.Random("%s|%s" % (seed, norm(frag))).random()
            if known and prefer:
                score += 1.0
            if filler:  # слова-паразиты в автопереводе — в первую очередь
                score += 2.0
            cands.append((score, ms[i].start(), ms[j].end()))
    picked = []
    for _, s, e in sorted(cands, reverse=True):
        if len(picked) >= count:
            break
        if all(e <= ps or s >= pe for ps, pe in picked):
            picked.append((s, e))
    for s, e in sorted(picked, reverse=True):
        body = body[:s] + o + body[s:e] + c + body[e:]
    return body


# ---------- словарь ----------
def glossary_path(lang: str = "it"):
    """Файл словаря языка: data/glossaries/<код>.json.

    The glossary file of one language: data/glossaries/<code>.json.
    """
    return GLOSSARY_DIR / ("%s.json" % code_of(lang))


def _pack_default(pack):
    """Встроенный пакет языка в формате файла словаря.

    The built-in language pack in the glossary file format.
    """
    return {
        "_version": int(pack.get("version", 1)),
        "phrases": dict(pack.get("phrases") or {}),
        "replace": dict(pack.get("replace") or {}),
        "exceptions": dict(pack.get("exceptions") or {}),
    }


def _phrase_parts(val):
    """«транскрипция | значение 1; значение 2» -> (транскрипция, [значения]).

    "transcription | meaning 1; meaning 2" -> (transcription, [meanings]).
    """
    ru, _, meanings = str(val).partition("|")
    return ru.strip(), [m.strip() for m in meanings.split(";") if m.strip()]


def _inject_fillers(data, pack):
    """Добавляет в словарь языка слова-паразиты: чтение и русские формы.

    Вызывается при каждой загрузке, поэтому чтение и значения всегда актуальны,
    а правки пользователя в других фразах не теряются.

    Список самих паразитов приходит из встроенного словаря только до тех пор,
    пока человек не отметил их галочками в настройках. После первой правки
    действует его выбор (ключ «_fillers_user»), и обновление словаря его не
    перезаписывает. Reading and meanings are refreshed on every load, but the
    filler list comes from the built-in pack only until the user ticks the boxes
    in the settings; after that «_fillers_user» keeps their choice in place.
    """
    phrases = data.setdefault("phrases", {})
    by_norm = {norm(k): k for k in phrases}
    from_pack = []
    for f in pack.get("fillers") or []:
        target = str(f.get("target") or "").strip()
        if not target:
            continue
        ru_forms = [str(x).strip() for x in (f.get("ru") or []) if str(x).strip()]
        if not ru_forms:
            continue
        from_pack.append({"target": target, "ru": ru_forms})
        key = by_norm.get(norm(target))
        if key is None:
            reading = str(f.get("reading") or "").strip() or target
            phrases[target] = reading + " | " + "; ".join(ru_forms)
            by_norm[norm(target)] = target
            continue
        cur = phrases.get(key)
        if not isinstance(cur, str):
            continue
        reading, mine = _phrase_parts(cur)
        have = {norm(m) for m in mine}
        extra = [m for m in ru_forms if norm(m) not in have]
        if extra:
            phrases[key] = (reading or key) + " | " + "; ".join(mine + extra)
    if data.get("_fillers_user"):
        chosen = []
        for f in data.get("_fillers") or []:
            if not isinstance(f, dict):
                continue
            target = str(f.get("target") or "").strip()
            ru_forms = [str(x).strip() for x in (f.get("ru") or []) if str(x).strip()]
            if target and ru_forms:
                chosen.append({"target": target, "ru": ru_forms})
        data["_fillers"] = chosen
    else:
        data["_fillers"] = from_pack
    return data


class Glossary:
    """Словарь одного языка: фразы, чтение, слова-паразиты.

    The glossary of one language: phrases, their Russian reading and fillers.
    """

    def __init__(self, data, lang="it"):
        self.lang = code_of(lang)
        self.meta = get_lang(self.lang)
        self.reading = has_reading(self.lang)
        phrases = data.get("phrases")
        if not isinstance(phrases, dict):  # старый плоский формат
            phrases = {
                k: v for k, v in data.items() if isinstance(v, str) and not k.startswith("_")
            }
        self.phrases = phrases
        self.by_it = {}  # норм. фраза на языке -> (оригинал, русская запись)
        self.by_meaning = {}  # норм. русское значение -> ключ by_it
        for it, val in phrases.items():
            if not isinstance(val, str):
                continue
            ru, meanings = _phrase_parts(val)
            if not ru:
                ru = it
            key = norm(it)
            self.by_it[key] = (it, ru)
            for m in meanings:
                mk = norm(m)
                if mk:
                    self.by_meaning.setdefault(mk, key)
        rep = data.get("replace") or data.get("it_replace") or {}
        self.replace = {norm(k): v for k, v in rep.items()} if isinstance(rep, dict) else {}
        exc = data.get("exceptions") or data.get("translit_exceptions") or {}
        self.exc = {norm(k): v for k, v in exc.items()} if isinstance(exc, dict) else {}
        self.fillers = [
            f for f in (data.get("_fillers") or []) if isinstance(f, dict) and f.get("ru")
        ]
        self.filler_keys = {_filler_key(r) for f in self.fillers for r in f["ru"]}
        self.filler_max_words = max((len(k.split()) for k in self.filler_keys), default=1)
        # у слов-паразитов приоритет: их русские формы ведут именно в свою фразу,
        # даже если такая же форма встречается у другой фразы словаря
        # fillers win: their Russian forms point at their own phrase even when
        # the very same form belongs to another glossary phrase
        for f in self.fillers:
            key = norm(f.get("target") or "")
            if key not in self.by_it:
                continue
            for r in f["ru"]:
                self.by_meaning[norm(r)] = key
                self.by_meaning[_filler_key(r)] = key

    def find_meaning(self, text: str) -> str | None:
        """Русская фраза -> ключ словаря или None. Учитывает е=ё, и=й и окончание «-те».

        A Russian phrase to a glossary key, or None. Ignores ё/е, й/и and the
        plural ending "-те".
        """
        k = norm(text)
        key = self.by_meaning.get(k)
        if key is None:
            # «ну, значит» == «ну значит»: знаки препинания внутри фразы не важны
            # "ну, значит" equals "ну значит": punctuation inside a phrase is ignored
            key = self.by_meaning.get(_filler_key(text))
        if key is None and k.endswith("те") and len(k) > 4:
            key = self.by_meaning.get(k[:-2])
        return key

    def phrase_keys(self, text: str, limit: int = 4) -> list[tuple[int, int, str]]:
        """Фразы словаря, найденные в тексте: (начало, конец, ключ).

        Glossary phrases found in the text: (start, end, key).

        Ищутся самые длинные фразы (до ``limit`` слов), между словами
        допускаются только пробелы и знаки внутри фразы — так же, как при
        переводе. По этому списку модуль «Анимации» узнаёт, что «да ну» и
        «да брось» — одна и та же фраза словаря.
        The same longest-match scan the translation uses: up to ``limit`` words,
        whitespace between them only. The Animations module uses it to see that
        «да ну» and «да брось» are one and the same glossary phrase.
        """
        matches = list(morph.WORD_RE.finditer(text or ""))
        found: list[tuple[int, int, str]] = []
        index = 0
        while index < len(matches):
            taken = 0
            for size in range(min(limit, len(matches) - index), 0, -1):
                last = index + size - 1
                if any(
                    text[matches[k].end() : matches[k + 1].start()].strip()
                    for k in range(index, last)
                ):
                    continue
                phrase = text[matches[index].start() : matches[last].end()]
                key = self.find_meaning(phrase)
                if key:
                    found.append((matches[index].start(), matches[last].end(), key))
                    taken = size
                    break
            index += taken or 1
        return found

    def to_ru(self, text: str, dialect: bool = False) -> str:
        """Фраза на языке перевода -> русская запись.

        Фразы из словаря берутся с готовым чтением. Для языков без русской
        записи (китайский, японский, корейский, арабский) слова показываются как есть.
        A phrase in the target language to its Russian reading. Glossary phrases
        come with a ready reading; for languages without one (Chinese, Japanese,
        Korean, Arabic) the words are shown as they are.
        """
        lang = self.lang
        ms = list(WORD_RE.finditer(text))
        if not ms:
            # иероглифы и прочие знаки без пробелов: только точное совпадение с словарём
            # Chinese characters and other space-less scripts: an exact match with
            # the glossary only
            hit = self.by_it.get(norm(text))
            return hit[1] if hit else text
        out, pos, i = [], 0, 0
        while i < len(ms):
            m = ms[i]
            out.append(text[pos : m.start()])
            hit = None
            for n in range(min(4, len(ms) - i), 0, -1):
                j = i + n - 1
                if any(text[ms[k].end() : ms[k + 1].start()].strip() for k in range(i, j)):
                    continue
                ent = self.by_it.get(norm(text[m.start() : ms[j].end()]))
                if ent:
                    hit = (ent[1], j)
                    break
            if hit:
                out.append(hit[0])
                pos = ms[hit[1]].end()
                i = hit[1] + 1
                continue
            w = m.group()
            rep = self.replace.get(norm(w)) if dialect else None
            if rep:
                ent = self.by_it.get(norm(rep))
                out.append(apply_case(w, ent[1] if ent else (translit_word(rep, lang) or rep)))
            else:
                exc = self.exc.get(norm(w))
                out.append(exc if exc else apply_case(w, translit_word(w, lang) or w))
            pos = m.end()
            i += 1
        out.append(text[pos:])
        return "".join(out)


def merge_defaults(user: dict, default: dict) -> dict:
    """Добавляет в словарь пользователя новые фразы и синонимы.
    Его транскрипции и правки не меняются.

    Adds new phrases and synonyms from a newer built-in pack to the user's
    glossary; the user's readings and edits stay untouched.
    """
    up = user.get("phrases")
    if not isinstance(up, dict):  # старый плоский формат
        up = {k: v for k, v in user.items() if isinstance(v, str) and not k.startswith("_")}
    up = dict(up)
    by_key = {norm(k): k for k in up}
    for it, val in default["phrases"].items():
        k = norm(it)
        if k not in by_key:
            up[it] = val
            by_key[k] = it
            continue
        cur = up[by_key[k]]
        if not isinstance(cur, str):
            continue
        ru, mine = _phrase_parts(cur)
        have = {norm(m) for m in mine}
        extra = [m for m in _phrase_parts(val)[1] if norm(m) not in have]
        if extra:
            up[by_key[k]] = (ru or by_key[k]) + " | " + "; ".join(mine + extra)
    out = {"_version": default["_version"], "phrases": up}
    for sec, old_sec in (("replace", "it_replace"), ("exceptions", "translit_exceptions")):
        d = user.get(sec)
        if not isinstance(d, dict):
            d = user.get(old_sec)
        d = dict(d) if isinstance(d, dict) else {}
        for k, v in (default.get(sec) or {}).items():
            d.setdefault(k, v)
        out[sec] = d
    return out


def _normalize_sections(data):
    """Старые имена разделов -> новые.

    Old section names -> new ones.
    """
    for new, old in (("replace", "it_replace"), ("exceptions", "translit_exceptions")):
        if old in data and new not in data:
            data[new] = data.pop(old)
    return data


def _migrate_old_glossary():
    """Единый старый data/glossary.json -> data/glossaries/it.json."""
    try:
        GLOSSARY_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    dst = glossary_path("it")
    if GLOSSARY_PATH.exists() and not dst.exists():
        try:
            shutil.copy2(GLOSSARY_PATH, dst)
            log.info("Словарь перенесён в %s", dst)
        except OSError:
            log.exception("Не удалось перенести старый словарь")


def load_glossary_data(lang: str = "it") -> dict:
    """Данные словаря языка: файл пользователя, дополненный встроенным пакетом.

    The glossary data of one language: the user's file topped up with the
    built-in pack, with a backup copy made before any migration.
    """
    lang = code_of(lang)
    _migrate_old_glossary()
    pack = get_pack(lang) or empty_pack(lang)
    default = _pack_default(pack)
    path = glossary_path(lang)
    data = read_json(path, None)
    if not isinstance(data, dict) or not data.get("phrases"):
        if path.exists():
            try:
                shutil.copy2(path, path.with_name(path.stem + ".bak.json"))
                log.warning("Словарь %s повреждён, сохранён как .bak.json", path.name)
            except OSError:
                pass
        data = {k: (dict(v) if isinstance(v, dict) else v) for k, v in default.items()}
    else:
        data = _normalize_sections(data)
        try:
            ver = int(data.get("_version", 0))
        except (TypeError, ValueError):
            ver = 0
        if ver < int(default["_version"]):
            try:
                shutil.copy2(path, path.with_name("%s.v%d.bak.json" % (path.stem, ver)))
            except OSError:
                pass
            data = merge_defaults(data, default)
            log.info("Словарь %s обновлён с версии %d до %d", lang, ver, int(default["_version"]))
    data = _inject_fillers(data, pack)
    data["_lang"] = lang
    write_json(path, data)
    return data


def save_glossary_data(lang, data):
    """Сохраняет словарь языка (используется окном настроек).

    Saves a language glossary (used by the settings window).
    """
    lang = code_of(lang)
    try:
        GLOSSARY_DIR.mkdir(parents=True, exist_ok=True)
        data = dict(data)
        data["_lang"] = lang
        write_json(glossary_path(lang), data)
        return True
    except OSError:
        log.exception("Не удалось сохранить словарь %s", lang)
        return False


def reset_glossary(lang="it"):
    """Сбрасывает словарь языка к встроенному.

    Resets a language glossary to the built-in one.
    """
    lang = code_of(lang)
    pack = get_pack(lang) or empty_pack(lang)
    data = {k: (dict(v) if isinstance(v, dict) else v) for k, v in _pack_default(pack).items()}
    data = _inject_fillers(data, pack)
    data["_lang"] = lang
    save_glossary_data(lang, data)
    return data


def load_glossary(lang: str = "it", cfg: Mapping[str, Any] | None = None) -> Glossary:
    """Готовый словарь языка для движка.

    A ready glossary for the engine. When the glossary module is disabled the
    result is empty: phrases and fillers never match, and the text goes to the
    translation services instead.
    """
    if cfg is not None and not modules.is_enabled(cfg, "glossary"):
        log.info("Модуль словаря выключен — работаю без встроенных фраз")
        return Glossary({"phrases": {}, "_lang": code_of(lang)}, lang)
    data = load_glossary_data(lang)
    log.info("Словарь загружен: %s (%d фраз)", code_of(lang), len(data.get("phrases") or {}))
    return Glossary(data, lang)


# ---------- движок ----------
class Engine:
    """Сборка сообщения: словарь + сокращения + перевод по сети.

    Message pipeline: glossary, slang and online translation. Every optional
    part is asked through app.modules, so switching a module off degrades the
    result instead of breaking the program.
    """

    def __init__(self, cfg: dict[str, Any], glossary: Glossary, translator: Any) -> None:
        self.cfg = cfg
        self.g = glossary
        self.tr = translator

    def _sync_direction(self, reverse: bool) -> None:
        """Держит направление переводчика в согласии с режимом движка.

        Окно «Проверка перевода» собирает свой Translator, поэтому направление
        выставляется здесь, а не только при сохранении настроек: иначе проверка
        режима «ваш язык → русский» уходила бы на язык сервера.
        """
        setter = getattr(self.tr, "set_direction", None)
        if callable(setter):
            try:
                setter("in" if reverse else "out")
            except Exception:
                log.exception("Не удалось переключить направление перевода")

    def _translate(self, text: str) -> str:
        """Перевод одной части сообщения с проверкой модуля / guarded translation.

        Если модуль перевода по сети выключен, работа не падает: возвращается
        исходный текст, а в журнал пишется причина.
        With online translation disabled nothing breaks: the original text comes
        back and the reason goes to the log.
        """
        if not modules.is_enabled(self.cfg, "translator"):
            log.info("Модуль перевода выключен; исходный текст сохранён (символов=%d)", len(text))
            return text
        return self.tr.translate(text)

    def _slang_on(self) -> bool:
        """Включён ли модуль сокращений / is the slang module active."""
        return modules.is_enabled(self.cfg, "slang")

    def segment(self, text: str, cap: bool = False) -> tuple[str, str]:
        """Содержимое одной пары маркеров -> (русская запись, текст на языке).

        The text between one pair of markers as (Russian reading, target text).
        """
        g = self.g
        core, tail = split_tail(text.strip())
        # целая фраза из словаря (в т.ч. паразит «ну, значит») — не режем по запятой
        # a whole phrase from the glossary (a filler too) is never split at a comma
        if g.find_meaning(core) is not None or g.by_it.get(norm(core)):
            parts = [core]
        else:
            parts = core.split(",")
        ru_parts, it_parts = [], []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            ent = g.by_it.get(norm(part))
            if not ent:
                mk = g.find_meaning(part)
                if mk:
                    ent = g.by_it[mk]
            if ent:
                it, ru = ent[0], ent[1]
                it = split_tail(it)[0]
            elif CYR_RE.search(part):
                source = slang.expand_russian(part)[0] if self._slang_on() else part
                it = split_tail(self._translate(source).strip())[0]
                ru = g.to_ru(it, dialect=True)
            else:
                it = part
                ru = g.to_ru(part)
            ru_parts.append(ru)
            it_parts.append(it)
        ru = ", ".join(ru_parts)
        it = ", ".join(it_parts)
        if cap or text.strip()[:1].isupper():
            ru = up_first(ru)
        return ru + tail, it + tail

    @measure_call("engine.process")
    def process(self, text: str, auto: bool = False, seed: float = 0.0) -> Result:
        """Обычный режим: русский текст -> русская запись и текст на языке.

        The default mode: Russian text in, the Russian reading and the target
        text out. ``auto`` marks the message picked by the auto-translation
        counter, ``seed`` keeps the chosen fragment stable while typing.
        """
        cfg = self.cfg
        self._sync_direction(False)
        prefix, body_text, is_cmd, is_counted = split_prefix(text)
        if is_cmd and not is_counted:
            # /me, /do, /b и т.п. в авто-режиме и в паразитах не участвуют;
            # ручные +маркеры+ в них по-прежнему работают
            # /me, /do, /b and the like take no part in auto-translation or fillers;
            # hand-written +markers+ still work inside them
            auto = False
            filler_on = False
        else:
            # обычные сообщения и /to /lto /l /wt /s /st — паразиты всегда
            filler_on = bool(cfg.get("filler_always", True))
        body, acts = hide_actions(body_text)
        rx = _marker_rx(cfg)
        if filler_on:
            body = wrap_fillers(body, cfg, self.g)
        if auto and not rx.search(body):  # свои +маркеры+ важнее автоперевода
            body = auto_wrap(body, cfg, self.g, seed)
        ru, it, pos, found = [], [], 0, False
        for mm in rx.finditer(body):
            found = True
            pre = body[pos : mm.start()]
            ru.append(pre)
            it.append(pre)
            before = PH_RE.sub("", "".join(ru)).strip()
            cap = (not before) or before[-1] in ".!?…"
            r, i = self.segment(mm.group(1), cap=cap)
            ru.append(r)
            it.append(i)
            pos = mm.end()
        tail = body[pos:]
        ru.append(tail)
        it.append(tail)
        return Result(
            prefix + restore_actions("".join(ru), acts),
            prefix + restore_actions("".join(it), acts),
            found,
        )

    # ---------- обратный режим: любой язык → русский ----------
    # ---------- полный перевод / full translation ----------
    @measure_call("engine.process_full")
    def process_full(self, text: str) -> Result:
        """Полный перевод: всё сообщение на язык перевода, без «русской записи».

        Режим для тех, кто играет на сервере своего языка и хочет, чтобы в чат
        уходил настоящий иностранный текст. Отличия от обычного режима:
        словарь по-прежнему важнее сервисов, но слов-паразитов нет, автоперевода
        нет (переводится всё), маркеры +...+ не нужны, а «Что уходит в чат» не
        спрашивается — уходит текст на языке.

        Everything goes to the target language, with no Russian reading. The
        glossary still wins over the services, but there are no fillers, no
        auto-translation (everything is translated), no +...+ markers and no
        "what goes to the chat" choice: the target text is what is sent.
        """
        self._sync_direction(False)
        src = (text or "").strip()
        if not src:
            return Result("", "", False)
        prefix, body, _is_cmd, _counted = split_prefix(src)
        ru = self._full_part(body, slang_on=self._slang_on())
        if not ru:
            return Result("", "", False)
        return Result(prefix + ru, prefix + ru, True)

    def _full_part(self, text: str, slang_on: bool) -> str:
        """Один кусок текста целиком на язык перевода, с учётом словаря.

        One chunk of text fully in the target language, the glossary included.

        Сначала ищем в словаре самые длинные фразы: там, где словарь знает
        фразу, сервис не спрашиваем вовсе — так результат и стабильнее, и
        укладывается в стиль сервера. Остальное уходит в переводчик.
        Glossary phrases are matched first and never asked from the services, so
        the result is both stable and in the server's own style.
        """
        text = text or ""
        if not text.strip():
            return text
        if not modules.is_enabled(self.cfg, "glossary"):
            return self._translate(slang.expand_russian(text)[0] if slang_on else text)
        out, pos = [], 0
        if not CYR_WORD_RE.search(text):  # иероглифы и прочие знаки без пробелов
            return self._translate(text)  # space-less scripts go as a whole
        # словарные фразы и слова-паразиты — это одно и то же: паразит тоже
        # фраза словаря, просто короче. Поэтому список один, иначе «ну, значит»
        # разъедется на два куска.
        # glossary phrases and fillers are one and the same thing: a filler is a
        # glossary phrase, only shorter. One list, or a phrase breaks in two.
        for start_, end_, key in sorted(self.g.phrase_keys(text)):
            if start_ < pos:
                continue
            gap = text[pos:start_]
            if gap.strip():
                src = slang.expand_russian(gap)[0] if slang_on else gap
                out.append(keep_edges(gap, self._translate(src)))
            else:
                out.append(gap)
            ent = self.g.by_it.get(key)
            out.append(ent[0] if ent else text[start_:end_])
            pos = end_
        tail = text[pos:]
        if tail.strip():
            src = slang.expand_russian(tail)[0] if slang_on else tail
            out.append(keep_edges(tail, self._translate(src)))
        else:
            out.append(tail)
        return "".join(out)

    @measure_call("engine.process_in")
    def process_in(self, text: str) -> Result:
        """Режим для иностранного игрока: любой язык → русский, перевод уходит в чат.

        Переводится всё содержимое сообщения, включая действия *...*.
        Сленг и сокращения (lol, brb, afk) разворачиваются до перевода:
        «brb» → «I'll be right back» → «я скоро вернусь».
        Служебная команда в начале (/me, /do, /to, /l …) остаётся как есть —
        вместе с ником у /to и /lto. Счётчик автоперевода и словарь не участвуют:
        текст незнакомый, поэтому переводится целиком.

        Foreign player mode: anything into Russian, and the translation goes to
        the game chat. Actions in *asterisks* are translated as well. The service
        command at the start (/me, /do, /to, /l ...) stays untouched, including
        the nickname after /to and /lto. The counter and the glossary do not take
        part: the text is unknown, so the whole message is translated.
        """
        self._sync_direction(True)
        src = (text or "").strip()
        if not src:
            return Result("", "", False)
        prefix, body, _is_cmd, _counted = split_prefix(src)
        slang_on = self._slang_on()
        if slang_on:
            # lol / brb / afk → полные фразы: переводчик сам поставит падеж и род.
            # Язык собеседника неизвестен, поэтому ищем во всех таблицах сразу.
            # The speaker's language is unknown, so every table is searched at
            # once before translation.
            body = slang.expand_any(body)[0]
        out, pos = [], 0
        for m in ACT_RE.finditer(body):
            part = body[pos : m.start()]
            out.append(keep_edges(part, self._translate(part)) if part.strip() else part)
            inner = m.group(0).strip("*")
            ru_inner = self._translate(inner).strip() if inner.strip() else ""
            out.append("*" + (ru_inner or inner) + "*")  # действие тоже переводим
            pos = m.end()
        rest = body[pos:]
        out.append(keep_edges(rest, self._translate(rest)) if rest.strip() else rest)
        ru = "".join(out).strip()
        if slang_on:
            # сервис мог оставить «afk»/«gg» как есть — подменяем лаконичным русским
            # a service may leave "afk" or "gg" as typed, so a short Russian takes over
            ru = slang.restore_any(ru)[0]
        if not ru:
            return Result("", body.strip(), False)
        return Result(prefix + ru, body.strip(), True)
