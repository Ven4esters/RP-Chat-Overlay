"""Write README-ready release metadata next to a Windows executable.

Usage from the project root or source directory::
    python source/tools/write_release_info.py dist/FiveMChatOverlay.exe

The script calculates sidecar checksums but never contacts VirusTotal or reads a scan verdict. Its README includes the hash-specific report page and explains possible heuristic alerts without asserting a result.
"""

from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_URL = "https://github.com/Ven4esters/FiveM-Chat-Overlay"


def _sha256_and_md5(path: Path) -> tuple[str, str]:
    sha256 = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha256.update(chunk)
            md5.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def write_release_info(exe_path: Path) -> tuple[Path, Path, Path]:
    """Create ``.md5``, ``.sha256`` and README TXT files adjacent to *exe_path*."""
    exe_path = exe_path.resolve()
    if not exe_path.is_file():
        raise FileNotFoundError(f"Executable not found: {exe_path}")
    with exe_path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError(f"Not a Windows executable (missing MZ header): {exe_path}")

    sys.path.insert(0, str(SOURCE_ROOT))
    from app import VERSION  # imported only after locating the source package

    md5, sha256 = _sha256_and_md5(exe_path)
    size_bytes = exe_path.stat().st_size
    size_mib = size_bytes / (1024 * 1024)
    built_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")

    md5_path = exe_path.with_name(exe_path.name + ".md5")
    sha256_path = exe_path.with_name(exe_path.name + ".sha256")
    readme_path = exe_path.with_name(f"{exe_path.stem}-README.txt")
    md5_path.write_text(f"{md5}  {exe_path.name}\n", encoding="ascii")
    sha256_path.write_text(f"{sha256}  {exe_path.name}\n", encoding="ascii")

    readme = f"""FIVEM CHAT OVERLAY - RELEASE INFORMATION

Product: FiveM Chat Overlay
Version: {VERSION}
Build time (UTC): {built_utc}
File: {exe_path.name}
Size: {size_bytes} bytes ({size_mib:.2f} MiB)
MD5: {md5}
SHA-256: {sha256}

PLATFORM AND INSTALLATION
Target: Windows 10/11, 64-bit
The EXE contains its Python runtime and application dependencies. No separate Python installation is required.
Run {exe_path.name}.

APPLICATION SUMMARY
Desktop overlay for roleplay chat in GTA V / FiveM. It prepares translated messages and can trigger configured character-animation rules.
Interface languages: Russian and English. Translation services require an internet connection unless a local service is configured.
Default hotkeys: T opens the game chat; F6 opens the overlay. Both can be changed in Settings.
The app does not write chat message text or translations to its routine logs.

PROJECT LINKS
Source repository: {REPOSITORY_URL}
Releases: {REPOSITORY_URL}/releases
Issues: {REPOSITORY_URL}/issues
Changelog: {REPOSITORY_URL}/blob/main/CHANGELOG.md
License: MIT

VIRUSTOTAL: REPORT AND POSSIBLE HEURISTIC ALERTS
Report / hash lookup page: https://www.virustotal.com/gui/file/{sha256}?nocache=1
The build script does not upload the EXE or retrieve a VirusTotal verdict. Check the current page for the actual scan date, engine names, detection count, and behavior results. A hash page alone is not proof that the file was scanned or found clean.

Why an engine may flag this build (possible causes, not a confirmed explanation for any specific verdict):
- PyInstaller one-file packaging embeds Python and dependencies in a self-extracting executable that unpacks files at runtime; generic packer or machine-learning heuristics can treat this pattern as suspicious.
- The app registers a configurable global hotkey and uses the Windows SendInput API to enter text in the game. These legitimate automation behaviors can resemble input-monitoring or injection patterns to generic heuristics.
- The build is not Authenticode-signed, so it has no publisher reputation established by a signing certificate.
- The optional DLX feature can, after user consent, download and launch a separate translation-service binary; download-and-launch behavior can contribute to heuristic alerts.

These are plausible characteristics to review against the report, not proof of a false positive. A detection count by itself also does not prove malware. Review the exact engine labels and sandbox behavior; submit the file to the detecting vendor for review if appropriate. Do not call the build safe or a false positive until the evidence supports that conclusion.

RELEASE CHECKLIST
1. Confirm the version, file size, and both checksum sidecars match this EXE.
2. Open the hash page and verify its SHA-256 matches the sidecar; upload the exact EXE if no analysis exists.
3. Record the actual scan date, detection count, engine names, report URL, and outcome in the release notes.
4. If the EXE changes, rebuild the checksums and repeat the review.
"""
    readme_path.write_text(readme, encoding="utf-8", newline="\n")
    print(f"README:    {readme_path}")
    print(f"MD5:       {md5_path}")
    print(f"SHA-256:   {sha256_path}")
    print(
        "VirusTotal report/lookup page (verify result manually): "
        f"https://www.virustotal.com/gui/file/{sha256}?nocache=1"
    )
    return readme_path, md5_path, sha256_path


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Usage: python write_release_info.py <FiveMChatOverlay.exe>", file=sys.stderr)
        return 2
    try:
        write_release_info(Path(args[0]))
    except (OSError, ValueError) as error:
        print(f"Could not write release metadata: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
