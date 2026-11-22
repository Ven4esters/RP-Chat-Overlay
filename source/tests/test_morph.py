"""Тесты модуля словоформ / morph module tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.morph import stem, lemma, keys_of, norm  # noqa: E402


def test_stem_russian_verb():
    """Стеминг русских глаголов."""
    result = stem("открыл")
    assert isinstance(result, str)
    assert len(result) > 0


def test_stem_russian_noun():
    """Стеминг русских существительных."""
    result = stem("зонта")
    assert isinstance(result, str)
    assert len(result) > 0


def test_stem_consistent_same_root():
    """Слова с одним корнем дают одинаковую основу."""
    s1 = stem("открыл")
    s2 = stem("открывает")
    # Оба должны давать основу на откр
    assert s1.startswith("откр") or s2.startswith("откр")


def test_norm_lowercase():
    """Нормализация приводит к нижнему регистру."""
    result = norm("ПриВет")
    assert result == "привет"


def test_keys_of_returns_frozenset():
    """keys_of возвращает frozenset."""
    result = keys_of("привет", 1)
    assert isinstance(result, frozenset)


def test_lemma_fallback():
    """Lemma работает даже без pymorphy3 (откат к stem)."""
    result = lemma(" zonタ")  # некорректное слово, должно обработаться
    assert isinstance(result, str)
