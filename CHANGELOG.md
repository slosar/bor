# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
