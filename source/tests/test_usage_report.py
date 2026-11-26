"""Tests for privacy and aggregation of the opt-in usage report."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.usage_report as usage_report  # noqa: E402
from app.config import DEFAULT_CONFIG  # noqa: E402


def test_report_is_disabled_by_default():
    """New installs do not collect or write report data."""
    assert DEFAULT_CONFIG["usage_report_enabled"] is False
    usage_report.stop()


def test_report_aggregates_calls_without_recording_chat_text(tmp_path):
    """Only fixed operation labels and timing aggregates reach the report."""
    report_path = tmp_path / "usage-report.md"
    usage_report.set_enabled(True, report_path)

    @usage_report.measure_call("translation")
    def translate(text):
        if text == "private chat phrase":
            return "translated private phrase"
        raise ValueError(text)

    assert translate("private chat phrase") == "translated private phrase"
    try:
        translate("another private message")
    except ValueError:
        pass
    else:
        raise AssertionError("expected test translation to fail")

    usage_report.stop()
    report = report_path.read_text(encoding="utf-8")
    assert "Translation service calls" in report
    assert "| 2 | 1 |" in report
    assert "private chat phrase" not in report
    assert "translated private phrase" not in report
    assert "another private message" not in report
    assert "names, game IDs or call arguments" in report


def test_report_can_be_disabled_mid_session(tmp_path):
    """Disabling writes the last snapshot and stops subsequent measurements."""
    report_path = tmp_path / "usage-report.md"
    usage_report.set_enabled(True, report_path)

    @usage_report.measure_call("animation.plan")
    def match_rules():
        return "ok"

    assert match_rules() == "ok"
    usage_report.set_enabled(False)
    first_snapshot = report_path.read_text(encoding="utf-8")
    assert "Animation rule matching" in first_snapshot

    assert match_rules() == "ok"
    assert report_path.read_text(encoding="utf-8") == first_snapshot
