# Repository Guidelines

## Project Structure & Module Organization
Core application code lives in `bor/`. `bor/app.py` is the Textual entry point, `bor/config.py` handles TOML config loading, `bor/mu.py` wraps `mu`, and `bor/tabs/` contains UI views such as `message_index.py`, `message.py`, and `compose.py`. Tests live in `tests/` and mirror user-facing areas such as CLI, config, compose flow, and app integration. Supporting docs are in `documentation/`; contributor notes and working artifacts are in `agents/`.

## Build, Test, and Development Commands
Set up a local dev environment with:

```bash
python -m pip install -e ".[dev]"
```

Run the app locally with `python -m bor.app` or `bor` after installation. Run the full test suite with `pytest`; CI uses the same command on Python 3.10. Build distributable artifacts with `python -m build`, which matches `.github/workflows/build.yml`.

## Coding Style & Naming Conventions
Target Python 3.10+ and follow the existing style: 4-space indentation, type hints on public functions, and short module docstrings where helpful. Ruff is configured with a 100-character line length and checks for pycodestyle, pyflakes, import sorting, pep8-naming, and pyupgrade rules. Use `snake_case` for functions and modules, `PascalCase` for classes, and keep Textual widget names descriptive (`MessageIndexWidget`, `ComposeView`).

## Testing Guidelines
Use `pytest` for all tests and `pytest-asyncio` for async/Textual behavior. Name files `tests/test_*.py` and keep test names behavior-focused, for example `test_cli_version_prints_and_exits`. Prefer mocks over real `mu` access so tests stay deterministic. Add or update tests for every user-visible change, especially around keybindings, config overrides, and message workflows.

## Commit & Pull Request Guidelines
Recent history favors short, imperative commit subjects and merge commits from PR branches, for example `Use deterministic filename for browser temp HTML files to prevent accumulation`. Keep commit titles specific to a single change. PRs should include a concise summary, linked issue if applicable, and screenshots or terminal captures for UI-visible changes. Call out config, dependency, or release-impacting changes explicitly.
