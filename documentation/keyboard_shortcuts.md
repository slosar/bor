# Bor Keyboard Shortcuts

Complete reference of all keyboard shortcuts in Bor email reader.

## Tab Switching

| Key | Action |
|-----|--------|
| Alt+0 | Switch to Message Index (Tab 0) |
| Alt+1 | Switch to Tab 1 |
| Alt+2 | Switch to Tab 2 |
| Alt+3 | Switch to Tab 3 |
| Alt+4 | Switch to Tab 4 |
| Alt+5 | Switch to Tab 5 |
| Alt+6 | Switch to Tab 6 |
| Alt+7 | Switch to Tab 7 |
| Alt+8 | Switch to Tab 8 |
| Alt+9 | Switch to Tab 9 |
| Ctrl+PageUp | Previous tab |
| Ctrl+PageDown | Next tab |

## Global Shortcuts

| Key | Action |
|-----|--------|
| Ctrl+Q | Quit application |

## Message Index

### Navigation

| Key | Action |
|-----|--------|
| ↑ or P | Move cursor up |
| ↓ or N | Move cursor down |
| PageUp | Page up |
| PageDown or Space | Page down |
| Home | Go to first message |
| End | Go to last message |

### Message Actions

| Key | Action |
|-----|--------|
| Enter | Open selected message |
| R | Reply to message |
| F | Forward message |
| C | Compose new message |
| E | Edit draft (if in Drafts folder; removes draft from Drafts immediately) |
| M | Mark/unmark message |
| X | Archive message(s) (with y/n confirmation) |
| A | Apply flag (U/N/F to add, Shift+U/N/F to remove) |
| D | Delete message(s) (with y/n confirmation) |
| Z | Undo last move |

### Search & Navigation

| Key | Action |
|-----|--------|
| S | Search with mu query |
| I | Show Inbox |
| O | Show Archive |
| U | Show Drafts |

### View Options

| Key | Action |
|-----|--------|
| T | Toggle threading |
| Ctrl+T | Show thread for current message |

### Sync & Refresh

| Key | Action |
|-----|--------|
| L | Run synchronization command |
| Ctrl+R | Refresh mu index and message list |

## Message View

### Navigation

| Key | Action |
|-----|--------|
| ↑ | Scroll up |
| ↓ | Scroll down |
| PageUp | Page up |
| PageDown or Space | Page down |
| Home | Scroll to top |
| End | Scroll to bottom |

### Message Navigation

| Key | Action |
|-----|--------|
| N | Next message |
| P | Previous message |
| < | Return to index (keep tab open) |
| Q | Close tab and return to index |

### Actions

| Key | Action |
|-----|--------|
| R | Reply to message |
| F | Forward message |
| C | Compose new message |
| M | Mark/unmark message and advance to next |
| X | Archive message (with y/n confirmation) |
| A | Apply flag (U/N/F to add, Shift+U/N/F to remove) |
| D | Delete message (with y/n confirmation) |
| O | Open URL (if multiple, pick [1-9]) |
| Z | View attachments |
| Ctrl+R | Toggle full headers |

## Attachments View

### Selection

| Key | Action |
|-----|--------|
| 1-9 | Select attachment by number |
| ↑ | Move up in list |
| ↓ | Move down in list |

### Actions

| Key | Action |
|-----|--------|
| Enter | Open with system viewer |
| S | Save selected attachment |
| Shift+S | Save all attachments |
| Q or Esc | Close tab and return to message view |
| < | Return to index (keep tab open) |

## URL Opener Limitation

The URL picker shows and opens the first 9 URLs. If a message has more than 9 URLs, it is easier to copy/paste the link or use terminal link clicking instead.

## Compose

### Navigation

| Key | Action |
|-----|--------|
| Tab | Move to next field / Autocomplete |
| Shift+Tab | Move to previous field |
| Arrow keys | Move within text |
| PageUp/PageDown | Page through body |
| Home | Go to start of line |
| End | Go to end of line |

### Editing

| Key | Action |
|-----|--------|
| Ctrl+C | Copy |
| Ctrl+X | Cut |
| Ctrl+V | Paste |
| Ctrl+Z | Undo |
| Ctrl+Y | Redo |

### Commands

| Key | Action |
|-----|--------|
| Ctrl+L L | Send message |
| Ctrl+L D | Save as draft |
| Ctrl+L X | Cancel (with confirmation) |
| Ctrl+L T/C/B/S/E | Jump to To/CC/BCC/Subject/Editor field |
| Ctrl+L A | Attach file (with path completion) |
| Ctrl+I | Insert file contents |
| Ctrl+S | Search in index |

### Autocompletion

In To/CC/BCC fields:
- Type partial name or email, press Tab to autocomplete
- Cycles through matching contacts and aliases

In body:
- Type alias letter, press Tab to expand (configurable in [aliases])

In attachment path input:
- Press Tab to complete file/folder names
- Starts from home directory, remembers last used folder

## Sync Tab

| Key | Action |
|-----|--------|
| R | Re-run sync command |
| Ctrl+C | Cancel running command |
| Q | Close tab and return to index |
| < | Return to index (keep tab open) |

## Tips

### Efficient Navigation
- Use N/P in message view to quickly browse through messages
- Use Alt+0 to quickly return to the index from any tab
- Use < to return to index without closing the current tab

### Batch Operations
- Mark multiple messages with M, then use X or D to act on all marked
- Use A to apply/remove flags on marked messages
- Use Z to undo accidental moves

### Quick Search
- Press I/O/U for quick access to Inbox/Archive/Drafts
- Use Ctrl+F for incremental search in the index
- Use S for complex mu queries
- Use Ctrl+T to see full thread context
