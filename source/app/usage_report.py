"""Opt-in, privacy-preserving local performance summary.

The report stores only operation names, elapsed-time aggregates and failure
counts. It never records function arguments, chat text, usernames or game IDs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
import os
from pathlib import Path
import threading
import time
from typing import Callable, TypeVar

T = TypeVar("T")

# Bucket boundaries cap the memory used for timings regardless of session length.
_BUCKETS_MS = (1, 5, 20, 50, 100, 250, 500, 1000, 3000, 10000)
_ACTIVE: UsageReporter | None = None
_ACTIVE_LOCK = threading.RLock()

_OPERATION_LABELS = {
    "translation": "Translation service calls",
    "engine.process": "Message processing (partial/default)",
    "engine.process_full": "Message processing (full mode)",
    "engine.process_in": "Message processing (to Russian)",
    "game.send_chat": "Sending text to game chat",
    "animation.plan": "Animation rule matching",
}


class UsageReporter:
    """Collect bounded aggregates and atomically write a Markdown report."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.started_at = datetime.now(timezone.utc)
        self._started = time.monotonic()
        self._lock = threading.RLock()
        self._metrics: dict[str, dict[str, int | float | list[int]]] = {}

    def record(self, operation: str, elapsed_seconds: float, failed: bool) -> None:
        """Record a single call without retaining any call arguments or result."""
        try:
            elapsed_ms = max(0.0, float(elapsed_seconds) * 1000.0)
            with self._lock:
                metric = self._metrics.setdefault(
                    operation,
                    {
                        "count": 0,
                        "failures": 0,
                        "total_ms": 0.0,
                        "min_ms": elapsed_ms,
                        "max_ms": elapsed_ms,
                        "buckets": [0] * (len(_BUCKETS_MS) + 1),
                    },
                )
                metric["count"] += 1
                metric["failures"] += int(failed)
                metric["total_ms"] += elapsed_ms
                metric["min_ms"] = min(float(metric["min_ms"]), elapsed_ms)
                metric["max_ms"] = max(float(metric["max_ms"]), elapsed_ms)
                bucket = next(
                    (index for index, boundary in enumerate(_BUCKETS_MS) if elapsed_ms <= boundary),
                    len(_BUCKETS_MS),
                )
                metric["buckets"][bucket] += 1
        except Exception:
            # Instrumentation must never change application behaviour.
            return

    def write(self) -> None:
        """Write the current snapshot; safe to call from the GUI or worker thread."""
        try:
            with self._lock:
                metrics = {
                    name: {**values, "buckets": list(values["buckets"])}
                    for name, values in self._metrics.items()
                }
            content = self._render(metrics)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(self.path.name + ".tmp")
            temporary.write_text(content, encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError:
            import logging

            logging.getLogger("app").exception("Could not write the opt-in usage report")

    def _render(self, metrics: dict[str, dict]) -> str:
        elapsed = max(0, int(time.monotonic() - self._started))
        updated = datetime.now(timezone.utc).isoformat(timespec="seconds")
        lines = [
            "# FiveM Chat Overlay — local usage and performance report",
            "",
            f"- Started (UTC): {self.started_at.isoformat(timespec='seconds')}",
            f"- Updated (UTC): {updated}",
            f"- Measured runtime: {_format_duration(elapsed)}",
            "- Privacy: aggregates only; no chat text, usernames, game IDs or call "
            "arguments are collected.",
            "",
            "| Operation | Calls | Failures | Average | Maximum | p50 (approx.) | p95 (approx.) |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        if not metrics:
            lines.append("| No measured operations yet | 0 | 0 | — | — | — | — |")
        for operation, metric in sorted(metrics.items()):
            label = _OPERATION_LABELS.get(operation, "Other application operation")
            count = int(metric["count"])
            average = float(metric["total_ms"]) / count if count else 0.0
            buckets = metric["buckets"]
            lines.append(
                "| %s | %d | %d | %s | %s | %s | %s |"
                % (
                    label,
                    count,
                    int(metric["failures"]),
                    _format_ms(average),
                    _format_ms(float(metric["max_ms"])),
                    _percentile_bucket(buckets, count, 0.50),
                    _percentile_bucket(buckets, count, 0.95),
                )
            )
        lines.extend(
            [
                "",
                "This file is generated locally because usage reporting was enabled in Settings.",
                "It is not uploaded or transmitted by the application. You may review or "
                "delete it at any time.",
                "",
            ]
        )
        return "\n".join(lines)


def _percentile_bucket(buckets: list[int], count: int, percentile: float) -> str:
    if not count:
        return "—"
    target = max(1, int(count * percentile + 0.999999))
    seen = 0
    for index, bucket_count in enumerate(buckets):
        seen += bucket_count
        if seen >= target:
            if index == len(_BUCKETS_MS):
                return "> 10000 ms"
            lower = 0 if index == 0 else _BUCKETS_MS[index - 1]
            upper = _BUCKETS_MS[index]
            return f"≤ {upper} ms" if lower == 0 else f"{lower}–{upper} ms"
    return "—"


def _format_ms(value: float) -> str:
    return f"{value:.1f} ms"


def _format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"


def measure_call(operation: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator that measures duration/failure, while deliberately ignoring args."""

    def decorate(function: Callable[..., T]) -> Callable[..., T]:
        @wraps(function)
        def measured(*args, **kwargs):
            with _ACTIVE_LOCK:
                reporter = _ACTIVE
            if reporter is None:
                return function(*args, **kwargs)
            started = time.perf_counter()
            failed = False
            try:
                return function(*args, **kwargs)
            except BaseException:
                failed = True
                raise
            finally:
                reporter.record(operation, time.perf_counter() - started, failed)

        return measured

    return decorate


def set_enabled(enabled: bool, path: str | Path | None = None) -> None:
    """Start or stop collection. Collection remains completely off by default."""
    global _ACTIVE
    with _ACTIVE_LOCK:
        current = _ACTIVE
        if enabled and current is not None:
            return
        if not enabled and current is None:
            return
        if current is not None:
            current.write()
            _ACTIVE = None
        if enabled:
            if path is None:
                from app.config import DATA

                path = DATA / "usage-report.md"
            _ACTIVE = UsageReporter(path)
            _ACTIVE.write()


def flush() -> None:
    """Persist an enabled report without stopping collection."""
    with _ACTIVE_LOCK:
        current = _ACTIVE
    if current is not None:
        current.write()


def stop() -> None:
    """Persist the final report and disable collection at application exit."""
    set_enabled(False)
