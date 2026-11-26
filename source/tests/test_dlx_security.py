"""Regression tests for keeping proxy credentials out of logs and UI text."""

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.dlx import _mask_url  # noqa: E402


def test_mask_url_redacts_user_info_and_query_secrets():
    """Passwords and token-like query values never survive URL masking."""
    masked = _mask_url(
        "https://alice:p%40ss@proxy.example:8443/path"
        "?token=secret-token&api_key=secret-key&refresh_token=refresh-secret&region=eu"
        "#secret-fragment"
    )
    parts = urlsplit(masked)

    assert parts.netloc == "***:***@proxy.example:8443"
    assert parse_qs(parts.query) == {
        "token": ["***"],
        "api_key": ["***"],
        "refresh_token": ["***"],
        "region": ["eu"],
    }
    assert parts.fragment == ""
    for secret in (
        "alice",
        "p%40ss",
        "secret-token",
        "secret-key",
        "refresh-secret",
        "secret-fragment",
    ):
        assert secret not in masked


def test_mask_url_keeps_non_sensitive_diagnostic_details():
    """Hosts, ports, paths, and harmless query parameters remain useful."""
    assert _mask_url("https://dlx.example:1188/health?region=eu") == (
        "https://dlx.example:1188/health?region=eu"
    )


def test_mask_url_handles_ipv6_proxy_hosts():
    """Credential masking preserves valid bracketed IPv6 address syntax."""
    assert _mask_url("http://user:pass@[::1]:8080?password=secret") == (
        "http://***:***@[::1]:8080?password=%2A%2A%2A"
    )
