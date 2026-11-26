"""Тесты модуля переводчика / translator module tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.translator import (  # noqa: E402
    SERVICES,
    Translator,
    _error_kind,
    _short,
    dlx_code,
)


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


def test_short_connection_error():
    """_short распознаёт ошибку соединения."""
    errors = ["getaddrinfo failed"]
    result = _short(errors)
    assert "соедин" in result.lower()


def test_connection_error_is_redacted():
    """Remote error text never leaks through the safe summary."""
    from urllib.error import URLError

    summary = _error_kind(URLError("private chat phrase"))
    assert summary == "network error"
    assert "private chat phrase" not in summary


def test_http_error_summary_omits_response_body():
    """HTTP diagnostics retain status codes but never response payloads."""
    from urllib.error import HTTPError
    from io import BytesIO

    error = HTTPError("https://service.invalid/translate", 429, "private response", {}, BytesIO())
    assert _error_kind(error) == "http 429"


def test_timeout_summary_is_stable():
    """Timeouts have a predictable, non-sensitive error label."""
    assert _error_kind(TimeoutError("private request details")) == "timeout"


def test_google_fallback_does_not_import_untrusted_package():
    """Translation uses our direct HTTP clients, not deep-translator."""
    names = [name for name, _service in SERVICES]
    assert names == ["Google", "Google-2", "MyMemory", "Lingva", "LibreTranslate"]


def test_translation_log_contains_metadata_not_chat_text(monkeypatch, caplog):
    """Successful translations are logged without either side of the chat."""
    import logging
    import threading
    import time

    import app.translator as translator_module

    monkeypatch.setattr(
        translator_module,
        "SERVICES",
        (("TestService", lambda text, target, source: "private translated phrase"),),
    )
    translator = Translator.__new__(Translator)
    translator.cache = {}
    translator.local = None
    translator.net_lock = threading.Lock()
    translator.last = 0.0
    translator.out_target = "it"
    translator.direction = "out"
    translator.target = "it"
    translator.source = "ru"
    translator._saved_at = time.time()
    translator._dirty = False
    private_text = "private original phrase"

    with caplog.at_level(logging.INFO, logger="app"):
        assert translator.translate(private_text) == "private translated phrase"

    assert private_text not in caplog.text
    assert "private translated phrase" not in caplog.text
    assert "chars=23" in caplog.text
