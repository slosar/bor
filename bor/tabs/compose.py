"""
Compose tab for Bor email reader.

Email composition with address autocompletion and attachment handling.
"""

from __future__ import annotations

import email.utils
import os
import re
import smtplib
import tempfile
import shutil
from datetime import datetime
from email.header import Header
from email.message import EmailMessage as StdEmailMessage
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Input, TextArea, Static, Label, ListView, ListItem
from textual.reactive import reactive
from textual.message import Message

try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    HAS_PYPERCLIP = False


def _clip_copy(text: str) -> None:
    if not HAS_PYPERCLIP:
        return
    try:
        pyperclip.copy(text)
    except Exception:
        pass


def _clip_paste() -> str:
    if not HAS_PYPERCLIP:
        return ""
    try:
        return pyperclip.paste() or ""
    except Exception:
        return ""

from bor.tabs.base import BaseTab
from bor.mu import EmailMessage, EmailAddress
from bor.config import get_config, load_mailrc_aliases
from bor.editing import copy_to_clipboard, kill_input_line, kill_text_line


# Custom messages for Ctrl+L commands
class ComposeCommand(Message):
    """Base class for compose commands."""
    pass

class SendMessage(ComposeCommand):
    """Command to send the message."""
    pass

class SaveDraft(ComposeCommand):
    """Command to save as draft."""
    pass

class CancelCompose(ComposeCommand):
    """Command to cancel composition."""
    pass

class FocusTo(ComposeCommand):
    """Command to focus To field."""
    pass

class FocusCC(ComposeCommand):
    """Command to focus CC field."""
    pass

class FocusBCC(ComposeCommand):
    """Command to focus BCC field."""
    pass

class FocusSubject(ComposeCommand):
    """Command to focus Subject field."""
    pass

class FocusEditor(ComposeCommand):
    """Command to focus Editor/body field."""
    pass


class AttachFile(ComposeCommand):
    """Command to attach a file."""
    pass


class AttachFilesFromDirectory(ComposeCommand):
    """Command to attach multiple files from a directory."""
    pass


class CtrlLMixin:
    """
    Mixin for handling Ctrl+L command sequences.
    
    Handles Ctrl+L followed by:
    - L: Send message
    - D: Save draft
    - X: Cancel
    - T: Go to To field
    - C: Go to CC field
    - B: Go to BCC field
    - S: Go to Subject field
    - E: Go to Editor
    - A: Attach file
    - Z: Attach many files from a directory
    """
    
    _ctrl_l_pressed: bool = False
    
    def handle_ctrl_l_key(self, event: events.Key) -> bool:
        """
        Handle key events for Ctrl+L sequences.
        
        Args:
            event: Key event
            
        Returns:
            True if event was handled, False otherwise
        """
        # Handle second key after Ctrl+L
        if self._ctrl_l_pressed:
            self._ctrl_l_pressed = False
            key = event.key.lower() if event.key else ""
            
            if key == "l":
                self.post_message(SendMessage())
                event.prevent_default()
                event.stop()
                return True
            elif key == "d":
                self.post_message(SaveDraft())
                event.prevent_default()
                event.stop()
                return True
            elif key == "x":
                self.post_message(CancelCompose())
                event.prevent_default()
                event.stop()
                return True
            elif key == "t":
                self.post_message(FocusTo())
                event.prevent_default()
                event.stop()
                return True
            elif key == "c":
                self.post_message(FocusCC())
                event.prevent_default()
                event.stop()
                return True
            elif key == "b":
                self.post_message(FocusBCC())
                event.prevent_default()
                event.stop()
                return True
            elif key == "s":
                self.post_message(FocusSubject())
                event.prevent_default()
                event.stop()
                return True
            elif key == "e":
                self.post_message(FocusEditor())
                event.prevent_default()
                event.stop()
                return True
            elif key == "a":
                self.post_message(AttachFile())
                event.prevent_default()
                event.stop()
                return True
            elif key == "z":
                self.post_message(AttachFilesFromDirectory())
                event.prevent_default()
                event.stop()
                return True
            # Unknown sequence - ignore
            return True
        
        # Check for Ctrl+L
        if event.key == "ctrl+l":
            self._ctrl_l_pressed = True
            event.prevent_default()
            event.stop()
            return True

        # Block Ctrl+Q in compose fields to avoid accidental quit
        if event.key == "ctrl+q":
            event.prevent_default()
            event.stop()
            return True
        
        return False


class AddressInput(CtrlLMixin, Input):
    """
    Input widget for email addresses with autocompletion.

    Supports Tab completion from mu contacts and .mailrc aliases.
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initialize address input."""
        super().__init__(*args, **kwargs)
        self._contacts: List[EmailAddress] = []
        self._aliases: dict = {}
        self._completion_index: int = 0
        self._completions: List[str] = []

    def set_contacts(self, contacts: List[EmailAddress]) -> None:
        """
        Set the contacts list for completion.

        Args:
            contacts: List of email addresses for completion
        """
        self._contacts = contacts

    def set_aliases(self, aliases: dict) -> None:
        """
        Set the email aliases for completion.

        Args:
            aliases: Dictionary mapping alias names to email addresses
        """
        self._aliases = aliases

    def _find_address_start(self, text: str, cursor_pos: int) -> int:
        """
        Find the start of the current email address before cursor position.
        
        Properly handles commas inside quoted strings (e.g., "Last, First" <email>).
        
        Args:
            text: Full text of the input field
            cursor_pos: Current cursor position
            
        Returns:
            Start position of current address
        """
        # Parse backwards from cursor to find the start of this address
        # We need to respect quoted strings
        in_quotes = False
        escape_next = False
        
        for i in range(cursor_pos - 1, -1, -1):
            char = text[i]
            
            if escape_next:
                escape_next = False
                continue
                
            if char == '\\':
                escape_next = True
                continue
                
            if char == '"':
                in_quotes = not in_quotes
                continue
                
            # Only treat comma as separator if not in quotes
            if char == ',' and not in_quotes:
                return i + 1
        
        return 0
    
    def _get_completions(self, prefix: str) -> List[str]:
        """
        Get completion suggestions for a prefix.

        Args:
            prefix: Text to complete

        Returns:
            List of completion suggestions
        """
        completions = []
        prefix_lower = prefix.lower()

        # Check aliases first
        for alias, email_addr in self._aliases.items():
            if alias.lower().startswith(prefix_lower):
                completions.append(email_addr)

        # Check contacts (substring match like mu cfind)
        for contact in self._contacts:
            name = contact.name or ""
            email = contact.email or ""
            name_lower = name.lower()
            email_lower = email.lower()
            if prefix_lower in name_lower or prefix_lower in email_lower:
                completions.append(str(contact))

        # If nothing matched locally, try a targeted mu cfind
        if not completions and prefix:
            mu = getattr(self.app, "mu", None)
            if mu is not None:
                try:
                    remote_contacts = mu.find_contacts(pattern=prefix, maxnum=50)
                except Exception:
                    remote_contacts = []

                if remote_contacts:
                    existing_keys = {((c.email or "").lower() or (c.name or "").lower()) for c in self._contacts}
                    for contact in remote_contacts:
                        key = (contact.email or "").lower() or (contact.name or "").lower()
                        if key and key not in existing_keys:
                            self._contacts.append(contact)
                            existing_keys.add(key)
                        completions.append(str(contact))

        return completions

    def _on_key(self, event: events.Key) -> None:
        """Handle key events for completion."""
        # Handle clipboard operations
        if event.key == "ctrl+c":
            _clip_copy(self.value)
            event.prevent_default()
            event.stop()
            return
        elif event.key == "ctrl+v":
            text = _clip_paste()
            if text:
                self.insert_text_at_cursor(text)
            event.prevent_default()
            event.stop()
            return
        elif event.key == "ctrl+x":
            _clip_copy(self.value)
            self.value = ""
            event.prevent_default()
            event.stop()
            return
        elif event.key == "ctrl+k":
            new_value, new_cursor, killed_text = kill_input_line(self.value, self.cursor_position)
            copy_to_clipboard(killed_text)
            self.value = new_value
            self.cursor_position = new_cursor
            event.prevent_default()
            event.stop()
            return
        
        # Check Ctrl+L sequences first
        if self.handle_ctrl_l_key(event):
            return
            
        if event.key == "tab":
            # Get the current word being typed
            value = self.value
            cursor = self.cursor_position

            # Find the start of the current address (respecting quoted strings)
            start = self._find_address_start(value, cursor)

            # Get the prefix to complete
            prefix = value[start:cursor].strip()

            if prefix:
                # Try autocompletion
                if not self._completions or self._completion_index >= len(self._completions):
                    self._completions = self._get_completions(prefix)
                    self._completion_index = 0

                if self._completions:
                    # Insert completion
                    completion = self._completions[self._completion_index]
                    new_value = value[:start] + (" " if start > 0 else "") + completion + value[cursor:]
                    self.value = new_value
                    self.cursor_position = start + len(completion) + (1 if start > 0 else 0)
                    self._completion_index = (self._completion_index + 1) % len(self._completions)
                    event.prevent_default()
                    event.stop()
                    return
                    
            # No prefix or no completions - move to next field
            self.screen.focus_next()
            event.prevent_default()
            event.stop()
        else:
            # Reset completion state on any other key
            self._completions = []
            self._completion_index = 0
            super()._on_key(event)


class SubjectInput(CtrlLMixin, Input):
    """Input widget for subject line with Ctrl+L support."""
    
    def __init__(self, *args, **kwargs) -> None:
        """Initialize subject input."""
        super().__init__(*args, **kwargs)
        self._ctrl_l_pressed = False
    
    def _on_key(self, event: events.Key) -> None:
        """Handle key events."""
        # Handle clipboard operations
        if event.key == "ctrl+c":
            _clip_copy(self.value)
            event.prevent_default()
            event.stop()
            return
        elif event.key == "ctrl+v":
            text = _clip_paste()
            if text:
                self.insert_text_at_cursor(text)
            event.prevent_default()
            event.stop()
            return
        elif event.key == "ctrl+x":
            _clip_copy(self.value)
            self.value = ""
            event.prevent_default()
            event.stop()
            return
        elif event.key == "ctrl+k":
            new_value, new_cursor, killed_text = kill_input_line(self.value, self.cursor_position)
            copy_to_clipboard(killed_text)
            self.value = new_value
            self.cursor_position = new_cursor
            event.prevent_default()
            event.stop()
            return
        
        if self.handle_ctrl_l_key(event):
            return
        if event.key == "tab":
            # Move to next field (editor)
            self.screen.focus_next()
            event.prevent_default()
            event.stop()
            return
        super()._on_key(event)


class ComposeTextArea(CtrlLMixin, TextArea):
    """
    Text area for email body composition.

    Supports text autocompletion with configurable shortcuts.
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initialize compose text area."""
        super().__init__(*args, **kwargs)
        self._aliases: dict = {}
        self._ctrl_l_pressed: bool = False
        self._append_next_kill: bool = False

    def set_aliases(self, aliases: dict) -> None:
        """
        Set text aliases for completion.

        Args:
            aliases: Dictionary mapping single characters to expanded text
        """
        self._aliases = aliases

    @staticmethod
    def _cursor_to_index(text: str, row: int, col: int) -> int:
        """Convert (row, col) cursor location to absolute index."""
        lines = text.split("\n")
        if not lines:
            return 0

        row = max(0, min(row, len(lines) - 1))
        col = max(0, min(col, len(lines[row])))

        index = 0
        for line_index in range(row):
            index += len(lines[line_index]) + 1
        index += col
        return index

    @staticmethod
    def _index_to_cursor(text: str, index: int) -> tuple[int, int]:
        """Convert absolute index to (row, col) cursor location."""
        if not text:
            return (0, 0)

        index = max(0, min(index, len(text)))
        prefix = text[:index]
        row = prefix.count("\n")
        last_newline = prefix.rfind("\n")
        col = index if last_newline == -1 else index - last_newline - 1
        return (row, col)

    @staticmethod
    def _delete_previous_word(text: str, cursor_index: int) -> tuple[str, int]:
        """Delete the previous word (and preceding whitespace) from cursor."""
        if cursor_index <= 0:
            return text, 0

        start = cursor_index
        while start > 0 and text[start - 1].isspace():
            start -= 1
        while start > 0 and not text[start - 1].isspace():
            start -= 1

        return text[:start] + text[cursor_index:], start

    @staticmethod
    def _transpose_at_cursor(text: str, cursor_index: int) -> tuple[str, int]:
        """Transpose characters around cursor position."""
        if len(text) < 2 or cursor_index <= 0:
            return text, cursor_index

        if cursor_index >= len(text):
            left_index = len(text) - 2
            right_index = len(text) - 1
            new_cursor = len(text)
        else:
            left_index = cursor_index - 1
            right_index = cursor_index
            new_cursor = min(cursor_index + 1, len(text))

        if text[left_index] == "\n" or text[right_index] == "\n":
            return text, cursor_index

        chars = list(text)
        chars[left_index], chars[right_index] = chars[right_index], chars[left_index]
        return "".join(chars), new_cursor

    def _kill_line_at_cursor(self) -> None:
        """Kill from the cursor to the end of the current line and copy it."""
        row, col = self.cursor_location
        cursor_index = self._cursor_to_index(self.text, row, col)
        new_text, new_index, killed_text = kill_text_line(self.text, cursor_index)
        copy_to_clipboard(killed_text, append=self._append_next_kill)
        self._append_next_kill = bool(killed_text)
        self.text = new_text
        self.cursor_location = self._index_to_cursor(new_text, new_index)

    def _on_key(self, event: events.Key) -> None:
        """Handle key events for text completion and commands."""
        if event.key != "ctrl+k":
            self._append_next_kill = False

        # Handle clipboard operations - must prevent default to avoid SIGINT
        if event.key == "ctrl+c":
            selected = self.selected_text
            if selected:
                _clip_copy(selected)
            event.prevent_default()
            event.stop()
            return
        elif event.key == "ctrl+v":
            text = _clip_paste()
            if text:
                self.insert(text)
            event.prevent_default()
            event.stop()
            return
        elif event.key == "ctrl+x":
            selected = self.selected_text
            if selected:
                _clip_copy(selected)
                # Delete selection
                start, end = self.selection
                if start > end:
                    start, end = end, start
                self.delete(start, end)
            event.prevent_default()
            event.stop()
            return
        elif event.key == "ctrl+k":
            self._kill_line_at_cursor()
            event.prevent_default()
            event.stop()
            return

        if event.key in {"ctrl+backspace", "ctrl+w"}:
            row, col = self.cursor_location
            cursor_index = self._cursor_to_index(self.text, row, col)
            new_text, new_index = self._delete_previous_word(self.text, cursor_index)

            if new_text != self.text:
                self.text = new_text
                self.cursor_location = self._index_to_cursor(new_text, new_index)

            event.prevent_default()
            event.stop()
            return

        if event.key == "ctrl+t":
            row, col = self.cursor_location
            cursor_index = self._cursor_to_index(self.text, row, col)
            new_text, new_index = self._transpose_at_cursor(self.text, cursor_index)

            if new_text != self.text:
                self.text = new_text
                self.cursor_location = self._index_to_cursor(new_text, new_index)

            event.prevent_default()
            event.stop()
            return
        
        # Check Ctrl+L sequences first
        if self.handle_ctrl_l_key(event):
            return

        # Handle Tab for text aliases
        if event.key == "tab":
            # Get character before cursor
            cursor = self.cursor_location
            text = self.text
            lines = text.split("\n")

            if cursor[0] < len(lines):
                line = lines[cursor[0]]
                if cursor[1] > 0:
                    char = line[cursor[1] - 1]
                    if char in self._aliases:
                        # Expand alias
                        expansion = self._aliases[char]
                        # Remove the trigger character and insert expansion
                        new_line = line[:cursor[1] - 1] + expansion + line[cursor[1]:]
                        lines[cursor[0]] = new_line
                        self.text = "\n".join(lines)
                        event.prevent_default()
                        event.stop()
                        return

        super()._on_key(event)


class FilePathInput(Input):
    """
    Input widget for file paths with tab completion.
    
    Supports Tab completion for file/directory names.
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initialize file path input."""
        super().__init__(*args, **kwargs)
        self._completions: List[str] = []
        self.select_on_focus = False

    def _get_completions(self, path_str: str) -> List[str]:
        """
        Get completion suggestions for a path.

        Args:
            path_str: Current path string

        Returns:
            List of completion suggestions
        """
        if not path_str:
            path_str = str(Path.home())
        
        path = Path(path_str).expanduser()
        
        # If path ends with / or is a directory without trailing content, list its contents
        if path_str.endswith("/") or (path.is_dir() and path_str == str(path)):
            parent = path
            prefix = ""
        else:
            parent = path.parent
            prefix = path.name.lower()
        
        if not parent.exists():
            return []
        
        completions = []
        try:
            for entry in sorted(parent.iterdir()):
                name = entry.name
                if prefix and not name.lower().startswith(prefix):
                    continue
                
                full_path = str(entry)
                if entry.is_dir():
                    full_path += "/"
                completions.append(full_path)
        except PermissionError:
            pass
        
        return completions

    @staticmethod
    def _longest_shared_completion_prefix(path_str: str, completions: List[str]) -> str:
        """Return the farthest bash-style completion prefix we can safely insert."""
        if not completions:
            return path_str

        if len(completions) == 1:
            return completions[0]

        shared_prefix = os.path.commonprefix(completions)
        if shared_prefix.startswith(path_str):
            return shared_prefix
        return path_str

    def on_key(self, event: events.Key) -> None:
        """Handle key events for completion."""
        if event.key == "ctrl+k":
            new_value, new_cursor, killed_text = kill_input_line(self.value, self.cursor_position)
            copy_to_clipboard(killed_text)
            self.value = new_value
            self.cursor_position = new_cursor
            event.prevent_default()
            event.stop()
        elif event.key == "tab":
            current_value = self.value
            self._completions = self._get_completions(current_value)

            if self._completions:
                self.value = self._longest_shared_completion_prefix(
                    current_value, self._completions
                )

            # Move cursor to end of line
            self.cursor_position = len(self.value)

            # Post message to update completions display
            self.post_message(FilePathInput.CompletionsChanged(self._completions, -1))

            event.prevent_default()
            event.stop()
        elif event.key == "escape":
            # Cancel attachment input
            self.post_message(FilePathInput.Cancelled())
            event.prevent_default()
            event.stop()
        elif event.key == "enter":
            # Confirm attachment
            self.post_message(FilePathInput.Submitted(self.value))
            event.prevent_default()
            event.stop()
        else:
            # Reset completions when typing
            self._completions = []
            # Clear completions display
            self.post_message(FilePathInput.CompletionsChanged([], 0))

    class Submitted(Message):
        """File path submitted message."""
        def __init__(self, path: str) -> None:
            self.path = path
            super().__init__()

    class Cancelled(Message):
        """File path input cancelled message."""
        pass

    class CompletionsChanged(Message):
        """Completions list changed message."""
        def __init__(self, completions: List[str], current_index: int) -> None:
            self.completions = completions
            self.current_index = current_index
            super().__init__()


class BulkAttachmentItem(ListItem):
    """List item representing a file that may be attached."""

    def __init__(self, path: Path, selected: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self.path = path
        self.selected = selected

    def compose(self) -> ComposeResult:
        """Create the list item."""
        yield Static(self._render_label())

    def toggle(self) -> None:
        """Toggle whether this file is selected for attachment."""
        self.selected = not self.selected
        self._refresh()

    def set_selected(self, selected: bool) -> None:
        """Set the selected state."""
        if self.selected != selected:
            self.selected = selected
            self._refresh()

    def _refresh(self) -> None:
        """Refresh the rendered label."""
        self.query_one(Static).update(self._render_label())

    def _render_label(self) -> str:
        """Return the display string for this item."""
        marker = "[x]" if self.selected else "[ ]"
        size = 0
        if self.path.exists():
            try:
                size = self.path.stat().st_size
            except OSError:
                size = 0
        if size < 1024:
            size_text = f"{size} B"
        elif size < 1024 * 1024:
            size_text = f"{size / 1024:.1f} KB"
        else:
            size_text = f"{size / (1024 * 1024):.1f} MB"
        return f"{marker} {self.path.name} ({size_text})"


class BulkAttachmentList(ListView):
    """Keyboard-friendly file picker for bulk attachment selection."""

    class Toggled(Message):
        """Posted when the highlighted item is toggled."""

        def __init__(self, item: BulkAttachmentItem) -> None:
            self.item = item
            super().__init__()

    class Cancelled(Message):
        """Posted when the picker is cancelled."""

        pass

    class SelectAllToggled(Message):
        """Posted when the user requests a select-all toggle."""

        pass

    def on_key(self, event: events.Key) -> None:
        """Handle picker-specific key bindings."""
        if event.key == "space":
            item = self.highlighted_child
            if isinstance(item, BulkAttachmentItem):
                item.toggle()
                self.post_message(self.Toggled(item))
            event.prevent_default()
            event.stop()
            return

        if event.key == "ctrl+a":
            self.post_message(self.SelectAllToggled())
            event.prevent_default()
            event.stop()
            return

        if event.key == "escape":
            self.post_message(self.Cancelled())
            event.prevent_default()
            event.stop()
            return


class ComposeWidget(BaseTab):
    """
    Compose widget for email composition.

    Handles composing new messages, replies, and forwards.
    """

    BINDINGS = [
        Binding("ctrl+s", "search", "Search", show=False),
        Binding("ctrl+i", "insert_file", "Insert File"),
    ]

    DEFAULT_CSS = """
    ComposeWidget {
        height: 1fr;
    }

    ComposeWidget .header-container {
        height: auto;
        padding: 0 1;
        background: $surface;
    }

    ComposeWidget .header-row {
        height: 3;
        margin: 0;
    }

    ComposeWidget .header-label {
        width: 10;
        height: 3;
        color: $text-muted;
        content-align: left middle;
    }

    ComposeWidget .header-input {
        width: 1fr;
        height: 3;
        margin: 0;
    }

    ComposeWidget .body-container {
        height: 1fr;
    }

    ComposeWidget TextArea {
        height: 1fr;
    }

    ComposeWidget .attachment-bar {
        height: auto;
        padding: 0 1;
        background: $warning-darken-2;
    }

    ComposeWidget .attachment-input-bar {
        height: auto;
        min-height: 2;
        padding: 0 1;
        background: $primary-darken-2;
        layout: vertical;
        border: solid $success;
    }

    ComposeWidget .attachment-input-bar.hidden {
        display: none;
    }

    ComposeWidget .attachment-input-label {
        width: auto;
        color: $text;
    }

    ComposeWidget .attachment-path-input {
        width: 1fr;
    }

    ComposeWidget .attachment-completions {
        height: 15;
        min-height: 15;
        max-height: 15;
        width: 1fr;
        padding: 0 1;
        background: $surface;
        color: $text;
        border: solid $surface-darken-1;
    }

    ComposeWidget .bulk-attachment-picker {
        height: auto;
        max-height: 18;
        padding: 0 1 1 1;
        background: $panel;
        border: solid $accent;
    }

    ComposeWidget .bulk-attachment-picker.hidden {
        display: none;
    }

    ComposeWidget .bulk-attachment-picker-title {
        height: auto;
        padding: 0 0 1 0;
        color: $text;
    }

    ComposeWidget #bulk-attachment-list {
        height: 12;
        border: solid $surface-darken-1;
        background: $surface;
    }

    ComposeWidget .status-bar {
        height: 1;
        dock: bottom;
        background: $surface;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        reply_to: Optional[EmailMessage] = None,
        forward: Optional[EmailMessage] = None,
        edit_draft: Optional[EmailMessage] = None,
        reply_all: bool = False,
        *args,
        **kwargs
    ) -> None:
        """
        Initialize the compose widget.

        Args:
            reply_to: Message to reply to
            forward: Message to forward
            edit_draft: Draft message to edit
            reply_all: If True, include CC recipients in reply
        """
        super().__init__(*args, **kwargs)
        self.reply_to = reply_to
        self.reply_all = reply_all
        self.forward = forward
        self.edit_draft = edit_draft
        self.attachments: List[Path] = []
        self._contacts: List[EmailAddress] = []
        self._email_aliases: dict = {}
        self._text_aliases: dict = {}
        self._last_attachment_dir: Path = Path.home()  # Track last used directory
        self._file_path_mode: Optional[str] = None
        self._bulk_picker_directory: Optional[Path] = None
        self._draft_deleted: bool = False

    def compose(self) -> ComposeResult:
        """Create the widget layout."""
        config = get_config()

        with Vertical():
            with Container(classes="header-container"):
                with Horizontal(classes="header-row"):
                    yield Label("To:", classes="header-label")
                    yield AddressInput(id="to-input", classes="header-input")
                with Horizontal(classes="header-row"):
                    yield Label("CC:", classes="header-label")
                    yield AddressInput(id="cc-input", classes="header-input")
                with Horizontal(classes="header-row"):
                    yield Label("BCC:", classes="header-label")
                    yield AddressInput(id="bcc-input", classes="header-input")
                with Horizontal(classes="header-row"):
                    yield Label("Subject:", classes="header-label")
                    yield SubjectInput(id="subject-input", classes="header-input")

            with Container(classes="body-container"):
                yield ComposeTextArea(id="body-input")

            with Container(classes="attachment-bar", id="attachment-bar"):
                yield Label("", id="attachment-label")

            with Vertical(classes="attachment-input-bar hidden", id="attachment-input-bar"):
                yield Label("", id="attachment-completions", classes="attachment-completions")
                with Horizontal():
                    yield Label("", id="file-path-input-label", classes="attachment-input-label")
                    yield FilePathInput(id="attachment-path-input", classes="attachment-path-input")

            with Vertical(classes="bulk-attachment-picker hidden", id="bulk-attachment-picker"):
                yield Label("", id="bulk-attachment-picker-title", classes="bulk-attachment-picker-title")
                yield BulkAttachmentList(id="bulk-attachment-list")

            with Horizontal(classes="status-bar"):
                yield Label(
                    "Ctrl+L: L=Send D=Draft X=Cancel A=Attach Z=Bulk Attach | T/C/B/S/E=Jump | Tab=Next",
                    id="status",
                )

    def on_mount(self) -> None:
        """Handle widget mount."""
        self._load_contacts()
        self._load_aliases()
        self._setup_inputs()
        self._initialize_content()
        self._update_attachment_bar()

        # Set initial focus based on compose mode
        if self.reply_to or self.edit_draft:
            # Replies and draft edits start in editor
            self.query_one("#body-input", ComposeTextArea).focus()
        else:
            # New compose and forward start in To field
            self.query_one("#to-input", AddressInput).focus()

    def _load_contacts(self) -> None:
        """Load contacts from mu."""
        self._contacts = self.bor_app.mu.find_contacts(maxnum=500)

    def _load_aliases(self) -> None:
        """Load email and text aliases."""
        config = get_config()
        self._email_aliases = {**config.email_aliases, **load_mailrc_aliases()}
        self._text_aliases = config.aliases

    def _setup_inputs(self) -> None:
        """Set up input widgets with completion data."""
        for input_id in ["to-input", "cc-input", "bcc-input"]:
            addr_input = self.query_one(f"#{input_id}", AddressInput)
            addr_input.set_contacts(self._contacts)
            addr_input.set_aliases(self._email_aliases)

        body_input = self.query_one("#body-input", ComposeTextArea)
        body_input.set_aliases(self._text_aliases)

    def _initialize_content(self) -> None:
        """Initialize email content based on mode (reply, forward, draft)."""
        config = get_config()

        if self.reply_to:
            self._init_reply()
        elif self.forward:
            self._init_forward()
        elif self.edit_draft:
            self._init_draft()
        else:
            # New message - add signature
            body_input = self.query_one("#body-input", ComposeTextArea)
            if config.identity.signature:
                body_input.text = "\n\n" + config.identity.signature

    def _init_reply(self) -> None:
        """Initialize content for reply."""
        msg = self.reply_to
        if not msg:
            return

        config = get_config()
        
        to_input = self.query_one("#to-input", AddressInput)
        to_addrs = self._reply_to_addresses(msg, config.identity.email)
        
        # If reply all, move original TO/CC recipients to CC (excluding self and duplicates)
        if self.reply_all:
            cc_input = self.query_one("#cc-input", AddressInput)
            cc_list = self._reply_cc_addresses(msg, config.identity.email, to_addrs)

            if cc_list:
                cc_input.value = ", ".join(cc_list)
        
        to_input.value = ", ".join(to_addrs)

        # Set Subject
        subject_input = self.query_one("#subject-input", Input)
        subject = msg.subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        subject_input.value = subject

        # Set body with quote
        body_input = self.query_one("#body-input", ComposeTextArea)

        date_str = msg.date.strftime("%Y-%m-%d %H:%M") if msg.date else ""
        header = f"\n\nOn {date_str}, {msg.from_addr} wrote:\n"

        # Quote original message
        original = msg.body_txt or ""
        quoted = "\n".join(f"> {line}" for line in original.split("\n"))

        body_input.text = header + quoted + "\n\n" + config.identity.signature

    @staticmethod
    def _address_matches(email: str, other_email: str) -> bool:
        """Return True when two email addresses refer to the same mailbox."""
        return bool(email and other_email and email.casefold() == other_email.casefold())

    @classmethod
    def _dedupe_reply_addresses(
        cls,
        addresses: List[EmailAddress],
        identity_email: str,
        seen_emails: Optional[Set[str]] = None,
    ) -> List[str]:
        """Format addresses while excluding self and duplicate email addresses."""
        formatted: List[str] = []
        seen = seen_emails if seen_emails is not None else set()

        for addr in addresses:
            if not addr.email or cls._address_matches(addr.email, identity_email):
                continue

            email_key = addr.email.casefold()
            if email_key in seen:
                continue

            formatted.append(str(addr))
            seen.add(email_key)

        return formatted

    @classmethod
    def _reply_to_addresses(cls, msg: EmailMessage, identity_email: str) -> List[str]:
        """Choose To recipients for a reply."""
        if cls._address_matches(msg.from_addr.email, identity_email):
            sent_to_addrs = cls._dedupe_reply_addresses(list(msg.to_addrs), identity_email)
            if sent_to_addrs:
                return sent_to_addrs

        if msg.list_post_addr and msg.list_post_addr.email:
            # Mailing list: reply to the list address (List-Post header)
            return [str(msg.list_post_addr)]
        if msg.reply_to_addr and msg.reply_to_addr.email:
            return [str(msg.reply_to_addr)]
        if msg.from_addr.email:
            return [str(msg.from_addr)]
        return []

    @classmethod
    def _reply_cc_addresses(
        cls,
        msg: EmailMessage,
        identity_email: str,
        to_addrs: List[str],
    ) -> List[str]:
        """Choose CC recipients for reply-all."""
        seen_emails: Set[str] = set()

        for _, email_addr in email.utils.getaddresses(to_addrs):
            if email_addr:
                seen_emails.add(email_addr.casefold())

        return cls._dedupe_reply_addresses(
            list(msg.to_addrs) + list(msg.cc_addrs),
            identity_email,
            seen_emails,
        )

    def _init_forward(self) -> None:
        """Initialize content for forward."""
        msg = self.forward
        if not msg:
            return

        # Ensure we have the full message content and attachments
        full_msg = self.bor_app.mu.view(msg.path, mark_as_read=False)
        if full_msg:
            msg = full_msg
            self.forward = full_msg

        # Set Subject
        subject_input = self.query_one("#subject-input", Input)
        subject = msg.subject
        if not subject.lower().startswith("fwd:"):
            subject = f"Fwd: {subject}"
        subject_input.value = subject

        # Set body
        body_input = self.query_one("#body-input", ComposeTextArea)
        config = get_config()

        date_str = msg.date.strftime("%Y-%m-%d %H:%M") if msg.date else ""
        to_list = ", ".join(str(addr) for addr in msg.to_addrs)

        header = f"\n\n---------- Forwarded message ----------\n"
        header += f"From: {msg.from_addr}\n"
        header += f"Date: {date_str}\n"
        header += f"Subject: {msg.subject}\n"
        header += f"To: {to_list}\n\n"

        original_txt = msg.body_txt or ""
        original_html = msg.body_html or ""

        if original_txt and original_html:
            body_input.text = (
                header
                + original_txt
                + "\n\n[Forwarded HTML part]\n"
                + original_html
                + "\n\n"
                + config.identity.signature
            )
        elif original_txt:
            body_input.text = header + original_txt + "\n\n" + config.identity.signature
        elif original_html:
            body_input.text = (
                header
                + "[Forwarded HTML part]\n"
                + original_html
                + "\n\n"
                + config.identity.signature
            )
        else:
            body_input.text = header + "\n\n" + config.identity.signature

        # Forward all attachments by extracting them into a temp directory
        if msg.attachments:
            target_dir = Path(tempfile.mkdtemp(prefix="bor-forward-"))
            extracted = self._collect_forward_attachments(
                msg.path,
                msg.attachments,
                target_dir,
                self.bor_app.mu.extract_attachment
            )
            if extracted:
                self.attachments.extend(extracted)

    @staticmethod
    def _collect_forward_attachments(
        message_path: str,
        attachments: List[Dict[str, object]],
        target_dir: Path,
        extract_func: Callable[[str, int, str], Optional[str]]
    ) -> List[Path]:
        """
        Extract attachments for forwarding without overwriting duplicates.

        Args:
            message_path: Path to the source message
            attachments: Attachment metadata list
            target_dir: Directory to place extracted attachments
            extract_func: Function to extract a single attachment

        Returns:
            List of extracted attachment paths in target_dir
        """
        extracted: List[Path] = []
        seen_names: Dict[str, int] = {}

        for index, attachment in enumerate(attachments):
            part_index = attachment.get("part_index") if isinstance(attachment, dict) else None
            if not part_index:
                continue

            staging_dir = target_dir / f"part-{part_index}-{index}"
            staging_dir.mkdir(parents=True, exist_ok=True)

            extracted_path = extract_func(message_path, int(part_index), str(staging_dir))
            if not extracted_path:
                continue

            path = Path(extracted_path)
            original_name = path.name
            current_count = seen_names.get(original_name, 0)
            seen_names[original_name] = current_count + 1

            if current_count:
                new_name = f"{path.stem} ({current_count + 1}){path.suffix}"
            else:
                new_name = original_name

            final_path = target_dir / new_name
            while final_path.exists():
                current_count = seen_names[original_name] + 1
                seen_names[original_name] = current_count
                new_name = f"{path.stem} ({current_count}){path.suffix}"
                final_path = target_dir / new_name

            shutil.move(str(path), str(final_path))
            extracted.append(final_path)

            try:
                staging_dir.rmdir()
            except OSError:
                pass

        return extracted

    def _init_draft(self) -> None:
        """Initialize content from draft."""
        msg = self.edit_draft
        if not msg:
            return

        # Load full message
        full_msg = self.bor_app.mu.view(msg.path, mark_as_read=False)
        if not full_msg:
            return

        # Set To
        to_input = self.query_one("#to-input", AddressInput)
        to_input.value = ", ".join(str(addr) for addr in full_msg.to_addrs)

        # Set CC
        cc_input = self.query_one("#cc-input", AddressInput)
        cc_input.value = ", ".join(str(addr) for addr in full_msg.cc_addrs)

        # Set BCC
        bcc_input = self.query_one("#bcc-input", AddressInput)
        bcc_input.value = ", ".join(str(addr) for addr in full_msg.bcc_addrs)

        # Set Subject
        subject_input = self.query_one("#subject-input", Input)
        subject_input.value = full_msg.subject

        # Set body
        body_input = self.query_one("#body-input", ComposeTextArea)
        body_input.text = full_msg.body_txt or ""

        # Remove the original draft so it doesn't remain in Drafts
        self._delete_original_draft(msg)

    def _update_attachment_bar(self) -> None:
        """Update the attachment bar display."""
        bar = self.query_one("#attachment-bar", Container)
        label = self.query_one("#attachment-label", Label)

        if self.attachments:
            names = [a.name for a in self.attachments]
            label.update(f"📎 Attachments: {', '.join(names)}")
            bar.display = True
        else:
            bar.display = False

    def _refresh_index_after_draft_change(self) -> None:
        """Refresh the message index after draft changes."""
        import asyncio
        from bor.tabs.message_index import MessageIndexWidget
        try:
            index_widget = self.bor_app.query_one(MessageIndexWidget)
        except Exception:
            return

        query = index_widget.current_query
        if not query:
            config = get_config()
            query = f'maildir:"{config.folders.inbox}"'

        asyncio.create_task(index_widget.search(query))

    def _delete_original_draft(self, msg: EmailMessage) -> None:
        """Remove the original draft from Drafts when editing."""
        if self._draft_deleted:
            return

        config = get_config()
        moved = self.bor_app.mu.move(msg.path, config.folders.trash)
        if moved:
            self._draft_deleted = True
            self._refresh_index_after_draft_change()

    def _format_address(self, name: str, email_addr: str) -> str:
        """
        Format an email address with proper encoding for non-ASCII names.
        
        Args:
            name: Display name (may contain non-ASCII characters)
            email_addr: Email address
            
        Returns:
            Properly formatted and encoded address string
        """
        if not name:
            return email_addr
        
        # Check if name contains non-ASCII characters
        try:
            name.encode('ascii')
            # ASCII only - use simple formataddr
            return email.utils.formataddr((name, email_addr))
        except UnicodeEncodeError:
            # Non-ASCII - encode the name using RFC 2047
            encoded_name = Header(name, 'utf-8').encode()
            return f"{encoded_name} <{email_addr}>"

    def _format_address_list(self, addresses: str) -> str:
        """
        Format a list of email addresses with proper encoding.
        
        Args:
            addresses: Comma-separated list of addresses (may be "Name <email>" or just "email")
            
        Returns:
            Properly formatted and encoded address list
        """
        if not addresses:
            return ""
        
        result = []
        # Use email.utils.getaddresses which handles quoted strings and commas properly
        parsed = email.utils.getaddresses([addresses])
        
        for name, email_addr in parsed:
            if email_addr:
                result.append(self._format_address(name, email_addr))
        
        return ", ".join(result)

    @staticmethod
    def _compose_references(reply_to: EmailMessage) -> str:
        """
        Build the References header value when replying to a message.

        Args:
            reply_to: Message being replied to

        Returns:
            Space-separated References header value (may be empty)
        """
        if not reply_to or not reply_to.msgid:
            return ""

        chain: List[str] = []
        seen: Set[str] = set()

        for ref in reply_to.references or []:
            clean_ref = ref.strip()
            if clean_ref and clean_ref not in seen:
                chain.append(clean_ref)
                seen.add(clean_ref)

        parent_msgid = reply_to.msgid.strip()
        if parent_msgid and parent_msgid not in seen:
            chain.append(parent_msgid)

        return " ".join(chain)

    @staticmethod
    def _read_insert_file(path: Path) -> str:
        """Read text content from a file for insertion into the editor."""
        with path.open("r", encoding="utf-8") as handle:
            return handle.read()

    def _build_message(self) -> MIMEMultipart:
        """
        Build the email message for sending.

        Returns:
            MIME message ready for sending
        """
        config = get_config()

        # Create message
        if self.attachments:
            msg = MIMEMultipart("mixed")
        else:
            msg = MIMEMultipart("alternative")

        # Set headers - use formataddr for proper encoding of non-ASCII names
        from bor import __version__
        msg["From"] = self._format_address(config.identity.name, config.identity.email)
        msg["To"] = self._format_address_list(self.query_one("#to-input", AddressInput).value)
        msg["Subject"] = self.query_one("#subject-input", Input).value
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg["Message-ID"] = email.utils.make_msgid()
        msg["User-Agent"] = f"Bor/{__version__}"

        cc = self.query_one("#cc-input", AddressInput).value
        if cc:
            msg["CC"] = self._format_address_list(cc)

        bcc = self.query_one("#bcc-input", AddressInput).value
        if bcc:
            msg["BCC"] = self._format_address_list(bcc)

        # Reply headers
        if self.reply_to and self.reply_to.msgid:
            parent_msgid = self.reply_to.msgid.strip()
            msg["In-Reply-To"] = parent_msgid

            references = self._compose_references(self.reply_to)
            if references:
                msg["References"] = references

        # Add body
        body = self.query_one("#body-input", ComposeTextArea).text
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Add attachments
        for attachment_path in self.attachments:
            try:
                with open(attachment_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f"attachment; filename={attachment_path.name}"
                    )
                    msg.attach(part)
            except Exception:
                pass

        return msg

    def _send_message(self) -> bool:
        """
        Send the composed message via SMTP.

        Returns:
            True if successful
        """
        config = get_config()

        try:
            msg = self._build_message()

            # Connect to SMTP server
            if config.smtp.use_starttls:
                server = smtplib.SMTP(config.smtp.server, config.smtp.port)
                server.starttls()
            elif config.smtp.use_tls:
                server = smtplib.SMTP_SSL(config.smtp.server, config.smtp.port)
            else:
                server = smtplib.SMTP(config.smtp.server, config.smtp.port)

            # Login if credentials provided
            if config.smtp.username:
                password = config.smtp.password
                if not password:
                    # Try to get from keyring
                    try:
                        import keyring
                        password = keyring.get_password("bor-email", config.smtp.username)
                    except Exception:
                        pass

                if password:
                    server.login(config.smtp.username, password)

            # Send - extract email addresses properly using email.utils.getaddresses
            # This correctly handles quoted display names with commas
            to_addrs = []
            if msg["To"]:
                to_addrs.extend([email for name, email in email.utils.getaddresses([msg["To"]])])
            if msg["CC"]:
                to_addrs.extend([email for name, email in email.utils.getaddresses([msg["CC"]])])
            if msg["BCC"]:
                to_addrs.extend([email for name, email in email.utils.getaddresses([msg["BCC"]])])

            to_addrs = [addr for addr in to_addrs if addr]

            server.sendmail(config.identity.email, to_addrs, msg.as_string())
            server.quit()

            # Copy to sent folder
            self._save_to_folder(config.folders.sent, msg)

            return True

        except Exception as e:
            self.notify(f"Error sending message: {e}", severity="error")
            return False

    def _save_draft(self) -> bool:
        """
        Save the message as a draft.

        Returns:
            True if successful
        """
        config = get_config()
        return self._save_to_folder(config.folders.drafts)

    def _save_to_folder(self, folder: str, msg: Optional[MIMEMultipart] = None) -> bool:
        """
        Save the message to a maildir folder.

        Args:
            folder: Target maildir folder
            msg: Message to save (builds new if None)

        Returns:
            True if successful
        """
        config = get_config()

        if msg is None:
            msg = self._build_message()

        root = self.bor_app.mu.get_root_maildir()
        target_dir = Path(root) / folder.lstrip("/") / "cur"
        target_dir.mkdir(parents=True, exist_ok=True)

        # Generate maildir-style filename
        timestamp = int(datetime.now().timestamp())
        hostname = os.uname().nodename
        filename = f"{timestamp}.{os.getpid()}.{hostname}:2,S"

        target_path = target_dir / filename

        try:
            with open(target_path, "w") as f:
                f.write(msg.as_string())
            return True
        except Exception as e:
            self.notify(f"Error saving: {e}", severity="error")
            return False

    # Event handlers for Ctrl+L commands (from any input)

    def on_send_message(self, event: SendMessage) -> None:
        """Handle send message command."""
        if self._send_message():
            # Mark original message as replied/forwarded
            if self.reply_to:
                self.bor_app.mu.mark_replied(self.reply_to.path)
            elif self.forward:
                self.bor_app.mu.mark_forwarded(self.forward.path)
            self.notify("Message sent!")
            self.close_tab()

    def on_save_draft(self, event: SaveDraft) -> None:
        """Handle save draft command."""
        if self._save_draft():
            self.bor_app.mu.index()
            self._refresh_index_after_draft_change()
            self.notify("Draft saved!")
            self.close_tab()

    def on_cancel_compose(self, event: CancelCompose) -> None:
        """Handle cancel compose command."""
        # TODO: Add confirmation dialog
        self.close_tab()

    def on_focus_to(self, event: FocusTo) -> None:
        """Handle focus To field command."""
        self.query_one("#to-input").focus()

    def on_focus_cc(self, event: FocusCC) -> None:
        """Handle focus CC field command."""
        self.query_one("#cc-input").focus()

    def on_focus_bcc(self, event: FocusBCC) -> None:
        """Handle focus BCC field command."""
        self.query_one("#bcc-input").focus()

    def on_focus_subject(self, event: FocusSubject) -> None:
        """Handle focus Subject field command."""
        self.query_one("#subject-input").focus()

    def on_focus_editor(self, event: FocusEditor) -> None:
        """Handle focus Editor/body field command."""
        self.query_one("#body-input").focus()

    def on_attach_file(self, event: AttachFile) -> None:
        """Handle attach file command (Ctrl-L A)."""
        self.action_attach_file()

    def on_attach_files_from_directory(self, event: AttachFilesFromDirectory) -> None:
        """Handle bulk attach command (Ctrl-L Z)."""
        self.action_attach_files_from_directory()

    def on_file_path_input_submitted(self, event: FilePathInput.Submitted) -> None:
        """Handle file path submitted for attachment or insertion."""
        path = Path(event.path).expanduser()
        mode = self._file_path_mode or "attach"
        
        # Hide the input bar
        self.query_one("#attachment-input-bar", Vertical).add_class("hidden")
        
        if mode == "bulk_attach_dir":
            if not path.exists():
                self.notify(f"Directory not found: {path}", severity="error")
                self.query_one("#body-input").focus()
                return

            if not path.is_dir():
                self.notify(f"Not a directory: {path}", severity="error")
                self.query_one("#body-input").focus()
                return

            self._last_attachment_dir = path
            self._show_bulk_attachment_picker(path)
            return

        # Validate the file
        if not path.exists():
            self.notify(f"File not found: {path}", severity="error")
            self.query_one("#body-input").focus()
            return

        if not path.is_file():
            self.notify(f"Not a file: {path}", severity="error")
            self.query_one("#body-input").focus()
            return

        body_input = self.query_one("#body-input", ComposeTextArea)

        if mode == "insert":
            try:
                content = self._read_insert_file(path)
            except UnicodeDecodeError:
                self.notify(f"File is not valid UTF-8 text: {path.name}", severity="error")
                body_input.focus()
                return
            except OSError as error:
                self.notify(f"Error reading file: {error}", severity="error")
                body_input.focus()
                return

            body_input.focus()
            body_input.insert(content)
            self.notify(f"Inserted: {path.name}")
        else:
            if path not in self.attachments:
                self.attachments.append(path)
                self._update_attachment_bar()
                self.notify(f"Attached: {path.name}")
            else:
                self.notify(f"Already attached: {path.name}", severity="warning")
        
        # Remember the directory for next time
        self._last_attachment_dir = path.parent
        self._file_path_mode = None
        
        # Return focus to body
        body_input.focus()

    def on_file_path_input_cancelled(self, event: FilePathInput.Cancelled) -> None:
        """Handle file path input cancelled."""
        # Hide the input bar
        self.query_one("#attachment-input-bar", Vertical).add_class("hidden")
        self._file_path_mode = None
        
        # Return focus to body
        self.query_one("#body-input").focus()

    def on_bulk_attachment_list_toggled(self, event: BulkAttachmentList.Toggled) -> None:
        """Update picker instructions after a file is toggled."""
        self._update_bulk_picker_title()

    def on_bulk_attachment_list_cancelled(self, event: BulkAttachmentList.Cancelled) -> None:
        """Close the bulk picker without attaching files."""
        self._hide_bulk_attachment_picker()
        self.query_one("#body-input", ComposeTextArea).focus()

    def on_bulk_attachment_list_select_all_toggled(
        self, event: BulkAttachmentList.SelectAllToggled
    ) -> None:
        """Toggle all files in the picker."""
        list_view = self.query_one("#bulk-attachment-list", BulkAttachmentList)
        items = [
            item for item in list_view.children if isinstance(item, BulkAttachmentItem)
        ]
        should_select = any(not item.selected for item in items)
        for item in items:
            item.set_selected(should_select)
        self._update_bulk_picker_title()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle confirming the bulk attachment picker."""
        if not isinstance(event.list_view, BulkAttachmentList):
            return

        selected_paths = self._get_selected_bulk_attachment_paths()
        if not selected_paths:
            self.notify("No files selected", severity="warning")
            return

        added = []
        duplicates = []
        for path in selected_paths:
            if path in self.attachments:
                duplicates.append(path.name)
                continue
            self.attachments.append(path)
            added.append(path.name)

        self._update_attachment_bar()
        self._last_attachment_dir = self._bulk_picker_directory or self._last_attachment_dir
        self._hide_bulk_attachment_picker()
        self.query_one("#body-input", ComposeTextArea).focus()

        if added:
            self.notify(f"Attached {len(added)} file(s)")
        elif duplicates:
            self.notify("Selected files were already attached", severity="warning")

        if duplicates and added:
            self.notify(
                f"Skipped {len(duplicates)} already attached file(s)",
                severity="warning",
            )

    def on_file_path_input_completions_changed(self, event: FilePathInput.CompletionsChanged) -> None:
        """Handle completions list change."""
        label = self.query_one("#attachment-completions", Label)
        
        if not event.completions:
            label.update("")
            return
        
        # Format completions, highlighting the current one
        parts = []
        for i, comp in enumerate(event.completions):
            # Show just the filename part
            name = Path(comp).name
            if comp.endswith("/"):
                name += "/"
            if i == event.current_index:
                parts.append(f"[bold reverse]{name}[/bold reverse]")
            else:
                parts.append(name)
        
        label.update(" | ".join(parts))

    # Actions

    def action_search(self) -> None:
        """Search in message index."""
        self.switch_to_index()

    def action_insert_file(self) -> None:
        """Insert file contents into body."""
        self._show_file_path_input(mode="insert", label="Insert file: ")

    def action_attach_file(self) -> None:
        """Attach a file."""
        self._show_file_path_input(mode="attach", label="Attach file: ")

    def action_attach_files_from_directory(self) -> None:
        """Attach multiple files from a selected directory."""
        self._show_file_path_input(mode="bulk_attach_dir", label="Attach files from directory: ")

    def _show_file_path_input(self, mode: str, label: str) -> None:
        """Show the path input UI used for attach/insert actions."""
        self._file_path_mode = mode
        self._hide_bulk_attachment_picker()

        # Show the attachment input bar
        self.query_one("#attachment-input-bar", Vertical).remove_class("hidden")
        self.query_one("#file-path-input-label", Label).update(label)
        
        # Clear completions display initially
        self.query_one("#attachment-completions", Label).update("")
        
        # Set start path to last used directory and focus
        path_input = self.query_one("#attachment-path-input", FilePathInput)
        path_input.value = str(self._last_attachment_dir) + "/"
        path_input.cursor_position = len(path_input.value)
        path_input.focus()

    @staticmethod
    def _list_bulk_attachable_files(directory: Path) -> List[Path]:
        """Return the direct child files in a directory, sorted by name."""
        files: List[Path] = []
        try:
            for entry in sorted(directory.iterdir(), key=lambda path: path.name.lower()):
                if entry.is_file():
                    files.append(entry)
        except PermissionError:
            return []
        return files

    def _show_bulk_attachment_picker(self, directory: Path) -> None:
        """Populate and show the bulk attachment picker for a directory."""
        files = self._list_bulk_attachable_files(directory)
        if not files:
            self.notify(f"No files found in {directory}", severity="warning")
            self._file_path_mode = None
            self.query_one("#body-input", ComposeTextArea).focus()
            return

        self._bulk_picker_directory = directory
        self._file_path_mode = None

        picker = self.query_one("#bulk-attachment-picker", Vertical)
        list_view = self.query_one("#bulk-attachment-list", BulkAttachmentList)
        list_view.clear()
        for path in files:
            list_view.append(BulkAttachmentItem(path))

        picker.remove_class("hidden")
        self._update_bulk_picker_title()
        list_view.index = 0
        list_view.focus()

    def _hide_bulk_attachment_picker(self) -> None:
        """Hide the bulk attachment picker."""
        self.query_one("#bulk-attachment-picker", Vertical).add_class("hidden")
        self._bulk_picker_directory = None

    def _get_selected_bulk_attachment_paths(self) -> List[Path]:
        """Return the currently selected paths in the bulk picker."""
        list_view = self.query_one("#bulk-attachment-list", BulkAttachmentList)
        return [
            item.path
            for item in list_view.children
            if isinstance(item, BulkAttachmentItem) and item.selected
        ]

    def _update_bulk_picker_title(self) -> None:
        """Refresh the picker title and key hints."""
        title = self.query_one("#bulk-attachment-picker-title", Label)
        count = len(self._get_selected_bulk_attachment_paths())
        directory = self._bulk_picker_directory or self._last_attachment_dir
        title.update(
            "Select files from "
            f"{directory} | Space=toggle Enter=attach Esc=cancel Ctrl+A=toggle all | "
            f"{count} selected"
        )
