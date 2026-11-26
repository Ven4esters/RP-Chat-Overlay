"""Offline tests for translation adapters, fallback ordering, and cache state."""

import socket
import sys
import threading
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.dlx as dlx_module  # noqa: E402
import app.translator as translator_module  # noqa: E402
from app.translator import TranslateError, Translator  # noqa: E402


def _bare_translator(*, direction="out", target="it", source="ru", cache=None):
    translator = Translator.__new__(Translator)
    translator.cache = dict(cache or {})
    translator.local = None
    translator.net_lock = threading.Lock()
    translator._cache_lock = threading.RLock()
    translator.last = time.monotonic()
    translator.out_target = target
    translator.direction = direction
    translator.target = target if direction == "out" else "ru"
    translator.source = source if direction == "out" else "auto"
    translator._saved_at = time.monotonic()
    translator._dirty = False
    return translator


def test_google_gtx_joins_segments_and_encodes_text(monkeypatch):
    seen = []

    def fake_json(url, data=None):
        seen.append((url, data))
        return [[["Hola"], [" mundo"], []]]

    monkeypatch.setattr(translator_module, "_http_json", fake_json)
    assert translator_module._google_gtx("hello world", "es") == "Hola mundo"
    query = parse_qs(urlparse(seen[0][0]).query)
    assert query["q"] == ["hello world"]
    assert query["tl"] == ["es"]
    assert seen[0][1] is None


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ([["Hola", "en"]], "Hola"),
        (["Hola"], "Hola"),
        ([{"sentences": [{"trans": "Hola"}, {"trans": "!"}]}], "Hola!"),
        ({"translation": "Hola"}, "Hola"),
        ({"trans": "Hola"}, "Hola"),
        ({"unknown": True}, ""),
        ([], ""),
        ("unexpected", ""),
    ],
)
def test_google_clients5_response_shapes(monkeypatch, response, expected):
    monkeypatch.setattr(translator_module, "_http_json", lambda *_args, **_kwargs: response)
    assert translator_module._google_clients5("hello", "es") == expected


def test_lingva_retries_mirrors_quotes_text_and_skips_empty(monkeypatch):
    calls = []
    responses = iter([RuntimeError("offline"), {"translation": " "}, {"translation": " Hola "}])

    def fake_json(url, data=None):
        calls.append(url)
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(translator_module, "_http_json", fake_json)
    assert translator_module._lingva("hello / world", "es", "") == "Hola"
    assert len(calls) == 3
    assert calls[0].endswith("/auto/es/hello%20%2F%20world")
    assert calls[1].startswith(translator_module.LINGVA_HOSTS[1])


def test_lingva_raises_last_mirror_error(monkeypatch):
    calls = []

    def fail(url, **_kwargs):
        calls.append(url)
        raise RuntimeError(f"failed {len(calls)}")

    monkeypatch.setattr(translator_module, "_http_json", fail)
    with pytest.raises(RuntimeError, match="failed 3"):
        translator_module._lingva("hello", "it")
    assert len(calls) == len(translator_module.LINGVA_HOSTS)


def test_libretranslate_rejects_auto_and_posts_form_data(monkeypatch):
    calls = []

    def fake_text(url, data=None):
        calls.append((url, data))
        return '{"translatedText":" Hola "}'

    monkeypatch.setattr(translator_module, "_http_text", fake_text)
    with pytest.raises(RuntimeError, match="автоопределение"):
        translator_module._free_libre("hello", "ru", "auto")
    assert calls == []

    assert translator_module._free_libre("hello world", "es", "en") == "Hola"
    assert calls[0][0].endswith("/translate")
    assert parse_qs(calls[0][1].decode()) == {
        "q": ["hello world"],
        "source": ["en"],
        "target": ["es"],
        "format": ["text"],
    }


def test_libretranslate_skips_empty_mirrors_and_raises_last_failure(monkeypatch):
    calls = []

    def empty_then_success(url, data=None):
        calls.append(url)
        return '{"translatedText":""}' if len(calls) == 1 else '{"translatedText":"ready"}'

    monkeypatch.setattr(translator_module, "_http_text", empty_then_success)
    assert translator_module._free_libre("hello", "es", "en") == "ready"
    assert len(calls) == 2

    calls.clear()

    def fail(url, data=None):
        calls.append(url)
        raise OSError(f"mirror {len(calls)}")

    monkeypatch.setattr(translator_module, "_http_text", fail)
    with pytest.raises(OSError, match="mirror 3"):
        translator_module._free_libre("hello", "es", "en")
    assert len(calls) == len(translator_module.LIBRE_HOSTS)


def test_mymemory_decodes_html_and_rejects_auto_source(monkeypatch):
    calls = []

    def fake_json(url, data=None):
        calls.append(url)
        return {"responseStatus": 200, "responseData": {"translatedText": "Hola &amp; adiós"}}

    monkeypatch.setattr(translator_module, "_http_json", fake_json)
    with pytest.raises(RuntimeError, match="автоопределение"):
        translator_module._mymemory("hello", "es", "auto")
    assert calls == []
    assert translator_module._mymemory("hello", "es", "en") == "Hola & adiós"
    assert parse_qs(urlparse(calls[0]).query)["langpair"] == ["en|es"]


@pytest.mark.parametrize(
    "response",
    [
        {"responseStatus": 429, "responseDetails": "quota reached"},
        {"responseStatus": 200, "responseData": {"translatedText": "MYMEMORY WARNING: bad"}},
    ],
)
def test_mymemory_rejects_service_errors(monkeypatch, response):
    monkeypatch.setattr(translator_module, "_http_json", lambda *_args, **_kwargs: response)
    with pytest.raises(RuntimeError):
        translator_module._mymemory("hello", "es", "en")


def test_http_text_decodes_replacement_characters_and_passes_post_body(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"hello \xff"

    def urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(translator_module.urllib.request, "urlopen", urlopen)
    assert translator_module._http_text("https://example.invalid", b"payload") == "hello \ufffd"
    assert captured["request"].data == b"payload"
    assert captured["timeout"] == translator_module.TIMEOUT


def test_nested_request_deadline_restores_outer_timeout(monkeypatch):
    monkeypatch.setattr(translator_module.time, "monotonic", lambda: 10.0)
    assert translator_module._request_timeout() == translator_module.TIMEOUT
    with translator_module._request_deadline_scope(20.0):
        assert translator_module._request_timeout() == translator_module.TIMEOUT
        with translator_module._request_deadline_scope(10.25):
            assert translator_module._request_timeout() == pytest.approx(0.25)
        assert translator_module._request_timeout() == translator_module.TIMEOUT
    assert translator_module._request_timeout() == translator_module.TIMEOUT


def test_error_classification_and_rate_limit_detection():
    error = HTTPError("url", 403, "private", {}, BytesIO())
    assert translator_module._error_kind(error) == "http 403"
    assert translator_module._error_kind(URLError(socket.timeout())) == "timeout"
    assert translator_module._error_kind(ConnectionError("secret")) == "network error"
    assert translator_module._error_kind(ValueError("secret")) == "ValueError"
    assert translator_module._is_busy(RuntimeError("too many requests"))
    assert translator_module._is_busy(RuntimeError("quota"))
    assert not translator_module._is_busy(RuntimeError("temporary error"))
    assert translator_module._short(["service: bad json"]) == "сервисы не ответили"


def test_cache_cleanup_timestamp_normalizes_naive_and_aware_datetimes():
    naive = datetime(2026, 1, 2, 3, 4, 5)
    aware = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    expected = "2026-01-02T03:04:05+00:00"
    assert translator_module.cache_cleanup_timestamp(naive) == expected
    assert translator_module.cache_cleanup_timestamp(aware) == expected
    previous = datetime(2026, 1, 1, 12)
    current = datetime(2026, 1, 2, 12)
    assert translator_module.cache_cleanup_due("daily", previous.isoformat(), current)


def test_translator_initializes_bad_cache_and_sets_directions(monkeypatch):
    monkeypatch.setattr(translator_module, "read_json", lambda *_args: ["not", "a", "dict"])
    translator = Translator("es")
    assert translator.cache == {}
    assert translator.target == "es"
    assert translator.source == "ru"
    assert translator.set_direction("reverse") == "in"
    assert (translator.target, translator.source) == ("ru", "auto")
    assert translator.set_target("it") == "ru"
    assert translator.out_target == "it"
    assert translator.set_direction("out") == "out"
    assert (translator.target, translator.source) == ("it", "ru")
    assert Translator.is_reverse("  TO_RU ") is True
    assert Translator.is_reverse("es") is False


def test_local_deepl_service_is_first_and_maps_language_codes():
    seen = []

    class Local:
        def translate(self, text, source, target):
            seen.append((text, source, target))
            return "translated"

    translator = _bare_translator()
    assert translator._chain()[0][0] == "Google"
    translator.local = Local()
    assert translator._chain()[0][0] == translator_module.LOCAL_NAME
    assert translator._via_local("hello", "es", "ru") == "translated"
    assert seen == [("hello", "ru", "ES")]


def test_configured_vercel_service_uses_token_for_each_selected_target(tmp_path, monkeypatch):
    calls = []
    local = dlx_module.DlxService(
        {
            "dlx_enabled": True,
            "dlx_url": "https://my-project.vercel.app/api/translate",
            "dlx_url_token": "private-token",
        },
        directory=tmp_path,
    )

    def post(url, payload, headers, timeout):
        calls.append((url, payload, headers, timeout))
        return {"data": f"{payload['target_lang']} translation"}

    monkeypatch.setattr(dlx_module, "_http_post_json", post)
    translator = _bare_translator(target="it")
    translator.local = local

    assert translator.translate("hello") == "IT translation"
    translator.set_target("de")
    assert translator.translate("hello") == "DE translation"

    assert [call[0] for call in calls] == [
        "https://my-project.vercel.app/translate",
        "https://my-project.vercel.app/translate",
    ]
    assert [call[1] for call in calls] == [
        {"text": "hello", "source_lang": "ru", "target_lang": "IT"},
        {"text": "hello", "source_lang": "ru", "target_lang": "DE"},
    ]
    assert all(call[2] == {"Authorization": "Bearer private-token"} for call in calls)


def test_translate_returns_empty_and_uses_directional_cache_key(monkeypatch):
    monkeypatch.setattr(
        translator_module,
        "SERVICES",
        (("Test", lambda *_args: "translated in reverse"),),
    )
    translator = _bare_translator(cache={"out\x1fit\x1fhello": "cached"})
    assert translator.translate("  ") == ""
    assert translator.translate("hello") == "cached"
    translator.direction = "in"
    translator.target = "ru"
    assert translator.translate("hello") == "translated in reverse"


def test_translate_skips_cooled_service_then_stores_first_success(monkeypatch):
    monkeypatch.setattr(translator_module.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(translator_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(translator_module, "_cool", {"Busy": 200.0})
    called = []
    monkeypatch.setattr(
        translator_module,
        "SERVICES",
        (
            ("Busy", lambda *_args: called.append("busy") or "unexpected"),
            ("Fallback", lambda *_args: called.append("fallback") or "result"),
        ),
    )
    translator = _bare_translator()
    assert translator.translate("hello") == "result"
    assert called == ["fallback"]
    assert translator.cache["out\x1fit\x1fhello"] == "result"
    assert translator._dirty is True


def test_translate_cools_http_429_and_raises_safe_summary(monkeypatch):
    monkeypatch.setattr(translator_module.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(translator_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(translator_module, "_cool", {})
    error = HTTPError("url", 429, "private payload", {}, BytesIO())
    monkeypatch.setattr(
        translator_module, "SERVICES", (("Google", lambda *_args: (_ for _ in ()).throw(error)),)
    )
    translator = _bare_translator()
    with pytest.raises(TranslateError) as raised:
        translator.translate("private chat")
    assert "429" in str(raised.value)
    assert "private payload" not in str(raised.value)
    assert translator_module._cool["Google"] == 100.0 + translator_module.COOL


def test_store_bounds_cache_and_flushes_dirty_state(monkeypatch):
    writes = []
    monkeypatch.setattr(translator_module, "CACHE_MAX", 2)
    monkeypatch.setattr(translator_module, "CACHE_SAVE_EVERY", 0)
    monkeypatch.setattr(
        translator_module, "write_json", lambda _path, data, **_kwargs: writes.append(dict(data))
    )
    translator = _bare_translator(cache={"first": "1", "second": "2"})
    translator._store("third", "3")
    assert translator.cache == {"second": "2", "third": "3"}
    assert writes == [{"second": "2", "third": "3"}]
    assert translator._dirty is False


def test_flush_cache_is_noop_when_clean_and_handles_read_only_disk(monkeypatch):
    translator = _bare_translator()
    writes = []
    monkeypatch.setattr(
        translator_module, "write_json", lambda *_args, **_kwargs: writes.append(True)
    )
    translator.flush_cache()
    assert writes == []
    translator._dirty = True

    def fail_write(*_args, **_kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(translator_module, "write_json", fail_write)
    translator.flush_cache()
    assert translator._dirty is True


def test_translate_rechecks_cache_after_acquiring_network_lock(monkeypatch):
    translator = _bare_translator()
    key = "out\x1fit\x1fhello"

    class CacheRaceLock:
        def __enter__(self):
            translator.cache[key] = "written by another thread"

        def __exit__(self, *_args):
            return False

    translator.net_lock = CacheRaceLock()
    monkeypatch.setattr(
        translator_module,
        "SERVICES",
        (("ShouldNotRun", lambda *_args: pytest.fail("network must be skipped")),),
    )
    assert translator.translate("hello") == "written by another thread"


@pytest.mark.parametrize("clock_values", [[100.0, 116.0], [100.0, 100.0, 100.0, 116.0]])
def test_translate_stops_chain_when_deadline_expires(monkeypatch, clock_values):
    translator = _bare_translator()
    translator.last = 100.0
    clock = iter(clock_values)
    monkeypatch.setattr(translator_module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(translator_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        translator_module,
        "SERVICES",
        (("NeverCalled", lambda *_args: pytest.fail("expired chain must not call service")),),
    )
    with pytest.raises(TranslateError):
        translator.translate("hello")


def test_translate_falls_through_empty_service_responses(monkeypatch):
    translator = _bare_translator()
    monkeypatch.setattr(translator_module.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(translator_module.time, "sleep", lambda _seconds: None)
    calls = []
    monkeypatch.setattr(
        translator_module,
        "SERVICES",
        (
            ("Empty", lambda *_args: calls.append("empty") or "  "),
            ("Success", lambda *_args: calls.append("success") or "translated"),
        ),
    )
    assert translator.translate("hello") == "translated"
    assert calls == ["empty", "success"]
