"""Unit tests for the DLX release installer without external network access."""

import io
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import dlx  # noqa: E402


def make_pe():
    data = bytearray(512 * 1024 + 256)
    data[:2] = b"MZ"
    offset = 0x80
    data[0x3C:0x40] = offset.to_bytes(4, "little")
    data[offset : offset + 4] = b"PE\x00\x00"
    return bytes(data)


class Download:
    def __init__(self, chunks):
        self.chunks = iter(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size):
        return next(self.chunks, b"")


def test_install_downloads_selected_release_and_reports_progress(tmp_path, monkeypatch):
    svc = dlx.DlxService(directory=tmp_path)
    binary = make_pe()
    monkeypatch.setattr(
        dlx,
        "_http_get_json",
        lambda _url: {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": "windows-amd64.exe",
                    "browser_download_url": "https://example.test/dlx.exe",
                }
            ],
        },
    )
    requests = []
    monkeypatch.setattr(
        dlx.urllib.request,
        "urlopen",
        lambda request, timeout: (
            requests.append((request, timeout)) or Download([binary[:65536], binary[65536:]])
        ),
    )
    monkeypatch.setattr(svc, "_fetch_license", lambda: None)
    progress = []

    assert svc.install(progress.append) is True
    assert svc.binary.read_bytes() == binary
    assert svc.version() == "v1.2.3"
    assert progress == ["скачиваю v1.2.3…"]
    assert requests[0][0].full_url == "https://example.test/dlx.exe"
    assert requests[0][1] == 60
    assert not list(tmp_path.glob("*.tmp"))


def test_install_falls_back_to_latest_release_when_github_api_is_rate_limited(
    tmp_path, monkeypatch
):
    svc = dlx.DlxService(directory=tmp_path)
    binary = make_pe()
    api_error = urllib.error.HTTPError(
        dlx.RELEASE_API,
        403,
        "Forbidden",
        {"X-RateLimit-Remaining": "0"},
        io.BytesIO(b'{"message":"API rate limit exceeded"}'),
    )
    monkeypatch.setattr(dlx, "_http_get_json", lambda *_args: (_ for _ in ()).throw(api_error))
    monkeypatch.setattr(dlx, "_latest_release_tag", lambda: "v1.3.1")
    requests = []
    monkeypatch.setattr(
        dlx.urllib.request,
        "urlopen",
        lambda request, timeout: requests.append((request, timeout)) or Download([binary]),
    )
    monkeypatch.setattr(svc, "_fetch_license", lambda: None)
    progress = []

    assert svc.install(progress.append) is True
    assert svc.binary.read_bytes() == binary
    assert svc.version() == "v1.3.1"
    assert requests[0][0].full_url == dlx.LATEST_WINDOWS_BINARY_URL
    assert requests[0][1] == 60
    assert progress == ["скачиваю v1.3.1…"]


def test_install_does_not_fallback_for_unrelated_github_forbidden_response(tmp_path, monkeypatch):
    svc = dlx.DlxService(directory=tmp_path)
    error = urllib.error.HTTPError(
        dlx.RELEASE_API, 403, "Forbidden", {}, io.BytesIO(b'{"message":"access denied"}')
    )
    monkeypatch.setattr(dlx, "_http_get_json", lambda *_args: (_ for _ in ()).throw(error))
    monkeypatch.setattr(
        dlx, "_latest_release_tag", lambda: pytest.fail("unexpected release-page fallback")
    )
    assert svc.install() is False
    assert svc.status()["state"] == "error"
    assert "нет доступа к GitHub" in svc.status()["reason"]


def test_install_reports_github_failure_and_releases_lock(tmp_path, monkeypatch):
    svc = dlx.DlxService(directory=tmp_path)
    monkeypatch.setattr(
        dlx,
        "_http_get_json",
        lambda _url: (_ for _ in ()).throw(OSError("offline")),
    )
    assert svc.install() is False
    assert svc.status()["state"] == "error"
    assert "нет доступа к GitHub" in svc.status()["reason"]
    assert svc._install_lock.acquire(blocking=False)
    svc._install_lock.release()


def test_install_rejects_release_without_executable_asset(tmp_path, monkeypatch):
    svc = dlx.DlxService(directory=tmp_path)
    monkeypatch.setattr(dlx, "_http_get_json", lambda _url: {"tag_name": "v2", "assets": []})
    assert svc.install() is False
    assert svc.status()["state"] == "error"
    assert svc.status()["reason"] == "в релизе нет файла для Windows"


def test_download_failure_removes_partial_file_and_sets_error(tmp_path, monkeypatch):
    svc = dlx.DlxService(directory=tmp_path)
    monkeypatch.setattr(
        dlx,
        "_http_get_json",
        lambda _url: {
            "tag_name": "v1",
            "assets": [
                {"name": "windows.exe", "browser_download_url": "https://example.test/dlx.exe"}
            ],
        },
    )

    class BrokenDownload:
        def __enter__(self):
            raise OSError("connection dropped")

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(dlx.urllib.request, "urlopen", lambda *_args, **_kwargs: BrokenDownload())
    assert svc.install() is False
    assert svc.status()["state"] == "error"
    assert "скачивание не удалось" in svc.status()["reason"]
    assert not list(tmp_path.glob("*.tmp"))
