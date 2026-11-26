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

from app import animations as anims
from app.config import DEFAULT_CONFIG
from app.settings_ui import SettingsWindow, ToggleSwitch


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


def test_keyword_cell_opens_multiline_editor_and_is_not_inline_editable(qapp, monkeypatch):
    """Selecting keywords opens the dedicated editor instead of editing a narrow cell."""
    window = SettingsWindow(dict(DEFAULT_CONFIG))
    opened = []
    try:
        row = window._add_anim_row(anims.Rule(keywords="wave, привет", name="wave"))
        item = window.tbl_anims.item(row, 1)
        assert not (item.flags() & Qt.ItemFlag.ItemIsEditable)

        monkeypatch.setattr(window, "_edit_anim_keywords", lambda selected: opened.append(selected))
        window.tbl_anims.cellClicked.emit(row, 1)

        assert opened == [item]
    finally:
        window.close()
        qapp.processEvents()


def test_default_key_fields_show_requested_keys(qapp):
    """The settings form starts with T for game chat and F6 for the overlay."""
    window = SettingsWindow(dict(DEFAULT_CONFIG))
    try:
        assert window.ed_chatkey.text() == "t"
        assert window.ed_hotkey.text() == "F6"
        assert (
            window.chk_chat_first.text() == "Сначала открывать чат игры (клавиша T), потом оверлей"
        )
        assert "F6" in window.lb_hotkey_hint.text()
        assert "T" in window.lb_hotkey_hint.text()

        window.ed_chatkey.setText("F8")
        assert "F8" in window.chk_chat_first.text()
        assert "F8" in window.lb_hotkey_hint.text()
        window.ed_hotkey.setText("Ctrl+Alt+Q")
        window._hotkey_changed()
        assert "Ctrl+Alt+Q" in window.lb_hotkey_hint.text()
        assert "Ctrl+Alt+Q" in window.header_sub.text()
    finally:
        window.close()
        qapp.processEvents()


def test_animation_page_reactivates_immediately_when_module_is_enabled(qapp):
    """Enabling Animations restores existing controls without needing a table edit."""
    cfg = dict(DEFAULT_CONFIG)
    cfg["anims_enabled"] = False
    cfg["game_send"] = True
    window = SettingsWindow(cfg)
    try:
        window.nav.setCurrentRow(window._anims_row)
        qapp.processEvents()

        assert window.page_anims.property("moduleOff") is True
        assert not window.bt_anim_add.isEnabled()

        window.chk_modules["anims_enabled"].setChecked(True)
        qapp.processEvents()

        assert window.page_anims.property("moduleOff") is False
        assert window.bt_anim_add.isEnabled()
        assert window.tbl_anims.isEnabled()
    finally:
        window.close()
        qapp.processEvents()
