"""Unit tests for DLX lifecycle state transitions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import dlx  # noqa: E402


def make_service(tmp_path, cfg=None):
    return dlx.DlxService(cfg=cfg, directory=tmp_path)


def test_external_start_rejects_non_http_urls(tmp_path):
    svc = make_service(tmp_path, {"dlx_url": "file:///etc/passwd"})
    assert svc.start() is False
    assert svc.status()["state"] == "error"
    assert "http:// или https://" in svc.status()["reason"]


def test_external_start_marks_service_ready_and_records_note(tmp_path, monkeypatch):
    svc = make_service(tmp_path, {"dlx_url": "https://example.test/api/translate"})
    monkeypatch.setattr(svc, "probe", lambda: "ready")
    assert svc.start() is True
    assert svc.port == 443
    assert svc._spawn == {"url": "https://example.test/api/translate"}
    assert svc.status()["state"] == "ready"
    assert "example.test" in svc.status()["note"]


def test_external_start_preserves_upstream_failure_state(tmp_path, monkeypatch):
    svc = make_service(tmp_path, {"dlx_url": "https://example.test"})
    monkeypatch.setattr(svc, "probe", lambda: "upstream")
    assert svc.start() is False
    assert svc.status()["state"] == "upstream"
    assert "DeepL отказал" in svc.status()["reason"]


def test_external_start_reports_probe_error_without_leaking_secrets(tmp_path, monkeypatch):
    svc = make_service(
        tmp_path,
        {"dlx_url": "https://user:private@example.test/path?token=hidden"},
    )
    svc._probe_error = "bad token"
    monkeypatch.setattr(svc, "probe", lambda: "down")
    assert svc.start() is False
    status = svc.status()
    assert status["state"] == "error"
    assert status["reason"] == "bad token"
    assert "private" not in status["note"]


def test_ensure_obeys_module_switch_and_rechecks_ready_external_service(tmp_path, monkeypatch):
    svc = make_service(tmp_path, {"dlx_enabled": False, "dlx_url": "https://example.test"})
    assert svc.ensure() is False
    svc.cfg = {"dlx_enabled": True, "dlx_url": "https://example.test"}
    svc._state = "ready"
    monkeypatch.setattr(svc, "probe", lambda: "ready")
    assert svc.ensure() is True
    assert svc.status()["state"] == "ready"


def test_ensure_keeps_upstream_state_when_probe_is_not_ready(tmp_path, monkeypatch):
    svc = make_service(tmp_path, {"dlx_enabled": True, "dlx_url": "https://example.test"})
    svc._state = "upstream"
    monkeypatch.setattr(svc, "probe", lambda: "upstream")
    assert svc.ensure() is False
    assert svc.status()["state"] == "upstream"


def test_start_reports_missing_binary(tmp_path):
    svc = make_service(tmp_path, {"dlx_enabled": True})
    assert svc.start() is False
    assert svc.status()["state"] == "missing"
    assert svc.status()["reason"] == "сервис не установлен"


def test_stop_terminates_child_and_clears_runtime_state(tmp_path):
    class Process:
        returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 0

        def wait(self, timeout):
            assert timeout == 3
            return self.returncode

    svc = make_service(tmp_path)
    process = Process()
    svc._process = process
    svc._job = 100
    svc._state = "ready"
    svc.stop()
    assert svc._process is None
    assert svc._job is None
    assert svc._stop_watch.is_set()
    assert svc.status()["state"] == "off"


def test_local_start_skips_foreign_busy_port_and_uses_fallback(tmp_path, monkeypatch):
    svc = make_service(tmp_path, {"dlx_enabled": True, "dlx_port": 1200})
    monkeypatch.setattr(svc, "installed", lambda: True)
    monkeypatch.setattr(svc, "_ensure_token", lambda: "secret")
    monkeypatch.setattr(svc, "resolve_proxy", lambda: "")
    monkeypatch.setattr(dlx, "loopback_ok", lambda: (True, ""))
    free_ports = iter((1201, 1202, 1203))
    monkeypatch.setattr(dlx, "free_port", lambda: next(free_ports))
    monkeypatch.setattr(
        dlx, "_port_owner", lambda port: "OtherApp (pid 42)" if port == 1200 else ""
    )
    attempts = []

    def try_start(port, token, proxy):
        attempts.append((port, token, proxy))
        return (port == 1201, "not ready")

    monkeypatch.setattr(svc, "_try_start", try_start)
    assert svc.start() is True
    assert attempts == [(1201, "secret", "")]
    assert svc.status()["note"] == "порт 1201"


def test_try_start_returns_ready_when_child_and_probe_succeed(tmp_path, monkeypatch):
    svc = make_service(tmp_path)
    svc.command = ["test-service"]

    class Process:
        _handle = 123
        returncode = None

        @staticmethod
        def poll():
            return None

        def terminate(self):
            self.returncode = 0

        def kill(self):
            self.returncode = -9

        def wait(self, timeout):
            assert timeout == 3
            return self.returncode

    monkeypatch.setattr(dlx.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    monkeypatch.setattr(svc, "probe", lambda: "ready")
    monkeypatch.setattr(svc, "_start_watch", lambda: None)

    assert svc._try_start(1188, "secret", "") == (True, "")
    assert svc.status()["state"] == "ready"
    assert svc.port == 1188


def test_try_start_reports_spawn_error_and_broken_windows_binary(tmp_path, monkeypatch):
    svc = make_service(tmp_path)
    monkeypatch.setattr(
        dlx.subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("cannot launch")),
    )
    ok, reason = svc._try_start(1188, "secret", "")
    assert not ok
    assert "не удалось запустить" in reason

    error = OSError("invalid executable")
    error.winerror = 193
    monkeypatch.setattr(
        dlx.subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )
    svc.binary.parent.mkdir(parents=True, exist_ok=True)
    svc.binary.write_bytes(b"bad")
    ok, reason = svc._try_start(1188, "secret", "")
    assert not ok
    assert "повреждён" in reason
    assert not svc.binary.exists()


def test_watch_thread_reports_exit_and_successful_restart(tmp_path, monkeypatch):
    svc = make_service(tmp_path, {"dlx_enabled": True})
    events = []

    class ExitedProcess:
        returncode = 7

        @staticmethod
        def poll():
            return 7

    class RunningProcess:
        returncode = None

        @staticmethod
        def poll():
            return None

    class StopEvent:
        waits = 0

        def clear(self):
            pass

        def wait(self, interval):
            assert interval == 3.0
            self.waits += 1
            return self.waits > 1

    class ImmediateThread:
        def __init__(self, target, **_kwargs):
            self.target = target

        def start(self):
            self.target()

        @staticmethod
        def is_alive():
            return False

    svc._process = ExitedProcess()
    svc._stop_watch = StopEvent()
    svc.on_event = lambda kind, text: events.append((kind, text))
    svc._start_watch = dlx.DlxService._start_watch.__get__(svc)

    def restart():
        svc._process = RunningProcess()
        return True

    monkeypatch.setattr(svc, "start", restart)
    monkeypatch.setattr(dlx.threading, "Thread", ImmediateThread)
    svc._start_watch()

    assert [kind for kind, _text in events] == ["stopped", "restarted"]
    assert svc.status()["state"] == "error"
    assert svc._process is not None
