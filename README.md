# 🎮 Chat&AutoAnimations RP Overhaul

[![Windows 10 / 11](https://img.shields.io/badge/Windows-10%20%2F%2011-0078D4?logo=windows&logoColor=white)](https://github.com/Ven4esters/RP-Chat-Overlay/releases)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/release/python-312/)
![Языков: 13](https://img.shields.io/badge/languages-13-2e7d32)
![Сокращений: 300×6](https://img.shields.io/badge/abbreviations-300×6-8e6bd8)
![EXE ~47.7 MiB](https://img.shields.io/badge/exe-~47.7%20MiB-66d18b)
[![VirusTotal: report](https://img.shields.io/badge/VirusTotal-отчёт-394eff)](https://www.virustotal.com/gui/file/9a6c8da2e9472ee89ee3a6f6311844ed0a983d00327857a1749dc5782cc34749?nocache=1)
![Лицензия: MIT](https://img.shields.io/badge/license-MIT-green)

> Chat overlay with DeepL/Google translation and automatic animation application for roleplay games (GTA 5).

<a id="contents"></a>
<img src="source/images/forum/hdr_contents_en.png" width="720" alt="Contents">

## Contents

- [About the project](#about-the-project)
- [Features](#features)
- [Tech stack](#tech-stack)
- [Requirements](#requirements)
- [Installation](#installation)
- [Settings](#settings)
- [Translation modes and special symbols](#translation-modes-and-special-symbols)
- [DeepLX in Russia](#deeplx-in-russia)
- [License](#license)
- [Contacts](#contacts)

<a id="about-the-project"></a>
<img src="source/images/forum/hdr_about_en.png" width="720" alt="About the project">

The project is an overlay for roleplay chat in GTA 5. It translates incoming
and outgoing messages through DeepL (local service) or Google Translate, and
automatically applies character animations based on keyword matching.
The interface language can be switched between Russian and English without
restarting.

<a id="features"></a>
<img src="source/images/forum/hdr_features.png" width="720" alt="Features">

- Translate chat messages through DeepL or Google Translate
- Automatic animation triggers based on keyword matching
- Built-in glossaries and slang expansion for several languages
- DLX local service management (install, start, stop, proxy)
- Russian and English interface

<a id="tech-stack"></a>
<img src="source/images/forum/hdr_stack_en.png" width="720" alt="Tech stack">

Python 3.12 · PySide6 · deep-translator

<a id="requirements"></a>
<img src="source/images/forum/hdr_requirements_en.png" width="720" alt="Requirements">

- Windows 10 / 11
- GTA 5
- Python ≥ 3.12 (to run from sources)
- Internet connection for translation services

<a id="installation"></a>
<img src="source/images/forum/hdr_installation_en.png" width="720" alt="Installation">

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

Run `source/start.bat` — it finds or installs Python 3.12, creates a virtual
environment, installs dependencies and launches the app.

<a id="settings"></a>
<img src="source/images/forum/hdr_configuration_en.png" width="720" alt="Settings">

## Module system

The program is built from independent modules. Any module can be disabled in
settings — a disabled module does not break the rest, the program keeps
working in a reduced mode. If a module that another depends on is disabled,
the dependent is also reported as disabled.

### Modules (in settings window order)

| Module | Config key | Default | Purpose |
|---|---|---|---|
| Online translation | `translator_enabled` | On | The chain of Google, MyMemory, Lingva and LibreTranslate. Without it only the built-in glossaries work. |
| Glossary | `glossary_enabled` | On | Ready-made phrases with a Russian reading and meanings. Without it phrases are translated by the services, with no reading hint. |
| Slang and abbreviations | `slang` | On | `brb`, `afk`, `gg` and their Russian counterparts are expanded into full phrases before translation. |
| Auto-translation | `auto_mode` | Off | Every N-th message is translated automatically. Requires online translation. Works only in partial mode. |
| Sending into the game | `game_send` | On | The overlay opens the game chat, pastes the text and presses Enter. When off, the text is only copied to the clipboard. |
| DeepL alongside (DLX) | `dlx_enabled` | Off | A local DeepL service used as the first translator. Needs consent and about 15 MB on disk. |
| Animations | `anims_enabled` | Off | A keyword in your message starts `/anim` in the game, and `/sa` follows after the configured delay. Requires sending into the game. |
| Global hotkey | `hotkey_enabled` | On | Opens the overlay from inside the game with one key. Without it — double-click the tray icon. |

### Configuration variables

Settings are stored in `data/config.json` next to the executable. Do not put
real keys into the repository — they belong in the local data folder only.

#### Language and direction

| Variable | Required | Default | Description |
|---|---|---|---|
| `target_lang` | no | `it` | Translation target language |
| `send_mode` | no | `reading` | `reading` = Russian reading, `native` = foreign text |
| `mode` | no | `partial` | Translation mode: `full` | `partial` | `to_ru` |
| `direction` | no | `out` | Legacy duplicate of mode (`out` = Russian → language, `in` = language → Russian) |

#### Interface

| Variable | Required | Default | Description |
|---|---|---|---|
| `ui_lang` | no | `ru` | Interface language (`ru` / `en`) |
| `ui_lang_chosen` | no | `false` | Player already picked the language |
| `show_settings_on_start` | no | `true` | Show settings on start |
| `setup_done` | no | `false` | First run completed |
| `ui_scale` | no | `1.0` | Interface scale |
| `always_on_top` | no | `true` | Overlay above the game |

#### Modules

| Variable | Required | Default | Description |
|---|---|---|---|
| `translator_enabled` | no | `true` | Online translation |
| `glossary_enabled` | no | `true` | Glossary |
| `hotkey_enabled` | no | `true` | Global hotkey |
| `dlx_enabled` | no | `false` | DeepL alongside (DLX) |
| `dlx_asked` | no | `false` | Consent already shown |
| `dlx_port` | no | `0` | Service port, 0 means auto |
| `dlx_autostart` | no | `true` | Start with the app |
| `dlx_auto_update` | no | `true` | Check for updates |
| `dlx_proxy` | no | `` | HTTP proxy for DeepL |
| `dlx_use_system_proxy` | no | `true` | Use the Windows proxy |
| `dlx_url` | no | `` | Own service address instead of dlx.exe |
| `dlx_url_token` | no | `` | Token of that service |
| `dlx_pro_token` | no | `` | DeepL Pro OAuth token |
| `slang` | no | `true` | Slang and abbreviations |
| `slang_lang` | no | `` | Abbreviation table language |

#### Text and markers

| Variable | Required | Default | Description |
|---|---|---|---|
| `marker_open` | no | `+` | "translate this" marker |
| `marker_close` | no | `+` | Fragment close marker |
| `max_chars` | no | `256` | Message length limit |
| `debounce_ms` | no | `450` | Typing pause before translating |
| `filler_always` | no | `true` | Fillers in every message |

#### Auto-translation

| Variable | Required | Default | Description |
|---|---|---|---|
| `auto_mode` | no | `false` | Auto-translate on |
| `auto_every` | no | `4` | Every N-th message |
| `auto_position` | no | `last` | `last` | `first` | `random` | number 1..N |
| `auto_fragments` | no | `1` | Fragments per message |
| `auto_min_words` | no | `1` | Fragment length min |
| `auto_max_words` | no | `3` | Fragment length max |
| `auto_prefer_glossary` | no | `true` | Prefer glossary phrases |

#### Sending into the game

| Variable | Required | Default | Description |
|---|---|---|---|
| `game_send` | no | `true` | Send into the game |
| `game_press_enter` | no | `false` | Press Enter after pasting |
| `game_submit` | no | `true` | Submit the message |
| `game_chat_key` | no | `t` | In-game chat key |
| `game_open_chat_first` | no | `true` | Open the game chat first |
| `game_open_delay_ms` | no | `300` | Pause after opening chat |
| `game_paste_delay_ms` | no | `150` | Pause before pasting |
| `game_focus_delay_ms` | no | `150` | Pause before refocusing |
| `game_input_mode` | no | `paste` | `paste` = Ctrl+V, `type` = typed input |
| `game_window_class` | no | `grcWindow` | Game window class |
| `game_extra_exes` | no | `[]` | Extra game processes |

#### Animations

| Variable | Required | Default | Description |
|---|---|---|---|
| `slang_order` | no | `[]` | User's abbreviation order |
| `anims_enabled` | no | `false` | Animation module |
| `anim_rules` | no | `[]` | Rules: keyword → `/anim` |
| `anim_stop_key` | no | `f` | Stop key |
| `anim_stop_by_sa` | no | `true` | Stop with `/sa` command |
| `anim_stop_by_key` | no | `false` | Stop with the key |
| `anim_skip_negation` | no | `true` | Skip negation |
| `anim_extra_ms` | no | `50` | Tail after animation |
| `anim_in_vehicle` | no | `false` | "In a vehicle" mode |

<a id="translation-modes-and-special-symbols"></a>
<img src="source/images/forum/hdr_modes_en.png" width="720" alt="Translation modes and special symbols">

The program supports several translation methods and special markers in text:

### Auto-translate

Every N-th message is translated automatically. For commands `/to`, `/lto`,
`/l`, `/wt`, `/s`, `/st` auto-translate applies the same as to regular
messages.

### Forced fragment translation `+...+`

Wrap part of the text in `+` — the fragment will be translated even when
auto-translate is disabled. Example: `+`привет, брат`+` — always goes to chat
in the target language.

### Actions `*...*`

Text in asterisks is perceived as character action and translated in full.
Service commands (`/me`, `/do`, `/to`) and nicknames are not translated.

### Parasite words

These are filler words inserted into **every** message regardless of the
auto-translate counter: `Senti`, `Ma dai`, `Oye`, `那个` and others. Enabled
with a checkbox next to the phrase in the dictionary.

### Dictionary priority over translation

If a phrase exists in the built-in or user dictionary, it is translated
according to the dictionary entry (with the Russian transcription "how to
read aloud") and does not go to external translation services. The dictionary
takes priority over network translation.

<a id="deeplx-in-russia"></a>
<img src="source/images/forum/hdr_deeplx_en.png" width="720" alt="DeepLX in Russia">

Since June 2025, DeepL is blocked for Russian IP addresses. The local DLX
service starts, but DeepL returns error `503` — state
**«Работает, но DeepL не отвечает (503)»**.

Workaround: use an **HTTP proxy** (v2rayN, Clash, SOCKS5) or deploy your own
DLX server abroad ([detailed instructions](docs/DEEPLX-RUSSIA.md)).
If there is no proxy, simply disable DLX — the program falls back to regular
translation services without restrictions.

<a id="license"></a>
<img src="source/images/forum/hdr_license_en.png" width="720" alt="License">

[MIT](LICENSE)

<a id="contacts"></a>
<img src="source/images/forum/hdr_contacts_en.png" width="720" alt="Contacts">

- Author: [Ven4esters](https://github.com/Ven4esters)
- Issues and suggestions: [GitHub Issues](https://github.com/Ven4esters/RP-Chat-Overlay/issues)