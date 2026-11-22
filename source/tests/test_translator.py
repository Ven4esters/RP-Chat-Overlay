"""Тесты модуля переводчика / translator module tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.translator import dlx_code, _short  # noqa: E402


def test_dlx_code_auto():
    """dlx_code('auto') возвращает 'auto'."""
    assert dlx_code("auto") == "auto"


def test_dlx_code_empty():
    """dlx_code('') возвращает 'auto'."""
    assert dlx_code("") == "auto"


def test_dlx_code_known_language():
    """dlx_code для известного языка возвращает код DeepL (ru -> ru)."""
    result = dlx_code("ru")
    assert result == "ru"


def test_dlx_code_italian():
    """dlx_code для итальянского возвращает IT."""
    result = dlx_code("it")
    assert result == "IT"


def test_dlx_code_unknown_language():
    """dlx_code для неизвестного языка возвращает upper()."""
    result = dlx_code("xy")
    assert result == "XY"


def test_short_rate_limit():
    """_short распознаёт ошибку 429."""
    errors = ["DeepL ограничил запросы (429)"]
    result = _short(errors)
    assert "429" in result or "занят" in result.lower()


def short_connection_error():
    """_short распознаёт ошибку соединения."""
    errors = ["getaddrinfo failed"]
    result = _short(errors)
    assert "соедин" in result.lower()
