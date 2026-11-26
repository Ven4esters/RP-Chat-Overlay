"""Unit tests for proxy negotiation; no public hosts are contacted."""

import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import dlx  # noqa: E402


class FakeSocket:
    def __init__(self, replies=()):
        self.replies = list(replies)
        self.sent = []
        self.timeout = None
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def settimeout(self, timeout):
        self.timeout = timeout

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, _size):
        return self.replies.pop(0) if self.replies else b""

    def close(self):
        self.closed = True


def test_check_proxy_accepts_empty_and_http_proxy(monkeypatch):
    assert dlx.check_proxy("") == (True, "")
    sock = FakeSocket([b"HTTP/1.1 200 Connection established\r\n"])
    monkeypatch.setattr(dlx.socket, "create_connection", lambda *_args, **_kwargs: sock)
    assert dlx.check_proxy("http://proxy.test:8080", timeout=2) == (True, "")
    assert sock.timeout == 2
    assert b"CONNECT oneshot-free.www.deepl.com:443" in sock.sent[0]


def test_check_proxy_identifies_wrong_proxy_protocols(monkeypatch):
    socks = FakeSocket([b"\x05\x00"])
    monkeypatch.setattr(dlx.socket, "create_connection", lambda *_args, **_kwargs: socks)
    ok, message = dlx.check_proxy("http://proxy.test:1080")
    assert not ok
    assert "socks5://proxy.test:1080" in message

    http = FakeSocket([b"HTTP/1.1 200 OK"])
    monkeypatch.setattr(dlx.socket, "create_connection", lambda *_args, **_kwargs: http)
    ok, message = dlx.check_proxy("socks5://proxy.test:1080")
    assert not ok
    assert "HTTP-прокси" in message


def test_check_proxy_reports_rejected_protocol_and_network_failures(monkeypatch):
    sock = FakeSocket([b"\x05\xff"])
    monkeypatch.setattr(dlx.socket, "create_connection", lambda *_args, **_kwargs: sock)
    ok, message = dlx.check_proxy("socks5://proxy.test:1080")
    assert not ok
    assert "не отвечает как socks5" in message

    monkeypatch.setattr(
        dlx.socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(socket.timeout()),
    )
    assert "не ответил за 4 с" in dlx.check_proxy("http://proxy.test:8080")[1]
    monkeypatch.setattr(
        dlx.socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("unreachable")),
    )
    assert "недоступен" in dlx.check_proxy("http://proxy.test:8080")[1]


def test_proxy_socket_performs_http_connect_and_rejects_non_200(monkeypatch):
    sock = FakeSocket([b"HTTP/1.1 200 OK\r\n\r\n"])
    monkeypatch.setattr(dlx.socket, "create_connection", lambda *_args, **_kwargs: sock)
    assert dlx._proxy_socket("http://proxy.test:8080", "example.test", 443, 3) is sock
    assert b"CONNECT example.test:443" in sock.sent[0]

    denied = FakeSocket([b"HTTP/1.1 403 Forbidden\r\n\r\n"])
    monkeypatch.setattr(dlx.socket, "create_connection", lambda *_args, **_kwargs: denied)
    with pytest.raises(OSError, match="не открыл туннель"):
        dlx._proxy_socket("http://proxy.test:8080", "example.test", 443, 3)
    assert denied.closed


def test_proxy_socket_negotiates_socks5_with_password_auth(monkeypatch):
    sock = FakeSocket(
        [
            b"\x05\x02",  # username/password selected
            b"\x01\x00",  # credentials accepted
            b"\x05\x00\x00\x01",  # connect accepted, IPv4 bound address
            b"\x7f\x00\x00\x01",  # bound address
            b"\x00\x50",  # bound port
        ]
    )
    monkeypatch.setattr(dlx.socket, "create_connection", lambda *_args, **_kwargs: sock)
    assert dlx._proxy_socket("socks5://alice:p%40ss@proxy.test:1080", "deepl.test", 443, 3) is sock
    assert sock.sent[0] == b"\x05\x02\x00\x02"
    assert sock.sent[1] == b"\x01\x05alice\x04p@ss"
    assert b"\x05\x01\x00\x03\x0adeepl.test" in sock.sent[2]
    assert sock.sent[2].endswith((443).to_bytes(2, "big"))


def test_proxy_socket_supports_no_auth_and_closes_on_bad_greeting(monkeypatch):
    sock = FakeSocket([b"\x05\x00", b"\x05\x00\x00\x01", b"\x00\x00\x00\x01", b"\x00\x50"])
    monkeypatch.setattr(dlx.socket, "create_connection", lambda *_args, **_kwargs: sock)
    assert dlx._proxy_socket("socks5://proxy.test:1080", "127.0.0.1", 80, 3) is sock
    assert sock.sent[0] == b"\x05\x01\x00"
    assert sock.sent[1] == b"\x05\x01\x00\x01\x7f\x00\x00\x01\x00\x50"

    bad = FakeSocket([b"bad"])
    monkeypatch.setattr(dlx.socket, "create_connection", lambda *_args, **_kwargs: bad)
    with pytest.raises(OSError, match="приветствие SOCKS5"):
        dlx._proxy_socket("socks5://proxy.test:1080", "example.test", 443, 3)
    assert bad.closed


def test_proxy_socket_surfaces_authentication_and_connection_refusals(monkeypatch):
    auth_required = FakeSocket([b"\x05\x02"])
    monkeypatch.setattr(dlx.socket, "create_connection", lambda *_args, **_kwargs: auth_required)
    with pytest.raises(OSError, match="требует логин и пароль"):
        dlx._proxy_socket("socks5://proxy.test:1080", "example.test", 443, 3)

    auth_rejected = FakeSocket([b"\x05\x02", b"\x01\x01"])
    monkeypatch.setattr(dlx.socket, "create_connection", lambda *_args, **_kwargs: auth_rejected)
    with pytest.raises(OSError, match="не принял логин"):
        dlx._proxy_socket("socks5://alice:pass@proxy.test:1080", "example.test", 443, 3)
    assert auth_rejected.closed

    denied = FakeSocket([b"\x05\x00", b"\x05\x05\x00\x01"])
    monkeypatch.setattr(dlx.socket, "create_connection", lambda *_args, **_kwargs: denied)
    with pytest.raises(OSError, match="код 05"):
        dlx._proxy_socket("socks5://proxy.test:1080", "example.test", 443, 3)
    assert denied.closed
