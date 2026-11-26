"""Тесты модуля анимаций / anims module tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.animations import (  # noqa: E402
    MODE_ALWAYS,
    Rule,
    plan,
    MODE_ACTIONS,
    MODE_MESSAGES,
    message_family,
    family_hits,
    suggestions,
)


def test_message_family_plain_words():
    """message_family для обычных слов."""
    result = message_family("привет мир")
    assert result in ("messages", "actions", "both")


def test_message_family_with_action():
    """message_family для текста со звёздочками."""
    result = message_family("*открыл зонт*")
    assert result in ("messages", "actions", "both")


def test_message_family_empty():
    """message_family для пустой строки."""
    result = message_family("")
    assert result in ("messages", "actions", "both")


def test_family_hits_messages():
    """family_hits для обычных сообщений (MODE_MESSAGES=4)."""
    assert family_hits(MODE_MESSAGES, "messages") is True
    assert family_hits(MODE_MESSAGES, "actions") is False


def test_family_hits_actions():
    """family_hits для действий (MODE_ACTIONS=3)."""
    assert family_hits(MODE_ACTIONS, "actions") is True
    assert family_hits(MODE_ACTIONS, "messages") is False


def test_family_hits_has_action():
    """family_hits с has_action=True совпадает и с actions, и с messages."""
    assert family_hits(MODE_MESSAGES, "messages", has_action=True) is True
    assert family_hits(MODE_ACTIONS, "actions", has_action=True) is True


def test_family_hits_always():
    """MODE_ALWAYS подходит для любой семьи."""
    assert family_hits(MODE_ALWAYS, "messages") is True
    assert family_hits(MODE_ALWAYS, "actions") is True


def test_suggestions_returns_list():
    """suggestions возвращает список."""
    result = suggestions([], "привет")
    assert isinstance(result, list)


def test_animation_logs_do_not_include_chat_text(caplog):
    """Animation diagnostics must not persist player message contents."""
    import logging

    message = "private_chat_phrase waves goodbye"
    rule = Rule(keywords="private_chat_phrase", name="anim_wave")

    with caplog.at_level(logging.INFO, logger="app"):
        assert len(plan([rule], message)) == 1

    assert message not in caplog.text
    assert "private_chat_phrase" not in caplog.text
    assert "waves goodbye" not in caplog.text
