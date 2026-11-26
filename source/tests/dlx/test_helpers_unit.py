"""Unit tests for DLX network wrappers and validation helpers."""

import io
import json
import sys
import types
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import dlx  # noqa: E402


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", ""),
        ("  proxy.example:8080  ", "http://proxy.example:8080"),
        ("https://proxy.example:443", "https://proxy.example:443"),
        ("socks5://proxy.example:1080", "socks5://proxy.example:1080"),
        ("socks5h://proxy.example:1080", "socks5h://proxy.example:1080"),
        ("ftp://proxy.example:21", ""),
        ("http://proxy.example", ""),
        ("http://:8080", ""),
    ],
)
def test_normalize_proxy_validates_supported_address_forms(value, expected):
    assert dlx.normalize_proxy(value) == expected


def test_http_post_json_uses_proxy_free_opener_for_local_calls(monkeypatch):
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append((request, timeout))
            return Response(b'{"data":"ciao"}')

    monkeypatch.setattr(dlx, "_LOCAL_OPENER", Opener())
    answer = dlx._http_post_json(
        "http://127.0.0.1:1188/translate", {"text": "hi"}, {"Authorization": "Bearer t"}, 3
    )
    request, timeout = requests[0]
    assert answer == {"data": "ciao"}
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("Authorization") == "Bearer t"
    assert json.loads(request.data) == {"text": "hi"}
    assert timeout == 3


def test_http_post_json_uses_global_urlopen_when_external(monkeypatch):
    requests = []

    def urlopen(request, timeout):
        requests.append((request, timeout))
        return Response(b'{"data":"hello"}')

    monkeypatch.setattr(dlx.urllib.request, "urlopen", urlopen)
    answer = dlx._http_post_json("https://service.test/translate", {}, None, 5, local=False)
    assert answer == {"data": "hello"}
    assert requests[0][0].full_url == "https://service.test/translate"
    assert requests[0][1] == 5


def test_http_get_json_sets_github_headers_and_timeout(monkeypatch):
    requests = []

    def urlopen(request, timeout):
        requests.append((request, timeout))
        return Response(b'{"tag_name":"v1"}')

    monkeypatch.setattr(dlx.urllib.request, "urlopen", urlopen)
    assert dlx._http_get_json("https://api.github.test/release", timeout=2) == {"tag_name": "v1"}
    request, timeout = requests[0]
    assert request.get_method() == "GET"
    assert request.get_header("Accept") == "application/vnd.github+json"
    assert request.get_header("User-agent") == "RP-Chat-Overlay"
    assert timeout == 2


def test_github_rate_limit_detector_distinguishes_other_http_errors():
    exhausted = urllib.error.HTTPError(
        "https://api.github.com",
        403,
        "Forbidden",
        {"X-RateLimit-Remaining": "0"},
        io.BytesIO(b"{}"),
    )
    assert dlx._is_github_rate_limited(exhausted) is True

    message_only = urllib.error.HTTPError(
        "https://api.github.com",
        403,
        "Forbidden",
        {},
        io.BytesIO(b'{"message":"API rate limit exceeded"}'),
    )
    assert dlx._is_github_rate_limited(message_only) is True

    forbidden = urllib.error.HTTPError(
        "https://api.github.com", 403, "Forbidden", {}, io.BytesIO(b'{"message":"denied"}')
    )
    assert dlx._is_github_rate_limited(forbidden) is False
    other_status = urllib.error.HTTPError("https://api.github.com", 429, "rate limit", {}, None)
    assert dlx._is_github_rate_limited(other_status) is False


def test_latest_release_tag_uses_github_web_redirect_not_rest_api(monkeypatch):
    calls = []

    class RedirectResponse(Response):
        def geturl(self):
            return "https://github.com/OwO-Network/DLX/releases/tag/v1.3.1"

    def urlopen(request, timeout):
        calls.append((request, timeout))
        return RedirectResponse(b"")

    monkeypatch.setattr(dlx.urllib.request, "urlopen", urlopen)
    assert dlx._latest_release_tag() == "v1.3.1"
    assert calls[0][0].full_url == "https://github.com/OwO-Network/DLX/releases/latest"
    assert calls[0][1] == 8


def test_check_update_compares_latest_tag_to_installed_version(tmp_path, monkeypatch):
    svc = dlx.DlxService(directory=tmp_path)
    (tmp_path / "version.json").write_text('{"version":"v1"}', encoding="utf-8")
    monkeypatch.setattr(dlx, "_http_get_json", lambda *_args: {"tag_name": "v2"})
    assert svc.check_update() == "v2"
    monkeypatch.setattr(dlx, "_http_get_json", lambda *_args: {"tag_name": "v1"})
    assert svc.check_update() == ""
    monkeypatch.setattr(dlx, "_http_get_json", lambda *_args: (_ for _ in ()).throw(OSError()))
    assert svc.check_update() == ""


def test_version_and_status_report_safe_defaults_and_current_state(tmp_path):
    svc = dlx.DlxService(directory=tmp_path)
    assert svc.version() == ""
    assert svc.status() == {
        "state": "off",
        "port": 0,
        "version": "",
        "reason": "",
        "note": "",
        "installed": False,
        "running": False,
    }

    (tmp_path / "version.json").write_text('{"version":"v3"}', encoding="utf-8")
    svc._state = "ready"
    assert svc.version() == "v3"
    assert svc.status()["state"] == "ready"


def test_mask_url_redacts_user_info_and_sensitive_query_values():
    masked = dlx._mask_url(
        "https://user:secret@[2001:db8::1]:8443/path?access_token=abc&region=eu#fragment"
    )
    assert masked == ("https://***:***@[2001:db8::1]:8443/path?access_token=%2A%2A%2A&region=eu")
    assert dlx._mask_url("") == ""
    assert dlx._mask_url("https://proxy.test:not-a-port") == "***"


def test_latest_release_tag_handles_bad_redirect_and_network_error(monkeypatch):
    class BadRedirect(Response):
        @staticmethod
        def geturl():
            return "https://github.com/OwO-Network/DLX/releases"

    monkeypatch.setattr(
        dlx.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: BadRedirect(b""),
    )
    assert dlx._latest_release_tag() == ""
    monkeypatch.setattr(
        dlx.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")),
    )
    assert dlx._latest_release_tag() == ""


def test_free_port_skips_busy_candidates_then_returns_available_port(monkeypatch):
    outcomes = iter((False, True))

    class ProbeSocket:
        def __init__(self, *_args):
            self.available = next(outcomes)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def setsockopt(self, *_args):
            pass

        def bind(self, _address):
            if not self.available:
                raise OSError("already bound")

    monkeypatch.setattr(dlx.socket, "socket", ProbeSocket)
    assert dlx.free_port(12000, 12001) == 12001


def test_free_port_raises_when_every_candidate_is_busy(monkeypatch):
    class BusySocket:
        def __init__(self, *_args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def setsockopt(self, *_args):
            pass

        def bind(self, _address):
            raise OSError("already bound")

    monkeypatch.setattr(dlx.socket, "socket", BusySocket)
    with pytest.raises(dlx.DlxError, match="нет свободного порта"):
        dlx.free_port(12000, 12001)


def test_system_proxy_reads_and_normalizes_windows_settings(monkeypatch):
    class RegistryKey:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    registry = types.ModuleType("winreg")
    registry.HKEY_CURRENT_USER = object()
    registry.OpenKey = lambda *_args: RegistryKey()
    values = {"ProxyEnable": 1, "ProxyServer": "http=proxy.test:8080;https=other.test:443"}
    registry.QueryValueEx = lambda _key, name: (values[name], 1)
    monkeypatch.setitem(sys.modules, "winreg", registry)
    monkeypatch.setattr(dlx.sys, "platform", "win32")

    assert dlx.system_proxy() == "http://proxy.test:8080"
    values["ProxyEnable"] = 0
    assert dlx.system_proxy() == ""


def test_system_proxy_handles_missing_registry(monkeypatch):
    monkeypatch.delitem(sys.modules, "winreg", raising=False)
    monkeypatch.setattr(dlx.sys, "platform", "win32")
    assert dlx.system_proxy() == ""
