"""Tests for the critical-module coverage gate."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from check_coverage import check_coverage  # noqa: E402


def _file_report(percent):
    return {"summary": {"percent_covered": percent}}


def test_coverage_floor_passes_and_reports_long_term_goal_gap():
    report = {"files": {"core.py": _file_report(72.0)}}
    targets = {"goal_percent": 80, "critical_modules": {"core.py": 70}}

    failures, goal_gaps = check_coverage(report, targets)

    assert failures == []
    assert goal_gaps == ["core.py: 72.0% (goal 80.0%)"]


def test_coverage_below_floor_fails():
    report = {"files": {"core.py": _file_report(69.9)}}
    targets = {"goal_percent": 80, "critical_modules": {"core.py": 70}}

    failures, goal_gaps = check_coverage(report, targets)

    assert failures == ["core.py: 69.9% is below the 70.0% CI floor"]
    assert goal_gaps == []


def test_missing_critical_module_fails():
    failures, goal_gaps = check_coverage(
        {"files": {}}, {"goal_percent": 80, "critical_modules": {"core.py": 70}}
    )

    assert failures == ["core.py: missing from coverage report"]
    assert goal_gaps == []
