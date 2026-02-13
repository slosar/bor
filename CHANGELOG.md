# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - Unreleased

### Fixed
- Fixed bug where forwarding emails with multiple attachments having the same filename would only forward the last attachment. Duplicate filenames are now automatically renamed (e.g., "file.pdf", "file (2).pdf", "file (3).pdf").
