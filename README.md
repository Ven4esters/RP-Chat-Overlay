# Chat&AutoAnimations RP Overhaul

> Chat overlay with DeepL/Google translation and automatic animation application for roleplay games (GTA 5).

[![Windows 10 / 11](https://img.shields.io/badge/Windows-10%20%2F%2011-0078D4?logo=windows&logoColor=white)](https://github.com/Ven4esters/RP-Chat-Overlay/releases)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/release/python-312/)
[![Languages: 13](https://img.shields.io/badge/languages-13-2e7d32)]
[![Abbreviations: 300×6](https://img.shields.io/badge/abbreviations-300×6-8e6bd8)]
[![EXE ~47.7 MiB](https://img.shields.io/badge/exe-~47.7%20MiB-66d18b)]
[![VirusTotal](https://img.shields.io/badge/VirusTotal-отчёт-394eff)](https://www.virustotal.com/gui/file/9a6c8da2e9472ee89ee3a6f6311844ed0a983d00327857a1749dc5782cc34749?nocache=1)
[![MIT License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## Содержание
- [About the project](#about-the-project)
- [Features](#features)
- [Tech stack](#tech-stack)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [How to contribute](#how-to-contribute)
- [License](#license)
- [Contacts](#contacts)

## About the project
The project is an overlay for roleplay chat in GTA 5. It translates incoming and outgoing messages through DeepL (local service) or Google Translate, and automatically applies character animations (`*...*`) based on a configurable rule set. The interface language can be switched between Russian and English without restarting.

## Features
- Translate chat messages through DeepL or Google Translate
- Automatic animation triggers from `*...*` text spans
- Built-in glossaries and slang expansion for several languages
- Adjustable overlay transparency, position and hotkeys
- DLX local service management (install, start, stop, proxy)
- Russian and English interface

## Tech stack
Python 3.12 · PySide6 · deep-translator

## Requirements
- Windows (GTA 5)
- Python ≥ 3.12 (to run from sources)
- Internet connection for translation services

## Installation

### Compiled release (recommended)
Download the latest build from [GitHub Releases](https://github.com/Ven4esters/RP-Chat-Overlay/releases):

| File | SHA-256 | MD5 | Size |
|---|---|---|---|
| `RPChatOverlay.exe` | `9a6c8da2e9472ee89ee3a6f6311844ed0a983d00327857a1749dc5782cc34749` | `d854ac6a2c7d860ec59a5dd7acbc1a9e` | 47.7 MiB (49 990 457 bytes) |

Verify the checksum after downloading, then run `RPChatOverlay.exe`.

### From sources
```bash
git clone https://github.com/Ven4esters/RP-Chat-Overlay.git
cd RP-Chat-Overlay
```
Run `source/start.bat` — it finds or installs Python 3.12, creates a virtual environment, installs dependencies and launches the app.

## Quick start
```bash
source/start.bat
```
The overlay appears as a tray icon. Press the configured hotkey to show the chat window. Incoming/outgoing messages are translated automatically; `*...*` spans trigger animations if a matching rule exists.

Open **Settings** → **DeepL** to configure the local translation service, or **Settings** → **Animations** to manage animation rules.

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `ui_lang` | no | `ru` | Interface language (`ru` / `en`) |
| `target_lang` | no | `it` | Translation target language |
| `dlx_url` | no | — | Address of your own DeepL service |
| `dlx_url_token` | no | — | Bearer token for your own DeepL service |

Settings are stored in `data/config.json` next to the executable. Do not put real keys into the repository — they belong in the local data folder only.

## How to contribute
1. Fork the repository
2. Create a branch: `git checkout -b feature/my-change`
3. Make your changes and commit by [Conventional Commits](https://www.conventionalcommits.org/)
4. Open a Pull Request

Before PR: run lint and tests locally.

## License
[MIT](LICENSE)

## Contacts
- Author: [Ven4esters](https://github.com/Ven4esters)
- Issues and suggestions: [GitHub Issues](https://github.com/Ven4esters/RP-Chat-Overlay/issues)