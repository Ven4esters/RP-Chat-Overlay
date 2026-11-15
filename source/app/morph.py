"""Словоформы: как сравнивать ключевое слово с другими его формами.

Word forms: comparing a keyword with the other forms of the same word.

Зачем / why
-----------
Ключевое слово «открыл зонт» должно находить и «открывает зонт», и «открыла
зонта». Перечислять формы руками — плохо. Модуль даёт два уровня сравнения:

* **основы** (:func:`stem`) — без словарей и без сети: срезаем окончания по
  таблице русских флексий и один словообразовательный суффикс. «открыл»,
  «открывает» и «откроет» дают одну основу «откр».
* **леммы** (:func:`lemma`) — нормальная форма слова из словаря `pymorphy3`.
  Точнее там, где стемминг пасует: «зонта» → «зонт», «люди» → «человек».
  Если пакета нет, уровень честно откатывается к основе, а интерфейс говорит
  об этом в настройках.

A keyword must also find its other forms: «открыл зонт» has to fire on
«открывает зонт». Two levels are offered: **stems** (no dictionaries, no
network) and **lemmas** (the `pymorphy3` dictionary), which falls back to stems
when the package is missing.
"""

from __future__ import annotations

import re
import threading
import unicodedata
from functools import lru_cache

# ------------------------------------------------------------------- уровни
FORMS_EXACT = 0        # ровно та форма, что написана / exactly the written form
FORMS_STEM = 1         # сравнение по основе / compare by stem
FORMS_LEMMA = 2        # сравнение по лемме из словаря / compare by dictionary lemma

FORMS: tuple[int, ...] = (FORMS_EXACT, FORMS_STEM, FORMS_LEMMA)
FORMS_DEFAULT = FORMS_STEM

# Названия для выпадающего списка: короткие, чтобы влезали в столбец.
# Short titles for the combo box: they must fit the column.
FORMS_TITLES_RU: dict[int, str] = {
    FORMS_EXACT: "Точно",
    FORMS_STEM: "Основы",
    FORMS_LEMMA: "Леммы",
}

FORMS_TITLES_EN: dict[int, str] = {
    FORMS_EXACT: "Exact",
    FORMS_STEM: "Stems",
    FORMS_LEMMA: "Lemmas",
}

# Полные объяснения — для подсказки поля «Формы».
# Full explanations — for the "Forms" field tooltip.
FORMS_HINTS_RU: dict[int, str] = {
    FORMS_EXACT: "Только та форма, что написана в ключе: «открыл зонт» найдёт "
                 "«открыл зонт», но не «открывает зонт». Годится для имён и ников.",
    FORMS_STEM: "Любые падежи, числа и спряжения: «открыл», «открывает», "
                "«откроет» — одна основа. Без словарей, работает всегда.",
    FORMS_LEMMA: "Сравнение по словарной форме слова (пакет pymorphy3) и по "
                 "основе: «люди/человек», «зонта/зонт», «открыл/открывает». Без "
                 "пакета pymorphy3 работает как «Основы».",
}

FORMS_HINTS_EN: dict[int, str] = {
    FORMS_EXACT: "Only the written form: «открыл зонт» finds «открыл зонт» but "
                 "not «открывает зонт». Good for names and nicknames.",
    FORMS_STEM: "Any case, number and conjugation: «открыл», «открывает», "
                "«откроет» share one stem. No dictionaries, always available.",
    FORMS_LEMMA: "Comparison by the dictionary form (the pymorphy3 package) and "
                 "by the stem: «люди/человек», «зонта/зонт», «открыл/открывает». "
                 "Without pymorphy3 it works like «Stems».",
}

WORD_RE = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", re.UNICODE)

# окончания: сначала длинные, иначе «-ого» съестся как «-о»
# endings: longest first, otherwise «-ого» would be eaten as «-о»
_ENDINGS: tuple[str, ...] = tuple(sorted({
    # существительные / nouns
    "ами", "ями", "иями", "ов", "ев", "ей", "ой", "ам", "ям", "ах", "ях",
    "ом", "ем", "ём", "ы", "и", "а", "я", "о", "е", "у", "ю", "ь", "й",
    # прилагательные и причастия / adjectives and participles
    "ого", "его", "ому", "ему", "ыми", "ими", "ых", "их", "ый", "ий", "ая",
    "яя", "ое", "ее", "ые", "ие", "ую", "юю", "им", "ым",
    # глаголы и деепричастия / verbs and gerunds
    "ешься", "ишься", "ется", "ится", "ются", "ятся", "ешь", "ишь", "ете",
    "ите", "ут", "ют", "ат", "ят", "ет", "ит", "ла", "ло", "ли", "ть",
    "ться", "л", "в",
}, key=len, reverse=True))
# «ем» встречается и у существительных («объёмом»), и у глаголов («поем») — в
# наборе выше оно указано один раз; повтор в литерале ничего не менял, только
# сбивал с толку при чтении.
# "ем" belongs both to nouns and to verbs — it is listed once above; the repeated
# literal changed nothing, it only confused the reader.

# суффиксы, которые не меняют смысла: «откры-ва-ет», «мах-ну-л»
# suffixes that carry no meaning of their own
_VERB_SUFFIXES: tuple[str, ...] = ("ыва", "ива", "ну")

_VOWELS = "аяоеуыиэюёе"

# чередования, которые не выводятся из окончаний: «пьёт» -> «пить»
# alternations the ending table cannot explain
_ALTERNATIONS = {"пь": "пи", "ль": "ли", "шь": "ши", "вь": "ви", "бь": "би",
                 "мь": "ми", "сь": "си", "жь": "жи"}

_MIN_STEM = 2          # короче двух букв основа не бывает / stems are 2+ letters

# словарь морфологии берётся по требованию: без него программа работает
# the morphology dictionary is loaded on demand: without it the program works
_analyzer = None
_analyzer_lock = threading.Lock()
_analyzer_failed = False


@lru_cache(maxsize=8192)
def _norm_cached(word: str) -> str:
    """Приведение слова к сравнимому виду, с кэшем / word normalisation, cached."""
    text = unicodedata.normalize("NFC", word).lower().replace("ё", "е")
    return "".join(char for char in unicodedata.normalize("NFD", text)
                   if unicodedata.category(char) != "Mn")


def norm(word: str) -> str:
    """Нижний регистр, «ё» = «е», без диакритики.

    Lowercase, «ё» counts as «е», diacritics dropped.

    Результат кэшируется: ``norm`` вызывается на каждое слово сообщения для
    каждого правила, а слов в языке конечное число. Два разбора Unicode на слово
    были самой дорогой частью поиска — кэш убирает их для всех повторов.
    The result is cached: ``norm`` runs on every word of every message for every
    rule, while a language has a finite set of words. Two Unicode passes per word
    were the most expensive part of the search — the cache removes them for every
    repeat.
    """
    return _norm_cached(str(word or ""))


def stem(word: str) -> str:
    """Основа слова: «открывает», «открыл», «откроет» -> «откр».

    The stem of a word: «открывает», «открыл» and «откроет» -> «откр».
    """
    text = norm(word)
    for ending in _ENDINGS:
        if len(text) - len(ending) >= _MIN_STEM and text.endswith(ending):
            text = text[: -len(ending)]
            break
    for suffix in _VERB_SUFFIXES:       # «откры-ва-» -> «откр»
        if len(text) - len(suffix) >= _MIN_STEM and text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    while len(text) > _MIN_STEM and text[-1] in _VOWELS:   # «откры» -> «откр»
        text = text[:-1]
    return _ALTERNATIONS.get(text, text)


def _morph():
    """Разборщик pymorphy3 или None / the pymorphy3 analyzer or None."""
    global _analyzer, _analyzer_failed
    if _analyzer is not None or _analyzer_failed:
        return _analyzer
    with _analyzer_lock:
        if _analyzer is None and not _analyzer_failed:
            try:
                import pymorphy3
                _analyzer = pymorphy3.MorphAnalyzer()
            except Exception:
                _analyzer_failed = True
    return _analyzer


def lemmas_available() -> bool:
    """Есть ли словарь морфологии / is the morphology dictionary available."""
    return _morph() is not None


def lemma(word: str) -> str:
    """Словарная форма слова; без словаря — основа.

    The dictionary form of a word; the stem when no dictionary is available.
    """
    analyzer = _morph()
    if analyzer is None:
        return stem(word)
    text = norm(word)
    try:
        parsed = analyzer.parse(text)
    except Exception:
        return stem(text)
    if not parsed:
        return stem(text)
    return norm(parsed[0].normal_form) or stem(text)


def keys_of(word: str, forms: int) -> frozenset[str]:
    """Ключи сравнения слова для выбранного уровня / the comparison keys.

    Слово совпадает с другим, если наборы ключей пересекаются. Уровень «Леммы»
    даёт два ключа — основу и словарную лемму: лемма точнее («люди» = «человек»),
    а основа спасает видовые пары, у которых леммы разные («открыть» и
    «открывать» — разные леммы одного смысла).
    Two words match when their key sets intersect. The "Lemmas" level returns two
    keys, the stem and the dictionary lemma: the lemma is more precise («люди» =
    «человек») while the stem rescues aspect pairs, whose lemmas differ
    («открыть» and «открывать»).
    """
    if forms == FORMS_EXACT:
        return frozenset((norm(word),))
    if forms == FORMS_LEMMA:
        return frozenset((stem(word), lemma(word)))
    return frozenset((stem(word),))


class KeyCache:
    """Кэш «слово -> ключи» на одно сообщение: словарь морфологии не дёргаем дважды.

    A "word -> keys" cache for one message, so the morphology dictionary is never
    asked twice about the same word.
    """

    LIMIT = 4000       # больше в одном сообщении не встречается / per message cap

    def __init__(self) -> None:
        self._data: dict[tuple[int, str], frozenset[str]] = {}

    def __call__(self, word: str, forms: int) -> frozenset[str]:
        if forms not in FORMS:
            forms = FORMS_DEFAULT
        cache_key = (forms, norm(word))
        found = self._data.get(cache_key)
        if found is not None:
            return found
        if len(self._data) >= self.LIMIT:
            self._data.clear()
        value = keys_of(word, forms)
        self._data[cache_key] = value
        return value


def describe_forms(forms: int, english: bool = False) -> str:
    """Короткое название уровня для списка / the short title of a level."""
    table = FORMS_TITLES_EN if english else FORMS_TITLES_RU
    return table.get(int(forms), table[FORMS_DEFAULT])


def describe_forms_hint(forms: int, english: bool = False) -> str:
    """Полное объяснение уровня для подсказки / the full explanation of a level."""
    table = FORMS_HINTS_EN if english else FORMS_HINTS_RU
    return table.get(int(forms), table[FORMS_DEFAULT])
