# Contributing

Thanks for helping improve FiveM Chat Overlay. Changes should stay focused, preserve
Russian and English UI behavior, and include a regression test when they change
or fix behavior.

## Before opening a pull request

1. Open an issue first for a large behavior or architecture change.
2. Read [`STYLEGUIDE.md`](STYLEGUIDE.md) and keep the diff focused.
3. Add or update tests for the behavior and the relevant failure cases.
4. Update the README, `CHANGELOG.md`, or the relevant guide when behavior or
   setup changes.
5. Run the checks below and include their results in the pull request.

## Local checks

Use Python 3.12 on Windows for the full suite. From the repository root:

```powershell
python -m pip install -r source/requirements.txt
python -m pip install ruff pytest pytest-cov bandit pip-audit
ruff check source
ruff format --check source
python -m pytest source/tests -v
bandit -lll -r source/app
pip-audit -r source/requirements.txt
npm ci --prefix source/tools/deeplx-local
npm test --prefix source/tools/deeplx-local
npm audit --prefix source/tools/deeplx-local --audit-level=high
npx --yes markdownlint-cli2@0.24.2 --config .markdownlint-cli2.jsonc README.md README.ru.md CONTRIBUTING.md SECURITY.md '.github/**/*.md' 'docs/**/*.md' 'source/tools/deeplx-local/*.md'
python source/tools/check_readme.py
```

The Windows CI job also runs the Qt and Win32-specific tests and builds the
PyInstaller executable. Linux may skip those platform-dependent tests; see
[`docs/TESTING.md`](docs/TESTING.md) for the test matrix.

## Pull request checklist

Describe **what** changed, **why**, how it was tested, risks, and how to disable
or revert it. For UI changes, include before/after screenshots and check keyboard
navigation, long Russian and English text, and display scaling. Do not include
real chat text, tokens, passwords, or personal data in tests, logs, or screenshots.

Pull requests are reviewed for correctness, readability, security, error handling,
compatibility, tests, and documentation. Keep changes small enough to review in
one sitting; split unrelated changes rather than bundling them together.
