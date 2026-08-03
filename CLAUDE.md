# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bor is a terminal-based email client (think Pine/Alpine for 2025) built on:
- **mu** (maildir-utils) — external CLI tool for Maildir indexing and searching
- **Textual** — Python TUI framework for the interface

Package name on PyPI: `bormail`. Entry point: `bor.app:main`.

## Commands

### Development Setup
```bash
pip install -e ".[dev]"     # Install with dev tools
pip install -e ".[all]"     # Install with all optional features
```

### Running
```bash
bor                         # If installed
python -m bor.app           # Direct execution
```

### Testing
```bash
pytest tests/               # Run all tests
pytest tests/test_mu.py     # Run a single test file
pytest tests/test_app_integration.py::TestClassName::test_method  # Run single test
```
Tests use `pytest-asyncio` with `asyncio_mode = "auto"` — all test files support async.

### Linting
```bash
ruff check bor/             # Check linting
ruff format bor/            # Format code
mypy bor/                   # Type checking
```
Line length: 100 chars. Ruff rules: E, F, I, N, W, UP (E501 ignored).

### Release
1. Update version in `pyproject.toml`
2. Create and push a git tag (`v0.x.x`)
3. Publish a GitHub Release — the build workflow auto-publishes to PyPI

## Architecture

### Component Layers

```
BorApp (Textual app)
  └── TabbedContent
        ├── Tab 0: MessageIndexWidget (always open, cannot close)
        └── Tabs 1–9: MessageViewWidget | ComposeWidget | AttachmentsWidget | SyncWidget
              │
              ▼
         MuInterface  (subprocess wrapper around mu CLI)
              │
              ▼
         mu find/view/move/extract/cfind/index
              │
              ▼
         Maildir (~/.maildir or configured path)
```

### Key Files

| File | Purpose |
|------|---------|
| `bor/app.py` | `BorApp` — main Textual app; tab lifecycle (`add_tab`, `close_tab`, `open_message`, `open_compose`); Alt+0–9 tab switching |
| `bor/mu.py` | `MuInterface` wrapping mu CLI; `EmailMessage` and `EmailAddress` data classes; JSON parsing of mu output |
| `bor/config.py` | TOML config loading from `~/.config/bor.conf`; `get_config()` singleton; typed section classes |
| `bor/tabs/message_index.py` | `MessageIndexWidget` — DataTable-based message list, search, threading, mark/archive/delete |
| `bor/tabs/message.py` | `MessageViewWidget` — single message display with header/body; HTML→text via html2text |
| `bor/tabs/compose.py` | `ComposeWidget` — MIME building and SMTP sending; `AddressInput` with mu cfind autocompletion |
| `bor/tabs/attachments.py` | `AttachmentsWidget` — extract and preview (kitty icat) attachments |
| `bor/tabs/sync.py` | `SyncWidget` — run arbitrary external sync command with live output |

### Tab System

- **Tab 0** is always the Message Index and cannot be closed.
- Tabs 1–9 are dynamic. `BorApp.add_tab()` / `close_tab()` manage them.
- Alt+digit switching requires detecting special Unicode sequences that terminals emit.

### MuInterface

All mail operations go through `MuInterface` in `bor/mu.py` via subprocess:
- `find(query)` → `mu find --format=json ...` → `List[EmailMessage]`
- `view(path)` → reads the raw mail file with Python's `email.parser`
- `move(path, folder)` → `mu move ...`
- `find_contacts(query)` → `mu cfind --format=json ...`
- `extract_attachment(path, idx)` → `mu extract ...`

If you need to study oddities with respect to how mu operates, you can find mu source code soft-linked in agents/mu.

### Configuration Priority
1. `~/.config/bor.conf` (primary, TOML)
2. `~/.mailrc` (email aliases)
3. System keyring (passwords via optional `keyring` package)
4. Built-in defaults

### Styling

Textual CSS is defined inline in widget classes. Key CSS classes: `.unread`, `.flagged`, `.marked`, `.quoted`.

## Workflow Rules

- After implementing a new feature, update CHANGELOG.md with a summary 
- Make sure `documentation/keyboard_shortcuts.md` and `documentation/cofiguration.md` are kept up to date regarding recent changes.
