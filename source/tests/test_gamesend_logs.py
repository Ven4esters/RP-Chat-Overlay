"""Windows-only tests that game input logs redact submitted chat text."""

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.mark.skipif(sys.platform != "win32", reason="the game input adapter uses the Win32 API")
def test_game_send_logs_only_message_length(monkeypatch, caplog):
    """Both input paths log metadata without preserving the submitted message."""
    from app import gamesend

    monkeypatch.setattr(gamesend.user32, "IsWindow", lambda _hwnd: True)
    monkeypatch.setattr(gamesend, "focus", lambda _hwnd: True)
    monkeypatch.setattr(gamesend, "_ms", lambda *_args: None)
    monkeypatch.setattr(gamesend, "clear_chat_input", lambda: None)
    monkeypatch.setattr(gamesend, "paste", lambda: None)
    monkeypatch.setattr(gamesend, "type_text", lambda _text: None)
    monkeypatch.setattr(gamesend, "tap", lambda _key: None)
    monkeypatch.setattr(gamesend, "is_fg", lambda _hwnd: True)

    private_message = "private_player_message_42"
    config = {"game_input_mode": "paste", "game_submit": False}

    with caplog.at_level(logging.INFO, logger="app"):
        assert gamesend.send_to_open_chat(config, 1, private_message) == (True, "")
        assert gamesend.send_chat(config, 1, private_message) == (True, "")

    assert private_message not in caplog.text
    assert caplog.text.count("символов=") == 2
