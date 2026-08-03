# Bor Architecture

This document describes the architecture of the Bor terminal email reader.

## Overview

Bor is a terminal-based email client built on:
- **mu** - Mail indexer and searcher for Maildir
- **Textual** - Modern TUI framework for Python

## Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    BorApp (Textual)                     │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐   │
│  │   Header    │ │   Footer    │ │  TabbedContent  │   │
│  └─────────────┘ └─────────────┘ └─────────────────┘   │
│                                          │               │
│         ┌────────────────────────────────┼──────┐       │
│         ▼                                ▼      ▼       │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐   │
│  │   Tab 0:    │ │   Tab 1-9:  │ │   Dynamic Tabs  │   │
│  │  Message    │ │   Message/  │ │   (Compose,     │   │
│  │   Index     │ │  Compose/   │ │   Attachments,  │   │
│  └─────────────┘ │  Attachments│ │   Sync)         │   │
│                  └─────────────┘ └─────────────────┘   │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                    MuInterface                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐   │
│  │   find()    │ │   view()    │ │    move()       │   │
│  │   index()   │ │  contacts() │ │   delete()      │   │
│  └─────────────┘ └─────────────┘ └─────────────────┘   │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                    mu command-line                      │
│  mu find | mu view | mu cfind | mu extract | mu index  │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                    Maildir                              │
│              ~/Maildir/{cur,new,tmp}                    │
└─────────────────────────────────────────────────────────┘
```

## Modules

### bor/config.py

Handles configuration loading from `~/.config/bor.conf` (TOML format).

Key classes:
- `Config` - Main configuration container
- `GeneralConfig`, `FoldersConfig`, `SmtpConfig`, etc. - Section-specific configs

Functions:
- `load_config()` - Load configuration from file
- `get_config()` - Get global config singleton

### bor/mu.py

Interface to the mu mail indexer.

Key classes:
- `EmailAddress` - Email address with name and email
- `EmailMessage` - Email message with all metadata
- `MuInterface` - Main interface to mu commands

Key methods:
- `find()` - Search messages
- `view()` - Get full message content (also parses any `text/calendar` part into `EmailMessage.calendar_event`)
- `move()` - Move message between folders
- `find_contacts()` - Search contacts
- `extract_attachment()` - Extract attachment to file
- `queue_reindex()` - Queue a `mu remove`/`mu add` database update for the background worker
- `wait_for_reindex()` - Block until queued reindexing has drained (worker threads only)

Every method here blocks: `find()` and `find_contacts()` spawn subprocesses,
`view()` parses the whole MIME message. **None of them may be called from the UI
thread** — callers use `asyncio.to_thread` or a Textual worker. Flag changes and
moves rename the file synchronously (cheap, and it is what actually changes
message state) and defer the mu database update to a background thread, batching
pending paths into a single `remove` and a single `add`. Anything that queries mu
afterwards calls `wait_for_reindex()` first, from its worker thread, so results
reflect pending changes.

### bor/ical.py

Parses `text/calendar` (iCalendar) invites via the `icalendar` library into a
display-friendly `CalendarEvent` dataclass. Embedded `VTIMEZONE` definitions are
honoured, so Windows/Exchange timezone names (e.g. "Eastern Standard Time")
resolve to the correct DST-aware offset. Parsing is defensive — malformed
invites yield `None` rather than raising.

Key items:
- `CalendarEvent` - Essential event fields (method, summary, start/end, location, organizer, status, recurrence)
- `parse_calendar()` - Parse an iCalendar payload into a `CalendarEvent`

The message viewer (`bor/tabs/message.py`) renders this as a formatted block
above the body via `format_calendar_event()`.

### bor/app.py

Main Textual application.

Key classes:
- `BorApp` - Main application
- `BorTabbedContent` - Extended tabbed content with notifications

Key methods:
- `add_tab()` - Add new tab
- `close_tab()` - Close tab
- `open_message()` - Open message in new tab
- `open_compose()` - Open compose in new tab

### bor/tabs/

Tab widgets for different views.

#### base.py
- `BaseTab` - Base class for all tabs

#### message_index.py
- `MessageIndexWidget` - Message list with navigation and actions
- `SearchInput` - Search input with submission handling

#### message.py
- `MessageViewWidget` - Single message display
- `MessageHeader` - Header display widget
- `MessageBody` - Body display widget

#### compose.py
- `ComposeWidget` - Email composition
- `AddressInput` - Address input with autocompletion
- `ComposeTextArea` - Text area with shortcuts, and with targeted repainting
  (see below)

#### attachments.py
- `AttachmentsWidget` - Attachment list and preview
- `AttachmentItem` - List item for attachment
- `AttachmentPreview` - Preview pane

#### sync.py
- `SyncWidget` - External command runner with output

## Data Flow

### Reading Email

```
User Input (search query)
    │
    ▼
MessageIndexWidget.search()
    │
    ▼
MuInterface.find(query)
    │
    ▼
subprocess: mu find --format=json
    │
    ▼
Parse JSON → List[EmailMessage]
    │
    ▼
Display in DataTable
```

### Viewing Email

```
User Input (Enter key)
    │
    ▼
BorApp.open_message(msg)
    │
    ▼
Create MessageViewWidget
    │
    ├──▶ Render headers from the index row immediately ("Loading..." body)
    │
    ▼
Worker thread: MuInterface.view(path)
    │
    ▼
Parse email file with email.parser, convert HTML to text,
build the body Text, rename the file to drop the unread flag
    │
    ▼
Back on the UI thread: display headers and body
```

The parse costs 100-200ms for a typical message, so it runs on a worker thread;
doing it inline froze the UI on every message open. An `exclusive` worker group
means holding `n` cancels superseded loads instead of queueing them.

### Sending Email

```
User Input (Ctrl+L L)
    │
    ▼
ComposeWidget._build_message()
    │
    ▼
Build MIME message
    │
    ▼
Connect to SMTP server
    │
    ▼
server.sendmail()
    │
    ▼
Save to Sent folder
```

## Tab Management

Tabs are managed using Textual's `TabbedContent` widget:

- **Tab 0**: Always Message Index (cannot be closed)
- **Tabs 1-9**: Dynamic tabs for messages, compose, etc.

Tab switching via Alt+0-9 is handled by detecting special Unicode characters
that some terminals produce for Alt+digit combinations.

## Threading

Message threading uses mu's `--threads` option which returns thread information.
Thread level is used to indent subjects in the message list.

## Configuration Priority

1. `~/.config/bor.conf` (primary)
2. `~/.mailrc` (for email aliases)
3. System keyring (for passwords)
4. Built-in defaults

## Styling

Styles are defined inline in widget classes using Textual CSS. Key style classes:

- `.unread` - Unread messages
- `.flagged` - Important messages
- `.marked` - Selected for action
- `.quoted` - Quoted text in messages

## UI responsiveness

Two rules keep the interface from stalling.

**Nothing blocking on the event loop.** Textual runs the UI on a single asyncio
loop, so any synchronous subprocess or heavy parse freezes the whole app —
including keyboard input. `mu` calls and MIME parsing therefore run via
`asyncio.to_thread` or a Textual worker. This is the single biggest source of
perceived lag; see the `bor/mu.py` and "Viewing Email" notes above.

**Keep full GC collections rare.** Rendering allocates heavily, so with default
thresholds a generation 2 collection ran every few seconds and blocked for
50-97ms. `BorApp._load_inbox` calls `_tune_gc()` once startup has settled: it
freezes the startup object graph out of future scans and raises the generation 1
and 2 thresholds, leaving generation 0 alone. `BOR_NO_GC_TUNING=1` disables it;
the test suite sets that globally via `tests/conftest.py`, since an app fixture
must not leave the interpreter's collector reconfigured for later tests.

**Repaint only what changed.** Textual has no cell-level diffing: a dirty region
is re-emitted wholesale as ANSI. A widget that repaints itself entirely on every
keystroke costs kilobytes per keypress, which is invisible locally but very
noticeable over SSH. `ComposeTextArea` exists partly for this reason — it
redeclares `TextArea.selection` with `repaint=False` and refreshes only the
affected lines, taking typing and cursor movement from ~11.3KB to ~385 bytes per
keystroke.

### Profiling

`bor/profiling.py` instruments the whole pipeline — frame composition time,
bytes written per frame, terminal drain time, every `mu` call tagged with
whether it ran on the UI thread, garbage collection, and event-loop stalls with
a sampled main-thread stack:

```bash
python -m bor.profiling            # run bor with instrumentation
python -m bor.profiling --report   # summarise the run
```

The log path defaults to `/tmp/borprof.jsonl` and can be set with `$BORPROF_LOG`.
When chasing a stall, check whether `mu` calls report `MAIN THREAD` and whether
the stall overlaps a gen2 collection before suspecting the render path.
