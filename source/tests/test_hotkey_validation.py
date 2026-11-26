"""Validation tests for overlay hotkeys."""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytest.importorskip("PySide6")

from app.settings_ui import check_hotkey  # noqa: E402


def test_bare_letter_is_accepted_as_overlay_hotkey():
    """A bare letter such as T is a valid overlay hotkey."""
    assert check_hotkey("T") == (True, "")
    assert check_hotkey("t") == (True, "")
