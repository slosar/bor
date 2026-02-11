"""
Message Index tab for Bor email reader.

Displays a list of email messages with navigation and actions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, List, Optional, Set

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, Horizontal
from textual.message import Message
from textual.widgets import DataTable, Input, Static, Label
from textual.coordinate import Coordinate

from bor.tabs.base import BaseTab
from bor.mu import EmailMessage
from bor.config import get_config


class SearchInput(Input):
    """Input widget for search."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialize search input."""
        super().__init__(*args, placeholder="Search...", **kwargs)

    def on_key(self, event: events.Key) -> None:
        """Handle key events."""
        if event.key == "escape":
            # Hide search bar
            search_bar = self.parent
            search_bar.remove_class("visible")
            self.display = False
            # Focus the DataTable - need to go up to screen level to find it
            try:
                self.screen.query_one(DataTable).focus()
            except Exception:
                pass
            event.prevent_default()
            event.stop()
        elif event.key == "enter":
            # Trigger search
            self.post_message(SearchInput.Submitted(self.value))
            event.prevent_default()
            event.stop()

    class Submitted(Message):
        """Search submitted message."""

        def __init__(self, query: str) -> None:
            """Initialize with query."""
            self.query = query
            super().__init__()


class ConfirmBar(Static):
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
        self._callback: Optional[Callable] = None
        self._prompt: str = ""

    def ask(self, prompt: str, callback: Callable) -> None:
        """Show confirmation prompt."""
        self._prompt = prompt
        self._callback = callback
        self.update(f"{prompt} (y/n)")
        self.add_class("visible")
        self.focus()

    def on_key(self, event: events.Key) -> None:
        """Handle key events."""
        if event.key in ("y", "Y"):
            self.remove_class("visible")
            if self._callback:
                self._callback()
            event.prevent_default()
            event.stop()
        elif event.key in ("n", "N", "escape"):
            self.remove_class("visible")
            # Return focus to table
            try:
                self.screen.query_one(DataTable).focus()
            except Exception:
                pass
            event.prevent_default()
            event.stop()

    can_focus = True


class ReplyBar(Static):
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
        self._callback: Optional[Callable] = None

    def ask(self, callback: Callable) -> None:
        """Show reply options prompt."""
        self._callback = callback
        self.update("Reply to: (a)ll or (s)ender only?")
        self.add_class("visible")
        self.focus()

    def on_key(self, event: events.Key) -> None:
        """Handle key events."""
        key = event.key.lower() if event.key else ""
        
        if key in ("a", "s"):
            self.remove_class("visible")
            if self._callback:
                self._callback(key == "a")  # True for reply all, False for sender only
            event.prevent_default()
            event.stop()
        elif key == "escape":
            self.remove_class("visible")
            event.prevent_default()
            event.stop()

    can_focus = True


class FlagBar(Static):
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
        self._callback: Optional[Callable] = None

    def ask(self, callback: Callable) -> None:
        """Show flag selection prompt."""
        self._callback = callback
        self.update("Apply flag: (U)nread, (N)ew, (F)lagged | Shift+key to remove flag | (Esc) Cancel")
        self.add_class("visible")
        self.focus()

    def on_key(self, event: events.Key) -> None:
        """Handle key events."""
        key = event.key.lower() if event.key else ""
        char = event.character or ""
        
        # Check for shift+key (uppercase) to remove flag
        if char in ("U", "N", "F"):
            self.remove_class("visible")
            if self._callback:
                # Pass uppercase to indicate removal
                self._callback(char)
            event.prevent_default()
            event.stop()
        elif key in ("u", "n", "f"):
            self.remove_class("visible")
            if self._callback:
                self._callback(key)
            event.prevent_default()
            event.stop()
        elif key == "escape":
            self.remove_class("visible")
            # Return focus to table
            try:
                self.screen.query_one(DataTable).focus()
            except Exception:
                pass
            event.prevent_default()
            event.stop()

    can_focus = True


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
        #Binding("ctrl+f", "incremental_search", "Search"),  ## implement when we have a better idea what exactly
        Binding("s", "mu_search", "Mu Search"),
        Binding("i", "show_inbox", "Inbox"),
        Binding("o", "show_archive", "Archive"),
        Binding("u", "show_drafts", "Drafts"),
        Binding("l", "sync", "Sync"),
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

    MessageIndexWidget .marked {
        background: $primary-darken-2;
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
        self.messages: List[EmailMessage] = []
        self.marked_messages: Set[int] = set()
        self.current_query: str = ""
        self.threading_enabled: bool = get_config().threading.enabled
        self._search_visible: bool = False
        self._pending_action: Optional[Callable] = None

    def compose(self) -> ComposeResult:
        """Create the widget layout."""
        with Vertical():
            with Container(classes="search-bar", id="search-bar"):
                yield SearchInput(id="search-input")
            yield DataTable(id="message-table", cursor_type="row")
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

    async def search(self, query: str, threads: Optional[bool] = None) -> None:
        """
        Search for messages and display results.

        Args:
            query: Mu search query
            threads: Whether to use threading (None uses current setting)
        """
        config = get_config()
        use_threads = threads if threads is not None else self.threading_enabled

        self.current_query = query
        self.messages = self.bor_app.mu.find(
            query,
            maxnum=config.general.max_messages,
            threads=use_threads,
            descending=True
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

    async def _refresh_table(self) -> None:
        """Refresh the message table with current messages."""
        from rich.text import Text
        
        table = self.query_one(DataTable)
        table.clear()

        config = get_config()

        # Compute thread tree structure for proper visualization
        thread_prefixes = self._compute_thread_prefixes(self.messages)

        for idx, msg in enumerate(self.messages):
            # Build flags string
            flags = self._format_flags(msg, config)

            # Format date
            date_str = self._format_date(msg.date, config)

            # Format from
            from_str = msg.from_addr.name or msg.from_addr.email
            if len(from_str) > config.display.from_width:
                from_str = from_str[:config.display.from_width - 1] + "…"

            # Format subject with threading tree prefix
            subject = msg.subject
            if idx in thread_prefixes and thread_prefixes[idx]:
                subject = f"{thread_prefixes[idx]} {subject}"

            # Determine styling based on message state
            # For marked messages, use "on <color>" for background to span cell width
            style = ""
            if idx in self.marked_messages:
                # Use reverse or background color for visibility
                marked_style = config.colors.marked
                if marked_style == "reverse":
                    style = "reverse"
                else:
                    style = f"on {marked_style}" if not marked_style.startswith("on ") else marked_style
            elif msg.is_flagged:
                style = f"bold {config.colors.important}"
            elif msg.is_unread:
                style = f"bold {config.colors.unread}"
            
            # Create styled text for each cell
            if style:
                flags_text = Text(flags, style=style)
                date_text = Text(date_str, style=style)
                from_text = Text(from_str, style=style)
                subject_text = Text(subject, style=style)
            else:
                flags_text = flags
                date_text = date_str
                from_text = from_str
                subject_text = subject

            # Add row
            row_key = str(idx)
            table.add_row(flags_text, date_text, from_text, subject_text, key=row_key)

    def _compute_thread_prefixes(self, messages: List[EmailMessage]) -> dict:
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

    def _format_date(self, date: Optional[datetime], config) -> str:
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
        threading_status = "threaded" if self.threading_enabled else "flat"
        marked_count = len(self.marked_messages)
        marked_str = f" | {marked_count} marked" if marked_count > 0 else ""
        label.update(f"{len(self.messages)} messages ({threading_status}){marked_str}")

    def _get_current_message(self) -> Optional[EmailMessage]:
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

    def action_reply(self) -> None:
        """Reply to the selected message."""
        msg = self._get_current_message()
        if msg:
            # Check if there are multiple recipients - need full message for CC info
            full_msg = self.bor_app.mu.view(msg.path)
            # Show reply options if there are CC recipients or multiple TO recipients
            if full_msg and (full_msg.cc_addrs or len(full_msg.to_addrs) > 1):
                reply_bar = self.query_one("#reply-bar", ReplyBar)
                self._pending_reply_msg = full_msg
                reply_bar.ask(self._do_reply)
            else:
                self.bor_app.open_compose(reply_to=full_msg or msg)

    def _do_reply(self, reply_all: bool = False) -> None:
        """Actually open the reply compose."""
        msg = getattr(self, '_pending_reply_msg', None)
        if msg:
            self.bor_app.open_compose(reply_to=msg, reply_all=reply_all)
            self._pending_reply_msg = None

    def action_forward(self) -> None:
        """Forward the selected message."""
        msg = self._get_current_message()
        if msg:
            full_msg = self.bor_app.mu.view(msg.path, mark_as_read=False)
            self.bor_app.open_compose(forward=full_msg or msg)

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
        search_input.value = ""
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

    async def action_refresh(self) -> None:
        """Refresh the message index (re-run current search after mu index)."""
        status = self.query_one("#status-label", Label)
        status.update("Updating index...")
        
        # Run mu index
        self.bor_app.mu.index()
        
        # Re-run current search
        if self.current_query:
            await self.search(self.current_query)
        else:
            # Default to inbox
            config = get_config()
            await self.search(f'maildir:"{config.folders.inbox}"')
        
        status.update(f"Index updated - {len(self.messages)} messages")

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
        from rich.text import Text
        
        if idx < 0 or idx >= len(self.messages):
            return
            
        msg = self.messages[idx]
        config = get_config()
        table = self.query_one(DataTable)
        
        # Build flags string
        flags = self._format_flags(msg, config)
        date_str = self._format_date(msg.date, config)
        from_str = msg.from_addr.name or msg.from_addr.email
        if len(from_str) > config.display.from_width:
            from_str = from_str[:config.display.from_width - 1] + "…"
        
        # Format subject with threading tree prefix
        thread_prefixes = self._compute_thread_prefixes(self.messages)
        subject = msg.subject
        if idx in thread_prefixes and thread_prefixes[idx]:
            subject = f"{thread_prefixes[idx]} {subject}"
        
        # Determine styling
        # For marked messages, use "on <color>" for background to span cell width
        style = ""
        if idx in self.marked_messages:
            marked_style = config.colors.marked
            if marked_style == "reverse":
                style = "reverse"
            else:
                style = f"on {marked_style}" if not marked_style.startswith("on ") else marked_style
        elif msg.is_flagged:
            style = f"bold {config.colors.important}"
        elif msg.is_unread:
            style = f"bold {config.colors.unread}"
        
        # Create styled text using Rich Style for explicit color control
        from rich.style import Style as RichStyle
        if style:
            rich_style = RichStyle.parse(style)
            flags_text = Text(flags, style=rich_style)
            date_text = Text(date_str, style=rich_style)
            from_text = Text(from_str, style=rich_style)
            subject_text = Text(subject, style=rich_style)
        else:
            flags_text = Text(flags)
            date_text = Text(date_str)
            from_text = Text(from_str)
            subject_text = Text(subject)
        
        # Update the row in place
        row_key = str(idx)
        # DataTable doesn't have direct row update, so we update cell by cell
        try:
            # Get the coordinate for each cell and update
            from textual.coordinate import Coordinate
            
            # Get row index in the table
            row_idx = table.get_row_index(row_key)
            
            # Update each column by coordinate
            table.update_cell_at(Coordinate(row_idx, 0), flags_text, update_width=False)
            table.update_cell_at(Coordinate(row_idx, 1), date_text, update_width=False)
            table.update_cell_at(Coordinate(row_idx, 2), from_text, update_width=False)
            table.update_cell_at(Coordinate(row_idx, 3), subject_text, update_width=False)
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
            self._confirm_action(
                f"Archive {count} marked message(s)?",
                self._do_archive
            )
        else:
            msg = self._get_current_message()
            if msg:
                self._confirm_action(
                    f"Archive this message?",
                    self._do_archive
                )

    def _do_archive(self) -> None:
        """Actually perform the archive operation."""
        import asyncio
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
        await self.search(self.current_query)
        self._restore_cursor(desired_index)
        self.query_one(DataTable).focus()

    def action_apply_flag(self) -> None:
        """Apply a flag to marked messages or current message."""
        flag_bar = self.query_one("#flag-bar", FlagBar)
        flag_bar.ask(self._do_apply_flag)

    def _do_apply_flag(self, flag_key: str) -> None:
        """Actually apply the selected flag."""
        import asyncio
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
        
        # Check if removing (uppercase) or adding (lowercase)
        is_remove = flag_key.isupper()
        flag_lower = flag_key.lower()
        
        for idx, msg in messages_to_flag:
            if flag_lower == "u":
                if is_remove:
                    # Mark as read (remove unread)
                    self.bor_app.mu.mark_read(msg.path)
                    if "unread" in msg.flags:
                        msg.flags.remove("unread")
                    if "seen" not in msg.flags:
                        msg.flags.append("seen")
                else:
                    # Mark as unread
                    self.bor_app.mu.mark_unread(msg.path)
                    if "unread" not in msg.flags:
                        msg.flags.append("unread")
                    if "seen" in msg.flags:
                        msg.flags.remove("seen")
            elif flag_lower == "n":
                if is_remove:
                    # Remove new flag
                    self.bor_app.mu.mark_read(msg.path)
                    if "new" in msg.flags:
                        msg.flags.remove("new")
                else:
                    # Mark as new
                    self.bor_app.mu.mark_unread(msg.path)
                    if "new" not in msg.flags:
                        msg.flags.append("new")
                    if "unread" not in msg.flags:
                        msg.flags.append("unread")
            elif flag_lower == "f":
                if is_remove:
                    # Remove flagged
                    self.bor_app.mu.mark_flagged(msg.path, False)
                    if "flagged" in msg.flags:
                        msg.flags.remove("flagged")
                else:
                    # Mark as flagged/important
                    self.bor_app.mu.mark_flagged(msg.path, True)
                    if "flagged" not in msg.flags:
                        msg.flags.append("flagged")
            
            # Update the row display
            self._update_row_style(idx)
        
        # Clear marked messages after applying flags
        if self.marked_messages:
            self.marked_messages.clear()
            self._update_status()
        
        self.query_one(DataTable).focus()

    async def action_undo(self) -> None:
        """Undo the last move operation."""
        if self.bor_app.mu.undo_move():
            await self.search(self.current_query)

    async def action_toggle_threading(self) -> None:
        """Toggle threading on/off."""
        self.threading_enabled = not self.threading_enabled
        await self.search(self.current_query)

    async def action_show_thread(self) -> None:
        """Show all messages in the current thread."""
        msg = self._get_current_message()
        if msg:
            thread_messages = self.bor_app.mu.find_thread(msg)
            self.messages = thread_messages
            self.bor_app._current_messages = self.messages
            await self._refresh_table()
            self._update_status()

    def action_delete(self) -> None:
        """Delete marked messages or current message with confirmation."""
        if self.marked_messages:
            count = len(self.marked_messages)
            self._confirm_action(
                f"Delete {count} marked message(s)?",
                self._do_delete
            )
        else:
            msg = self._get_current_message()
            if msg:
                self._confirm_action(
                    f"Delete this message?",
                    self._do_delete
                )

    def _do_delete(self) -> None:
        """Actually perform the delete operation."""
        import asyncio
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

        await self.search(self.current_query)
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
