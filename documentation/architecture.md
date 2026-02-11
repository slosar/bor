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
- `view()` - Get full message content
- `move()` - Move message between folders
- `find_contacts()` - Search contacts
- `extract_attachment()` - Extract attachment to file

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
- `ComposeTextArea` - Text area with shortcuts

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
    ▼
MuInterface.view(path)
    │
    ▼
Parse email file with email.parser
    │
    ▼
Display headers and body
```

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
