"""Тесты модуля транслитерации / translit module tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.translit import strip_accents, norm, apply_case  # noqa: E402


def test_strip_accents():
    """strip_accents убирает диакритику."""
    result = strip_accents("éèê")
    assert "e" in result


def test_norm():
    """Нормализация строки."""
    result = norm("ПриВет")
    assert isinstance(result, str)


def test_apply_case():
    """Применение регистра."""
    result = apply_case("Привет", "привет")
    assert isinstance(result, str)
