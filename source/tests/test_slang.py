"""Тесты модуля сленга / slang module tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.slang import is_russian_token, expand_foreign, expand_russian, restore_russian, known  # noqa: E402


def test_is_russian_token_english():
    """Английский токен не является русским."""
    assert is_russian_token("brb") is False
    assert is_russian_token("afk") is False


def test_is_russian_token_russian():
    """Русский токен является русским."""
    assert is_russian_token("спс") is True
    assert is_russian_token("мб") is True


def test_expand_foreign_known():
    """Раскрытие известного иностранного сокращения."""
    result = expand_foreign("brb")[0]
    assert "back" in result.lower() or "right" in result.lower()


def test_expand_foreign_unknown():
    """Неизвестное сокращение возвращается как есть."""
    result = expand_foreign("xyz123")[0]
    assert result == "xyz123"


def test_expand_russian_known():
    """Раскрытие известного русского сокращения."""
    result = expand_russian("спс")[0]
    assert result.lower() == "спасибо"


def test_expand_russian_unknown():
    """Неизвестное русское сокращение возвращается как есть."""
    result = expand_russian("xyz")[0]
    assert result == "xyz"


def test_restore_russian():
    """Восстановление русского варианта ( puede вернуть как есть если нет в таблице)."""
    result = restore_russian("спс")[0]
    assert isinstance(result, str)
    assert len(result) > 0


def test_known_returns_dict():
    """known возвращает словарь с записями."""
    result = known()
    assert isinstance(result, dict)
