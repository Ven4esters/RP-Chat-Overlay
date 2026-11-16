"""Русская запись иностранных слов по звучанию / Russian reading of foreign words.

Нужна для подсказки «как это читается»: игрок видит рядом с фразой привычные
русские буквы. Для китайского, японского, корейского и арабского русской
записи нет — там слова показываются как есть.
Produces the "how it sounds" hint players see next to a phrase. There are rules
for Italian, Spanish, Portuguese, German, French, Polish, Turkish and English.
Chinese, Japanese, Korean and Arabic get no reading: translit_word() returns an
empty string and the overlay shows the original text.
"""
import re
import string
import unicodedata

V = "aeiou"
SIMPLE = {
    "a": "а", "i": "и", "o": "о", "u": "у", "b": "б", "d": "д", "f": "ф",
    "k": "к", "l": "л", "m": "м", "n": "н", "p": "п", "r": "р", "t": "т",
    "v": "в", "w": "в", "x": "кс", "y": "и", "j": "й",
}
SOFT = {"a": "я", "e": "е", "o": "о", "u": "ю"}

# языки, для которых русская запись не делается (другая письменность)
# languages with no Russian reading (another script)
NO_READING = {"zh-CN", "ja", "ko", "ar"}


def strip_accents(s):
    """Снимает диакритику только с латиницы (кириллица, например «й», не трогается).

    Strips diacritics from Latin letters only (Cyrillic, «й» for one, stays).
    """
    out = []
    for ch in s:
        d = unicodedata.normalize("NFD", ch)
        out.append(d[0] if d[0] in string.ascii_letters else ch)
    return "".join(out)


def norm(s):
    s = strip_accents(s.lower()).replace("’", "'").replace("ё", "е")
    s = re.sub(r"\s+", " ", s).strip()
    return s.strip(" .,!?…;:\"«»()-–—")


def apply_case(src, ru):
    if len(src) > 1 and src.isupper():
        return ru.upper()
    if src[:1].isupper():
        return ru[:1].upper() + ru[1:]
    return ru


def isv(ch):
    return ch != "" and ch in V


def has_reading(lang):
    """Есть ли для языка русская запись по звучанию.

    Whether a language has a Russian reading by sound.
    """
    return lang not in NO_READING


# ---------------------------------------------------------------- таблицы
def _scan(s, table, maxlen=5):
    """Жадно сопоставляет самый длинный шаблон из таблицы на каждой позиции.

    Greedily matches the longest pattern of the table at every position.
    """
    out = []
    i, n = 0, len(s)
    while i < n:
        for ln in range(min(maxlen, n - i), 0, -1):
            key = s[i:i + ln]
            if key in table:
                out.append(table[key])
                i += ln
                break
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


LETTERS = {
    "b": "б", "c": "к", "d": "д", "f": "ф", "g": "г", "h": "х", "j": "дж",
    "k": "к", "l": "л", "m": "м", "n": "н", "p": "п", "q": "к", "r": "р",
    "s": "с", "t": "т", "v": "в", "w": "в", "x": "кс", "z": "з",
}

ES = dict(LETTERS)
ES.update({
    "ch": "ч", "ll": "й", "rr": "рр",
    "que": "ке", "qui": "ки", "gue": "ге", "gui": "ги", "güe": "гуэ", "güi": "гуи",
    "ción": "сьон", "sión": "сьон", "cción": "ксьон",
    "cia": "сья", "cie": "сье", "cio": "сьо", "ciu": "сью",
    "ge": "хе", "gi": "хи", "ce": "се", "ci": "си",
    "qu": "к", "gu": "г", "ñ": "нь", "j": "х", "z": "с", "h": "", "v": "б",
    "y": "й", "á": "а", "é": "е", "í": "и", "ó": "о", "ú": "у", "ü": "у",
    "a": "а", "e": "е", "i": "и", "o": "о", "u": "у",
})

PT = dict(LETTERS)
PT.update({
    "ções": "сойс", "ção": "сан", "são": "сан", "ão": "ан", "ãe": "ан", "õe": "он",
    "ch": "ш", "nh": "нь", "lh": "ль", "rr": "рр", "ss": "сс",
    "que": "ке", "qui": "ки", "gue": "ге", "gui": "ги",
    "ge": "же", "gi": "жи", "ce": "се", "ci": "си",
    "qu": "к", "gu": "г", "ç": "с", "j": "ж", "x": "ш", "h": "", "z": "з",
    "ei": "ей", "ou": "о", "oi": "ой", "eu": "эу", "ai": "ай", "au": "ау",
    "ã": "ан", "õ": "он", "á": "а", "â": "а", "à": "а", "é": "е", "ê": "е",
    "í": "и", "ó": "о", "ô": "о", "ú": "у", "ü": "у", "y": "и", "w": "в",
    "a": "а", "e": "е", "i": "и", "o": "о", "u": "у",
})

DE = dict(LETTERS)
DE.update({
    "tsch": "ч", "sch": "ш", "ch": "х", "chs": "кс", "ck": "к", "ph": "ф", "th": "т",
    "sp": "шп", "st": "шт", "ss": "с", "ß": "с", "ei": "ай", "ie": "и", "eu": "ой",
    "äu": "ой", "au": "ау", "aa": "а", "ee": "е", "oo": "о", "qu": "кв",
    "z": "ц", "w": "в", "v": "ф", "s": "з", "j": "й", "y": "ю",
    "ä": "э", "ö": "ё", "ü": "ю", "a": "а", "e": "е", "i": "и", "o": "о", "u": "у",
})

FR = dict(LETTERS)
FR.update({
    "eaux": "о", "eau": "о", "oin": "уэн", "tion": "сьон", "sion": "сьон",
    "ain": "эн", "ein": "эн", "an": "ан", "am": "ам", "en": "ан",
    "em": "ам", "in": "эн", "im": "эн", "on": "он", "om": "ом", "un": "эн", "um": "ом",
    "ou": "у", "oi": "уа", "au": "о", "ai": "э", "ei": "э", "eu": "ё", "œu": "ё",
    "ch": "ш", "gn": "нь", "qu": "к", "ph": "ф", "th": "т", "ç": "с",
    "ge": "же", "gi": "жи", "j": "ж", "h": "", "x": "кс", "y": "й", "w": "в",
    "é": "е", "è": "э", "ê": "е", "ë": "э", "à": "а", "â": "а", "î": "и", "ï": "и",
    "ô": "о", "û": "у", "ù": "у", "ü": "ю", "œ": "ё",
    "a": "а", "e": "е", "i": "и", "o": "о", "u": "ю",
})

PL = dict(LETTERS)
PL.update({
    "szcz": "щ", "sz": "ш", "cz": "ч", "rz": "ж", "dź": "дзь", "dż": "дж",
    "ż": "ж", "ź": "зь", "ś": "сь", "ć": "чь", "ń": "нь", "ł": "л",
    "ą": "он", "ę": "ен", "ó": "у", "ch": "х", "w": "в", "j": "й", "y": "ы",
    "c": "ц", "z": "з", "g": "г", "h": "х",
    "a": "а", "e": "е", "i": "и", "o": "о", "u": "у",
})

TR = dict(LETTERS)
TR.update({
    "ş": "ш", "ç": "ч", "ğ": "", "ı": "ы", "ö": "ё", "ü": "ю", "c": "дж",
    "j": "ж", "y": "й", "ch": "ч", "a": "а", "e": "е", "i": "и", "o": "о", "u": "у",
})

EN = dict(LETTERS)
EN.update({
    "tion": "шн", "sion": "жн", "tch": "ч", "igh": "ай", "sh": "ш", "ch": "ч",
    "th": "с", "ph": "ф", "ck": "к", "oo": "у", "ee": "и", "ea": "и", "oa": "оу",
    "ai": "эй", "ay": "эй", "ow": "оу", "ou": "ау", "qu": "кв", "ing": "инг",
    "y": "и", "j": "дж", "a": "а", "e": "е", "i": "и", "o": "о", "u": "у",
})



# ---------------------------------------------------------------- итальянский
def _it_word(s):
    n = len(s)
    out = []
    i = 0

    def at(k):
        return s[k] if 0 <= k < n else ""

    while i < n:
        c = s[i]
        nx = at(i + 1)
        if s.startswith("gli", i):
            v = at(i + 3)
            if v in ("a", "e", "o", "u"):
                out.append("ль" + SOFT[v])
                i += 4
            else:
                out.append("льи")
                i += 3
        elif c == "g" and nx == "n":
            v = at(i + 2)
            if v in ("a", "e", "o", "u"):
                out.append("нь" + SOFT[v])
                i += 3
            elif v == "i":
                out.append("ни")
                i += 3
            else:
                out.append("нь")
                i += 2
        elif c == "s" and nx == "c":
            t = at(i + 2)
            if t == "e":
                out.append("ш")
                i += 2
            elif t == "i":
                out.append("ш")
                i += 3 if isv(at(i + 3)) else 2
            elif t == "h":
                out.append("ск")
                i += 3
            else:
                out.append("ск")
                i += 2
        elif c == "s":
            if nx == "s":
                out.append("сс")
                i += 2
            else:
                out.append("з" if isv(at(i - 1)) and isv(nx) else "с")
                i += 1
        elif c == "c":
            dbl = nx == "c"
            j = i + 1 + (1 if dbl else 0)
            t = at(j)
            if t == "h":
                out.append("кк" if dbl else "к")
                i = j + 1
            elif t in ("e", "i"):
                out.append("чч" if dbl else "ч")
                i = j + 1 if (t == "i" and isv(at(j + 1))) else j
            else:
                out.append("кк" if dbl else "к")
                i = j
        elif c == "g":
            dbl = nx == "g"
            j = i + 1 + (1 if dbl else 0)
            t = at(j)
            if t == "h":
                out.append("гг" if dbl else "г")
                i = j + 1
            elif t in ("e", "i"):
                out.append("ддж" if dbl else "дж")
                i = j + 1 if (t == "i" and isv(at(j + 1))) else j
            else:
                out.append("гг" if dbl else "г")
                i = j
        elif c == "q":
            if nx == "u":
                out.append("кв")
                i += 2
            else:
                out.append("к")
                i += 1
        elif c == "z":
            if nx == "z":
                out.append("цц")
                i += 2
            else:
                out.append("ц")
                i += 1
        elif c == "h":
            i += 1
        elif c in ("a", "e", "o") and nx == "i":
            base = "э" if (c == "e" and i == 0) else {"a": "а", "e": "е", "o": "о"}[c]
            out.append(base + "й")
            i += 2
        elif c == "e":
            out.append("э" if i == 0 else "е")
            i += 1
        else:
            out.append(SIMPLE.get(c, c))
            i += 1
    return "".join(out)


def _it(s):
    return _it_word(s)


def _generic(s, table):
    res = _scan(s, table)
    # «e» в начале слова по-испански читается как «э»
    # an "e" at the start of a Spanish word reads as "э"
    if s[:1] == "e" and res[:1] == "е":
        res = "э" + res[1:]
    return res


def _es(s):
    return _generic(s, ES)


def _pt(s):
    res = _scan(s, PT)
    # бразильское произношение: конечные -e/-o звучат как -и/-у
    # Brazilian pronunciation: final -e/-o sound like -и/-у
    if len(s) > 2 and s[-1] in "eo" and s[-2] not in "aeiouãõ":
        res = res[:-1] + {"e": "и", "o": "у"}[s[-1]]
    return res


def _de(s):
    res = _scan(s, DE)
    if s[:1] == "s" and len(s) > 1 and s[1] not in "aeiouäöü":
        res = "ш" + res[1:]
    return res


def _fr(s):
    res = _scan(s, FR)
    # немая конечная -e: «porte» -> «порт»
    if len(s) > 2 and s[-1] == "e" and s[-2] not in "aeiouéèêàâ":
        res = res[:-1]
    return res


def _pl(s):
    return _scan(s, PL)


def _tr(s):
    return _scan(s, TR)


def _en(s):
    res = _scan(s, EN)
    if len(s) > 2 and s[-1] == "e" and s[-2] not in "aeiou":
        res = res[:-1]
    return res


FUNCS = {"it": _it, "es": _es, "es-MX": _es, "pt-BR": _pt, "de": _de, "fr": _fr,
         "pl": _pl, "tr": _tr, "en": _en}


# ---------------------------------------------------------------- API
def translit_word(word, lang="it"):
    """Русская запись одного слова. Пустая строка — если язык без записи.

    The Russian reading of one word. An empty string for a language without one.
    """
    fn = FUNCS.get(lang)
    if fn is None:
        return ""
    s = strip_accents(word.lower()).replace("’", "").replace("'", "")
    s = s.strip(".,!?;:«»\"()")
    if not s:
        return ""
    s = s.replace("ё", "е")
    try:
        return fn(s)
    except Exception:
        return ""
