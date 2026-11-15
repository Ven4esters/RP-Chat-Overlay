"""engine.py — разбор сообщения: +маркеры+, *действия*, словарь, автоперевод фрагмента,
слова-паразиты (всегда), команды /to /lto /l /wt /s /st (учитываются в счётчике).

Движок не привязан к итальянскому: язык берётся из Glossary.lang,
словарь и слова-паразиты — из пакета языка (пакет langpacks).
"""
import random
import re
import shutil
from collections import namedtuple

from common import GLOSSARY_DIR, GLOSSARY_PATH, log, read_json, write_json
from langs import code_of, get as get_lang
from langpacks import empty_pack, get_pack
from translit import apply_case, has_reading, norm as _norm, translit_word

Result = namedtuple("Result", "text italian translated")


def norm(s):
    """Ключ сравнения: без регистра, ударений и знаков по краям; е=ё, и=й."""
    return _norm(s).replace("й", "и")


PH_RE = re.compile(r"\ue000(\d+)\ue000")
ACT_RE = re.compile(r"\*[^*]*(?:\*|$)")          # незакрытое действие — до конца строки
CMD_RE = re.compile(r"^\s*/\S+\s*")               # /me, /do, /b ...
CYR_RE = re.compile(r"[А-Яа-яЁё]")
CYR_WORD_RE = re.compile(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*")
WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ’']+")
TAIL_RE = re.compile(r"[.!?…]+$")

# служебные слова: сами по себе (и на краях фрагмента) в автоперевод не берутся
STOP = {norm(w) for w in (
    "и в во на с со к ко у о об от по за из для при про без до не ни но а да что как это то "
    "я ты он она оно мы вы они мне тебе меня тебя ему ей нам вам их же бы ли вот вон тут там "
    "уж ну же или либо чтобы если когда мой моя моё мои твой твоя твоё твои наш ваш"
).split()}

# ---------- команды, которые считаются сообщениями ----------
# /to, /lto, /l, /wt, /s, /st — это настоящие сообщения другим игрокам,
# поэтому они участвуют в счётчике автоперевода (AutoPlan) наравне с обычным текстом.
# Остальные команды (/me, /do, /b, /g, ...) в счётчик НЕ идут и не автопереводятся.
COUNTED_COMMANDS = {"/to", "/lto", "/l", "/wt", "/s", "/st"}
NICK_COMMANDS = {"/to", "/lto"}          # после команды идёт ник, его переводить нельзя
_CMD_TOKEN_RE = re.compile(r"^\s*(/\S+)")
_CMD_PREFIX_RE = re.compile(r"^\s*/\S+\s*")
_NICK_RE = re.compile(r"\S+\s*")


def get_command(text):
    """Команда в начале сообщения (в нижнем регистре) или "" если её нет."""
    m = _CMD_TOKEN_RE.match(text or "")
    return m.group(1).lower() if m else ""


def is_counted_command(text):
    """True, если сообщение — одна из команд /to /lto /l /wt /s /st."""
    return get_command(text) in COUNTED_COMMANDS


def split_prefix(text):
    """Разбирает команду: (префикс, тело, есть_команда, команда_учитывается).

    Для /to и /lto в префикс входит и ник: "/to Ivan привет" -> ("/to Ivan ", "привет").
    Для остальных команд префикс — только сама команда: "/l привет" -> ("/l ", "привет").
    """
    m = _CMD_PREFIX_RE.match(text or "")
    if not m:
        return "", text or "", False, False
    cmd = get_command(text)
    prefix, body = m.group(0), text[m.end():]
    if cmd in NICK_COMMANDS:
        nick = _NICK_RE.match(body)
        if nick:
            prefix += nick.group(0)
            body = body[nick.end():]
    return prefix, body, True, cmd in COUNTED_COMMANDS


# ---------- слова-паразиты: переводятся ВСЕГДА ----------
# Список слов-паразитов хранится в словаре языка (ключ "_fillers"), поэтому
# для каждого языка он свой: итальянские Senti / Ma dai, испанские Oye / No manches,
# китайские 那个 / 没办法 и т.д. Русские формы — то, что пользователь печатает в чате.
# Они переводятся в КАЖДОМ сообщении, вне зависимости от счётчика автоперевода
# (auto_every) и от того, попало ли сообщение в «переводимый» номер серии.


def _filler_key(s):
    """Ключ сравнения паразита: без регистра, ё/й, знаков и лишних пробелов."""
    return " ".join(re.sub(r"[^\w\s]", " ", norm(s)).split())


def is_filler_text(text, g=None):
    """True, если русская фраза — слово-паразит текущего языка."""
    if g is None:
        return False
    if _filler_key(text) not in g.filler_keys:
        return False
    return g.find_meaning(text) is not None


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
            ok = True
            for x in range(i, j):
                sep = body[ms[x].end():ms[x + 1].start()]
                if "\ue000" in sep or sep.strip(" ,") != "":
                    ok = False
                    break
            if not ok:
                continue
            frag = body[ms[i].start():ms[j].end()]
            if _filler_key(frag) in g.filler_keys and g.find_meaning(frag) is not None:
                cands.append((ms[i].start(), ms[j].end(), n))
                break  # самая длинная фраза с этой позиции уже найдена
    cands.sort(key=lambda c: (-c[2], c[0]))
    picked = []
    for s, e, _n in cands:
        if all(e <= ps or s >= pe for ps, pe in picked):
            picked.append((s, e))
    return sorted(picked)


def wrap_fillers(body, cfg, g):
    """Оборачивает слова-паразиты в маркеры (только вне +маркеров+ и *действий*)."""
    o, c = cfg["marker_open"], cfg["marker_close"]
    rx = _marker_rx(cfg)
    marked = [(m.start(), m.end()) for m in rx.finditer(body)]
    if marked:
        # режем тело на куски вне маркеров и обрабатываем каждый отдельно
        out, pos = [], 0
        for s, e in marked:
            out.append(_wrap_fillers_plain(body[pos:s], o, c, g))
            out.append(body[s:e])
            pos = e
        out.append(_wrap_fillers_plain(body[pos:], o, c, g))
        return "".join(out)
    return _wrap_fillers_plain(body, o, c, g)


def _wrap_fillers_plain(body, o, c, g):
    for s, e in sorted(_filler_spans(body, g), reverse=True):
        body = body[:s] + o + body[s:e] + c + body[e:]
    return body


def has_fillers(text, cfg, g):
    """Есть ли в сообщении слово-паразит, которое нужно перевести."""
    _prefix, body, is_cmd, is_counted = split_prefix(text)
    if is_cmd and not is_counted:
        return False
    body, _acts = hide_actions(body)
    return wrap_fillers(body, cfg, g) != body


# ---------- действия ----------
def hide_actions(text):
    acts = []

    def rep(m):
        acts.append(m.group(0))
        return "\ue000%d\ue000" % (len(acts) - 1)

    return ACT_RE.sub(rep, text), acts


def restore_actions(text, acts):
    return PH_RE.sub(lambda m: acts[int(m.group(1))], text)


def split_tail(s):
    m = TAIL_RE.search(s)
    return (s[:m.start()], m.group(0)) if m else (s, "")


def up_first(s):
    for i, ch in enumerate(s):
        if ch.isalpha():
            return s[:i] + ch.upper() + s[i + 1:]
    return s


def _marker_rx(cfg):
    return re.compile(
        re.escape(cfg["marker_open"]) + r"(.+?)" + re.escape(cfg["marker_close"]), re.S
    )


def has_markers(text, cfg):
    body, _ = hide_actions(text)
    return bool(_marker_rx(cfg).search(body))


def strip_markers(text, cfg):
    """Убирает маркеры, оставляя текст внутри (отправка без перевода)."""
    body, acts = hide_actions(text)
    return restore_actions(_marker_rx(cfg).sub(r"\1", body), acts)


# ---------- автоперевод: случайный фрагмент ----------
def _int(cfg, key, default):
    try:
        return int(cfg.get(key, default))
    except (TypeError, ValueError):
        return default


def auto_wrap(body, cfg, g, seed):
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
            if any(body[ms[x].end():ms[x + 1].start()].strip() for x in range(i, j)):
                break
            frag = body[ms[i].start():ms[j].end()]
            words = [norm(ms[x].group()) for x in range(i, j + 1)]
            known = g.find_meaning(frag) is not None
            filler = _filler_key(frag) in g.filler_keys and known
            if not known and (all(w in STOP for w in words)
                              or words[0] in STOP or words[-1] in STOP):
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
def glossary_path(lang="it"):
    """Файл словаря языка: data/glossaries/<код>.json."""
    return GLOSSARY_DIR / ("%s.json" % code_of(lang))


def _pack_default(pack):
    """Встроенный пакет языка в формате файла словаря."""
    return {
        "_version": int(pack.get("version", 1)),
        "phrases": dict(pack.get("phrases") or {}),
        "replace": dict(pack.get("replace") or {}),
        "exceptions": dict(pack.get("exceptions") or {}),
    }


def _phrase_parts(val):
    """«транскрипция | значение 1; значение 2» -> (транскрипция, [значения])."""
    ru, _, meanings = str(val).partition("|")
    return ru.strip(), [m.strip() for m in meanings.split(";") if m.strip()]


def _inject_fillers(data, pack):
    """Добавляет в словарь языка слова-паразиты: чтение и русские формы.

    Вызывается при каждой загрузке, поэтому список паразитов всегда актуален,
    а правки пользователя в других фразах не теряются.
    """
    phrases = data.setdefault("phrases", {})
    by_norm = {norm(k): k for k in phrases}
    fillers = []
    for f in pack.get("fillers") or []:
        target = str(f.get("target") or "").strip()
        if not target:
            continue
        ru_forms = [str(x).strip() for x in (f.get("ru") or []) if str(x).strip()]
        if not ru_forms:
            continue
        fillers.append({"target": target, "ru": ru_forms})
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
    data["_fillers"] = fillers
    return data


class Glossary:
    """Словарь одного языка: фразы, чтение, слова-паразиты."""

    def __init__(self, data, lang="it"):
        self.lang = code_of(lang)
        self.meta = get_lang(self.lang)
        self.reading = has_reading(self.lang)
        phrases = data.get("phrases")
        if not isinstance(phrases, dict):          # старый плоский формат
            phrases = {k: v for k, v in data.items()
                       if isinstance(v, str) and not k.startswith("_")}
        self.phrases = phrases
        self.by_it = {}        # норм. фраза на языке -> (оригинал, русская запись)
        self.by_meaning = {}   # норм. русское значение -> ключ by_it
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
        self.fillers = [f for f in (data.get("_fillers") or [])
                        if isinstance(f, dict) and f.get("ru")]
        self.filler_keys = {_filler_key(r) for f in self.fillers for r in f["ru"]}
        self.filler_max_words = max((len(k.split()) for k in self.filler_keys), default=1)
        # у слов-паразитов приоритет: их русские формы ведут именно в свою фразу,
        # даже если такая же форма встречается у другой фразы словаря
        for f in self.fillers:
            key = norm(f.get("target") or "")
            if key not in self.by_it:
                continue
            for r in f["ru"]:
                self.by_meaning[norm(r)] = key
                self.by_meaning[_filler_key(r)] = key

    def find_meaning(self, text):
        """Русская фраза -> ключ словаря или None. Учитывает е=ё, и=й и окончание «-те»."""
        k = norm(text)
        key = self.by_meaning.get(k)
        if key is None:
            # «ну, значит» == «ну значит»: знаки препинания внутри фразы не важны
            key = self.by_meaning.get(_filler_key(text))
        if key is None and k.endswith("те") and len(k) > 4:
            key = self.by_meaning.get(k[:-2])
        return key

    def is_filler(self, text):
        """True, если русская фраза — слово-паразит текущего языка."""
        return is_filler_text(text, self)

    def to_ru(self, text, dialect=False):
        """Фраза на языке перевода -> русская запись.

        Фразы из словаря берутся с готовым чтением. Для языков без русской
        записи (китайский, японский, корейский, арабский) слова показываются как есть.
        """
        lang = self.lang
        ms = list(WORD_RE.finditer(text))
        if not ms:
            # иероглифы и прочие знаки без пробелов: только точное совпадение с словарём
            hit = self.by_it.get(norm(text))
            return hit[1] if hit else text
        out, pos, i = [], 0, 0
        while i < len(ms):
            m = ms[i]
            out.append(text[pos:m.start()])
            hit = None
            for n in range(min(4, len(ms) - i), 0, -1):
                j = i + n - 1
                if any(text[ms[k].end():ms[k + 1].start()].strip() for k in range(i, j)):
                    continue
                ent = self.by_it.get(norm(text[m.start():ms[j].end()]))
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

    # прежнее имя — на случай внешних вызовов
    it_to_ru = to_ru


def merge_defaults(user, default):
    """Добавляет в словарь пользователя новые фразы и синонимы.
    Его транскрипции и правки не меняются."""
    up = user.get("phrases")
    if not isinstance(up, dict):                   # старый плоский формат
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
    """Старые имена разделов -> новые."""
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


def load_glossary_data(lang="it"):
    """Данные словаря языка: файл пользователя, дополненный встроенным пакетом."""
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
            log.info("Словарь %s обновлён с версии %d до %d",
                     lang, ver, int(default["_version"]))
    data = _inject_fillers(data, pack)
    data["_lang"] = lang
    write_json(path, data)
    return data


def save_glossary_data(lang, data):
    """Сохраняет словарь языка (используется окном настроек)."""
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
    """Сбрасывает словарь языка к встроенному."""
    lang = code_of(lang)
    pack = get_pack(lang) or empty_pack(lang)
    data = {k: (dict(v) if isinstance(v, dict) else v) for k, v in _pack_default(pack).items()}
    data = _inject_fillers(data, pack)
    data["_lang"] = lang
    save_glossary_data(lang, data)
    return data


def load_glossary(lang="it"):
    """Готовый словарь языка для движка."""
    data = load_glossary_data(lang)
    log.info("Словарь загружен: %s (%d фраз)", code_of(lang), len(data.get("phrases") or {}))
    return Glossary(data, lang)


# ---------- движок ----------
class Engine:
    def __init__(self, cfg, glossary, translator):
        self.cfg = cfg
        self.g = glossary
        self.tr = translator

    def segment(self, text, cap=False):
        """Содержимое одной пары маркеров -> (русская запись, итальянский)."""
        g = self.g
        core, tail = split_tail(text.strip())
        # целая фраза из словаря (в т.ч. паразит «ну, значит») — не режем по запятой
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
                it = split_tail(self.tr.translate(part).strip())[0]   # может бросить TranslateError
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

    def process(self, text, auto=False, seed=0.0):
        cfg = self.cfg
        prefix, body_text, is_cmd, is_counted = split_prefix(text)
        if is_cmd and not is_counted:
            # /me, /do, /b и т.п. в авто-режиме и в паразитах не участвуют;
            # ручные +маркеры+ в них по-прежнему работают
            auto = False
            filler_on = False
        else:
            # обычные сообщения и /to /lto /l /wt /s /st — паразиты всегда
            filler_on = bool(cfg.get("filler_always", True))
        body, acts = hide_actions(body_text)
        rx = _marker_rx(cfg)
        if filler_on:
            body = wrap_fillers(body, cfg, self.g)
        if auto and not rx.search(body):            # свои +маркеры+ важнее автоперевода
            body = auto_wrap(body, cfg, self.g, seed)
        ru, it, pos, found = [], [], 0, False
        for mm in rx.finditer(body):
            found = True
            pre = body[pos:mm.start()]
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