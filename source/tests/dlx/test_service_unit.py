"""Focused unit tests for DLX service configuration and request behavior."""

import re
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import dlx  # noqa: E402


class Response:
    def __init__(self, payload=b"{}", status=200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class Opener:
    def __init__(self, response=None, error=None):
        self.response = response or Response()
        self.error = error
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        if self.error:
            raise self.error
        return self.response


def service(tmp_path, cfg=None, **kwargs):
    return dlx.DlxService(cfg=cfg, directory=tmp_path, **kwargs)


def test_external_endpoint_normalizes_known_route_suffixes(tmp_path):
    for suffix in ("/api/translate", "/v1/translate", "/v2/translate", "/translate"):
        svc = service(tmp_path, {"dlx_url": f"https://example.test/base{suffix}/"})
        assert svc.external_url() == f"https://example.test/base{suffix}"
        assert svc._external_base() == "https://example.test/base"
        assert svc._url() == "https://example.test/base/translate"


def test_local_endpoint_defaults_to_loopback_and_configured_port(tmp_path):
    svc = service(tmp_path)
    assert svc._url() == f"http://127.0.0.1:{dlx.PORT_RANGE[0]}/translate"
    svc._port = 1234
    assert svc._url("/health") == "http://127.0.0.1:1234/health"


def test_external_service_counts_as_installed_and_alive(tmp_path):
    svc = service(tmp_path, {"dlx_url": "https://example.test"})
    assert svc.installed()
    assert svc._alive()
    assert not svc.enabled()


def test_external_auth_is_trimmed_and_ascii_only(tmp_path):
    svc = service(tmp_path, {"dlx_url": "https://example.test", "dlx_url_token": " abc\né "})
    assert svc._auth() == {"Authorization": "Bearer abc"}


def test_external_auth_omits_blank_token(tmp_path):
    svc = service(tmp_path, {"dlx_url": "https://example.test", "dlx_url_token": " \n"})
    assert svc._auth() == {}


def test_stored_token_is_loaded_and_reused(tmp_path, monkeypatch):
    svc = service(tmp_path)
    svc.dir.mkdir(parents=True, exist_ok=True)
    (svc.dir / "token.txt").write_text("saved-token\n", encoding="utf-8")
    monkeypatch.setattr(dlx.secrets, "token_hex", lambda _size: pytest.fail("unexpected token"))
    assert svc._ensure_token() == "saved-token"
    assert svc._ensure_token() == "saved-token"


def test_missing_token_is_generated_and_persisted(tmp_path, monkeypatch):
    svc = service(tmp_path)
    monkeypatch.setattr(dlx.secrets, "token_hex", lambda size: f"token-{size}")
    assert svc._ensure_token() == "token-16"
    assert (tmp_path / "token.txt").read_text(encoding="utf-8") == "token-16"


def test_command_line_binds_loopback_and_adds_optional_settings(tmp_path):
    svc = service(
        tmp_path,
        {"dlx_proxy": "localhost:8080", "dlx_pro_token": " pro-token "},
    )
    assert svc._command_line(1190, "secret", "socks5://proxy:1080") == [
        str(tmp_path / dlx.BINARY_NAME),
        "-ip",
        "127.0.0.1",
        "-port",
        "1190",
        "-token",
        "secret",
        "-proxy",
        "socks5://proxy:1080",
        "-s",
        "pro-token",
    ]
    assert svc._spawn == {
        "proxy": "http://localhost:8080",
        "pro": "pro-token",
        "used": "socks5://proxy:1080",
    }


def test_custom_command_interpolates_port_and_token(tmp_path):
    svc = service(tmp_path, command=["runner", "--port={port}", "--token={token}"])
    assert svc._command_line(1200, "abc") == ["runner", "--port=1200", "--token=abc"]


def test_needs_restart_tracks_proxy_and_pro_token(tmp_path):
    cfg = {"dlx_proxy": "proxy.test:8080", "dlx_pro_token": "pro"}
    svc = service(tmp_path, cfg)
    assert not svc.needs_restart()
    svc._command_line(1188, "token")
    assert not svc.needs_restart()
    cfg["dlx_pro_token"] = "new-pro"
    assert svc.needs_restart()


def test_needs_restart_tracks_external_url_changes(tmp_path):
    cfg = {"dlx_url": "https://one.test"}
    svc = service(tmp_path, cfg)
    svc._spawn = {"url": "https://one.test"}
    assert not svc.needs_restart()
    cfg["dlx_url"] = "https://two.test"
    assert svc.needs_restart()


def test_resolve_proxy_uses_configured_healthy_proxy(tmp_path, monkeypatch):
    svc = service(tmp_path, {"dlx_proxy": "proxy.test:8080", "dlx_use_system_proxy": False})
    monkeypatch.setattr(dlx, "check_proxy", lambda _url: (True, ""))
    assert svc.resolve_proxy() == "http://proxy.test:8080"
    assert svc._proxy_error == ""


def test_resolve_proxy_tries_protocol_fallback_and_records_failure(tmp_path, monkeypatch):
    svc = service(tmp_path, {"dlx_proxy": "http://proxy.test:8080", "dlx_use_system_proxy": False})
    calls = []

    def check(url):
        calls.append(url)
        return (len(calls) == 2, "unreachable")

    monkeypatch.setattr(dlx, "check_proxy", check)
    assert svc.resolve_proxy() == "socks5://proxy.test:8080"
    assert calls == ["http://proxy.test:8080", "socks5://proxy.test:8080"]

    monkeypatch.setattr(dlx, "check_proxy", lambda _url: (False, "bad proxy"))
    assert svc.resolve_proxy() == ""
    assert svc._proxy_error == "bad proxy"


def test_resolve_proxy_falls_back_to_direct_for_bad_system_proxy(tmp_path, monkeypatch):
    svc = service(tmp_path, {"dlx_use_system_proxy": True})
    monkeypatch.setattr(dlx, "system_proxy", lambda: "http://system.test:8080")
    monkeypatch.setattr(dlx, "check_proxy", lambda _url: (False, "offline"))
    assert svc.resolve_proxy() == ""
    assert svc._proxy_error == ""


def test_probe_requires_liveness_before_translation(tmp_path):
    svc = service(tmp_path)
    assert svc.probe() == "down"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("  translated  ", "translated"),
        ({"data": "  translated  "}, "translated"),
        ({"data": ["translated"]}, "translated"),
        ({"translations": [{"text": "translated"}]}, "translated"),
        ({"translations": ["translated"]}, "translated"),
        ({"data": 1, "translations": []}, ""),
        (None, ""),
    ],
)
def test_answer_text_supports_supported_service_shapes(payload, expected):
    assert dlx._answer_text(payload) == expected


def test_probe_reports_ready_upstream_and_bad_credentials(tmp_path, monkeypatch):
    svc = service(tmp_path, {"dlx_url": "https://example.test"})
    monkeypatch.setattr(dlx, "_LOCAL_OPENER", Opener())
    monkeypatch.setattr(dlx, "_http_post_json", lambda *_args: {"data": "ciao"})
    assert svc.probe() == "ready"
    assert svc.health()

    monkeypatch.setattr(dlx, "_http_post_json", lambda *_args: {})
    assert svc.probe() == "upstream"

    error = urllib.error.HTTPError("url", 401, "unauthorized", {}, None)
    monkeypatch.setattr(dlx, "_http_post_json", lambda *_args: (_ for _ in ()).throw(error))
    assert svc.probe() == "down"
    assert svc._probe_error == "сервис отклонил токен"


def test_probe_distinguishes_upstream_http_errors(tmp_path, monkeypatch):
    svc = service(tmp_path, {"dlx_url": "https://example.test"})
    monkeypatch.setattr(dlx, "_LOCAL_OPENER", Opener())
    error = urllib.error.HTTPError("url", 503, "upstream", {}, None)
    monkeypatch.setattr(dlx, "_http_post_json", lambda *_args: (_ for _ in ()).throw(error))
    assert svc.probe() == "upstream"


def test_translate_sends_payload_and_returns_normalized_text(tmp_path, monkeypatch):
    svc = service(tmp_path, {"dlx_url": "https://example.test", "dlx_url_token": "token"})
    calls = []

    def post(url, payload, headers, timeout):
        calls.append((url, payload, headers, timeout))
        return {"data": "  tradotto  "}

    monkeypatch.setattr(dlx, "_http_post_json", post)
    assert svc.translate("hello", "EN", "IT", 2.5) == "tradotto"
    assert calls == [
        (
            "https://example.test/translate",
            {"text": "hello", "source_lang": "EN", "target_lang": "IT"},
            {"Authorization": "Bearer token"},
            2.5,
        )
    ]


def test_translate_rejects_unavailable_service(tmp_path):
    svc = service(tmp_path)
    with pytest.raises(dlx.DlxError, match="не запущен"):
        svc.translate("hello")


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (429, "DeepL ограничил запросы (429)"),
        (503, "DeepL не отвечает (503)"),
        (413, "текст длиннее 1500 символов"),
        (400, "сервис не принял язык перевода"),
        (418, "HTTP 418"),
    ],
)
def test_translate_maps_http_errors_to_safe_messages(tmp_path, monkeypatch, code, expected):
    svc = service(tmp_path, {"dlx_url": "https://example.test"})
    error = urllib.error.HTTPError("url", code, "failure", {}, None)
    monkeypatch.setattr(dlx, "_http_post_json", lambda *_args: (_ for _ in ()).throw(error))
    with pytest.raises(dlx.DlxError, match=re.escape(expected)):
        svc.translate("hello")


def test_translate_handles_network_invalid_json_and_empty_response(tmp_path, monkeypatch):
    svc = service(tmp_path, {"dlx_url": "https://example.test"})
    monkeypatch.setattr(
        dlx,
        "_http_post_json",
        lambda *_args: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    with pytest.raises(dlx.DlxError, match="нет связи"):
        svc.translate("hello")

    monkeypatch.setattr(
        dlx, "_http_post_json", lambda *_args: (_ for _ in ()).throw(ValueError("bad json"))
    )
    with pytest.raises(dlx.DlxError, match="не JSON"):
        svc.translate("hello")

    monkeypatch.setattr(dlx, "_http_post_json", lambda *_args: {"message": "private"})
    with pytest.raises(dlx.DlxError, match="сервис вернул ошибку"):
        svc.translate("hello")


def test_pick_asset_prefers_windows_x64_and_ignores_invalid_assets():
    assets = [
        None,
        {"name": "source.zip", "browser_download_url": "https://example.test/source.zip"},
        {"name": "windows-arm.exe", "browser_download_url": "https://example.test/arm.exe"},
        {"name": "windows-amd64.exe", "browser_download_url": "https://example.test/x64.exe"},
        {"name": "windows-amd64.exe"},
    ]
    assert dlx._pick_asset(assets) == "https://example.test/x64.exe"
    assert dlx._pick_asset([]) == ""
