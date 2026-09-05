# Contributing to AbstractAssistant

Thanks for improving AbstractAssistant. This repo is part of the AbstractFramework ecosystem and
focuses on a macOS-first gateway-native tray app plus CLI.

Quick links:
- Docs hub: [docs/README.md](docs/README.md)
- Architecture: [docs/architecture.md](docs/architecture.md)
- API & CLI: [docs/api.md](docs/api.md)
- Security reports: [SECURITY.md](SECURITY.md)

## Ways to contribute

- Bug reports and triage
- Documentation improvements (clarity, accuracy, examples)
- Fixes and small features
- Test coverage for durability/tool-boundary behavior
- UI/UX improvements for the tray palette

## Development setup

Prerequisites:
- Python 3.10+
- Git
- macOS recommended for tray/UI testing (CLI and backend work cross-platform, but the UI is macOS-first)

Setup:

```bash
git clone https://github.com/lpalbou/abstractassistant.git
cd abstractassistant
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the test suite (recommended invocation, headless):

```bash
QT_QPA_PLATFORM=offscreen PYSTRAY_BACKEND=dummy python -m pytest -q
```

Note: the default pytest configuration runs `tests/basic/` (see `pyproject.toml`). The suite
builds the real Qt widgets offscreen, so it needs no display and no gateway.

Where things live:

- `abstractassistant/app.py` — the palette window (wiring only)
- `abstractassistant/controller.py` — preferences, caches, run scope, run commands
- `abstractassistant/ui/` — settings pages, approval sheet, activity card, voice strip, shared stylesheet
- `abstractassistant/core/` — voice conversation loop, tool presentation and risk, voice manager
- `abstractassistant/gateway/` — HTTP/SSE client, run input, ledger adapter

Design tokens are in `abstractassistant/theme.py` and the shared stylesheet in
`abstractassistant/ui/styles.py`; new UI should use them rather than literal colors.

## Running locally

CLI (one turn):

```bash
assistant run --prompt "Hello"
```

Tray UI (macOS):

```bash
assistant
```

Packaged macOS app validation:

```bash
build-macos-app
open /Applications/AbstractAssistant.app
```

When you change tray or palette behavior, validate the rebuilt `/Applications/AbstractAssistant.app`
too. Quit any older menu-bar process first so you are not comparing new source against an older
installed bundle.

## Code style and checks

Formatting and static checks (optional but encouraged):

```bash
black abstractassistant tests
isort abstractassistant tests
mypy abstractassistant
```

## Making a PR

- Keep PRs focused and small when possible.
- Add/adjust tests when behavior changes (especially around durability, tool approvals, and session storage).
- Update docs when you change CLI flags, defaults, or UX behavior.
- For larger changes, open an issue/discussion first to align on direction.

## Reporting bugs

Please include:
- platform + Python version
- AbstractAssistant version (from `python -m pip show abstractassistant`)
- reproduction steps and expected vs actual behavior
- logs (tray launcher log under `~/Library/Logs/Assistant/` for the packaged app, or paste terminal output for the CLI)

## Security issues

Do not open public issues for security vulnerabilities. See [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions are licensed under the MIT License (see `LICENSE`).
