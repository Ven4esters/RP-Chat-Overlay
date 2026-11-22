"""Встроенные словари для каждого языка перевода / built-in language packs.

Один модуль пакета — один язык. Каждый модуль содержит код языка, версию
словаря, фразы, слова-паразиты и необязательные таблицы замен.
One module per language; each one holds the language code, the glossary version,
the phrases, the filler words and optional replacement tables.


Каждый модуль пакета содержит:
    CODE        — код языка (как в langs.py)
    VERSION     — версия словаря; при увеличении словарь пользователя
                  дополняется новыми фразами без потери его правок
    PHRASES     — {"фраза на языке": "русская запись | значение 1; значение 2; ..."}
    FILLERS     — слова-паразиты: [{"target": фраза, "reading": запись,
                                    "ru": [что печатает пользователь по-русски]}]
    REPLACE     — (необязательно) местный сленг: {"слово": "фраза из словаря"}
    EXCEPTIONS  — (необязательно) как читать отдельные слова

Важно: модули импортируются статически (а не через importlib), иначе
PyInstaller не находит их при сборке exe и программа падает с
«No module named langpacks.it».
"""

from . import de as _de
from . import en as _en
from . import es as _es
from . import fr as _fr
from . import it as _it
from . import ja as _ja
from . import mx as _mx
from . import pl as _pl
from . import pt as _pt
from . import tr as _tr
from . import zh as _zh

MODULES = {
    "it": _it,
    "es": _es,
    "es-MX": _mx,
    "pt-BR": _pt,
    "zh-CN": _zh,
    "ja": _ja,
    "en": _en,
    "de": _de,
    "fr": _fr,
    "pl": _pl,
    "tr": _tr,
}


def has_pack(code):
    return code in MODULES


def get_pack(code):
    """Встроенный словарь языка или None, если для языка пакета нет."""
    m = MODULES.get(code)
    if m is None:
        return None
    return {
        "code": code,
        "version": int(getattr(m, "VERSION", 1)),
        "phrases": dict(getattr(m, "PHRASES", {})),
        "fillers": [dict(x) for x in getattr(m, "FILLERS", [])],
        "replace": dict(getattr(m, "REPLACE", {})),
        "exceptions": dict(getattr(m, "EXCEPTIONS", {})),
    }


def empty_pack(code, version=1):
    """Пустой словарь для языка без встроенного пакета.

    An empty glossary for a language without a built-in pack.
    """
    return {
        "code": code,
        "version": version,
        "phrases": {},
        "fillers": [],
        "replace": {},
        "exceptions": {},
    }
