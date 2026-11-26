"""Check per-module coverage floors for critical application logic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

TARGETS_PATH = Path(__file__).with_name("coverage_targets.json")


def check_coverage(
    report: Mapping[str, Any], targets: Mapping[str, Any]
) -> tuple[list[str], list[str]]:
    """Return gate failures and informational goal gaps for a coverage JSON report."""
    files = report.get("files", {})
    goal = float(targets.get("goal_percent", 80))
    failures: list[str] = []
    goal_gaps: list[str] = []

    for module, floor in targets.get("critical_modules", {}).items():
        file_report = files.get(module)
        if file_report is None:
            failures.append(f"{module}: missing from coverage report")
            continue
        coverage = float(file_report.get("summary", {}).get("percent_covered", 0.0))
        minimum = float(floor)
        if coverage + 1e-9 < minimum:
            failures.append(f"{module}: {coverage:.1f}% is below the {minimum:.1f}% CI floor")
        elif coverage + 1e-9 < goal:
            goal_gaps.append(f"{module}: {coverage:.1f}% (goal {goal:.1f}%)")

    return failures, goal_gaps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("coverage_json", type=Path, help="pytest-cov JSON report")
    args = parser.parse_args()

    try:
        report = json.loads(args.coverage_json.read_text(encoding="utf-8"))
        targets = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        parser.error(str(error))

    failures, goal_gaps = check_coverage(report, targets)
    for module, floor in targets["critical_modules"].items():
        file_report = report.get("files", {}).get(module)
        if file_report is None:
            continue
        percent = float(file_report.get("summary", {}).get("percent_covered", 0.0))
        print(f"{module}: {percent:.1f}% (CI floor {float(floor):.1f}%)")
    for gap in goal_gaps:
        print(f"Goal not yet met: {gap}")
    for failure in failures:
        print(f"Coverage gate failed: {failure}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
