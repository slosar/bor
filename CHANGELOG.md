# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
 
## [0.7]

### Added
- Calendar invites (messages with a `text/calendar` part) now show a formatted summary block above the message body, listing the event title, date and time (with timezone), location, organizer, recurrence, and status. Times are shown in the invite's own timezone and, when it differs, also converted to your local time. Windows/Exchange timezone names (e.g. "Eastern Standard Time") are resolved DST-aware via the new `icalendar` dependency.

### Fixed
- Fixed the long-standing UI stalls in message view and compose. Profiling the whole input-to-frame pipeline showed the rendering path was never the problem — it costs ~0.1ms per frame — while blocking work ran directly on the Textual event loop. Opening a message froze the UI for 200–330ms: `MuInterface.view()` parsed the MIME message on the UI thread and then spawned a synchronous `mu remove` + `mu add` pair to record the read flag. Message parsing, HTML-to-text conversion, and body formatting now run on a worker thread with headers rendered immediately from the index row; `mu find` and `mu cfind` moved off the loop too. Across a representative reading session this cut event-loop stalls over 80ms from 13 to 4 and key-to-frame latency from a mean of 63ms (p90 166ms) to 9ms (p90 32ms).
- Flag changes no longer reindex synchronously. `_set_flag()` and `move()` now perform the maildir rename immediately — that is what actually changes message state — and queue the `mu remove`/`mu add` database update onto a background thread, which batches all pending paths into one invocation of each command instead of two subprocesses per message. Searches wait for the queue to drain first (off the UI thread), so an index refresh right after archiving or deleting still sees up-to-date results.
- Fixed the entire compose editor repainting on every keystroke. Textual's `TextArea` declares its `selection` reactive with the default `repaint=True`, so each cursor move dirtied the whole widget: ~11.3KB of ANSI per keypress on a full-screen editor, versus ~1.8KB for the message index. `ComposeTextArea` now redeclares the reactive without the blanket repaint and refreshes only the affected lines, including all soft-wrap segments of a row and both the old and new matching-bracket lines. Typing and cursor movement dropped to ~385 bytes per keystroke, a 29× reduction that is most noticeable over SSH. Rendering was verified identical to stock `TextArea`, cell colours included, across typing, selection, scrolling, editing and soft-wrap scenarios.
- Reduced garbage-collection pauses, which were the largest remaining stall source once mu work moved off the event loop. Textual churns through short-lived render objects, so with CPython's default thresholds a full collection landed every few seconds and took 50–97ms. Once the inbox has loaded, Bor now calls `gc.freeze()` to move the startup object graph (modules, classes, compiled CSS, the widget tree — the bulk of ~135k tracked objects, none of it garbage) into a permanent generation that is never rescanned, and raises the generation 1 and 2 thresholds. Generation 0 is left alone since it already runs in ~0.05ms. Peak full-collection time dropped from 97ms to 17ms at a cost of ~2.6MB of extra resident memory over 60 message opens. Together with the fixes above this removes event-loop stalls over 80ms entirely (13 to 0 over a representative session) and brings key-to-frame latency to a mean of 5.9ms (p90 8.4ms), down from 63ms (p90 166ms). Set `BOR_NO_GC_TUNING=1` to disable, e.g. when chasing a memory leak the frozen generation would hide.
- Clipboard operations (`Ctrl+C`/`Ctrl+V`/`Ctrl+X`) in compose no longer crash over SSH or in other environments where pyperclip is installed but no clipboard backend (xclip, display, etc.) is available. The operations now fail silently instead of raising `PyperclipException`.
- Fixed apply-flag prompt key handling so unrelated keys are ignored without leaving the prompt or triggering message navigation.
- Fixed the compose attachment path prompt (`Ctrl+L A`) selecting the entire default directory on focus. The prompt now leaves the prefilled path intact with the cursor at the end, so typing continues from the default location instead of replacing it.

## [0.6]

### Added
- `Ctrl+L Z` in compose now supports bulk attachment selection. After choosing a directory, Bor opens a keyboard-friendly picker where `Space` toggles files, `Enter` attaches the selected set, `Esc` cancels, and `Ctrl+A` toggles all files.
- Added `attachments.force_kitty_support` to force Kitty graphics support even when `TERM` is not `xterm-kitty`.

### Fixed
- Fixed message viewer freezing with 100% CPU on messages containing a zero-width character (e.g. U+200B) at the start of an overlong unbreakable "word" such as a 300+ char URL. Root cause was an infinite loop in `rich.cells.split_graphemes` in Rich ≤14.3.2; bumped the minimum required versions to `textual>=8.2.7` and `rich>=15.0.0`, which include the fix.
- Removed an unused `mu view --format=sexp` subprocess call from `MuInterface.view()` that ran on every message open with a 60-second timeout; the result was never read (the email file is parsed directly with Python's `email` module).
- Eliminated a whole class of `MarkupError` crashes in the message viewer (e.g. on messages with `View [ https://... ]`-style links or `[bracketed]` text in the subject). The message body and header rendering no longer concatenate user content into Rich/Textual markup strings; instead they build a `rich.text.Text` programmatically with `.append()`, so user-supplied content can never be re-parsed as markup. Clickable URL links are preserved via styled spans rather than `[link="..."]` tags.
- Fixed a message-view `MarkupError` crash when opening messages whose plain-text body contains a bracketed URL such as `[https://...]`; Bor now keeps the visible bracket while generating valid Textual link markup.
- `Ctrl+K` now behaves more like emacs in editable fields across the app: it still kills from the cursor to the end of the current input line, and now also copies the killed text to the system clipboard for later paste/yank.
- The shared file-path prompt used by compose now has bash-like tab completion behavior: a single match completes immediately, multiple matches are shown without forcing one choice, and the input expands only to the longest shared prefix.
- Fixed a brittle `BorApp` type assertion in tab widgets that could fail in some runtime and test contexts even when the app instance was valid.

## [0.5.0]

### Added
- Search history: pressing `Up`/`Down` in the search box (`S`) scrolls through previous queries (newest first). The recalled query is editable before pressing Enter. History is persisted across sessions to `~/.local/share/bor/search_history` (up to 200 entries, deduplicated).
- `Ctrl+R` in message view now toggles a rich extended-header block showing: Message-ID, In-Reply-To, References count, Priority, Size, Folder, Flags, Tags, and extra transport headers (Return-Path, Sender, X-Mailer/User-Agent, X-Spam-Status/Score, Authentication-Results, X-Originating-IP, first Received hop). Previously `Ctrl+R` was wired up but had no visible effect.
- Added `V` shortcut in message view to open the current message in the system browser as a full HTML preview (similar to mu4e's view-in-browser). Uses the HTML part if present, otherwise wraps plain text. A header block with From/To/Date/Subject is prepended. The message is written to a temporary file and opened via `webbrowser.open`. The temporary directory is configurable via `html.browser_tmp_dir` (defaults to the system temp dir).
- Implemented compose `Ctrl+I` insert functionality: opens the same Tab-completing file-path prompt used for attachments, then inserts the selected file's UTF-8 text content at the current editor cursor position.
- Added compose editor shortcuts: `Ctrl+T` now transposes characters around the cursor, and `Ctrl+Backspace` performs backward word deletion matching `Ctrl+W` behavior.

### Fixed
- Fixed `MarkupError` crash when opening HTML emails whose converted plain text contains URLs with special characters (`"`, `]`, or trailing `)` from Markdown-style links). The URL is now sanitised before embedding it in a Rich `[link="…"]` markup tag, and a fallback renders the body without link markup if any error still occurs.
- Kitty inline image previews in the attachments tab now display at the image's natural pixel size instead of being stretched to fill the available terminal width. If the image is larger than the available preview area, it is scaled down to fit while preserving the aspect ratio. Cell pixel dimensions are queried via `TIOCGWINSZ`; a rough 2 px/cell fallback is used when the query fails.
- Fixed N/P (next/previous message) navigation breaking after opening attachments (Z) and returning (Q). The new `MessageViewWidget` received the fully-parsed message from `mu.view()` as its reference, whose `Message-ID` header retains angle brackets (`<foo@bar.com>`), while messages in the search index from `mu.find()` store msgids without them. The lookup always missed, so N/P silently did nothing. Fixed by stripping angle brackets in `mu.view()` when storing `msgid`, and normalising both sides of the comparison in the navigation actions.
- Fixed thread nesting depth computation (`_compute_thread_levels`). Previously, depth was calculated by counting the number of visible ancestors in the References list, which gave the wrong level whenever an email client (e.g. Outlook) only put the immediate parent in References rather than the full ancestor chain. Now each message's level is set to `parent_level + 1`, correctly nesting replies regardless of how short the References chain is.
- Fixed `Ctrl+T` (Show Thread) to find the complete thread even when reference chains are incomplete. The new search strategy uses `thread:` (mu's internal ThreadId field, equal to the oldest known reference) in addition to `msgid:`, and iterates until no new messages are found. This is particularly effective when multiple one-hop reference chains fragment the conversation into separate mu sub-threads.
- Fixed attachment extraction for messages signed with S/MIME (`multipart/signed`). The MIME part numbering now correctly counts `multipart/signed` (and `multipart/encrypted`) as extractable parts while still skipping structural multipart containers, matching mu's own numbering. Previously, PDFs in signed messages would extract the wrong part (a text/html body), saved with a generic name like `part-3` and opened in the browser instead of a PDF viewer.
- URLs in the message body are now clickable: clicking one opens it in the system browser. The `o` key still works for keyboard-driven URL selection.
- Reply now correctly handles mailing list emails. For messages with a `List-Post` header (e.g. Google Groups), replies go to the list address. For other messages with a `Reply-To` header, that address is used. The effective reply destination is shown in the message header as `List:` (for list mail) or `Reply-To:` (for non-list mail with a different reply address).

## [0.4.0]

### Added
- Added basic command-line options: `--version` to print the current Bor version, `--config PATH` to load an alternate config file, and repeatable `--set section.option=value` overrides for runtime config customization.
- Added `general.theme` configuration option to select the Textual UI theme (e.g. `textual-dark`, `textual-light`, `nord`, `gruvbox`, `dracula`). Invalid theme names now fall back to `textual-dark` with a warning.

### Fixed
- Fixed bug where forwarding emails with multiple attachments having the same filename would only forward the last attachment. Duplicate filenames are now automatically renamed (e.g., "file.pdf", "file (2).pdf", "file (3).pdf").
- Fixed message index refresh when returning to the index tab from other tabs (including reply/compose flows), so unread/read status is now up to date after send/cancel/close.
- Fixed marked-message persistence when viewing another message and returning to the index (`m`, `m`, `Enter`, `Q`): previously marked messages now remain marked.
- Fixed marked-row rendering so message marking inverts the full row width, not only the visible text.
- Fixed compose header row alignment so `To:`, `CC:`, `BCC:`, and `Subject:` labels are vertically centered with their input fields.
