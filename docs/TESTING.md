# Testing and verification

This project uses a small, deterministic pytest suite for message processing,
configuration, translation error handling, log privacy, animation matching, and
Qt layout behavior. Tests must not send real chat text to online services or rely
on the user's saved configuration.

## Run locally

Use Python 3.12. Install the application and test dependencies from the repository
root, then run:

```powershell
python -m pip install -r source/requirements.txt
python -m pip install pytest pytest-cov ruff bandit pip-audit
ruff check source
ruff format --check source
python -m pytest source/tests -v
bandit -lll -r source/app
pip-audit -r source/requirements.txt
```

The local DLX adapter has an isolated Node.js 18 test suite. It binds only to a
loopback ephemeral port and stubs the translation provider, so it does not call
DeepL or expose a public listener:

```powershell
npm ci --prefix source/tools/deeplx-local
npm test --prefix source/tools/deeplx-local
npm audit --prefix source/tools/deeplx-local --audit-level=high
```

To see the number and names of collected Python test cases without running them:

```powershell
python -m pytest source/tests --collect-only -q
```

## GitHub Actions jobs

The `CI` workflow separates the checks so the Actions summary shows where a
failure occurred:

| Job | Platform | What it checks |
|---|---|---|
| `quality-gates` | Ubuntu | Ruff, Markdown and local documentation links, Bandit, pip-audit, and npm audit |
| `linux-tests` | Ubuntu | Unit and integration tests with coverage output |
| `windows-tests` | Windows | Full pytest suite with required Qt runtime, Win32 adapters, and an EXE smoke build |
| `local-dlx-tests` | Ubuntu / Node.js 18 | DLX HTTP routes, Bearer authentication, request validation, and safe error responses |
| `documentation-links` | Ubuntu | External Markdown link check |
| `secret-scan` | Ubuntu | Gitleaks scan of checked-out files and Git history |

Pytest prints each test case in verbose mode in the job log. The Actions page
lists jobs and steps, not one workflow run per test case. Open a job and expand
its **Run tests** step to see individual test names and results.

## Platform notes

- `test_animchoice_ui.py` requires Qt's offscreen runtime. On Linux systems
  missing `libGL.so.1`, the module is skipped locally. The Windows CI job sets
  `RPCHAT_REQUIRE_QT_TESTS=1`, so an unavailable Qt runtime fails that job rather
  than silently skipping the UI regression.
- `test_gamesend_logs.py` and `test_overlay_logs.py` exercise Win32 input and
  overlay integration; they are marked Windows-only and run on `windows-latest`.
- Network errors and service responses are tested with deterministic stubs or
  constructed response objects; the unit suite does not contact translation
  services.

## Coverage targets

The long-term goal is **at least 80% line coverage per critical module**, not 80%
for the entire application. A whole-project percentage is misleading here: Qt UI,
Win32 integration and release-only paths need different runners and are not all
exercised by Linux unit tests.

The Linux CI job emits a coverage report and enforces the per-module floors in
[`source/tools/coverage_targets.json`](../source/tools/coverage_targets.json)
with [`source/tools/check_coverage.py`](../source/tools/check_coverage.py). The
floors are an initial ratchet based on the current test baseline; modules below
the 80% goal are reported as follow-up gaps rather than silently presented as
meeting the goal. Raise a floor only after adding tests, and do not lower it to
hide a regression.

| Critical module | CI floor | Long-term goal | Main responsibility |
|---|---:|---:|---|
| `config.py` | 80% | 80% | Configuration defaults, persistence, and validation |
| `morph.py` | 80% | 80% | Normalization and morphology used in matching |
| `usage_report.py` | 85% | 80% | Opt-in, privacy-preserving performance aggregates |
| `modules.py` | 90% | 80% | Module registry and lifecycle decisions |
| `translator.py` | 55% | 80% | Translation, caching, deadlines, and fallback behavior |
| `anims_rules.py` | 55% | 80% | Animation rule parsing, validation, and matching |
| `anims_runtime.py` | 30% | 80% | Animation queue and playback state machine |
| `engine.py` | 14% | 80% | Message processing and translation orchestration |
| `dlx.py` | 13% | 80% | DLX client and local-service integration |

These floors are deliberately honest starting points, not claims that every
critical module is already adequately tested. Expand coverage by testing
behavioral branches, boundary cases, and failures; do not write tests solely to
execute lines. Windows-only tests continue to be validated on the Windows CI
runner and must not be counted as Linux successes.

## Coverage map

| Area | Regression tests |
|---|---|
| Message parsing and animation matching | `test_anims.py`, `test_anims_runner.py`, `test_anims_stop.py`, `test_slang.py`, `test_translit.py` |
| Settings, language packs, and modules | `test_config.py`, `test_langs.py`, `test_modules.py` |
| Translation fallback, timeouts, and privacy-safe errors | `test_translator.py`, `test_dlx_response.py`, `test_dlx_security.py` |
| Bounded logs and chat-text redaction | `test_logging.py`, `test_gamesend_logs.py`, `test_overlay_logs.py` |
| Settings toggle keyboard/focus/accessibility behavior and animation chooser layout | `test_settings_ui.py`, `test_animchoice_ui.py` |
| Morphological matching | `test_morph.py` |
| DLX Node.js protocol and HTTP error handling | `source/tools/deeplx-local/test/server.test.js` |

## Manual UI smoke check

For a release candidate, check the real Windows app as well as automated tests:

1. Open Settings at 100% and 150% Windows display scaling; resize the window and
   verify the navigation and scrollable page remain usable.
2. Switch the interface between Russian and English; verify long labels are not
   clipped and controls remain reachable by keyboard.
3. Open and cancel the overlay with the configured hotkey and **Esc**; confirm
   the game chat and overlay return to the expected state.
4. Try a translation with the network unavailable and a DLX test with an
   unavailable endpoint; read the visible status and follow
   [`ERRORS_AND_FIXES.md`](ERRORS_AND_FIXES.md).
5. Open an animation chooser with long variant names and descriptions; verify
   scrolling, focus, **Enter**, and **Esc**.

Record platform-specific skips and any manual checks in the pull request. Do not
report a CI run as passing while it is queued or in progress.
