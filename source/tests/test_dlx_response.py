"""Tests for safely handling arbitrary local-service response payloads."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.dlx import _answer_error  # noqa: E402


def test_service_error_does_not_echo_remote_message():
    """A server response may include private request text; never return it."""
    private_text = "private roleplay phrase"
    result = _answer_error({"code": "invalid_request", "message": private_text})

    assert result == "сервис вернул ошибку (код invalid_request)"
    assert private_text not in result


def test_service_error_sanitizes_non_standard_code():
    """Unknown or malformed remote codes cannot inject arbitrary text."""
    result = _answer_error({"code": "bad code\nwith details", "error": "private text"})

    assert result == "сервис вернул ошибку"
    assert "private text" not in result


def test_empty_service_response_has_no_error():
    """Successful and empty payloads keep the existing no-error convention."""
    assert _answer_error({}) == ""
