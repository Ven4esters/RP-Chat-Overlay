"""Тесты модуля языков / langs module tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.langs import code_of, label, get  # noqa: E402


def test_code_of_known():
    """code_of для известного кода языка."""
    result = code_of("it")
    assert result == "it"


def test_code_of_unknown():
    """code_of для неизвестного кода возвращает 'it' (fallback)."""
    result = code_of("xx")
    assert result == "it"


def test_label_known():
    """label для известного языка."""
    result = label("it")
    assert isinstance(result, str)
    assert len(result) > 0


def test_get_returns_dict():
    """get возвращает словарь для известного языка."""
    result = get("it")
    assert isinstance(result, dict)
