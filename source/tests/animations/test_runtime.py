"""Animation runner orchestration and state-machine tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

from app import anims  # noqa: E402
from app.animations import Runner  # noqa: E402
from app.animations import runtime as runtime_module  # noqa: E402
from app.animations.rules import Choice, Rule  # noqa: E402


def _runner(*rules, enabled=True, send=None, on_event=None, **options):
    cfg = {
        "anims_enabled": enabled,
        "anim_rules": [rule.to_dict() for rule in rules],
        **options,
    }
    runner = Runner(cfg, send=send, on_event=on_event)
    queued = []
    runner._enqueue = lambda rule: queued.append(rule.name)
    runner._ensure_thread = lambda: None
    return runner, queued


class _StopSignal:
    def __init__(self, wait_result=False):
        self.wait_result = wait_result
        self.cleared = 0
        self.set_count = 0
        self.waits = []

    def clear(self):
        self.cleared += 1

    def set(self):
        self.set_count += 1

    def wait(self, timeout=None):
        self.waits.append(timeout)
        return self.wait_result(len(self.waits)) if callable(self.wait_result) else self.wait_result


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


def test_settings_helpers_reload_and_state_snapshot():
    first = Rule(keywords="wave", name="anim_wave", loop=True)
    runner, _ = _runner(first, anim_extra_ms="not-a-number")
    assert runner.enabled() is True
    assert runner.negation() is True
    assert runner.extra() == pytest.approx(runtime_module.ANIM_EXTRA_MS / 1000)
    assert runner.stop_methods() == (True, False)
    assert runner.rules()[0].name == "anim_wave"
    assert runner.state() == {
        "enabled": True,
        "rules": 1,
        "current": "",
        "loop": False,
        "queued": 0,
        "error": "",
        "trigger": "",
        "vehicle": False,
    }

    runner.cfg["anim_extra_ms"] = 10**9
    assert runner.extra() == pytest.approx(runtime_module.MAX_EXTRA_MS / 1000)
    runner.cfg["anim_extra_ms"] = -1
    assert runner.extra() == 0
    runner.cfg["anim_extra_ms"] = None
    runner.cfg["anim_gap_ms"] = "25"
    assert runner.extra() == 0.025
    runner.cfg["anim_stop_by_sa"] = False
    runner.cfg["anim_stop_by_key"] = True
    assert runner.stop_methods() == (False, True)

    runner.reload({"anims_enabled": True, "anim_rules": []})
    assert runner.rules() == []
    assert runner.state()["rules"] == 0


def test_reload_disabled_clears_queue_and_turns_off():
    runner, _ = _runner(Rule(keywords="wave", name="anim_wave"))
    runner._queue.append(Rule(keywords="old", name="anim_old"))
    runner.reload({"anims_enabled": False, "anim_rules": []})
    assert list(runner._queue) == []
    assert runner._stop_run.is_set()


def test_feed_filters_unready_rules_and_empty_messages():
    runner, queued = _runner(
        Rule(keywords=" ", name="bad"),
        Rule(keywords="valid", name="anim_valid", enabled=False),
        Rule(keywords="valid", name="anim_ready"),
    )
    assert runner.feed("  ") == []
    hits = runner.feed("valid")
    assert [rule.name for rule in hits] == ["anim_ready"]
    assert queued == ["anim_ready"]


def test_emit_contains_callback_errors_without_propagating(caplog):
    def broken(_kind, _text):
        raise RuntimeError("callback failed")

    runner, _ = _runner(on_event=broken)
    runner._emit("done", "anim_wave")
    assert "колбэк состояния упал" in caplog.text


def test_enqueue_snapshots_rules_and_rejects_overflow(monkeypatch):
    rule = Rule(keywords="wave", name="anim_wave")
    runner = Runner({})
    runner._ensure_thread = lambda: None
    monkeypatch.setattr(runtime_module, "MAX_QUEUE", 1)
    runner._enqueue(rule)
    rule.name = "changed_after_enqueue"
    assert runner._queue[0].name == "anim_wave"
    runner._enqueue(Rule(keywords="next", name="anim_next"))
    assert len(runner._queue) == 1
    assert runner.state()["error"] == "очередь переполнена"


def test_stop_user_preserves_queue_but_stop_clears_it():
    runner, _ = _runner()
    queued = Rule(keywords="later", name="anim_later")
    runner._queue.append(queued)
    events = []
    runner.on_event = lambda *event: events.append(event)

    assert runner.stop_user() is True
    assert list(runner._queue) == [queued]
    assert runner._reset_pending is True
    assert runner._stop_run.is_set()
    assert events[-1] == ("stopped", "остановлено игроком")

    assert runner.stop("settings changed") is True
    assert list(runner._queue) == []
    assert runner._reset_pending is False
    assert events[-1] == ("stopped", "settings changed")
    assert runner.stop() is False


def test_stop_user_without_work_returns_false():
    runner, _ = _runner()
    assert runner.stop_user() is False
    assert runner._reset_pending is True


def test_vehicle_transition_sends_exactly_one_forced_stop_and_quiets():
    sent = []
    runner, _ = _runner(send=lambda command: sent.append(command) or (True, ""))
    runner._current = Rule(keywords="wave", name="anim_wave")
    events = []
    runner.on_event = lambda *event: events.append(event)

    assert runner.set_vehicle(True, "test") is True
    assert sent == ["/sa"]
    assert runner.vehicle() is True
    assert events == [
        ("stopped", "остановлено перед машиной"),
        ("vehicle", "режим «в машине» включён"),
    ]
    assert runner.guard_quiet() is False
    assert runner.guard_quiet() is False
    assert runner._quiet_off is True
    assert runner.set_vehicle(True) is True
    assert sent == ["/sa"]

    assert runner.set_vehicle(False) is True
    assert runner.vehicle() is False
    assert events[-1] == ("vehicle", "режим «в машине» выключен")


def test_vehicle_transition_drops_waiting_queue_without_current_animation():
    runner, _ = _runner()
    runner._queue.extend(
        [Rule(keywords="one", name="anim_one"), Rule(keywords="two", name="anim_two")]
    )
    assert runner.set_vehicle(True) is True
    assert list(runner._queue) == []
    assert runner._stop_run.is_set()


def test_send_handles_success_failure_exception_and_vehicle_guard():
    sent = []
    events = []
    runner, _ = _runner(
        send=lambda command: sent.append(command) or (False, "rejected"),
        on_event=lambda *event: events.append(event),
    )
    rule = Rule(keywords="wave", name="anim_wave")

    assert runner._send("/anim anim_wave", rule) is False
    assert runner._last_error == "rejected"
    assert events == [("error", "/anim anim_wave: rejected")]

    runner.send = lambda _command: (_ for _ in ()).throw(RuntimeError("network gone"))
    assert runner._send("/sa", rule, quiet=True) is False
    assert runner._last_error == "network gone"
    assert len(events) == 1

    runner.set_vehicle(True)
    assert runner._send("/anim blocked", rule) is False
    assert runner._send("/sa", rule, force=True, quiet=True) is False


def test_stop_animation_supports_both_methods_and_failures():
    commands = []
    keys = []
    runner, _ = _runner(
        send=lambda command: commands.append(command) or (True, ""),
        anim_stop_by_sa=True,
        anim_stop_by_key=True,
        anim_stop_key="ctrl+f",
    )
    runner.press_key = lambda spec: keys.append(spec) or (True, "")
    rule = Rule(keywords="wave", name="anim_wave")
    runner._stop_animation(rule)
    assert commands == ["/sa"]
    assert keys == ["ctrl+f"]

    runner.press_key = None
    runner._stop_animation(rule)
    assert runner._last_error == ""

    runner.press_key = lambda _spec: (False, "key blocked")
    runner._stop_animation(rule)
    assert runner._last_error == "key blocked"

    runner.press_key = lambda _spec: (_ for _ in ()).throw(ValueError("input unavailable"))
    runner._stop_animation(rule)
    assert runner._last_error == "input unavailable"


def test_play_without_duration_sends_one_command_and_reports_done(monkeypatch):
    sent = []
    events = []
    runner, _ = _runner(
        send=lambda command: sent.append(command) or (True, ""),
        on_event=lambda *event: events.append(event),
    )
    runner._stop_run = _StopSignal()
    monkeypatch.setattr(runtime_module.time, "monotonic", lambda: 12.5)

    runner._play(Rule(keywords="wave", name="anim_wave", duration_ms=0))

    assert sent == ["/anim anim_wave"]
    assert events == [("playing", "anim_wave"), ("done", "anim_wave")]
    assert runner._end_at == 12.5
    assert runner._stop_run.cleared == 1


def test_play_does_not_wait_when_initial_send_fails(monkeypatch):
    events = []
    runner, _ = _runner(
        send=lambda _command: (False, "offline"),
        on_event=lambda *event: events.append(event),
    )
    runner._stop_run = _StopSignal()
    monkeypatch.setattr(runtime_module.time, "monotonic", lambda: 4.0)

    runner._play(Rule(keywords="wave", name="anim_wave", duration_ms=100))

    assert runner._last_error == "offline"
    assert runner._end_at == 4.0
    assert runner._stop_run.waits == []
    assert events == [("playing", "anim_wave"), ("error", "/anim anim_wave: offline")]


def test_play_waits_until_deadline_then_stops_and_notifies(monkeypatch):
    sent = []
    events = []
    runner, _ = _runner(
        send=lambda command: sent.append(command) or (True, ""),
        on_event=lambda *event: events.append(event),
        anim_extra_ms=0,
    )
    runner._stop_run = _StopSignal()
    clock = iter([10.0, 10.04, 10.04, 10.10])
    monkeypatch.setattr(runtime_module.time, "monotonic", lambda: next(clock))

    runner._play(Rule(keywords="wave", name="anim_wave", duration_ms=100))

    assert sent == ["/anim anim_wave", "/sa"]
    assert events[-1] == ("done", "anim_wave")
    assert runner._end_at == 10.1


def test_play_user_stop_clears_reset_and_notifies_choice(monkeypatch):
    rule = Rule(keywords="wave", name="anim_wave", duration_ms=100)
    events = []
    runner, _ = _runner(
        send=lambda _command: (True, ""),
        on_event=lambda *event: events.append(event),
    )
    runner._stop_run = _StopSignal(wait_result=True)
    runner._reset_pending = True
    runner._notify_rule_done = lambda actual: events.append(("rule-done", actual.name))
    stopped = []
    runner._stop_animation = lambda actual: stopped.append(actual.name)
    clock = iter([1.0, 1.01, 1.01, 1.02])
    monkeypatch.setattr(runtime_module.time, "monotonic", lambda: next(clock))

    runner._play(rule)

    assert stopped == ["anim_wave"]
    assert runner._reset_pending is False
    assert runner._end_at == 1.02
    assert events[-1] == ("rule-done", "anim_wave")


def test_play_loop_restarts_until_send_fails(monkeypatch):
    sent = []

    def send(command):
        sent.append(command)
        return (len(sent) == 1, "loop send failed")

    runner, _ = _runner(send=send)
    runner._stop_run = _StopSignal()
    clock = iter([0.0, 0.1])
    monkeypatch.setattr(runtime_module.time, "monotonic", lambda: next(clock))

    runner._play(Rule(keywords="wave", name="anim_wave", duration_ms=100, loop=True))

    assert sent == ["/anim anim_wave", "/anim anim_wave"]
    assert runner._last_error == "loop send failed"
    assert runner._end_at == pytest.approx(0.2)


def test_play_variant_change_stops_old_animation_and_restarts(monkeypatch):
    rule = Rule(
        keywords="wave",
        name="anim_one",
        duration_ms=1,
        choices=[Choice(name="anim_one", title="One"), Choice(name="anim_two", title="Two")],
    )
    sent = []
    events = []
    runner, _ = _runner(
        send=lambda command: sent.append(command) or (True, ""),
        on_event=lambda *event: events.append(event),
    )
    runner._stop_run = _StopSignal(wait_result=lambda count: count > 1)
    runner.chooser = lambda _rule, **_kwargs: Choice(name="anim_one", title="One")
    runner._take_swap = lambda _token: (
        Choice(name="anim_two", title="Two") if len(sent) == 1 else None
    )
    stopped = []
    finished = []
    runner._stop_animation = lambda actual: stopped.append(actual.name)
    runner._notify_rule_done = lambda actual: finished.append(actual.name)
    clock = iter([2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0])
    monkeypatch.setattr(runtime_module.time, "monotonic", lambda: next(clock))

    runner._play(rule)

    assert sent == ["/anim anim_one", "/anim anim_two"]
    assert stopped == ["anim_one"]
    assert finished == ["anim_one"]
    assert ("playing", "Two") in events


def test_choose_variants_handles_missing_choice_cancel_and_callback():
    runner, _ = _runner()
    empty = Rule(keywords="empty", name="")
    assert runner._choose(empty) is None

    single = Rule(keywords="one", name="anim_one")
    assert runner._choose(single).name == "anim_one"

    multiple = Rule(
        keywords="multi",
        choices=[Choice(name="anim_one"), Choice(name="anim_two")],
    )
    assert runner._choose(multiple).name == "anim_one"

    def chooser(_rule, on_change=None):
        assert callable(on_change)
        on_change(Choice(name="anim_two"))
        assert runner._swap_choice.name == "anim_two"
        return None

    runner.chooser = chooser
    runner._current = multiple
    assert runner._choose(multiple, token=runner._play_token) is None


def test_choose_uses_attached_chooser_and_falls_back_on_errors():
    runner, _ = _runner()
    rule = Rule(
        keywords="multi",
        choices=[Choice(name="anim_one"), Choice(name="anim_two")],
    )
    attached = []

    def chooser(_rule, on_change=None):
        return Choice(name="anim_two")

    chooser.attach = lambda actual, callback: attached.append((actual, callback))
    runner.chooser = chooser
    assert runner._choose(rule).name == "anim_two"
    assert attached[0][0] is rule
    attached[0][1](Choice(name="anim_one"))
    assert runner._queue[0].name == "anim_one"

    runner.chooser = lambda _rule, **_kwargs: (_ for _ in ()).throw(RuntimeError("chooser error"))
    assert runner._choose(rule).name == "anim_one"


def test_push_swap_removes_duplicate_and_can_cancel_current_rule():
    runner, _ = _runner()
    first = Rule(keywords="same", name="anim_old")
    duplicate = Rule.from_dict(first.to_dict())
    runner._queue.extend([first, duplicate, Rule(keywords="other", name="anim_other")])
    runner._current = first

    assert runner.push_swap(first, None) is True
    assert len(runner._queue) == 1
    assert runner._stop_run.is_set()

    choice = Choice(name="anim_new")
    assert runner.push_swap(first, choice) is True
    assert runner._queue[0].name == "anim_new"


def test_choice_notifications_support_legacy_callbacks_and_log_errors(caplog):
    runner, _ = _runner()

    class Chooser:
        def rule_finished(self):
            raise RuntimeError("finished failed")

        def rule_stopped(self):
            raise RuntimeError("stopped failed")

        def cancel(self):
            raise RuntimeError("cancel failed")

    runner.chooser = Chooser()
    runner._notify_rule_done(Rule(name="anim"))
    runner._chooser_stopped(Rule(name="anim"))
    runner._drop_choice_window(close=True)
    assert "не удалось снять пометку" in caplog.text
    assert "не удалось снять меню" in caplog.text
    assert "не удалось закрыть окно выбора" in caplog.text


def test_clear_and_shutdown_leave_no_worker_state():
    runner, _ = _runner()
    runner._queue.append(Rule(keywords="wave", name="anim_wave"))
    runner.clear("closing")
    assert list(runner._queue) == []
    assert runner._thread is None
    assert runner._done.is_set() is False
    runner.shutdown()
    assert runner._thread is None


def test_loop_consumes_queue_and_catches_playback_errors(monkeypatch):
    runner, _ = _runner()
    one = Rule(keywords="one", name="anim_one")
    runner._next = iter([one, None]).__next__
    runner._play = lambda _rule: None
    runner._loop()
    assert runner._current is None

    runner, _ = _runner()
    runner._next = iter([one, None]).__next__

    def fail(_rule):
        raise RuntimeError("play failed")

    runner._play = fail
    runner._loop()
    assert runner._last_error == "сбой при отправке"


def test_legacy_animation_facade_still_exports_core_api():
    assert anims.Runner is Runner
    assert anims.Rule is Rule
    assert callable(anims.plan)
