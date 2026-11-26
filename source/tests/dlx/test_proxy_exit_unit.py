"""Unit tests for the proxy exit lookup response handling."""

import json
import socket
import ssl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import dlx  # noqa: E402


class Tunnel:
    def __init__(self, chunks=()):
        self.chunks = iter(chunks)
        self.sent = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, _size):
        return next(self.chunks, b"")

    def close(self):
        self.closed = True


class TLSContext:
    def __init__(self, tunnel):
        self.tunnel = tunnel
        self.server_name = None

    def wrap_socket(self, sock, server_hostname):
        assert sock is self.tunnel
        self.server_name = server_hostname
        return self.tunnel


def test_proxy_exit_reports_country_and_closes_tunnel(monkeypatch):
    body = json.dumps(
        {"ip": "203.0.113.5", "country": "DE", "city": "Berlin", "org": "Example ISP"}
    ).encode()
    tunnel = Tunnel([b"HTTP/1.1 200 OK\r\n\r\n" + body])
    context = TLSContext(tunnel)
    monkeypatch.setattr(dlx, "_proxy_socket", lambda *_args: tunnel)
    monkeypatch.setattr(dlx.ssl, "create_default_context", lambda: context)

    ok, message = dlx.proxy_exit("http://proxy.test:8080", timeout=2)
    assert ok is True
    assert message == "203.0.113.5 (DE · Berlin, Example ISP)"
    assert context.server_name == "ipinfo.io"
    assert tunnel.sent[0].startswith(b"GET /json HTTP/1.1")
    assert tunnel.closed


def test_proxy_exit_flags_russian_exit_and_missing_ip(monkeypatch):
    tunnel = Tunnel([b"HTTP/1.1 200 OK\r\n\r\n" + b'{"ip":"192.0.2.1","country":"RU"}'])
    monkeypatch.setattr(dlx, "_proxy_socket", lambda *_args: tunnel)
    monkeypatch.setattr(dlx.ssl, "create_default_context", lambda: TLSContext(tunnel))
    ok, message = dlx.proxy_exit("http://proxy.test:8080")
    assert ok is False
    assert "выход из России" in message

    missing = Tunnel([b"HTTP/1.1 200 OK\r\n\r\n" + b'{"country":"DE"}'])
    monkeypatch.setattr(dlx, "_proxy_socket", lambda *_args: missing)
    monkeypatch.setattr(dlx.ssl, "create_default_context", lambda: TLSContext(missing))
    assert dlx.proxy_exit("http://proxy.test:8080") == (False, "сервис проверки не назвал адрес")


def test_proxy_exit_handles_bad_body_tls_and_connection_errors(monkeypatch):
    malformed = Tunnel([b"HTTP/1.1 200 OK\r\n\r\nnot-json"])
    monkeypatch.setattr(dlx, "_proxy_socket", lambda *_args: malformed)
    monkeypatch.setattr(dlx.ssl, "create_default_context", lambda: TLSContext(malformed))
    assert dlx.proxy_exit("http://proxy.test:8080") == (
        False,
        "ответ сервиса проверки не разобрать",
    )

    tunnel = Tunnel()
    context = TLSContext(tunnel)
    monkeypatch.setattr(dlx, "_proxy_socket", lambda *_args: tunnel)
    monkeypatch.setattr(dlx.ssl, "create_default_context", lambda: context)
    monkeypatch.setattr(
        context,
        "wrap_socket",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ssl.SSLError("bad cert")),
    )
    ok, message = dlx.proxy_exit("http://proxy.test:8080")
    assert not ok
    assert "https" in message
    assert tunnel.closed

    monkeypatch.setattr(
        dlx,
        "_proxy_socket",
        lambda *_args: (_ for _ in ()).throw(socket.timeout()),
    )
    assert dlx.proxy_exit("http://proxy.test:8080") == (False, "прокси не ответил при подключении")

    monkeypatch.setattr(
        dlx,
        "_proxy_socket",
        lambda *_args: (_ for _ in ()).throw(OSError("refused")),
    )
    assert dlx.proxy_exit("http://proxy.test:8080") == (
        False,
        "прокси не открыл туннель: refused",
    )


def test_proxy_exit_rejects_missing_or_invalid_proxy():
    assert dlx.proxy_exit("") == (False, "прокси не задан")
    assert dlx.proxy_exit("ftp://proxy.test:21") == (False, "прокси не задан")


def test_loopback_check_connects_and_reports_socket_failures(monkeypatch):
    assert dlx.loopback_ok() == (True, "")

    def fail_socket(*_args, **_kwargs):
        raise OSError("loopback blocked")

    monkeypatch.setattr(dlx.socket, "socket", fail_socket)
    ok, reason = dlx.loopback_ok()
    assert not ok
    assert "loopback blocked" in reason


def test_is_pe_file_checks_size_headers_and_missing_paths(tmp_path):
    small = tmp_path / "small.exe"
    small.write_bytes(b"MZ" + bytes(64))
    assert dlx._is_pe_file(small) is False

    pe = bytearray(512 * 1024 + 256)
    pe[:2] = b"MZ"
    offset = 0x80
    pe[0x3C:0x40] = offset.to_bytes(4, "little")
    pe[offset : offset + 4] = b"PE\x00\x00"
    valid = tmp_path / "valid.exe"
    valid.write_bytes(pe)
    assert dlx._is_pe_file(valid) is True

    pe[offset : offset + 4] = b"NOPE"
    invalid = tmp_path / "invalid.exe"
    invalid.write_bytes(pe)
    assert dlx._is_pe_file(invalid) is False
    assert dlx._is_pe_file(tmp_path / "missing.exe") is False
