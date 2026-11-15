"""langpacks/it.py — итальянский: базовый словарь программы.

Слова итальянского словаря лежат в glossary_data.py (там же формат и правила),
здесь добавлены только слова-паразиты из PDF «Слова-паразиты».
"""
from ..glossary_data import DEFAULT_GLOSSARY as _D

CODE = "it"
VERSION = int(_D.get("_version", 5))
PHRASES = _D["phrases"]
REPLACE = _D.get("it_replace") or {}
EXCEPTIONS = _D.get("translit_exceptions") or {}

# Слова-паразиты (PDF): переводятся в КАЖДОМ сообщении, вне зависимости от
# счётчика автоперевода. "ru" — то, что пользователь печатает по-русски.
FILLERS = [
    {"target": "Ma dai", "reading": "ма дай",
     "ru": ["да брось", "ну что ты", "да ладно", "брось", "да ну"]},
    {"target": "Madonn'", "reading": "мадонн", "ru": ["мадонна"]},
    {"target": "Mannaggia", "reading": "маннаджа",
     "ru": ["чёрт", "досада", "чёрт возьми", "чёрт побери"]},
    {"target": "Capisci?", "reading": "капищи", "ru": ["понимаешь"]},
    {"target": "Che vuoi fare?", "reading": "ке вуой фаре",
     "ru": ["а что поделаешь", "что поделаешь", "что поделать", "а что поделать"]},
    {"target": "Senti", "reading": "сэнти", "ru": ["слушай", "послушай"]},
    {"target": "Scemo", "reading": "шемо", "ru": ["дурачок", "дурак"]},
    {"target": "Agita", "reading": "аджита", "ru": ["тревога", "изжога", "нервы"]},
    {"target": "Allora", "reading": "аллора", "ru": ["ну значит", "итак"]},
    {"target": "Piano piano", "reading": "пьяно пьяно",
     "ru": ["потихоньку", "не спеша", "полегоньку", "потихонечку"]},
]
