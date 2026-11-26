"""Tests for README and checksum generation beside a Windows EXE."""

import hashlib
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "write_release_info.py"
SPEC = importlib.util.spec_from_file_location("write_release_info", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
release_info = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_info)


def test_writes_readme_and_checksums_next_to_exe(tmp_path):
    exe = tmp_path / "FiveMChatOverlay.exe"
    payload = b"MZ\x90\x00sample test executable"
    exe.write_bytes(payload)

    readme, md5_path, sha_path = release_info.write_release_info(exe)

    md5 = hashlib.md5(payload, usedforsecurity=False).hexdigest()
    sha256 = hashlib.sha256(payload).hexdigest()
    assert readme == tmp_path / "FiveMChatOverlay-README.txt"
    assert md5_path == tmp_path / "FiveMChatOverlay.exe.md5"
    assert sha_path == tmp_path / "FiveMChatOverlay.exe.sha256"
    assert md5_path.read_text(encoding="ascii") == f"{md5}  {exe.name}\n"
    assert sha_path.read_text(encoding="ascii") == f"{sha256}  {exe.name}\n"

    contents = readme.read_text(encoding="utf-8")
    assert "Product: FiveM Chat Overlay" in contents
    assert "Size: " in contents
    assert f"MD5: {md5}" in contents
    assert f"SHA-256: {sha256}" in contents
    assert "NOT SCANNED" in contents
    assert f"https://www.virustotal.com/gui/file/{sha256}" in contents
    assert "https://github.com/Ven4esters/FiveM-Chat-Overlay" in contents


def test_refuses_non_windows_file_without_writing_sidecars(tmp_path):
    not_exe = tmp_path / "not-exe.exe"
    not_exe.write_bytes(b"not a PE executable")

    try:
        release_info.write_release_info(not_exe)
    except ValueError as error:
        assert "MZ header" in str(error)
    else:
        raise AssertionError("non-Windows file was accepted")

    assert not list(tmp_path.glob("*.md5"))
    assert not list(tmp_path.glob("*.sha256"))
