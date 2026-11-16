"""Реестр языков перевода / the target language registry.

Один список описывает всё, что программа знает о языке: код, название,
код для сервиса перевода, наличие встроенного словаря и русской записи.
A single list describes everything the program knows about a language: its code,
name, the code used by the translation services, whether a built-in glossary
exists and whether a Russian reading can be produced.


Поля:
    code      — код языка (он же имя файла словаря: data/glossaries/<code>.json)
    name      — название по-русски
    name_en   — название по-английски
    native    — название на самом языке
    tr        — код для сервиса перевода (Google)
    pack      — модуль со встроенным словарём в пакете langpacks (или None)
    reading   — есть ли русская запись по звучанию
"""
from app.translit import has_reading

LANGUAGES = [
    # --- полностью поддерживаемые языки со встроенным словарём ---
    # fully supported languages with a built-in glossary
    dict(code="it", name_en="Italian", name="Итальянский", native="Italiano", tr="it", pack="it",
         about="Базовый язык программы: самый большой встроенный словарь и слова-паразиты.", about_en="The base language of the program: the largest built-in glossary and filler words."),
    dict(code="es", name_en="Spanish", name="Испанский", native="Español", tr="es", pack="es",
         about="Испанский (Испания). Встроенный словарь RP-фраз и слова-паразиты.", about_en="Spanish (Spain). A built-in glossary of RP phrases and filler words."),
    dict(code="es-MX", name_en="Spanish (Mexico)", name="Испанский (Мексика)", native="Español (México)", tr="es", pack="mx",
         about="Мексиканский испанский: güey, órale, no manches.", about_en="Mexican Spanish: güey, órale, no manches."),
    dict(code="pt-BR", name_en="Portuguese (Brazil)", name="Португальский (Бразилия)", native="Português (Brasil)", tr="pt",
         pack="pt", about="Бразильский португальский — самый популярный вариант на RP-серверах.", about_en="Brazilian Portuguese, the most common variant on RP servers."),
    dict(code="zh-CN", name_en="Chinese", name="Китайский", native="中文", tr="zh-CN", pack="zh",
         about="Китайский (упрощённый) с пиньинь-подсказками в словаре.", about_en="Simplified Chinese with pinyin hints in the glossary."),
    dict(code="ja", name_en="Japanese", name="Японский", native="日本語", tr="ja", pack="ja",
         about="Японский с ромадзи-подсказками в словаре.", about_en="Japanese with romaji hints in the glossary."),
    dict(code="en", name_en="English", name="Английский", native="English", tr="en", pack="en",
         about="Английский — язык большинства международных RP-серверов.", about_en="English, the language of most international RP servers."),
    # --- языки с переводом и словарём-заготовкой ---
    # languages translated online with a starter glossary
    dict(code="de", name_en="German", name="Немецкий", native="Deutsch", tr="de", pack="de",
         about="Немецкий: много крупных RP-серверов (Grand RP German и другие).", about_en="German: many large RP servers (Grand RP German and others)."),
    dict(code="fr", name_en="French", name="Французский", native="Français", tr="fr", pack="fr",
         about="Французский: несколько больших RP-проектов.", about_en="French: several big RP projects."),
    dict(code="pl", name_en="Polish", name="Польский", native="Polski", tr="pl", pack="pl",
         about="Польский: крупные RP-сервера (Majestic RP Warsaw и др.).", about_en="Polish: large RP servers (Majestic RP Warsaw and others)."),
    dict(code="tr", name_en="Turkish", name="Турецкий", native="Türkçe", tr="tr", pack="tr",
         about="Турецкий: большие RP-сообщества FiveM.", about_en="Turkish: big FiveM RP communities."),
    # --- перевод без встроенного словаря и без русской записи ---
    # translation only, with neither a built-in glossary nor a Russian reading
    dict(code="ko", name_en="Korean", name="Корейский", native="한국어", tr="ko", pack=None,
         about="Перевод через интернет; словарь можно загрузить вручную.", about_en="Translated over the internet; the glossary can be loaded manually."),
    dict(code="ar", name_en="Arabic", name="Арабский", native="العربية", tr="ar", pack=None,
         about="Перевод через интернет; словарь можно загрузить вручную.", about_en="Translated over the internet; the glossary can be loaded manually."),
]

BY_CODE = {x["code"]: x for x in LANGUAGES}


def get(code: str, default: str = "it") -> dict:
    """Описание языка по коду (с запасным вариантом).

    Language description by code, falling back to the default language.
    """
    return BY_CODE.get(code) or BY_CODE.get(default) or LANGUAGES[0]


def code_of(code: str) -> str:
    """Нормализация кода языка / normalise a language code.

    'es-mx' -> 'es-MX', 'pt' -> 'pt-BR', неизвестное -> 'it'.
    Unknown codes fall back to 'it'.
    """
    if not code:
        return "it"
    if code in BY_CODE:
        return code
    low = str(code).lower()
    for x in LANGUAGES:
        if x["code"].lower() == low or x["tr"].lower() == low:
            return x["code"]
    aliases = {"pt": "pt-BR", "br": "pt-BR", "pt-br": "pt-BR", "mx": "es-MX",
               "es-mx": "es-MX", "zh": "zh-CN", "cn": "zh-CN", "zh-cn": "zh-CN",
               "jp": "ja", "kr": "ko"}
    return aliases.get(low, "it")


def label(code: str, native: bool = False) -> str:
    """Название языка для интерфейса: «Итальянский (Italiano)».

    The language name shown in the UI: «Итальянский (Italiano)», or just the
    name when native=False.
    """
    x = get(code)
    name = x.get("name_en") if _english() else x["name"]
    if not native:
        return name or x["name"]
    sep = " — " if "(" in (name or "") else " ("
    tail = "" if sep == " — " else ")"
    return f"{name or x['name']}{sep}{x['native']}{tail}"


def _english():
    """True, если интерфейс переключён на английский."""
    try:
        from app import i18n
        return i18n.is_en()
    except Exception:
        return False


def reading(code: str) -> bool:
    """Есть ли русская запись по звучанию / is a Russian reading available."""
    return has_reading(code_of(code))


def choices() -> list[tuple[str, str]]:
    """Список (код, подпись) для выпадающего списка в настройках.

    (code, label) pairs for the drop-down lists in the settings.
    """
    return [(x["code"], label(x["code"], native=True)) for x in LANGUAGES]
