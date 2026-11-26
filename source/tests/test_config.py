"""Тесты модуля конфигурации / config module tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.config as config_module  # noqa: E402
from app.config import DEFAULT_CONFIG, _local_fallback_root, _root, resource_path, load_config  # noqa: E402


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


def test_load_config_preserves_configured_chat_and_overlay_keys(monkeypatch):
    """Existing key choices remain intact when a config is loaded."""
    saved = {"game_chat_key": "t", "hotkey": "F6"}
    monkeypatch.setattr(config_module, "read_json", lambda *_args: saved)
    monkeypatch.setattr(config_module, "save_config", lambda _cfg: None)

    loaded = load_config()
    assert loaded["game_chat_key"] == "t"
    assert loaded["hotkey"] == "F6"


def test_local_fallback_root_keeps_existing_legacy_user_data(tmp_path):
    """Renaming the app must not strand existing settings and logs."""
    legacy = tmp_path / "RPChatOverlay"
    legacy.mkdir()
    assert _local_fallback_root(tmp_path) == legacy


def test_local_fallback_root_uses_new_name_for_fresh_install(tmp_path):
    """Fresh installs use the new branded data directory."""
    assert _local_fallback_root(tmp_path) == tmp_path / "FiveMChatOverlay"


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
