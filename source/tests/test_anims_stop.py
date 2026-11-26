"""Animation stop-key validation and watcher tests."""

import sys
from pathlib import Path
from types import ModuleType

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import anims  # noqa: E402
from app import anims_stop  # noqa: E402
from app.anims_stop import (  # noqa: E402
    STOP_KEY_MODS,
    VAL_BAD_STOP_KEY,
    VAL_EMPTY_STOP_KEY,
    VAL_UNKNOWN_STOP_KEY,
    StopWatcher,
    stop_key_problem,
)


@pytest.mark.parametrize("spec", ["F", "space", "Ctrl+F12", "shift + f1", "F24"])
def test_valid_stop_keys(spec):
    assert stop_key_problem(spec) == ""


@pytest.mark.parametrize("spec", ["", "   "])
def test_missing_stop_key(spec):
    assert stop_key_problem(spec) == VAL_EMPTY_STOP_KEY


@pytest.mark.parametrize("spec", ["ctrl+alt", "ctrl+a+b"])
def test_ambiguous_stop_key(spec):
    assert stop_key_problem(spec) == VAL_BAD_STOP_KEY


@pytest.mark.parametrize("spec", ["escape", "f0", "f25"])
def test_unsupported_stop_key(spec):
    assert stop_key_problem(spec) == VAL_UNKNOWN_STOP_KEY


def test_legacy_anims_exports_stay_available():
    assert anims.stop_key_problem is stop_key_problem
    assert anims.StopWatcher is StopWatcher


def test_watcher_does_not_prepare_on_non_windows(monkeypatch):
    monkeypatch.setattr(anims_stop.sys, "platform", "linux")
    watcher = StopWatcher("F", lambda: None)
    assert watcher._ok is False
    assert watcher._vk == 0


def test_watcher_prepares_key_with_lazy_hotkey_import(monkeypatch):
    fake_hotkey = ModuleType("app.hotkey")
    fake_hotkey.parse_hotkey = lambda spec: (3, 0x70)
    monkeypatch.setattr(anims_stop.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "app.hotkey", fake_hotkey)

    watcher = StopWatcher("ctrl+alt+f1", lambda: None)

    assert watcher._ok is True
    assert (watcher._mods, watcher._vk) == (3, 0x70)


def test_watcher_requires_key_and_requested_modifiers(monkeypatch):
    fake_hotkey = ModuleType("app.hotkey")
    fake_hotkey.MODS = {"alt": 1, "ctrl": 2, "shift": 4, "win": 8}
    monkeypatch.setitem(sys.modules, "app.hotkey", fake_hotkey)
    watcher = StopWatcher("F", lambda: None)
    watcher._mods = fake_hotkey.MODS["ctrl"] | fake_hotkey.MODS["shift"]
    pressed = {0x11: True, 0x10: True}
    monkeypatch.setattr(watcher, "_down", lambda vk: pressed.get(vk, False))

    assert watcher._mods_down() is True
    pressed[0x10] = False
    assert watcher._mods_down() is False
    watcher._mods = 0
    assert watcher._mods_down() is True
    assert STOP_KEY_MODS == ("ctrl", "alt", "shift", "win")


class _ScheduledPolls:
    """Supply key states for deterministic polling without sleeping."""

    def __init__(self, stop_after):
        self.stop_after = stop_after
        self.calls = 0

    def wait(self, _timeout):
        self.calls += 1
        return self.calls > self.stop_after

    def set(self):
        self.calls = self.stop_after + 1


def test_watcher_calls_callback_once_per_press_edge():
    calls = []
    watcher = StopWatcher("F", lambda: calls.append("stop"))
    watcher._ok = True
    watcher._stop_flag = _ScheduledPolls(stop_after=4)
    key_states = iter([True, True, False, True])
    watcher._down = lambda _vk: next(key_states)
    watcher._mods_down = lambda: True

    watcher.run()

    assert calls == ["stop", "stop"]
    assert watcher._stop_flag.calls == 5


def test_watcher_checks_active_state_only_at_press_edge():
    calls = []
    active_states = iter([False, True])
    watcher = StopWatcher("F", lambda: calls.append("stop"), active_fn=lambda: next(active_states))
    watcher._ok = True
    watcher._stop_flag = _ScheduledPolls(stop_after=4)
    key_states = iter([True, True, False, True])
    watcher._down = lambda _vk: next(key_states)
    watcher._mods_down = lambda: True

    watcher.run()

    assert calls == ["stop"]
