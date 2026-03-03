# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0]

### Added
- Search history: pressing `Up`/`Down` in the search box (`S`) scrolls through previous queries (newest first). The recalled query is editable before pressing Enter. History is persisted across sessions to `~/.local/share/bor/search_history` (up to 200 entries, deduplicated).
- `Ctrl+R` in message view now toggles a rich extended-header block showing: Message-ID, In-Reply-To, References count, Priority, Size, Folder, Flags, Tags, and extra transport headers (Return-Path, Sender, X-Mailer/User-Agent, X-Spam-Status/Score, Authentication-Results, X-Originating-IP, first Received hop). Previously `Ctrl+R` was wired up but had no visible effect.
- Added `V` shortcut in message view to open the current message in the system browser as a full HTML preview (similar to mu4e's view-in-browser). Uses the HTML part if present, otherwise wraps plain text. A header block with From/To/Date/Subject is prepended. The message is written to a temporary file and opened via `webbrowser.open`. The temporary directory is configurable via `html.browser_tmp_dir` (defaults to the system temp dir).
- Implemented compose `Ctrl+I` insert functionality: opens the same Tab-completing file-path prompt used for attachments, then inserts the selected file's UTF-8 text content at the current editor cursor position.
- Added compose editor shortcuts: `Ctrl+T` now transposes characters around the cursor, and `Ctrl+Backspace` performs backward word deletion matching `Ctrl+W` behavior.

### Fixed
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
