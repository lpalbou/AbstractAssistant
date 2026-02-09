# Contributing to AbstractAssistant

Thanks for improving AbstractAssistant. This repo is part of the AbstractFramework ecosystem and focuses on a
macOS-first tray app + CLI that host a local, durable agent.

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
- UI/UX improvements for the tray bubble

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

Run the test suite (recommended invocation):

```bash
python -m pytest -q
```

Note: the default pytest configuration runs `tests/basic/` and `tests/integration/` (see `pyproject.toml`).

## Running locally

CLI (one turn):

```bash
assistant run --prompt "Hello"
```

Tray UI (macOS):

```bash
assistant tray
```

Debug logs:

```bash
assistant --debug tray
```

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
- logs (`assistant --debug tray` for the UI, or paste terminal output for the CLI)

## Security issues

Do not open public issues for security vulnerabilities. See [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions are licensed under the MIT License (see `LICENSE`).
