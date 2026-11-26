"""Tests for the interface translation catalog and function module split."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import i18n  # noqa: E402


def test_english_catalog_is_loaded_from_separate_data_module():
    """Runtime translation continues to use the extracted English catalog."""
    previous = i18n.lang()
    try:
        i18n.set_lang("en")
        assert i18n.t("Кэш переводов") == "Translation cache"
        assert i18n.t("Собирать отчёт производительности") == "Collect a performance report"
    finally:
        i18n.set_lang(previous)


def test_unknown_translation_keeps_source_text():
    """An untranslated string remains readable in English mode."""
    previous = i18n.lang()
    try:
        i18n.set_lang("en")
        assert i18n.t("Uncatalogued source label") == "Uncatalogued source label"
    finally:
        i18n.set_lang(previous)
