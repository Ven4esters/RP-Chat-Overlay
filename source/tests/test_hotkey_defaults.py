"""Regressions for the default chat/overlay keys and safe hotkey dispatch."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from app.config import DEFAULT_CONFIG
from app.keycodes import chat_key_vk


def test_default_chat_and_overlay_keys_are_swapped_as_requested():
    assert DEFAULT_CONFIG["game_chat_key"] == "t"
    assert DEFAULT_CONFIG["hotkey"] == "F6"


def test_game_chat_key_parser_supports_function_keys_and_letters():
    assert chat_key_vk({"game_chat_key": "F6"}) == 0x75
    assert chat_key_vk({"game_chat_key": "f12"}) == 0x7B
    assert chat_key_vk({"game_chat_key": "t"}) == ord("T")
    with pytest.raises(ValueError):
        chat_key_vk({"game_chat_key": "F25"})


@pytest.mark.skipif(os.name != "nt", reason="the global hotkey adapter uses Win32")
def test_overlay_hotkey_can_be_a_bare_letter():
    from app.hotkey import parse_hotkey

    assert parse_hotkey("T") == (0, ord("T"))


@pytest.mark.skipif(os.name != "nt", reason="the overlay adapter uses Win32")
def test_hotkey_dispatch_ignores_keypress_while_overlay_is_visible():
    from app.overlay import Overlay

    class FakeOverlay:
        opening = False
        sending = False

        def __init__(self, visible):
            self.visible = visible
            self.open_calls = 0

        def isVisible(self):
            return self.visible

        def open_overlay(self):
            self.open_calls += 1

    visible = FakeOverlay(True)
    Overlay.open_overlay_from_hotkey(visible)
    assert visible.open_calls == 0

    hidden = FakeOverlay(False)
    Overlay.open_overlay_from_hotkey(hidden)
    assert hidden.open_calls == 1
