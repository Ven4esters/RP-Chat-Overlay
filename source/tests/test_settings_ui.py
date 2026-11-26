"""Qt accessibility and keyboard regressions for settings controls."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

try:
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication
except (ImportError, OSError) as error:
    if os.environ.get("RPCHAT_REQUIRE_QT_TESTS") == "1":
        raise
    pytest.skip(f"Qt runtime is unavailable: {error}", allow_module_level=True)

from app.settings_ui import ToggleSwitch


@pytest.fixture(scope="module")
def qapp():
    """Reuse one offscreen Qt application for this module."""
    return QApplication.instance() or QApplication([])


def test_toggle_switch_is_keyboard_operable_and_named(qapp):
    """A switch can be reached by Tab and toggled with Space, with a spoken name."""
    switch = ToggleSwitch()
    switch.setAccessibleName("Enable local translation service")
    switch.show()
    switch.setFocus()
    qapp.processEvents()
    changed = []
    switch.toggled.connect(changed.append)

    assert switch.focusPolicy() == Qt.FocusPolicy.TabFocus
    assert switch.accessibleName() == "Enable local translation service"
    assert switch.hasFocus()
    assert 150 <= switch._anim.duration() <= 300

    press = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_Space,
        Qt.KeyboardModifier.NoModifier,
    )
    release = QKeyEvent(
        QEvent.Type.KeyRelease,
        Qt.Key.Key_Space,
        Qt.KeyboardModifier.NoModifier,
    )
    qapp.sendEvent(switch, press)
    qapp.sendEvent(switch, release)
    qapp.processEvents()

    assert switch.isChecked()
    assert changed == [True]
    switch.close()


def test_external_switch_state_updates_do_not_emit_user_action(qapp):
    """Service status can update the switch without triggering a start/stop request."""
    switch = ToggleSwitch()
    changed = []
    switch.toggled.connect(changed.append)

    switch.set_on(True)
    assert switch.isChecked()
    assert changed == []

    switch.set_on(False)
    assert not switch.isChecked()
    assert changed == []
