"""Shared text-editing helpers for Bor widgets."""

from __future__ import annotations

from typing import Optional


try:
    import pyperclip
except ImportError:  # pragma: no cover - optional dependency
    pyperclip = None


def copy_to_clipboard(text: str, append: bool = False) -> None:
    """Copy text to the system clipboard when clipboard support is available."""
    if pyperclip is None or not text:
        return
    if append:
        try:
            text = pyperclip.paste() + text
        except Exception:
            pass
    pyperclip.copy(text)


def kill_input_line(value: str, cursor_position: int) -> tuple[str, int, str]:
    """Kill from the cursor to the end of a single-line input."""
    cursor_position = max(0, min(cursor_position, len(value)))
    killed_text = value[cursor_position:]
    return value[:cursor_position], cursor_position, killed_text


def kill_text_line(text: str, cursor_index: int) -> tuple[str, int, str]:
    """Kill from the cursor to the end of the current line, emacs-style."""
    cursor_index = max(0, min(cursor_index, len(text)))

    if cursor_index == len(text) and cursor_index > 0 and text[cursor_index - 1] == "\n":
        killed_text = "\n"
        return text[: cursor_index - 1], cursor_index - 1, killed_text

    newline_index = text.find("\n", cursor_index)

    if newline_index == -1:
        killed_text = text[cursor_index:]
        return text[:cursor_index], cursor_index, killed_text

    if cursor_index == newline_index:
        killed_text = "\n"
        return text[:cursor_index] + text[newline_index + 1 :], cursor_index, killed_text

    killed_text = text[cursor_index:newline_index]
    return text[:cursor_index] + text[newline_index:], cursor_index, killed_text
