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
| Ctrl+Q | Quit application (ignored while a compose tab is active) |

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
| E | Edit draft (only in the Drafts folder; the original is moved to Trash once the edited version is saved or sent) |
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

In the search prompt:

| Key | Action |
|-----|--------|
| Enter | Run the query (and add it to the search history) |
| ↑ / ↓ | Browse previous queries |
| Ctrl+K | Delete to end of line (copied to clipboard) |
| Esc | Close the prompt |

### View Options

| Key | Action |
|-----|--------|
| T | Toggle threading |
| Ctrl+T | Show thread for current message (stays until the next search, I/O/U or T) |

### Sync & Refresh

| Key | Action |
|-----|--------|
| L | Run synchronization command |
| Ctrl+R | Refresh mu index and message list |

### LLM

| Key | Action |
|-----|--------|
| Q | Open the LLM tab (or switch to it) to ask about your mail |

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
| M | Mark/unmark message and advance to next (marked messages show a red 𝐌 in the flags column) |
| X | Archive message (with y/n confirmation) |
| A | Apply flag (U/N/F to add, Shift+U/N/F to remove) |
| D | Delete message (with y/n confirmation) |
| O | Open URL (if multiple, pick [1-9]) |
| V | View message in browser (full HTML preview) |
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
| Up/Down | Move between To/CC/BCC/Subject fields and the body |
| Left/Right | Move within text |
| PageUp/PageDown | Page through body |
| Home | Go to start of line |
| End | Go to end of line |

### Editing

| Key | Action |
|-----|--------|
| Ctrl+C | Copy (body: selection; header fields: the whole field) |
| Ctrl+X | Cut (body: selection; header fields: the whole field) |
| Ctrl+V | Paste |
| Ctrl+K | Delete to end of line, copying it to the clipboard (repeated presses in the body append) |
| Ctrl+U | Delete to start of line |
| Ctrl+W | Delete previous word |
| Ctrl+Backspace | Delete previous word (body only) |
| Ctrl+T | Transpose characters around the cursor (body) |
| Ctrl+Z | Undo (body) |
| Ctrl+Y | Redo (body) |

### Commands

| Key | Action |
|-----|--------|
| Ctrl+L L | Send message |
| Ctrl+L D | Save as draft |
| Ctrl+L X | Cancel, after a y/n confirmation (an edited draft stays in Drafts unchanged) |
| Ctrl+L T/C/B/S/E | Jump to To/CC/BCC/Subject/Editor field |
| Ctrl+L A | Attach file (with path completion) |
| Ctrl+L Z | Attach several files from a directory (opens a picker) |
| Ctrl+I | Insert file contents (only in terminals that report Ctrl+I separately from Tab, e.g. kitty; elsewhere it acts as Tab) |
| Ctrl+S | Switch to the message index (does not open the search prompt) |

In the bulk-attachment picker (`Ctrl+L Z`):

| Key | Action |
|-----|--------|
| Space | Toggle the highlighted file |
| Ctrl+A | Toggle all files |
| Enter | Attach the selected files |
| Esc | Cancel |

### Autocompletion

In To/CC/BCC fields:
- Type partial name or email, press Tab to autocomplete
- Cycles through matching contacts and aliases

In body:
- Type alias letter, press Tab to expand (configurable in [aliases])
- Tab with no alias before the cursor moves to the To field (Shift+Tab in To comes back)

In attachment path input:
- Ctrl+K deletes to end of line; Esc cancels
- Press Tab to complete file/folder names
- Matching is case-insensitive; with multiple matches the input extends to the longest shared prefix (keeping the actual file casing) and the matches are listed
- Starts from home directory, remembers last used folder

## Sync Tab

| Key | Action |
|-----|--------|
| R | Re-run sync command |
| Ctrl+C | Cancel running command |
| X | Close tab (cancels a running command) and return to index |
| M | Return to index (keep tab open) |

After a successful sync Bor runs `mu index`, refreshes the message index, and
closes the Sync tab automatically. On failure the tab stays open with the output.

## LLM Tab

Ask questions about your mail; the model searches and reads it (read-only) and
answers in the tab. See the `[llm]` section in [configuration.md](configuration.md).

| Key | Action |
|-----|--------|
| Enter | Ask the question |
| ↑ / ↓ | Browse earlier questions |
| Ctrl+K | Delete to end of line (copied to clipboard) |
| PageUp / PageDown | Scroll the conversation |
| Esc | Cancel the question being answered; otherwise return to the index |
| Ctrl+N | Start a new conversation |

Each step the model takes (a search, reading a message or a thread) is shown as
a dim line, followed by the answer and its token use and cost. You can switch
to other tabs while it works; a notification says when the answer is ready.
The conversation lasts until `Ctrl+N` or quitting Bor (closing the tab keeps it).

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
- Use S for mu queries; ↑/↓ in the prompt recalls earlier ones
- Use Ctrl+T to see full thread context
