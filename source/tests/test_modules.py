"""Тесты модуля реестра модулей / module registry tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.modules import Module, is_enabled, disabled, blockers, needed_in_other_mode, summary  # noqa: E402


def test_module_creation():
    """Создание модуля с обязательными полями."""
    m = Module(
        key="test_module",
        title_ru="Тестовый модуль",
        title_en="Test module",
        desc_ru="Описание",
        desc_en="Description",
        config_key="test_enabled",
    )
    assert m.key == "test_module"
    assert m.title_ru == "Тестовый модуль"
    assert m.title_en == "Test module"
    assert m.config_key == "test_enabled"
    assert m.default is True
    assert m.requires == ()


def test_is_enabled_without_dependencies():
    """Модуль без зависимостей включается по флагу."""
    cfg = {"test_enabled": True}
    assert is_enabled(cfg, "translator") is True  # translator_enabled default True
    cfg2 = {"translator_enabled": False}
    assert is_enabled(cfg2, "translator") is False


def test_is_enabled_with_dependencies():
    """Модуль с зависимостями выключен, если зависимость выключена."""
    cfg = {"dlx_enabled": True, "translator_enabled": False}
    # dlx требует translator
    assert is_enabled(cfg, "dlx") is False

    cfg2 = {"dlx_enabled": True, "translator_enabled": True}
    assert is_enabled(cfg2, "dlx") is True


def test_disabled_returns_keys():
    """disabled возвращает ключи выключенных модулей."""
    cfg = {"translator_enabled": False, "dlx_enabled": True}
    result = disabled(cfg)
    assert "translator" in result


def test_blockers_returns_disabled_parents():
    """blockers возвращает выключенные родительские модули."""
    cfg = {"dlx_enabled": True, "translator_enabled": False}
    result = blockers(cfg, "dlx")
    assert "translator" in result

    cfg2 = {"dlx_enabled": True, "translator_enabled": True}
    result2 = blockers(cfg2, "dlx")
    assert result2 == []


def test_needed_in_other_mode():
    """needed_in_other_mode для модуля с ограничением по режиму."""
    cfg = {"mode": "full"}
    # autotranslate только в partial режиме
    assert needed_in_other_mode(cfg, "autotranslate") is True

    cfg2 = {"mode": "partial"}
    assert needed_in_other_mode(cfg2, "autotranslate") is False

    # модуль без ограничения по режиму
    cfg3 = {"mode": "full"}
    assert needed_in_other_mode(cfg3, "translator") is False


def test_summary_all_enabled():
    """summary когда все модули включены."""
    cfg = {m.config_key: True for m in __import__("app.modules", fromlist=["MODULES"]).MODULES}
    result = summary(cfg)
    assert "все включены" in result


def test_summary_some_disabled():
    """summary когда некоторые модули выключены."""
    cfg = {"translator_enabled": False, "glossary_enabled": True}
    result = summary(cfg)
    assert "выключены" in result
    assert "translator" in result
