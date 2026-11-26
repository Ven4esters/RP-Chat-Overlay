"""Animation runner orchestration tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.anims import Runner  # noqa: E402
from app.anims_rules import Rule  # noqa: E402


def _runner(*rules, enabled=True):
    cfg = {
        "anims_enabled": enabled,
        "anim_rules": [rule.to_dict() for rule in rules],
    }
    runner = Runner(cfg)
    queued = []
    runner._enqueue = lambda rule: queued.append(rule.name)
    return runner, queued


def test_feed_queues_rules_in_message_order_and_deduplicates_per_rule():
    runner, queued = _runner(
        Rule(keywords="first", name="anim_first"),
        Rule(keywords="second", name="anim_second"),
    )

    hits = runner.feed("second first second")

    assert [rule.name for rule in hits] == ["anim_second", "anim_first"]
    assert queued == ["anim_second", "anim_first"]


def test_feed_does_not_match_when_module_is_disabled():
    runner, queued = _runner(Rule(keywords="hello", name="anim_wave"), enabled=False)

    assert runner.feed("hello") == []
    assert queued == []


def test_vehicle_mode_blocks_rule_matching_without_replaying_stale_messages():
    runner, queued = _runner(Rule(keywords="hello", name="anim_wave"))

    assert runner.set_vehicle(True) is True
    assert runner.vehicle() is True
    assert runner.feed("hello") == []
    assert queued == []

    assert runner.set_vehicle(False) is True
    assert runner.feed("hello")
    assert queued == ["anim_wave"]
