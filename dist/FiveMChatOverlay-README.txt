FIVEM CHAT OVERLAY - RELEASE INFORMATION

Product: FiveM Chat Overlay
Version: 1.18.0
Build time (UTC): 2026-11-26T08:17:35+00:00
File: FiveMChatOverlay.exe
Size: 51126578 bytes (48.76 MiB)
MD5: a40fb74101f3b963a24cb30bad75811a
SHA-256: e6be035ad6a515a4d7f54d7fecdd3cecb347ed45c48696f1c2259971450bbecc

PLATFORM AND INSTALLATION
Target: Windows 10/11, 64-bit
The EXE contains its Python runtime and application dependencies. No separate Python installation is required.
Run FiveMChatOverlay.exe.

APPLICATION SUMMARY
Desktop overlay for roleplay chat in GTA V / FiveM. It prepares translated messages and can trigger configured character-animation rules.
Interface languages: Russian and English. Translation services require an internet connection unless a local service is configured.
Default hotkeys: T opens the game chat; F6 opens the overlay. Both can be changed in Settings.
The app does not write chat message text or translations to its routine logs.

PROJECT LINKS
Source repository: https://github.com/Ven4esters/FiveM-Chat-Overlay
Releases: https://github.com/Ven4esters/FiveM-Chat-Overlay/releases
Issues: https://github.com/Ven4esters/FiveM-Chat-Overlay/issues
Changelog: https://github.com/Ven4esters/FiveM-Chat-Overlay/blob/main/CHANGELOG.md
License: MIT

VIRUSTOTAL REPORT AND POSSIBLE ALERT REASONS
Report / hash lookup page:
https://www.virustotal.com/gui/file/e6be035ad6a515a4d7f54d7fecdd3cecb347ed45c48696f1c2259971450bbecc?nocache=1
The build script does not upload the EXE or retrieve a VirusTotal verdict. Open the page to check the current scan date, engine labels, detection count, and behavior results. A hash page alone is not proof that the file was scanned or found clean.

Possible heuristic causes for this build (not confirmed as the cause of any specific detection):
- PyInstaller one-file packaging embeds Python and dependencies in a self-extracting EXE that unpacks files at runtime; generic packer or machine-learning heuristics may flag this pattern.
- The app registers a configurable global hotkey and uses Windows SendInput to enter text in the game. Those legitimate automation behaviors can resemble input monitoring or injection to generic heuristics.
- The EXE is not Authenticode-signed, so it has no publisher reputation from a signing certificate.
- Optional DLX can, after user consent, download and launch a separate translation-service binary; that download-and-launch pattern can contribute to heuristic alerts.

These are plausible characteristics to compare with the actual report, not proof that a detection is a false positive. A detection count alone also does not prove malware. Review exact engine labels and sandbox behavior; ask the detecting vendor to review the file if appropriate. Do not claim the file is clean without checking the report.

RELEASE CHECKLIST
1. Confirm the version, file size, and both checksum sidecars match this EXE.
2. Verify the report's SHA-256 equals the sidecar; upload this exact EXE if no analysis exists.
3. Record the actual scan date, detection count, engine names, report URL, and outcome in release notes.
4. If the EXE changes, rebuild the checksums and repeat the review.
