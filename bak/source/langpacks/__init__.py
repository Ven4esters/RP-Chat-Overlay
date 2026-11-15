"""langpacks — встроенные словари для каждого языка перевода.

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
from langpacks import de as _de
from langpacks import en as _en
from langpacks import es as _es
from langpacks import fr as _fr
from langpacks import it as _it
from langpacks import ja as _ja
from langpacks import mx as _mx
from langpacks import pl as _pl
from langpacks import pt as _pt
from langpacks import tr as _tr
from langpacks import zh as _zh

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


def pack_codes():
    return sorted(MODULES)


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
    """Пустой словарь для языка без встроенного пакета."""
    return {"code": code, "version": version, "phrases": {}, "fillers": [],
            "replace": {}, "exceptions": {}}
