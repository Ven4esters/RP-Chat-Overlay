"""Сленг и сокращения / slang and abbreviations.

Сокращение раскрывается в полную фразу ДО перевода, поэтому падеж, род и
время получаются верными: «brb» -> «I'll be right back» -> «я скоро вернусь».
Если сервис всё же вернул латиницу, подставляется короткий русский вариант.
An abbreviation is expanded into a full phrase BEFORE translation, so case,
gender and tense come out right. If a service still returns Latin letters, a
short Russian variant is substituted.

Зачем это нужно
---------------
Живой чат пишут сокращениями: «lol», «brb», «afk», «idk». Машинный перевод
такие токены либо оставляет латиницей, либо переводит по одной букве, поэтому
в русской строке появляется мусор.

Как это работает
----------------
1. Перед переводом сокращение разворачивается в полную фразу на языке
   источника: «idk» → «I don't know», «brb» → «I'll be right back».
   Дальше обычный переводчик ставит русские слова в нужный падеж, род
   и время — «I'll be right back» → «я скоро вернусь», а не «скоро назад».
   Именно поэтому таблица хранит полную фразу, а не готовый перевод.
2. Если сервис всё же вернул сокращение как есть (так бывает с «afk», «gg»),
   его подменяет лаконичный русский вариант из второй колонки. Варианты
   подобраны так, чтобы стоять в любом месте предложения: без рода
   («не за клавиатурой», «мне всё равно»), в первом лице без прошедшего
   времени («скоро вернусь», «уже иду») или наречием («кстати», «по-моему»).
3. Обратное направление (русский → язык сервера) получает то же самое
   в русской записи: «спс» → «спасибо», «мб» → «может быть».

Языки
-----
Встроенные таблицы живут в app.slang_data: у английского, немецкого,
французского, испанского, арабского и русского языка своя таблица примерно на
триста сокращений. Работает та, которую выбрал set_language(); выбор приходит
из настроек (``slang_lang``, иначе — из языка перевода). Токены ищутся по целым
словам, поэтому внутри «nice» и «super» ничего не меняется.

Languages
---------
The built-in tables live in app.slang_data: English, German, French, Spanish,
Arabic and Russian each have a table of roughly three hundred abbreviations. The
one in use is the one set_language() picked, and the choice comes from the
settings (``slang_lang``, or else the translation language). Tokens are matched as
whole words, so nothing changes inside "nice" or "super".

Свои сокращения
---------------
Встроенные таблицы дополняются тем, что игрок добавил в окне настроек
(раздел «Сокращения»). Хранятся они в data/slang.json; у каждой записи есть
поле ``lang``, поэтому у языка своя таблица и правка одной не лезет в другую.
Старый плоский вид (без языка) читается как английский. Своя запись перекрывает
встроенную: так можно и переписать «afk» по-своему, и выключить ненужное
сокращение, оставив обе колонки пустыми. Если разворот пуст, а русский вариант
задан, сокращение подменяется уже после перевода.

The built-in tables are extended by whatever the player added in the settings
window. It lives in data/slang.json, where every entry carries a ``lang`` field,
so each language keeps its own table and editing one never reaches into another.
The old flat shape without a language reads as English. An own entry overrides a
built-in one: "afk" can be reworded and an unwanted abbreviation switched off by
leaving both columns empty. With an empty expansion a set Russian variant the
token is substituted after translation instead.

Смайлы не трогаются
-------------------
«xD», «x)», «:)», «^^» — выражение лица, а не сокращение: в служебных чатах
/b, /ab и /f они остаются как набраны. Проверка одна на все таблицы.
"xD", "x)", ":)" and "^^" are faces rather than abbreviations: in the /b, /ab and
/f service chats they stay as typed. One guard covers every table.
"""
import re
from typing import Final

from app import slang_data
from app.config import SLANG_PATH, log, read_json, write_json

# Таблицы сокращений живут в app.slang_data (там же объяснено, почему данные
# отдельно от кода). Здесь остаётся только замена.
# The abbreviation tables live in app.slang_data, where the reason for keeping
# the data apart from the code is explained. Only the replacement stays here.
FOREIGN: Final[dict[str, str]] = slang_data.ENGLISH
RUSSIAN: Final[dict[str, str]] = slang_data.RUSSIAN

# Дополнительные образцы смеха, которых нет в таблицах: «looool», «lmaooo».
# Они не словарные записи, а шаблоны, поэтому и лежат здесь.
# Extra laughter patterns that the tables do not hold: "looool", "lmaooo".
# They are patterns rather than entries, so they stay here.
LAUGH = ((r"l+o+l+", "haha"),
         (r"lma+o+", "haha"),
         (r"rofl+", "haha"),
         (r"ke+k+", "haha"))

CYR_RX = re.compile(r"[а-яё]", re.IGNORECASE)


def is_russian_token(token):
    """Сокращение записано кириллицей — значит, оно русское.

    An abbreviation written in Cyrillic is a Russian one.
    """
    return bool(CYR_RX.search(str(token or "")))


# ---------- рабочие таблицы (встроенные + то, что добавил игрок) ----------
# Всё это — состояние ОДНОГО языка, выбранного через set_language(): у каждого
# языка своя таблица, и переключение языка пересобирает рабочие словари.
# All of this is the state of the ONE language chosen through set_language():
# every language has its own table, and switching languages rebuilds the dicts.
_lang = slang_data.DEFAULT_LANG
_user = {}                 # сокращение -> (разворот, русский вариант)
_user_all = {}             # язык -> то же самое / language -> the same
_foreign = dict(FOREIGN)
_russian = dict(RUSSIAN)
_loaded = False

_RX_FOREIGN = None
_RX_RUSSIAN = None


# Смайлы и жесты: токен с закрывающей скобкой, двоеточием или «^^» — это
# выражение лица, а не сокращение, и в служебных чатах /b /ab /f он остаётся
# как есть. Проверка одна на всех, чтобы новая таблица не принесла «x)».
# Faces and gestures: a token with a closing bracket, a colon or "^^" is an
# expression rather than an abbreviation, and in the /b /ab /f service chats it
# stays as typed. One guard for every table, so a new one cannot bring "x)" in.
_FACE_RX = re.compile(r"[)(:]|\^\^")


def _token_rx(words):
    """Регулярка по целым словам: длинные варианты идут первыми.

    A whole-word pattern, longest variants first.

    Смайлы выбрасываются до сборки шаблона: «x)» в таблице не должно ломать
    разбор скобок в чате.
    Faces are dropped before the pattern is built: an "x)" in a table must not
    break bracket handling in chat.
    """
    words = [w for w in words if w and not _FACE_RX.search(w)]
    if not words:
        return None
    parts = sorted(words, key=len, reverse=True)
    return re.compile(r"(?<![0-9A-Za-z_а-яёА-ЯЁ])(?:%s)(?![0-9A-Za-z_а-яёА-ЯЁ])"
                      % "|".join(re.escape(p) for p in parts), re.IGNORECASE)


_RX_LAUGH = None


def _laugh_rx():
    """Образцы смеха для текущего языка; для нелатинских языков их нет.

    Laughter patterns for the current language; non-Latin languages have none.

    «XD» — это не слово, а выражение лица, и в русском чате его не трогают.
    В арабском таблица смеха уже своя, и латинские шаблоны там только мешают.
    "XD" is a face rather than a word and is left alone in Russian chat. The
    Arabic table holds its own laughter, and Latin patterns only get in the way.
    """
    if _lang != "en":
        return None
    return re.compile(r"(?<![0-9A-Za-z_])(?:%s)(?![0-9A-Za-z_])"
                      % "|".join(p for p, _en in LAUGH), re.IGNORECASE)

# «I'm afk» → «I'm not at the keyboard», а не «I'm I'm away…»:
# если перед сокращением уже стоит подлежащее или форма to be, берём вариант
# без ведущего «I»/«I'm»/«I'll».
_LEAD_RX = re.compile(r"^(?:i'm|i am|i'll|i've|i)\s+", re.IGNORECASE)
_SUBJECT_RX = re.compile(
    r"(?:\b(?:i'm|im|i am|i'll|i've|he's|she's|it's|we're|they're|you're|"
    r"is|are|am|was|were)\s*,?\s*"
    r"(?:(?:not|never|still|really|always|so|just|probably|already)\s+){0,2})$",
    re.IGNORECASE)


def _tail_form(english):
    """Полная фраза без ведущего «I»/«I'm»/«I'll» — для контекста с подлежащим.

    The full phrase without a leading "I"/"I'm"/"I'll", for a context that
    already has a subject.
    """
    return _LEAD_RX.sub("", english)


def _has_subject(text, pos):
    """Есть ли прямо перед сокращением подлежащее или форма to be.

    Whether a subject or a form of "to be" sits right before the abbreviation.
    """
    return bool(_SUBJECT_RX.search(text[:pos]))


_TAILS = {}


def _clean_rows(rows):
    """Записи игрока в виде (сокращение, разворот, вариант), без пустых.

    The player's rows as (token, expansion, variant), empty ones dropped.
    """
    out = []
    for token, pair in (rows or {}).items():
        token = str(token or "").strip()
        if not token:
            continue
        pair = list(pair) + ["", ""]
        expand = str(pair[0] or "").strip()
        ru = str(pair[1] or "").strip()
        out.append((token, expand, ru))
    return out


def _russian_side():
    """Русские сокращения: встроенные плюс свои кириллические, с любого языка.

    Russian abbreviations: the built-in ones plus the player's own Cyrillic
    entries, which count whatever table they were typed in.
    """
    rows = dict(slang_data.RUSSIAN)
    for code in list(_user_all) + [_lang]:
        for token, expand, ru in _clean_rows(_user_all.get(code)):
            if not is_russian_token(token):
                continue
            if expand or ru:
                rows[token] = expand or ru
            else:
                rows.pop(token, None)
    return rows


def _norm(code):
    """Код языка в виде, который понимают таблицы: «es-MX» → «es».

    A language code in the shape the tables understand: "es-MX" becomes "es".

    У неизвестного языка своей таблицы нет — берётся английская (см.
    :func:`app.slang_data.table`).
    An unknown language has no table of its own, so the English one is used.
    """
    code = str(code or "").lower().split("-")[0]
    return code if code in slang_data.BY_LANG else slang_data.DEFAULT_LANG


def builtin(code=None):
    """Встроенные записи языка: сокращение -> (разворот, русский вариант).

    The built-in entries of one language.

    Русский язык — это обратное направление, и второй колонки у него нет.
    Russian is the reverse direction and has no second column.
    """
    code = _norm(code or _lang)
    if code == "ru":
        return {token: (expand, "") for token, expand in slang_data.RUSSIAN.items()}
    return {token: (expand, slang_data.RU_SHORT.get(token.lower(), ""))
            for token, expand in slang_data.table(code).items()}


def _table_for(code):
    """Встроенная таблица языка плюс свои записи этого языка.

    The built-in table of one language plus the player's own entries for it.

    У русского языка «иностранной» таблицы нет: русские сокращения — это
    обратная сторона, её собирает :func:`_russian_side`.
    Russian has no "foreign" table: Russian abbreviations are the reverse side,
    built by :func:`_russian_side`.
    """
    rows = builtin(code)
    for token, expand, ru in _clean_rows(_user_all.get(code)):
        if is_russian_token(token):
            continue
        if expand or ru:
            rows[token] = (expand, ru)
        else:
            rows.pop(token, None)
    return rows


def _rebuild():
    """Пересобирает рабочие таблицы и регулярки под текущий язык и правки.

    Rebuilds the working tables and patterns for the current language and the
    player's own edits.
    """
    global _foreign, _russian, _RX_FOREIGN, _RX_RUSSIAN, _RX_LAUGH, _TAILS, _mixed, _user
    _foreign = _table_for(_lang)
    _russian = _russian_side()
    _RX_FOREIGN = _token_rx(_foreign)
    _RX_RUSSIAN = _token_rx(_russian)
    _RX_LAUGH = _laugh_rx()
    _TAILS = {token: _tail_form(item[0]) for token, item in _foreign.items() if item[0]}
    _user = _user_all.get(_lang) or {}
    _mixed = None                      # общий набор соберётся заново


# ---------- язык таблицы ----------
def set_language(code):
    """Выбрать язык сокращений и пересобрать таблицы.

    Choose the abbreviation language and rebuild the tables.

    Свои записи не теряются: они хранятся в памяти отдельно от встроенных и
    накладываются заново.
    The player's own entries are not lost: they live apart from the built-ins
    and are applied again on top.
    """
    global _lang
    code = _norm(code)
    if code == _lang:
        return _lang
    _lang = code
    _rebuild()
    return _lang


def code_for(code=None):
    """Код таблицы для языка сервера: «es-MX» → «es», «it» → «en».

    The table code for a server language: "es-MX" gives "es", "it" gives "en".

    У языков без своей таблицы (итальянский, португальский, польский и прочие
    из app.langs) работает английская: латинские сокращения узнаёт любой игрок.
    Languages without a table of their own (Italian, Portuguese, Polish and the
    rest of app.langs) use the English one.
    """
    return _norm(code or _lang)


def use_for(cfg):
    """Выставить язык таблицы по настройкам / pick the table language from the config.

    Игрок может выбрать таблицу явно (``slang_lang``); если не выбрал, таблица
    следует за языком перевода — на немецком сервере первой должна работать
    немецкая.
    The player may pick a table explicitly (``slang_lang``); otherwise the table
    follows the translation language: a German server wants German first.
    """
    return set_language((cfg or {}).get("slang_lang")
                        or (cfg or {}).get("target_lang") or slang_data.DEFAULT_LANG)


def language():
    """Текущий язык таблицы сокращений / the current abbreviation language."""
    return _lang


def languages():
    """Языки, у которых есть встроенная таблица: [(код, подпись)].

    The languages with a built-in table: (code, caption).
    """
    return [(code, slang_data.LANG_TITLES.get(code, code.upper()))
            for code in slang_data.BY_LANG]


# ---------- свои сокращения игрока ----------
# the player's own abbreviations
def load_user():
    """Читает data/slang.json (если он есть) и применяет к таблицам."""
    global _loaded
    data = read_json(SLANG_PATH, {})
    entries = data.get("custom") if isinstance(data, dict) and "custom" in data else data
    if not isinstance(entries, dict):
        entries = {}
    # по языкам: запись без поля lang считается английской, как и раньше
    # by language: an entry without lang counts as English, as before
    global _user_all
    _user_all = {}
    by_lang = {}
    for token, pair in entries.items():
        code = slang_data.DEFAULT_LANG
        if isinstance(pair, dict):
            code = str(pair.get("lang") or slang_data.DEFAULT_LANG).lower()
        by_lang.setdefault(code, {})[token] = pair
    for code, rows in by_lang.items():
        _set_user(rows, code)
    _set_user(by_lang.get(_lang, {}), _lang)
    _loaded = True
    return dict(_user)


def _set_user(entries, code=None):
    """Разложить записи игрока по языкам, выбрав нужный.

    Sort the player's entries by language, choosing the one needed.

    В файле запись выглядит так: ``{"lang": "de", "token": "hdl",
    "expand": "hab dich lieb"}``. Так у одного языка своя таблица, и правка
    немецкой не лезет в английскую.

    An entry looks like ``{"lang": "de", "token": "hdl", "expand": "hab dich
    lieb"}``, so every language keeps its own table and editing German does not
    touch English.
    """
    global _user, _user_all
    code = _norm(code or _lang)
    clean = {}
    for token, pair in (entries or {}).items():
        token = str(token or "").strip()
        if not token:
            continue
        lang_code = code
        if isinstance(pair, dict):
            lang_code = str(pair.get("lang") or code).lower()
            pair = [pair.get("expand", ""), pair.get("ru", "")]
        elif isinstance(pair, str):
            pair = [pair, ""]
        pair = list(pair) + ["", ""]
        if lang_code != code:
            # запись другого языка остаётся в общей копилке и не теряется
            # an entry of another language stays in the shared store
            other = _user_all.setdefault(lang_code, {})
            other[token] = (str(pair[0] or "").strip(), str(pair[1] or "").strip())
            continue
        clean[token] = (str(pair[0] or "").strip(), str(pair[1] or "").strip())
    _user_all[code] = clean
    # рабочий словарь — только у текущего языка; чужие записи лежат в копилке
    # и ждут своего переключения (см. _rebuild)
    # only the current language owns the working tables; foreign entries wait in
    # the store for their turn, see _rebuild
    _rebuild()


def set_user(entries, code=None):
    """Применить свои сокращения только в памяти (без записи на диск).

    Apply the player's own abbreviations in memory only, without writing to disk.
    """
    _ensure()
    _set_user(entries, code)
    return dict(_user)


def user_entries(code=None):
    """Свои сокращения одного языка: сокращение -> [разворот, вариант].

    The player's own abbreviations of one language.
    """
    _ensure()
    code = _norm(code or _lang)
    return {k: [v[0], v[1]] for k, v in (_user_all.get(code) or {}).items()}


def save_languages(by_lang):
    """Применить и записать правки сразу нескольких языков.

    Apply and write the edits of several languages in one go.

    Окно настроек держит несохранённые правки каждого языка отдельно; при
    «Сохранить» они уходят одним файлом, а не по одному на язык.
    The settings window keeps each language's unsaved edits apart; "Save" writes
    them as one file rather than one per language.
    """
    for code, rows in (by_lang or {}).items():
        _set_user(rows, code)
    try:
        write_json(SLANG_PATH, {"custom": _dump_all()})
    except OSError:
        log.exception("Не удалось сохранить свои сокращения")
    log.info("Своих сокращений сохранено: %d (%s)", len(_user), _lang)
    return dict(_user)


def _dump_all():
    """Все свои записи для файла: ``{сокращение: {lang, expand, ru}}``.

    Every own entry for the file: ``{token: {lang, expand, ru}}``.

    Плоский вид (без языка) остаётся ради старых версий программы: они прочтут
    такой файл как английский, а не сломаются.
    The flat shape without a language is kept for older builds: they read such a
    file as English instead of breaking.
    """
    out = {}
    for code, rows in _user_all.items():
        for token, (expand, ru) in rows.items():
            out[token] = {"lang": code, "expand": expand, "ru": ru}
    for token, (expand, ru) in _user.items():
        out.setdefault(token, {"lang": _lang, "expand": expand, "ru": ru})
    return out


def entries(code=None):
    """Таблица для окна настроек: [(сокращение, разворот, вариант, своё?)].

    The table for the settings window.

    Показывается только выбранный язык: у каждого языка своя таблица, и правка
    немецкой не подмешивается в английскую. Для русского языка показываются
    русские сокращения — та сторона, что работает в направлении «русский →
    язык». Выключенное сокращение (обе колонки пусты) остаётся в списке, чтобы
    его можно было вернуть.
    Only the chosen language is shown: every language keeps its own table, so
    editing German does not mix into English. For Russian the Russian
    abbreviations appear — the side used by the "Russian → language" direction.
    A disabled abbreviation (both columns empty) stays in the list so it can be
    brought back.
    """
    _ensure()
    code = _norm(code or _lang)
    mine = _user_all.get(code) or {}
    rows = []
    for token, (expand, ru) in builtin(code).items():
        own = mine.get(token)
        if own is None:
            rows.append((token, expand, ru, False))
        else:
            rows.append((token, own[0], own[1], True))
    for token, (expand, ru) in mine.items():
        if token not in builtin(code):
            rows.append((token, expand, ru, True))
    rows.sort(key=lambda r: (not r[3], r[0].lower()))
    return rows


def known():
    """Сколько сокращений в таблицах — для справки и самопроверки.

    How many abbreviations the tables hold, for reference and self-check.
    """
    laughs = len(LAUGH) if _lang == "en" else 0
    return {"язык": _lang, "иностранные": len(_foreign) + laughs,
            "русские": len(_russian), "свои": len(_user)}


def _ensure():
    if not _loaded:
        load_user()


# ---------- чужой язык без выбора ----------
# В режиме «ваш язык → русский» язык собеседника неизвестен, поэтому токен
# ищется сразу во всех таблицах. Совпадающие сокращения («lol», «gg») берутся
# из английской — она первая и самая общая.
# In the "any language into Russian" mode the speaker's language is unknown, so
# a token is looked up in every table at once. Tokens present in several tables
# ("lol", "gg") come from English, which comes first and is the most common.
_mixed = None


def _mixed_foreign():
    """Все таблицы разом: сокращение -> (разворот, русский вариант).

    Every table at once: token -> (expansion, Russian variant).
    """
    global _mixed
    if _mixed is None:
        rows = {}
        for code in ("en", "de", "fr", "es", "ar"):
            for token, pair in _table_for(code).items():
                rows.setdefault(token.lower(), pair)
        _mixed = rows
    return _mixed


def expand_any(text):
    """Развернуть сокращение любого языка перед переводом на русский.

    Expand an abbreviation of any language before translating into Russian.

    Свои записи игрока важнее встроенных: он мог переписать «afk» по-своему.
    The player's own entries win over the built-in ones: "afk" may be rewritten.
    """
    if not text:
        return text, []
    _ensure()
    rows = dict(_mixed_foreign())
    rows.update(_foreign)
    rx = _token_rx(rows)

    def pick(token, start):
        item = rows.get(token.lower())
        if not item or not item[0]:
            return None
        return item[0]

    return _replace(text, rx, pick)


def restore_any(text):
    """Оставить собеседнику лаконичный русский вариант — на любом языке.

    Give a short Russian reading for whatever abbreviation survived translation.
    """
    if not text:
        return text, []
    _ensure()
    rows = dict(_mixed_foreign())
    rows.update(_foreign)

    def pick(token, start):
        item = rows.get(token.lower())
        if not item or not item[1]:
            return None
        ru = item[1]
        return _capitalize(ru) if _at_sentence_start(text, start) else ru

    return _replace(text, _token_rx(rows), pick)


# ---------- замена ----------
def _capitalize(word):
    return word[:1].upper() + word[1:]


def _at_sentence_start(text, pos):
    """True, если перед позицией конец строки или знак конца предложения."""
    before = text[:pos].rstrip()
    return (not before) or before[-1] in ".!?…;:—-*\"«("


def _replace(text, rx, pick):
    """Общая замена по регулярке; pick(токен, начало) -> строка или None."""
    if rx is None:
        return text, []
    out, pos, hits = [], 0, []
    for m in rx.finditer(text):
        token = m.group(0)
        new = pick(token, m.start())
        if new is None:
            continue
        out.append(text[pos:m.start()])
        out.append(new)
        pos = m.end()
        hits.append((token, new))
    if not hits:
        return text, hits
    out.append(text[pos:])
    return "".join(out), hits


def expand_foreign(text):
    """Сокращение → полная фраза перед переводом. Возвращает (текст, замены).

    An abbreviation turned into its full phrase before translation. Returns the
    new text together with the replacements made.
    """
    if not text:
        return text, []
    _ensure()
    hits = []

    def by_laugh(token, start):
        lower = token.lower()
        for pattern, en in LAUGH:
            if re.fullmatch(pattern, lower):
                return en
        return None

    text, more = _replace(text, _RX_LAUGH, by_laugh)
    hits += more

    def by_token(token, start):
        lower = token.lower()
        item = _foreign.get(lower)
        if not item or not item[0]:
            return None
        tail = _TAILS.get(lower)
        if tail and _has_subject(text, start):
            return tail
        return item[0]

    text, more = _replace(text, _RX_FOREIGN, by_token)
    return text, hits + more


def restore_russian(text):
    """Оставшиеся латинские сокращения → лаконичный русский вариант.

    Latin abbreviations a service left as typed turn into the short Russian variant.
    """
    if not text:
        return text, []
    _ensure()

    def pick(token, start):
        item = _foreign.get(token.lower())
        if not item or not item[1]:
            return None
        ru = item[1]
        return _capitalize(ru) if _at_sentence_start(text, start) else ru

    return _replace(text, _RX_FOREIGN, pick)


def expand_russian(text):
    """Русское сокращение → полная русская запись (перед переводом на язык).

    A Russian abbreviation turned into the full Russian phrase before translating
    it into the server's language.
    """
    if not text:
        return text, []
    _ensure()

    def pick(token, start):
        word = _russian.get(token.lower())
        if not word:
            return None
        return _capitalize(word) if _at_sentence_start(text, start) else word

    return _replace(text, _RX_RUSSIAN, pick)
