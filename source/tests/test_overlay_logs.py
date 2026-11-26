"""Windows-only regression for redaction in the final send path."""

import logging
import sys
from threading import Event
from types import SimpleNamespace

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="the overlay imports Win32 game integration")
def test_finish_logs_only_output_length(monkeypatch, caplog):
    """Finishing a message never stores its content in the application log."""
    from PySide6.QtWidgets import QApplication, QWidget

    import app.overlay as overlay_module

    qapp = QApplication.instance() or QApplication([])
    assert qapp is not None
    overlay = overlay_module.Overlay.__new__(overlay_module.Overlay)
    QWidget.__init__(overlay)
    private_message = "private_overlay_message_314"
    overlay.cfg = {"max_chars": 256}
    overlay.input = SimpleNamespace(text=lambda: private_message)
    overlay.plan = SimpleNamespace(advance=lambda: None)
    overlay.game_hwnd = None
    overlay.tracker = SimpleNamespace(get=lambda _foreground: None)
    overlay.game_chat_open = False
    overlay._reset = lambda: None
    overlay._pending_text = ""
    overlay.prev_hwnd = None
    overlay.notify = lambda _message: None
    monkeypatch.setattr(overlay_module.modules, "is_enabled", lambda *_args: False)

    try:
        with caplog.at_level(logging.INFO, logger="app"):
            overlay.finish(private_message)
        assert private_message not in caplog.text
        assert "символов=" in caplog.text
    finally:
        overlay.close()


@pytest.mark.skipif(sys.platform != "win32", reason="the overlay imports Win32 game integration")
def test_translation_worker_stops_without_emitting_after_shutdown():
    """Shutdown discards an in-flight translation instead of signaling dead Qt objects."""
    from app.overlay import Worker

    started, release = Event(), Event()
    delivered = []

    def translate(job):
        started.set()
        assert release.wait(2.0)
        return job

    worker = Worker(translate, lambda *result: delivered.append(result))
    worker.start()
    worker.submit((1, "typing"))
    try:
        assert started.wait(1.0)
        worker.stop()
    finally:
        release.set()
        worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert delivered == []
