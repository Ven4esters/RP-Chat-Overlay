"""Unit tests for child-process startup outcomes without spawning DLX."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import dlx  # noqa: E402


class Process:
    def __init__(self, returncode=None):
        self.returncode = returncode
        self._handle = 123

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def kill(self):
        self.returncode = -9

    def wait(self, timeout):
        assert timeout == 3
        return self.returncode


def make_service(tmp_path):
    return dlx.DlxService(command=["stub-dlx"], directory=tmp_path)


def test_try_start_marks_process_ready_when_probe_succeeds(tmp_path, monkeypatch):
    svc = make_service(tmp_path)
    process = Process()
    calls = []
    monkeypatch.setattr(
        dlx.subprocess, "Popen", lambda *args, **kwargs: calls.append((args, kwargs)) or process
    )
    monkeypatch.setattr(dlx, "_kill_orphans_with_job", lambda _handle: 456)
    monkeypatch.setattr(svc, "probe", lambda: "ready")
    monkeypatch.setattr(svc, "_start_watch", lambda: None)

    assert svc._try_start(1188, "secret-token", "") == (True, "")
    assert svc.status()["state"] == "ready"
    assert svc.port == 1188
    assert svc.token == "secret-token"
    assert svc._job == 456
    assert calls[0][0][0] == ["stub-dlx"]
    assert calls[0][1]["env"]["TOKEN"] == "secret-token"
    assert calls[0][1]["cwd"] == str(tmp_path)


def test_try_start_keeps_running_process_on_upstream_failure(tmp_path, monkeypatch):
    svc = make_service(tmp_path)
    process = Process()
    monkeypatch.setattr(dlx.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(dlx, "_kill_orphans_with_job", lambda _handle: None)
    monkeypatch.setattr(svc, "probe", lambda: "upstream")
    monkeypatch.setattr(svc, "_start_watch", lambda: None)

    ok, reason = svc._try_start(1188, "token", "")
    assert ok is False
    assert "DeepL не отвечает" in reason
    assert svc.status()["state"] == "upstream"
    assert svc._process is process


def test_try_start_reports_child_that_exits_immediately(tmp_path, monkeypatch):
    svc = make_service(tmp_path)
    process = Process(returncode=7)
    monkeypatch.setattr(dlx.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(dlx, "_kill_orphans_with_job", lambda _handle: None)

    ok, reason = svc._try_start(1188, "token", "")
    assert ok is False
    assert reason == "сервис завершился (код 7)"


def test_try_start_maps_exec_format_error_to_reinstall(tmp_path, monkeypatch):
    svc = make_service(tmp_path)
    dropped = []

    class WinError193(OSError):
        winerror = 193

    monkeypatch.setattr(
        dlx.subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(WinError193("bad image")),
    )
    monkeypatch.setattr(svc, "_drop_binary", dropped.append)
    ok, reason = svc._try_start(1188, "token", "")
    assert ok is False
    assert reason == "файл сервиса повреждён"
    assert dropped == ["файл сервиса повреждён — скачаю заново"]


def test_try_start_returns_safe_error_for_other_spawn_failures(tmp_path, monkeypatch):
    svc = make_service(tmp_path)
    monkeypatch.setattr(
        dlx.subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("permission denied")),
    )
    ok, reason = svc._try_start(1188, "token", "")
    assert ok is False
    assert reason == "не удалось запустить: permission denied"


def test_try_start_sets_windows_no_window_flags_when_running_on_windows(tmp_path, monkeypatch):
    svc = make_service(tmp_path)
    process = Process()
    startup = type("StartupInfo", (), {"dwFlags": 0})()
    monkeypatch.setattr(dlx.sys, "platform", "win32")
    monkeypatch.setattr(dlx.subprocess, "STARTUPINFO", lambda: startup, raising=False)
    monkeypatch.setattr(dlx.subprocess, "STARTF_USESHOWWINDOW", 1, raising=False)
    monkeypatch.setattr(dlx, "_kill_orphans_with_job", lambda _handle: None)
    monkeypatch.setattr(svc, "probe", lambda: "ready")
    monkeypatch.setattr(svc, "_start_watch", lambda: None)
    popen_options = {}
    monkeypatch.setattr(
        dlx.subprocess,
        "Popen",
        lambda *_args, **kwargs: popen_options.update(kwargs) or process,
    )

    assert svc._try_start(1188, "token", "") == (True, "")
    assert startup.dwFlags == 1
    assert popen_options["creationflags"] == 0x08000000 | 0x00000200
    assert popen_options["startupinfo"] is startup
