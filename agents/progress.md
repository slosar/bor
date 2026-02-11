# Bor - Terminal Email Reader Progress

## Overview
Terminal-based email reader using mu for message access and textual for UI.

## Status: ✓ Complete (Initial Implementation)

## Architecture

### Components
1. **Configuration** (`bor/config.py`) - Configuration file handling (~/.config/bor.conf)
2. **Mu Interface** (`bor/mu.py`) - Interface to mu command-line tool
3. **Main App** (`bor/app.py`) - Textual application
4. **Message Index Tab** (`bor/tabs/message_index.py`) - List of messages
5. **Message Tab** (`bor/tabs/message.py`) - Single message view
6. **Attachments Tab** (`bor/tabs/attachments.py`) - Attachments handling
7. **Compose Tab** (`bor/tabs/compose.py`) - Email composition
8. **Sync Tab** (`bor/tabs/sync.py`) - External sync command

### Technology Choices
- **Email backend**: mu (maildir indexer/searcher)
- **UI**: textual library
- **SMTP**: Python's smtplib with email module
- **HTML rendering**: html2text or rich for terminal rendering
- **Config format**: TOML

## Progress

### Phase 1: Foundation ✓
- [x] Analyze mu4e code to understand mu interaction
- [x] Create project structure
- [x] Define configuration schema

### Phase 2: Core Implementation ✓
- [x] Implement mu interface (find, view, move, etc.)
- [x] Implement base Textual app with tab management
- [x] Implement Message Index tab
- [x] Implement Message view tab
- [x] Implement Attachments tab
- [x] Implement Compose tab
- [x] Implement Sync tab

### Phase 3: Polish ✓
- [x] Add documentation
- [x] Create README
- [x] Create tests

## Completed Files
- `bor/__init__.py` - Package initialization
- `bor/config.py` - Configuration handling
- `bor/mu.py` - Mu interface
- `bor/app.py` - Main Textual application
- `bor/tabs/__init__.py` - Tabs package
- `bor/tabs/base.py` - Base tab class
- `bor/tabs/message_index.py` - Message list
- `bor/tabs/message.py` - Message view
- `bor/tabs/attachments.py` - Attachment handling
- `bor/tabs/compose.py` - Email composition
- `bor/tabs/sync.py` - Sync command runner
- `bor.conf.example` - Example configuration
- `pyproject.toml` - Package configuration
- `README.md` - Project documentation
- `documentation/` - Full documentation
- `tests/` - Unit tests

## Notes
- mu uses JSON/sexp output for machine parsing
- Tab switching uses Alt+0-9 keys (special unicode chars in terminal)
- Must handle threading display with indentation

## Recent Improvements
- [x] Thread visualization with box-drawing characters (├── └── │)
- [x] Thread levels computed from message references
- [x] Confirmation dialogs (y/n) for archive and delete actions
- [x] Ctrl+R to refresh mu index
- [x] Auto-refresh after sync completion
- [x] N/P navigation in message view (next/previous message)
- [x] Message colors: unread (bold cyan), flagged (bold yellow), marked (reverse)
- [x] Read status updates in index after viewing message
- [x] Delete action in message view with confirmation
- [x] Draft save reloads mu index; editing a draft removes it from Drafts
- [x] HTML fallback strips style/script blocks to avoid CSS in message body
- [x] Ctrl+Q blocked in compose; footer no longer shows quit during compose
- [x] Archive keeps cursor near original position for marked messages

