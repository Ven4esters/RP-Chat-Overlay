"""langs.py — реестр языков перевода.

Поля:
    code      — код языка (он же имя файла словаря: data/glossaries/<code>.json)
    name      — название по-русски
    native    — название на самом языке
    tr        — код для сервиса перевода (Google)
    pack      — модуль со встроенным словарём в пакете langpacks (или None)
    reading   — есть ли русская запись по звучанию
"""
from translit import has_reading

LANGUAGES = [
    # --- полностью поддерживаемые языки со встроенным словарём ---
    dict(code="it", name="Итальянский", native="Italiano", tr="it", pack="it",
         about="Базовый язык программы: самый большой встроенный словарь и слова-паразиты."),
    dict(code="es", name="Испанский", native="Español", tr="es", pack="es",
         about="Испанский (Испания). Встроенный словарь RP-фраз и слова-паразиты."),
    dict(code="es-MX", name="Испанский (Мексика)", native="Español (México)", tr="es", pack="mx",
         about="Мексиканский испанский: güey, órale, no manches."),
    dict(code="pt-BR", name="Португальский (Бразилия)", native="Português (Brasil)", tr="pt",
         pack="pt", about="Бразильский португальский — самый популярный вариант на RP-серверах."),
    dict(code="zh-CN", name="Китайский", native="中文", tr="zh-CN", pack="zh",
         about="Китайский (упрощённый) с пиньинь-подсказками в словаре."),
    dict(code="ja", name="Японский", native="日本語", tr="ja", pack="ja",
         about="Японский с ромадзи-подсказками в словаре."),
    dict(code="en", name="Английский", native="English", tr="en", pack="en",
         about="Английский — язык большинства международных RP-серверов."),
    # --- языки с переводом и словарём-заготовкой ---
    dict(code="de", name="Немецкий", native="Deutsch", tr="de", pack="de",
         about="Немецкий: много крупных RP-серверов (Grand RP German и другие)."),
    dict(code="fr", name="Французский", native="Français", tr="fr", pack="fr",
         about="Французский: несколько больших RP-проектов."),
    dict(code="pl", name="Польский", native="Polski", tr="pl", pack="pl",
         about="Польский: крупные RP-сервера (Majestic RP Warsaw и др.)."),
    dict(code="tr", name="Турецкий", native="Türkçe", tr="tr", pack="tr",
         about="Турецкий: большие RP-сообщества FiveM."),
    # --- перевод без встроенного словаря и без русской записи ---
    dict(code="ko", name="Корейский", native="한국어", tr="ko", pack=None,
         about="Перевод через интернет; словарь можно загрузить вручную."),
    dict(code="ar", name="Арабский", native="العربية", tr="ar", pack=None,
         about="Перевод через интернет; словарь можно загрузить вручную."),
]

BY_CODE = {x["code"]: x for x in LANGUAGES}


def get(code, default="it"):
    """Описание языка по коду (с запасным вариантом)."""
    return BY_CODE.get(code) or BY_CODE.get(default) or LANGUAGES[0]


def code_of(code):
    """Нормализует код языка: 'es-mx' -> 'es-MX', 'pt' -> 'pt-BR'."""
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


def label(code, native=False):
    """Название языка для интерфейса: «Итальянский (Italiano)»."""
    x = get(code)
    return f"{x['name']} ({x['native']})" if native else x["name"]


def reading(code):
    return has_reading(code_of(code))


def choices():
    """Список (код, подпись) для выпадающего списка в настройках."""
    return [(x["code"], label(x["code"], native=True)) for x in LANGUAGES]
