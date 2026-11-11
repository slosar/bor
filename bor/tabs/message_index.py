"""
Message Index tab for Bor email reader.

Displays a list of email messages with navigation and actions.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import DataTable, Input, Label, Static

from bor.config import get_config
from bor.editing import kill_input_to_end
from bor.mu import EmailMessage
from bor.tabs.base import BaseTab

if TYPE_CHECKING:
    from bor.mu import MuInterface


_HISTORY_FILE = Path.home() / ".local" / "share" / "bor" / "search_history"
_MAX_HISTORY = 200


class SearchInput(Input):
    """Input widget for search with Up/Down history navigation."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialize search input."""
        super().__init__(*args, placeholder="Search...", **kwargs)
        self._history: list[str] = []
        self._history_pos: int = -1  # -1 = not browsing; ≥0 = index into _history
        self._saved_value: str = ""  # typed value saved when history browsing starts
        self._load_history()

    # ------------------------------------------------------------------
    # History persistence

    def _load_history(self) -> None:
        """Load search history from disk."""
        try:
            if _HISTORY_FILE.exists():
                lines = _HISTORY_FILE.read_text(encoding="utf-8").splitlines()
                self._history = [line for line in lines if line.strip()]
        except Exception:
            pass

    def _save_to_history(self, query: str) -> None:
        """Append a query to history (deduplicating) and persist to disk."""
        query = query.strip()
        if not query:
            return
        try:
            self._history.remove(query)
        except ValueError:
            pass
        self._history.append(query)
        if len(self._history) > _MAX_HISTORY:
            self._history = self._history[-_MAX_HISTORY:]
        self._history_pos = -1
        try:
            _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            _HISTORY_FILE.write_text("\n".join(self._history), encoding="utf-8")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public API

    def reset_for_new_search(self) -> None:
        """Clear the input and reset history browsing position."""
        self.value = ""
        self._history_pos = -1
        self._saved_value = ""

    # ------------------------------------------------------------------
    # Key handling

    def on_key(self, event: events.Key) -> None:
        """Handle key events."""
        if event.key == "escape":
            search_bar = self.parent
            search_bar.remove_class("visible")
            self.display = False
            self._history_pos = -1
            try:
                self.screen.query_one(DataTable).focus()
            except Exception:
                pass
            event.prevent_default()
            event.stop()

        elif event.key == "ctrl+k":
            kill_input_to_end(self)
            event.prevent_default()
            event.stop()

        elif event.key == "up":
            if self._history:
                if self._history_pos == -1:
                    # Begin browsing: save whatever the user had typed
                    self._saved_value = self.value
                    self._history_pos = len(self._history) - 1
                elif self._history_pos > 0:
                    self._history_pos -= 1
                # at oldest entry (pos == 0) further Up is a no-op
                self.value = self._history[self._history_pos]
                self.cursor_position = len(self.value)
            event.prevent_default()
            event.stop()

        elif event.key == "down":
            if self._history_pos != -1:
                if self._history_pos < len(self._history) - 1:
                    self._history_pos += 1
                    self.value = self._history[self._history_pos]
                else:
                    # Past the newest entry: restore the originally typed value
                    self._history_pos = -1
                    self.value = self._saved_value
                self.cursor_position = len(self.value)
            event.prevent_default()
            event.stop()

        elif event.key == "enter":
            self._save_to_history(self.value)
            self.post_message(SearchInput.Submitted(self.value))
            event.prevent_default()
            event.stop()

    class Submitted(Message):
        """Search submitted message."""

        def __init__(self, query: str) -> None:
            """Initialize with query."""
            self.query = query
            super().__init__()


class PromptBar(Static):
    """Base for the one-line prompts docked at the bottom of a tab.

    Showing a prompt takes focus; answering or dismissing it hands focus back
    to whatever had it before, falling back to the message table.
    """

    can_focus = True

    def __init__(self, *args, **kwargs) -> None:
        """Initialize the prompt bar."""
        super().__init__(*args, **kwargs)
        self._previous_focus: Widget | None = None

    def _open(self, text: str) -> None:
        """Show the prompt and take focus."""
        self._previous_focus = self.app.focused
        self.update(text)
        self.add_class("visible")
        self.focus()

    def _close(self) -> None:
        """Hide the prompt and return focus."""
        self.remove_class("visible")
        self._restore_focus()

    def _restore_focus(self) -> None:
        """Return focus to the widget that opened the prompt."""
        try:
            if self._previous_focus is not None and self._previous_focus is not self:
                self._previous_focus.focus()
                return
        except Exception:
            pass

        try:
            self.screen.query_one(DataTable).focus()
        except Exception:
            pass


class ConfirmBar(PromptBar):
    """Confirmation bar widget for y/n prompts."""

    DEFAULT_CSS = """
    ConfirmBar {
        display: none;
        dock: bottom;
        height: 1;
        background: yellow;
        color: black;
        text-style: bold;
        padding: 0 1;
        layer: confirm;
    }
    ConfirmBar.visible {
        display: block;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initialize confirmation bar."""
        super().__init__(*args, **kwargs)
        self._callback: Callable | None = None

    def ask(self, prompt: str, callback: Callable) -> None:
        """Show confirmation prompt."""
        self._callback = callback
        self._open(f"{prompt} (y/n)")

    def on_key(self, event: events.Key) -> None:
        """Handle key events."""
        if event.key in ("y", "Y"):
            self._close()
            if self._callback:
                self._callback()
            event.prevent_default()
            event.stop()
        elif event.key in ("n", "N", "escape"):
            self._close()
            event.prevent_default()
            event.stop()


class ReplyBar(PromptBar):
    """Reply options bar widget for (a)ll or (s)ender only choices."""

    DEFAULT_CSS = """
    ReplyBar {
        display: none;
        dock: bottom;
        height: 1;
        background: $secondary;
        color: $text;
        text-style: bold;
        padding: 0 1;
        layer: confirm;
    }
    ReplyBar.visible {
        display: block;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initialize reply bar."""
        super().__init__(*args, **kwargs)
        self._callback: Callable | None = None
        self._cancel_callback: Callable[[], None] | None = None

    def ask(self, callback: Callable, cancel_callback: Callable[[], None] | None = None) -> None:
        """Show reply options prompt."""
        self._callback = callback
        self._cancel_callback = cancel_callback
        self._open("Reply to: (a)ll or (s)ender only?")

    def on_key(self, event: events.Key) -> None:
        """Handle key events."""
        key = event.key.lower() if event.key else ""

        if key in ("a", "s"):
            self._close()
            if self._callback:
                self._callback(key == "a")  # True for reply all, False for sender only
            self._callback = None
            self._cancel_callback = None
        elif key == "escape":
            self._close()
            if self._cancel_callback:
                self._cancel_callback()
            self._callback = None
            self._cancel_callback = None

        event.prevent_default()
        event.stop()


class FlagBar(PromptBar):
    """Flag selection bar widget for applying flags to messages."""

    DEFAULT_CSS = """
    FlagBar {
        display: none;
        dock: bottom;
        height: 1;
        background: $primary;
        color: $text;
        text-style: bold;
        padding: 0 1;
        layer: confirm;
    }
    FlagBar.visible {
        display: block;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initialize flag bar."""
        super().__init__(*args, **kwargs)
        self._callback: Callable | None = None

    def ask(self, callback: Callable) -> None:
        """Show flag selection prompt."""
        self._callback = callback
        self._open(
            "Apply flag: (U)nread, (N)ew, (F)lagged | Shift+key to remove flag | (Esc) Cancel"
        )

    def on_key(self, event: events.Key) -> None:
        """Handle key events."""
        key = event.key.lower() if event.key else ""
        char = event.character or ""

        # Check for shift+key (uppercase) to remove flag
        if char in ("U", "N", "F"):
            self._close()
            if self._callback:
                # Pass uppercase to indicate removal
                self._callback(char)
        elif key in ("u", "n", "f"):
            self._close()
            if self._callback:
                self._callback(key)
        elif key == "escape":
            self._close()

        event.prevent_default()
        event.stop()


class MessageTable(DataTable):
    """The message list table, where Home/End go to the first/last message.

    DataTable binds Home/End to horizontal scrolling. As the focused widget
    its bindings win, so the index's own Home/End bindings never ran.
    """

    def action_scroll_home(self) -> None:
        """Move the cursor to the first message."""
        self.action_scroll_top()

    def action_scroll_end(self) -> None:
        """Move the cursor to the last message."""
        self.action_scroll_bottom()


def apply_flag(mu: MuInterface, path: str, flags: list[str], flag_key: str) -> None:
    """Apply a FlagBar choice to a message file and its in-memory flag list.

    Lowercase u/n/f adds unread/new/flagged; uppercase removes it. `path` is
    the maildir file to rename; `flags` is updated in place so the index row
    can be redrawn without a new mu query.
    """
    is_remove = flag_key.isupper()
    flag_lower = flag_key.lower()

    if flag_lower == "u":
        if is_remove:
            # Mark as read (remove unread)
            mu.mark_read(path)
            if "unread" in flags:
                flags.remove("unread")
            if "seen" not in flags:
                flags.append("seen")
        else:
            # Mark as unread
            mu.mark_unread(path)
            if "unread" not in flags:
                flags.append("unread")
            if "seen" in flags:
                flags.remove("seen")
    elif flag_lower == "n":
        if is_remove:
            # Remove new flag
            mu.mark_read(path)
            if "new" in flags:
                flags.remove("new")
        else:
            # Mark as new
            mu.mark_unread(path)
            if "new" not in flags:
                flags.append("new")
            if "unread" not in flags:
                flags.append("unread")
    elif flag_lower == "f":
        if is_remove:
            # Remove flagged
            mu.mark_flagged(path, False)
            if "flagged" in flags:
                flags.remove("flagged")
        else:
            # Mark as flagged/important
            mu.mark_flagged(path, True)
            if "flagged" not in flags:
                flags.append("flagged")


class MessageIndexWidget(BaseTab):
    """
    Message Index widget.

    Displays a list of email messages and handles navigation and actions.
    """

    BINDINGS = [
        # Navigation
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("n", "cursor_down", "Next", show=False),
        Binding("p", "cursor_up", "Previous", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
        Binding("space", "page_down", "Page Down", show=False),
        Binding("home", "scroll_home", "Top", show=False),
        Binding("end", "scroll_end", "Bottom", show=False),
        # Actions
        Binding("enter", "open_message", "Open"),
        Binding("r", "reply", "Reply"),
        Binding("f", "forward", "Forward"),
        Binding("c", "compose", "Compose"),
        # Binding("ctrl+f", "incremental_search", "Search"),  ## implement when we have a better idea what exactly
        Binding("s", "mu_search", "Mu Search"),
        Binding("i", "show_inbox", "Inbox"),
        Binding("o", "show_archive", "Archive"),
        Binding("u", "show_drafts", "Drafts"),
        Binding("l", "sync", "Sync"),
        Binding("q", "open_llm", "Ask LLM"),
        Binding("m", "mark_message", "Mark"),
        Binding("x", "archive", "Archive Msg"),
        Binding("a", "apply_flag", "Apply Flag"),
        Binding("z", "undo", "Undo"),
        Binding("t", "toggle_threading", "Threading"),
        Binding("ctrl+t", "show_thread", "Show Thread"),
        Binding("d", "delete", "Delete"),
        Binding("e", "edit_draft", "Edit Draft"),
        Binding("ctrl+r", "refresh", "Refresh"),
    ]

    DEFAULT_CSS = """
    MessageIndexWidget {
        height: 1fr;
    }

    MessageIndexWidget DataTable {
        height: 1fr;
    }

    MessageIndexWidget .status-bar {
        height: 1;
        dock: bottom;
        background: $surface;
        padding: 0 1;
    }

    MessageIndexWidget .search-bar {
        height: 3;
        dock: top;
        display: none;
        background: $surface;
        padding: 0 1;
    }

    MessageIndexWidget .search-bar.visible {
        display: block;
    }

    MessageIndexWidget .search-bar Input {
        width: 100%;
        background: $background;
        color: $text;
        border: solid $primary;
    }

    MessageIndexWidget DataTable > .datatable--cursor {
        background: $primary;
    }

    MessageIndexWidget .unread {
        color: $primary;
        text-style: bold;
    }

    MessageIndexWidget .flagged {
        color: $warning;
    }

    MessageIndexWidget .confirm-bar {
        height: 1;
        dock: bottom;
        background: $warning;
        color: $background;
        padding: 0 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initialize the message index widget."""
        super().__init__(*args, **kwargs)
        self.messages: list[EmailMessage] = []
        self.marked_messages: set[int] = set()
        self.current_query: str = ""
        # Message whose thread is shown (Ctrl+T); None when showing current_query
        self._thread_anchor: EmailMessage | None = None
        self.threading_enabled: bool = get_config().threading.enabled
        self._search_visible: bool = False
        self._pending_action: Callable | None = None

    def compose(self) -> ComposeResult:
        """Create the widget layout."""
        with Vertical():
            with Container(classes="search-bar", id="search-bar"):
                yield SearchInput(id="search-input")
            yield MessageTable(id="message-table", cursor_type="row")
            yield ConfirmBar("", classes="confirm-bar", id="confirm-bar")
            yield FlagBar("", id="flag-bar")
            yield ReplyBar("", id="reply-bar")
            with Horizontal(classes="status-bar"):
                yield Label("", id="status-label")

    def on_mount(self) -> None:
        """Handle widget mount."""
        table = self.query_one(DataTable)

        # Add columns
        config = get_config()
        table.add_column("", key="flags", width=config.display.flags_width)
        table.add_column("Date", key="date", width=config.display.date_width)
        table.add_column("From", key="from", width=config.display.from_width)
        table.add_column("Subject", key="subject")

        table.cursor_type = "row"
        table.zebra_stripes = True

    async def search(self, query: str, threads: bool | None = None) -> None:
        """
        Search for messages and display results.

        Args:
            query: Mu search query
            threads: Whether to use threading (None uses current setting)
        """
        config = get_config()
        use_threads = threads if threads is not None else self.threading_enabled

        self.current_query = query
        self._thread_anchor = None
        # `mu find` spawns a subprocess and takes ~40ms on a large index, which
        # is long enough to be felt as a stall if it runs on the event loop.
        self.messages = await asyncio.to_thread(
            self._find_messages, query, use_threads, config.general.max_messages
        )

        # Update app's message list
        self.bor_app._current_messages = self.messages
        self.bor_app._current_index = 0

        # Clear marked messages
        self.marked_messages.clear()

        # Refresh the table
        await self._refresh_table()

        # Update status
        self._update_status()

    def _find_messages(self, query: str, use_threads: bool, maxnum: int) -> list[EmailMessage]:
        """Run a mu query. Runs on a worker thread.

        Waits for any queued reindexing first, so a search issued right after
        an archive/delete/flag change sees the updated database.
        """
        mu = self.bor_app.mu
        mu.wait_for_reindex()
        return mu.find(query, maxnum=maxnum, threads=use_threads, descending=True)

    async def _refresh_table(self) -> None:
        """Refresh the message table with current messages."""
        table = self.query_one(DataTable)
        table.clear()

        config = get_config()

        # Compute thread tree structure for proper visualization
        thread_prefixes = self._compute_thread_prefixes(self.messages)

        for idx, msg in enumerate(self.messages):
            cells = self._row_cells(idx, msg, config, thread_prefixes)
            table.add_row(*cells, key=str(idx))

    def _row_cells(
        self, idx: int, msg: EmailMessage, config, thread_prefixes: dict
    ) -> tuple[Text, Text, Text, Text]:
        """Build the flags, date, from and subject cells for one message row.

        Every cell is a Text: DataTable parses plain-string cells as markup,
        which hid subjects such as "[mu-discuss] ..." and crashed on "[/x]".
        """
        date_str = self._format_date(msg.date, config)

        from_str = msg.from_addr.name or msg.from_addr.email
        if len(from_str) > config.display.from_width:
            from_str = from_str[: config.display.from_width - 1] + "…"

        # Subject with threading tree prefix
        subject = msg.subject
        if thread_prefixes.get(idx):
            subject = f"{thread_prefixes[idx]} {subject}"

        style = ""
        if msg.is_flagged:
            style = f"bold {config.colors.important}"
        elif msg.is_unread:
            style = f"bold {config.colors.unread}"

        flags_text = self._flags_text(
            msg, config, marked=idx in self.marked_messages, base_style=style
        )
        return (
            flags_text,
            Text(date_str, style=style),
            Text(from_str, style=style),
            Text(subject, style=style),
        )

    def _compute_thread_prefixes(self, messages: list[EmailMessage]) -> dict:
        """
        Compute tree prefixes for thread visualization.

        Returns a dict mapping message index to its tree prefix string,
        e.g., "│ └" or "├" like mu4e displays.
        """
        if not messages:
            return {}

        prefixes = {}
        n = len(messages)

        for idx, msg in enumerate(messages):
            level = msg.thread_level
            if level == 0:
                prefixes[idx] = ""
                continue

            # Build the prefix by looking at each level
            prefix_parts = []

            for lvl in range(1, level + 1):
                if lvl == level:
                    # This is the connector for this message
                    # Check if there's a sibling after this at the same or higher level
                    is_last = True
                    for future_idx in range(idx + 1, n):
                        future_level = messages[future_idx].thread_level
                        if future_level < lvl:
                            # We've gone up in the tree, so this is last at this level
                            break
                        if future_level == lvl:
                            # There's a sibling after us
                            is_last = False
                            break

                    prefix_parts.append("└" if is_last else "├")
                else:
                    # This is a vertical connector from an ancestor level
                    # Check if there are more siblings at this level after us
                    has_continuation = False
                    for future_idx in range(idx + 1, n):
                        future_level = messages[future_idx].thread_level
                        if future_level < lvl:
                            # We've gone up past this level
                            break
                        if future_level == lvl:
                            # There's still something at this level
                            has_continuation = True
                            break
                        # If future_level > lvl, it's a deeper nesting, keep looking
                        if future_level >= lvl:
                            has_continuation = True

                    prefix_parts.append("│" if has_continuation else " ")

            prefixes[idx] = "".join(prefix_parts)

        return prefixes

    def _format_flags(self, msg: EmailMessage, config) -> str:
        """Format the flags column for a message."""
        flags = []

        if msg.is_unread:
            flags.append(config.display.flag_unread)
        if msg.is_replied:
            flags.append(config.display.flag_replied)
        if msg.is_forwarded:
            flags.append(config.display.flag_forwarded)
        if msg.is_flagged:
            flags.append(config.display.flag_flagged)
        if msg.has_attachments:
            flags.append(config.display.flag_attachment)

        return "".join(flags)

    def _flags_text(self, msg: EmailMessage, config, marked: bool, base_style: str) -> Text:
        """Build the flags column cell; the marked symbol is shown in red."""
        text = Text()
        if marked:
            text.append(config.display.flag_marked, style="red")
        flags = self._format_flags(msg, config)
        if flags:
            text.append(flags, style=base_style or None)
        return text

    def _format_date(self, date: datetime | None, config) -> str:
        """Format date for display."""
        if date is None:
            return ""

        now = datetime.now()

        # Use time format for today's messages
        if date.date() == now.date():
            return date.strftime(config.general.time_format)

        # Use short format for this year
        if date.year == now.year:
            return date.strftime(config.general.short_date_format)

        # Use full format for older messages
        return date.strftime(config.general.date_format)

    def _update_status(self) -> None:
        """Update the status bar."""
        label = self.query_one("#status-label", Label)
        if self._thread_anchor is not None:
            threading_status = "thread view"
        else:
            threading_status = "threaded" if self.threading_enabled else "flat"
        marked_count = len(self.marked_messages)
        marked_str = f" | {marked_count} marked" if marked_count > 0 else ""
        label.update(f"{len(self.messages)} messages ({threading_status}){marked_str}")

    def _get_current_message(self) -> EmailMessage | None:
        """Get the currently selected message."""
        table = self.query_one(DataTable)
        if table.cursor_row is not None and 0 <= table.cursor_row < len(self.messages):
            return self.messages[table.cursor_row]
        return None

    def _get_current_index(self) -> int:
        """Get the current cursor row index."""
        table = self.query_one(DataTable)
        return table.cursor_row if table.cursor_row is not None else 0

    # Actions

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        table = self.query_one(DataTable)
        table.action_cursor_up()
        self.bor_app._current_index = self._get_current_index()

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        table = self.query_one(DataTable)
        table.action_cursor_down()
        self.bor_app._current_index = self._get_current_index()

    def action_page_up(self) -> None:
        """Page up."""
        table = self.query_one(DataTable)
        table.action_page_up()
        self.bor_app._current_index = self._get_current_index()

    def action_page_down(self) -> None:
        """Page down."""
        table = self.query_one(DataTable)
        table.action_page_down()
        self.bor_app._current_index = self._get_current_index()

    def action_scroll_home(self) -> None:
        """Scroll to top."""
        table = self.query_one(DataTable)
        table.action_scroll_home()
        self.bor_app._current_index = 0

    def action_scroll_end(self) -> None:
        """Scroll to bottom."""
        table = self.query_one(DataTable)
        table.action_scroll_end()
        self.bor_app._current_index = len(self.messages) - 1

    def action_open_message(self) -> None:
        """Open the selected message."""
        msg = self._get_current_message()
        if msg:
            # Update current index before opening so message view tracks it correctly
            self.bor_app._current_index = self._get_current_index()
            self.bor_app.open_message(msg)

    async def action_reply(self) -> None:
        """Reply to the selected message."""
        msg = self._get_current_message()
        if msg:
            # Check if there are multiple recipients - need full message for CC
            # info. Parsing it (and marking it read) is too slow for the UI thread.
            full_msg = await asyncio.to_thread(self.bor_app.mu.view, msg.path)
            # Show reply options if there are CC recipients or multiple TO recipients
            if full_msg and (full_msg.cc_addrs or len(full_msg.to_addrs) > 1):
                reply_bar = self.query_one("#reply-bar", ReplyBar)
                self._pending_reply_msg = full_msg
                reply_bar.ask(self._do_reply, self._cancel_reply)
            else:
                self.bor_app.open_compose(reply_to=full_msg or msg)

    def _do_reply(self, reply_all: bool = False) -> None:
        """Actually open the reply compose."""
        msg = getattr(self, "_pending_reply_msg", None)
        if msg:
            self.bor_app.open_compose(reply_to=msg, reply_all=reply_all)
            self._pending_reply_msg = None

    def _cancel_reply(self) -> None:
        """Clear any pending reply state after dismissing the reply prompt."""
        self._pending_reply_msg = None

    def action_forward(self) -> None:
        """Forward the selected message."""
        msg = self._get_current_message()
        if msg:
            # The compose tab loads the full message (body, attachments) itself
            self.bor_app.open_compose(forward=msg)

    def action_compose(self) -> None:
        """Compose a new message."""
        self.bor_app.open_compose()

    def action_incremental_search(self) -> None:
        """Show incremental search input."""
        # this should not be called
        raise NotImplementedError("Incremental search not implemented yet")

    async def on_search_input_submitted(self, event: SearchInput.Submitted) -> None:
        """Handle search submission."""
        search_bar = self.query_one("#search-bar")
        search_bar.remove_class("visible")
        search_input = self.query_one("#search-input", SearchInput)
        search_input.display = False

        if event.query:
            # Filter current messages or do new search
            await self.search(event.query)

        self.query_one(DataTable).focus()

    def action_mu_search(self) -> None:
        """Open mu search dialog."""
        search_bar = self.query_one("#search-bar")
        search_bar.add_class("visible")
        search_input = self.query_one("#search-input", SearchInput)
        search_input.display = True
        search_input.reset_for_new_search()
        search_input.focus()

    async def action_show_inbox(self) -> None:
        """Show inbox folder."""
        config = get_config()
        await self.search(f'maildir:"{config.folders.inbox}"')

    async def action_show_archive(self) -> None:
        """Show archive folder."""
        config = get_config()
        await self.search(f'maildir:"{config.folders.archive}"')

    async def action_show_drafts(self) -> None:
        """Show drafts folder."""
        config = get_config()
        await self.search(f'maildir:"{config.folders.drafts}"')

    def action_sync(self) -> None:
        """Run synchronization."""
        self.bor_app.open_sync()

    def action_open_llm(self) -> None:
        """Switch to the LLM tab."""
        self.bor_app.open_llm()

    async def action_refresh(self) -> None:
        """Refresh the message index (re-run current search after mu index)."""
        status = self.query_one("#status-label", Label)
        status.update("Updating index...")

        # Run mu index (seconds on a large maildir; keep it off the UI thread)
        await asyncio.to_thread(self.bor_app.mu.index)

        # Re-run current search
        if self._thread_anchor is not None or self.current_query:
            await self.rerun_view()
        else:
            # Default to inbox
            config = get_config()
            await self.search(f'maildir:"{config.folders.inbox}"')

        status.update(f"Index updated - {len(self.messages)} messages")

    async def refresh_current_view(self) -> None:
        """Refresh current query results and preserve cursor position."""
        current_index = self._get_current_index()
        marked_ids = self._capture_marked_message_ids()

        if self._thread_anchor is not None or self.current_query:
            await self.rerun_view()
        else:
            config = get_config()
            await self.search(f'maildir:"{config.folders.inbox}"')

        await self._restore_marked_messages(marked_ids)
        self._restore_cursor(current_index)

    def _message_identity(self, message: EmailMessage) -> str:
        """Return a stable identity for a message across index refreshes."""
        return message.msgid or message.path

    def _capture_marked_message_ids(self) -> set[str]:
        """Capture stable identities for currently marked messages."""
        marked_ids: set[str] = set()
        for idx in self.marked_messages:
            if 0 <= idx < len(self.messages):
                marked_ids.add(self._message_identity(self.messages[idx]))
        return marked_ids

    async def _restore_marked_messages(self, marked_ids: set[str]) -> None:
        """Restore marked messages after a refresh using stable identities."""
        if not marked_ids:
            return

        self.marked_messages = {
            idx
            for idx, message in enumerate(self.messages)
            if self._message_identity(message) in marked_ids
        }
        if self.marked_messages:
            await self._refresh_table()
        self._update_status()

    def action_mark_message(self) -> None:
        """Mark/unmark the current message."""
        idx = self._get_current_index()
        if idx is None:
            return
        if idx in self.marked_messages:
            self.marked_messages.remove(idx)
        else:
            self.marked_messages.add(idx)

        # Update the row styling
        self._update_row_style(idx)
        self._update_status()
        # Move to next message
        self.action_cursor_down()

    def _update_row_style(self, idx: int) -> None:
        """Update the styling of a single row."""
        if idx < 0 or idx >= len(self.messages):
            return

        config = get_config()
        table = self.query_one(DataTable)
        cells = self._row_cells(
            idx, self.messages[idx], config, self._compute_thread_prefixes(self.messages)
        )

        # DataTable doesn't have direct row update, so we update cell by cell
        try:
            from textual.coordinate import Coordinate

            row_idx = table.get_row_index(str(idx))
            for column, cell in enumerate(cells):
                table.update_cell_at(Coordinate(row_idx, column), cell, update_width=False)
            # Force visual refresh
            self.refresh(layout=True)
        except Exception:
            pass  # Row might not exist

    def _confirm_action(self, prompt: str, callback: Callable) -> None:
        """Show confirmation bar and execute callback if confirmed."""
        confirm_bar = self.query_one("#confirm-bar", ConfirmBar)
        confirm_bar.ask(prompt, callback)

    def _restore_cursor(self, desired_index: int) -> None:
        """Restore table cursor to a desired index after refresh."""
        table = self.query_one(DataTable)
        if not self.messages:
            return
        index = max(0, min(desired_index, len(self.messages) - 1))
        table.move_cursor(row=index)
        self.bor_app._current_index = index

    def action_archive(self) -> None:
        """Archive marked messages or current message with confirmation."""
        if self.marked_messages:
            count = len(self.marked_messages)
            self._confirm_action(f"Archive {count} marked message(s)?", self._do_archive)
        else:
            msg = self._get_current_message()
            if msg:
                self._confirm_action("Archive this message?", self._do_archive)

    def _do_archive(self) -> None:
        """Actually perform the archive operation."""
        asyncio.create_task(self._do_archive_async())

    async def _do_archive_async(self) -> None:
        """Async archive operation."""
        config = get_config()
        archive_folder = config.folders.archive
        current_index = self._get_current_index()
        desired_index = current_index

        if self.marked_messages:
            removed_above = sum(1 for idx in self.marked_messages if idx < current_index)
            desired_index = current_index - removed_above

        if self.marked_messages:
            # Archive all marked messages
            for idx in sorted(self.marked_messages, reverse=True):
                if 0 <= idx < len(self.messages):
                    msg = self.messages[idx]
                    self.bor_app.mu.move(msg.path, archive_folder)
            self.marked_messages.clear()
        else:
            # Archive current message
            msg = self._get_current_message()
            if msg:
                self.bor_app.mu.move(msg.path, archive_folder)

        # Refresh the list
        await self.rerun_view()
        self._restore_cursor(desired_index)
        self.query_one(DataTable).focus()

    def action_apply_flag(self) -> None:
        """Apply a flag to marked messages or current message."""
        flag_bar = self.query_one("#flag-bar", FlagBar)
        flag_bar.ask(self._do_apply_flag)

    def _do_apply_flag(self, flag_key: str) -> None:
        """Actually apply the selected flag."""
        asyncio.create_task(self._do_apply_flag_async(flag_key))

    async def _do_apply_flag_async(self, flag_key: str) -> None:
        """Async flag application. Uppercase = remove, lowercase = add."""
        messages_to_flag = []

        if self.marked_messages:
            for idx in self.marked_messages:
                if 0 <= idx < len(self.messages):
                    messages_to_flag.append((idx, self.messages[idx]))
        else:
            idx = self._get_current_index()
            msg = self._get_current_message()
            if msg:
                messages_to_flag.append((idx, msg))

        for idx, msg in messages_to_flag:
            apply_flag(self.bor_app.mu, msg.path, msg.flags, flag_key)
            self._update_row_style(idx)

        # Clear marked messages after applying flags
        if self.marked_messages:
            self.marked_messages.clear()
            self._update_status()

        self.query_one(DataTable).focus()

    async def action_undo(self) -> None:
        """Undo the last move operation."""
        if self.bor_app.mu.undo_move():
            await self.rerun_view()

    async def action_toggle_threading(self) -> None:
        """Toggle threading on/off."""
        self.threading_enabled = not self.threading_enabled
        await self.search(self.current_query)

    async def action_show_thread(self) -> None:
        """Show all messages in the current thread, with the cursor on this one."""
        msg = self._get_current_message()
        if msg:
            await self._show_thread(msg)
            anchor_id = self._message_identity(msg)
            for idx, message in enumerate(self.messages):
                if self._message_identity(message) == anchor_id:
                    self._restore_cursor(idx)
                    break

    async def _show_thread(self, anchor: EmailMessage) -> None:
        """Replace the list with the thread containing `anchor`."""
        # find_thread() runs several `mu find` passes; keep them off the UI.
        self.messages = await asyncio.to_thread(self._find_thread, anchor)
        self._thread_anchor = anchor
        self.bor_app._current_messages = self.messages
        self.bor_app._current_index = 0
        # Marks are row positions in the previous list
        self.marked_messages.clear()
        await self._refresh_table()
        self._update_status()

    def _find_thread(self, anchor: EmailMessage) -> list[EmailMessage]:
        """Run the thread query. Runs on a worker thread."""
        mu = self.bor_app.mu
        mu.wait_for_reindex()
        return mu.find_thread(anchor)

    async def rerun_view(self) -> None:
        """Re-run whatever the list shows: the thread view or the current query."""
        if self._thread_anchor is not None:
            await self._show_thread(self._thread_anchor)
        else:
            await self.search(self.current_query)

    def action_delete(self) -> None:
        """Delete marked messages or current message with confirmation."""
        if self.marked_messages:
            count = len(self.marked_messages)
            self._confirm_action(f"Delete {count} marked message(s)?", self._do_delete)
        else:
            msg = self._get_current_message()
            if msg:
                self._confirm_action("Delete this message?", self._do_delete)

    def _do_delete(self) -> None:
        """Actually perform the delete operation."""
        asyncio.create_task(self._do_delete_async())

    async def _do_delete_async(self) -> None:
        """Async delete operation."""
        config = get_config()

        if self.marked_messages:
            for idx in sorted(self.marked_messages, reverse=True):
                if 0 <= idx < len(self.messages):
                    msg = self.messages[idx]
                    self.bor_app.mu.move(msg.path, config.folders.trash)
            self.marked_messages.clear()
        else:
            msg = self._get_current_message()
            if msg:
                self.bor_app.mu.move(msg.path, config.folders.trash)

        await self.rerun_view()
        self.query_one(DataTable).focus()

    def action_edit_draft(self) -> None:
        """Edit a draft message."""
        msg = self._get_current_message()
        if msg:
            config = get_config()
            # Check if message is in drafts folder
            if config.folders.drafts in msg.maildir:
                self.bor_app.open_compose(edit_draft=msg)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection (double-click or Enter)."""
        self.action_open_message()
