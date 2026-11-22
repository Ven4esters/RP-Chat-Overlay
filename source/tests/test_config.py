"""Тесты модуля конфигурации / config module tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DEFAULT_CONFIG, _root, resource_path, load_config  # noqa: E402


def test_default_config_has_required_keys():
    """DEFAULT_CONFIG содержит все ключи по умолчанию."""
    assert "target_lang" in DEFAULT_CONFIG
    assert "ui_lang" in DEFAULT_CONFIG
    assert "mode" in DEFAULT_CONFIG
    assert "translator_enabled" in DEFAULT_CONFIG
    assert "glossary_enabled" in DEFAULT_CONFIG
    assert "game_send" in DEFAULT_CONFIG
    assert "dlx_enabled" in DEFAULT_CONFIG
    assert "anims_enabled" in DEFAULT_CONFIG
    assert "hotkey_enabled" in DEFAULT_CONFIG


def test_default_config_values():
    """Проверка значений по умолчанию."""
    assert DEFAULT_CONFIG["target_lang"] == "it"
    assert DEFAULT_CONFIG["ui_lang"] == "ru"
    assert DEFAULT_CONFIG["mode"] == "partial"
    assert DEFAULT_CONFIG["translator_enabled"] is True
    assert DEFAULT_CONFIG["glossary_enabled"] is True
    assert DEFAULT_CONFIG["dlx_enabled"] is False
    assert DEFAULT_CONFIG["anims_enabled"] is False


def test_root_returns_path():
    """_root возвращает объект Path."""
    root = _root()
    assert isinstance(root, Path)
    assert root.exists()


def test_resource_path_returns_path():
    """resource_path возвращает объект Path."""
    path = resource_path("icon.ico")
    assert isinstance(path, Path)


def test_load_config_returns_dict():
    """load_config возвращает словарь."""
    cfg = load_config()
    assert isinstance(cfg, dict)
