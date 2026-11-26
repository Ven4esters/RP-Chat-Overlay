"""Regression tests for bounded logs and private-message redaction."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import errorlog  # noqa: E402
from app.config import setup_logging  # noqa: E402
from app.engine import Engine  # noqa: E402


def test_setup_logging_uses_bounded_rotating_handler(tmp_path, monkeypatch):
    """Application logs keep only a bounded number of UTF-8 files."""
    import app.config as config

    logs = tmp_path / "logs"
    data = tmp_path / "data"
    captured = {}

    monkeypatch.setattr(config, "DATA", data)
    monkeypatch.setattr(config, "LOGS", logs)
    monkeypatch.setattr(config, "GLOSSARY_DIR", data / "glossaries")
    monkeypatch.setattr(config, "LOG_PATH", logs / "app.log")
    monkeypatch.setattr(config.logging, "basicConfig", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(config.sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(errorlog, "install", lambda: None)

    handler = None
    try:
        setup_logging()
        handler = captured["handlers"][0]
        assert isinstance(handler, RotatingFileHandler)
        assert handler.baseFilename == str((logs / "app.log").resolve())
        assert handler.maxBytes == 2 * 1024 * 1024
        assert handler.backupCount == 3
        assert handler.encoding == "utf-8"
    finally:
        if handler is not None:
            handler.close()


def test_error_log_rotates_before_opening(tmp_path, monkeypatch):
    """An oversized crash log is archived rather than growing indefinitely."""
    path = tmp_path / "errors.log"
    backup = tmp_path / "errors.log.1"
    path.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    monkeypatch.setattr(errorlog, "LOGS", tmp_path)
    monkeypatch.setattr(errorlog, "ERROR_PATH", path)
    monkeypatch.setattr(errorlog, "_handle", None)

    try:
        errorlog._open()
        assert backup.stat().st_size == 2 * 1024 * 1024 + 1
        assert path.exists()
        assert 0 < path.stat().st_size < 256
        assert "error log started" in path.read_text(encoding="utf-8")
    finally:
        if errorlog._handle is not None:
            errorlog._handle.close()
        errorlog._handle = None


def test_disabled_translation_log_does_not_include_chat_text(monkeypatch, caplog):
    """The engine reports metadata, not the player's message content."""
    import app.engine as engine_module

    private_message = "player_private_roleplay_text"
    monkeypatch.setattr(engine_module.modules, "is_enabled", lambda _cfg, _name: False)
    engine = Engine({}, None, None)

    with caplog.at_level(logging.INFO, logger="app"):
        assert engine._translate(private_message) == private_message

    assert private_message not in caplog.text
    assert "символов=" in caplog.text
