"""Qt regression tests for the in-game animation chooser layout."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

try:
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication, QLabel
except (ImportError, OSError) as error:
    if os.environ.get("RPCHAT_REQUIRE_QT_TESTS") == "1":
        raise
    pytest.skip(f"Qt runtime is unavailable: {error}", allow_module_level=True)

from app.anims import Choice
from app.animchoice import ChoiceWindow


@pytest.fixture(scope="module")
def qapp():
    """Reuse one offscreen Qt application for this module."""
    return QApplication.instance() or QApplication([])


def test_choice_cards_keep_wrapped_text_inside_scroll_view(qapp):
    """Long localized labels remain readable; the list scrolls instead of shrinking cards."""
    choices = [
        Choice(
            name=f"anim_variant_{index}",
            title=f"A long animation title number {index} that should wrap naturally",
            description=(
                "A longer explanation of the movement, pose, and intended roleplay "
                "context that needs more than one line in the chooser. "
            )
            * 2,
        )
        for index in range(12)
    ]
    window = ChoiceWindow(
        "Choose the animation for this matching phrase",
        "The selected command will be sent to the game chat.",
        choices,
        lambda _choice: None,
    )
    try:
        window.show()
        qapp.processEvents()

        assert window._scroll.verticalScrollBar().maximum() > 0
        for card in window.buttons:
            assert card.height() >= card.layout().sizeHint().height()
            assert card.accessibleName()
            for label in card.findChildren(QLabel):
                if label.wordWrap():
                    assert label.height() >= label.heightForWidth(label.width())

        selected = []
        window.done_callback = selected.append
        window.buttons[2].setFocus()
        qapp.processEvents()
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Return,
            Qt.KeyboardModifier.NoModifier,
        )
        window.keyPressEvent(event)
        assert selected == [choices[2]]
    finally:
        window.close()
        qapp.processEvents()
