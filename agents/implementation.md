# Bor Implementation Details

## Mu Command Interface

### Search for messages
```bash
mu find <query> --format=json -n <maxnum> [-t] [-z]
```
- `-t`: threading
- `-z`: descending order (newest first)
- `--format=json`: machine-readable output

### View single message
```bash
mu view <file-path> --format=sexp
```

### Contact search
```bash
mu cfind <pattern> --format=json
```

### Move/flag messages
Using mu server protocol or filesystem operations with `mu add`/`mu remove`.

After moving or renaming message files:
```bash
mu remove <old-path>  # Remove old entry from database
mu add <new-path>     # Add new entry to database
```

### Update index
```bash
mu index
```

## Configuration Schema (TOML)

```toml
[general]
max_messages = 400
date_format = "%Y-%m-%d %H:%M"

[folders]
inbox = "/inbox"
archive = "/archive"
drafts = "/drafts"
sent = "/sent"
trash = "/trash"

[smtp]
server = "smtp.example.com"
port = 587
username = "user@example.com"
use_tls = true

[identity]
name = "Your Name"
email = "user@example.com"
signature = """
--
Your Name
"""

[colors]
unread = "blue"
important = "orange"

[sync]
command = "mbsync -a"

[aliases]
# Tab autocompletions: letter -> expanded text
a = "Best regards,\n  Your Name"
b = "Thanks for your email,"

[email_aliases]
# .mailrc style aliases
john = "john.doe@example.com"
team = "team@example.com, lead@example.com"
```

## Tab Management

Each tab is a TabPane in TabbedContent:
- Tab 0: Message Index (always visible)
- Tab 1-9: Dynamic tabs (Message, Compose, Attachments, Sync)

Alt+N switching handled via unicode character detection as in terminal_editor.py.

## Key Bindings

### Global
- Alt+0-9: Switch tabs
- Ctrl+Q: Quit

### Message Index
- N/P or Up/Down: Navigate
- Enter: Open message
- R: Reply
- F: Forward
- C: Compose
- S: Search (mu query)
- Ctrl+S: Incremental search
- I: Inbox
- O: Archive
- U: Drafts
- J: Jump to folder
- M: Mark message
- A: Archive message(s)
- D: Delete message(s)
- T: Toggle threading
- Z: Undo last move

### Message View
- Space/PgDn: Scroll down
- Up/Down: Scroll
- M: Return to index
- X: Close and return
- N/P: Next/Previous message
- R: Reply
- F: Forward
- A: Archive
- Z: Attachments tab

### Compose
- Ctrl+L L: Send
- Ctrl+L D: Save draft
- Ctrl+L X: Cancel
- Ctrl+S: Search
- Ctrl+I: Insert file
- Ctrl+A: Attach file
- Tab: Autocomplete

## Message Flags Display

Unicode symbols for flags:
- 📧 or ● : Unread
- ↩ : Replied
- → : Forwarded
- ⚑ : Important/Flagged  
- 📎 : Has attachments
- 🔒 : Encrypted
- ✓ : Signed

## Threading Display

```
Subject 1
├── Re: Subject 1
│   └── Re: Re: Subject 1
└── Re: Subject 1 (different branch)
Subject 2
```

Use ↳ for thread continuation.
