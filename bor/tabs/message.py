"""
Message View tab for Bor email reader.

Displays a single email message with headers and body.
"""

from __future__ import annotations

import re
import subprocess
import webbrowser
from typing import Callable, Optional

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, ScrollableContainer
from textual.widgets import Static, Label, Markdown
from textual.reactive import reactive

from bor.tabs.base import BaseTab
from bor.mu import EmailMessage, MuInterface
from bor.config import get_config


def html_to_text(html: str) -> str:
    """
    Convert HTML to plain text.

    Uses html2text if available, otherwise a simple regex-based conversion.

    Args:
        html: HTML content to convert

    Returns:
        Plain text representation
    """
    try:
        import html2text
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0  # No wrapping
        return h.handle(html)
    except ImportError:
        pass

    # Simple fallback: strip HTML tags
    # Remove style/script/head blocks to avoid dumping CSS/JS
    text = re.sub(r'(?is)<(script|style)\b[^>]*>.*?</\1>', '', html)
    text = re.sub(r'(?is)<head\b[^>]*>.*?</head>', '', text)
    text = re.sub(r'(?is)<!--.*?-->', '', text)

    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text = re.sub(r'<p[^>]*>', '\n\n', text, flags=re.I)
    text = re.sub(r'</p>', '', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&quot;', '"', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


class MessageHeader(Static):
    """Widget to display message headers."""

    DEFAULT_CSS = """
    MessageHeader {
        background: $surface;
        padding: 1;
        margin-bottom: 1;
    }

    MessageHeader .header-label {
        color: $text-muted;
        width: 10;
    }

    MessageHeader .header-value {
        color: $text;
    }
    """

    def __init__(self, message: EmailMessage, show_full: bool = False, **kwargs) -> None:
        """
        Initialize message header display.

        Args:
            message: Email message to display
            show_full: Whether to show full headers (including BCC, etc.)
        """
        super().__init__(**kwargs)
        self.message = message
        self.show_full = show_full

    def compose(self) -> ComposeResult:
        """Create the header layout."""
        yield Static(self._format_headers(), id="header-content")

    def update_message(self, message: EmailMessage) -> None:
        """Update the displayed message."""
        self.message = message
        try:
            content = self.query_one("#header-content", Static)
            content.update(self._format_headers())
        except Exception:
            pass

    def _format_headers(self) -> str:
        """Format headers for display."""
        lines = []

        # From
        lines.append(f"[bold]From:[/bold]    {self.message.from_addr}")

        # To
        to_list = ", ".join(str(addr) for addr in self.message.to_addrs)
        lines.append(f"[bold]To:[/bold]      {to_list}")

        # CC
        if self.message.cc_addrs:
            cc_list = ", ".join(str(addr) for addr in self.message.cc_addrs)
            lines.append(f"[bold]CC:[/bold]      {cc_list}")

        # BCC (only in full header mode)
        if self.show_full and self.message.bcc_addrs:
            bcc_list = ", ".join(str(addr) for addr in self.message.bcc_addrs)
            lines.append(f"[bold]BCC:[/bold]     {bcc_list}")

        # Date
        date_str = ""
        if self.message.date:
            date_str = self.message.date.strftime("%Y-%m-%d %H:%M:%S %Z")
        lines.append(f"[bold]Date:[/bold]    {date_str}")

        # Subject
        lines.append(f"[bold]Subject:[/bold] {self.message.subject}")

        # Attachments count
        if self.message.attachments:
            count = len(self.message.attachments)
            lines.append(f"[bold]Attach:[/bold]  {count} attachment(s)")

        # Full headers
        if self.show_full:
            if self.message.msgid:
                lines.append(f"[bold]Msg-ID:[/bold]  {self.message.msgid}")
            if self.message.in_reply_to:
                lines.append(f"[bold]Reply-To:[/bold] {self.message.in_reply_to}")

        return "\n".join(lines)


class MessageBody(ScrollableContainer):
    """Widget to display message body."""

    can_focus = True

    DEFAULT_CSS = """
    MessageBody {
        height: 1fr;
        padding: 1;
    }

    MessageBody .quoted {
        color: $text-muted;
        text-style: italic;
    }
    """

    def __init__(self, content: str, **kwargs) -> None:
        """
        Initialize message body display.

        Args:
            content: Message body text
        """
        super().__init__(**kwargs)
        self.content = content

    def compose(self) -> ComposeResult:
        """Create the body layout."""
        # Try to use Markdown for rich display
        yield Static(self.content)


class UrlPickerBar(Static):
    """URL selection bar widget for choosing a link to open."""

    DEFAULT_CSS = """
    UrlPickerBar {
        display: none;
        dock: bottom;
        height: auto;
        background: $primary;
        color: $text;
        text-style: bold;
        padding: 0 1;
        layer: confirm;
    }
    UrlPickerBar.visible {
        display: block;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initialize URL picker bar."""
        super().__init__(*args, **kwargs)
        self._urls: list[str] = []
        self._callback: Optional[Callable[[str], None]] = None
        self._error: str = ""

    def ask(self, urls: list[str], callback: Callable[[str], None]) -> None:
        """Show URL selection prompt."""
        self._urls = urls
        self._callback = callback
        self._error = ""
        self._render_prompt()
        self.add_class("visible")
        self.focus()

    def _render_prompt(self) -> None:
        lines = ["Select URL [1-9] (Esc cancels):"]
        for idx, url in enumerate(self._urls[:9], start=1):
            display_url = url if len(url) <= 72 else f"{url[:69]}..."
            lines.append(f" [{idx}] {display_url}")
        if len(self._urls) > 9:
            lines.append(f"(+{len(self._urls) - 9} more)")
        if self._error:
            lines.append(self._error)
        self.update("\n".join(lines))

    def on_key(self, event: events.Key) -> None:
        """Handle key events for URL selection."""
        if event.key == "escape":
            self.remove_class("visible")
            self._error = ""
            try:
                self.screen.query_one(ScrollableContainer).focus()
            except Exception:
                pass
            event.prevent_default()
            event.stop()
            return

        if event.character and event.character.isdigit():
            idx = int(event.character)
            if idx == 0:
                self._error = "Selection must be 1-9."
                self._render_prompt()
            elif idx <= len(self._urls) and idx <= 9:
                self.remove_class("visible")
                url = self._urls[idx - 1]
                if self._callback:
                    self._callback(url)
                self._error = ""
            else:
                self._error = "Invalid selection."
                self._render_prompt()
            event.prevent_default()
            event.stop()

    can_focus = True


class MessageViewWidget(BaseTab):
    """
    Message View widget.

    Displays a single email message with headers and body content.
    """

    BINDINGS = [
        # Navigation
        Binding("up", "scroll_up", "Scroll Up", show=False),
        Binding("down", "scroll_down", "Scroll Down", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
        Binding("space", "page_down", "Page Down", show=False),
        Binding("home", "scroll_home", "Top", show=False),
        Binding("end", "scroll_end", "Bottom", show=False),

        # Actions - < returns without closing, Q closes and returns (< handled in on_key)
        Binding("q", "close_and_return", "Close"),
        # M, X, D, A work as in Message Index
        Binding("m", "mark_message", "Mark"),
        Binding("x", "archive", "Archive"),
        Binding("d", "delete", "Delete"),
        Binding("a", "apply_flag", "Apply Flag"),
        # Message navigation
        Binding("n", "next_message", "Next"),
        Binding("p", "prev_message", "Previous"),
        Binding("r", "reply", "Reply"),
        Binding("f", "forward", "Forward"),
        Binding("c", "compose", "Compose"),
        Binding("z", "attachments", "Attachments"),
        Binding("o", "open_url", "Open URL"),
        Binding("ctrl+r", "toggle_full_headers", "Full Headers"),
    ]

    DEFAULT_CSS = """
    MessageViewWidget {
        height: 1fr;
    }

    MessageViewWidget ScrollableContainer {
        height: 1fr;
    }

    MessageViewWidget .attachment-info {
        background: $warning-darken-2;
        color: $text;
        padding: 0 1;
        margin: 1 0;
    }
    """

    show_full_headers: reactive[bool] = reactive(False)

    def __init__(self, message: EmailMessage, *args, **kwargs) -> None:
        """
        Initialize the message view.

        Args:
            message: Email message to display
        """
        super().__init__(*args, **kwargs)
        self._message_ref = message
        self._full_message: Optional[EmailMessage] = None
        self._content: str = ""
        # Track all message indices that were viewed/read during this session
        self._read_message_indices: set = set()

    @property
    def message(self) -> Optional[EmailMessage]:
        """Get the full message."""
        return self._full_message

    def compose(self) -> ComposeResult:
        """Create the widget layout."""
        from bor.tabs.message_index import ConfirmBar, FlagBar, ReplyBar
        with ScrollableContainer():
            yield MessageHeader(self._message_ref, id="msg-header")
            yield Static("", id="attachment-info", classes="attachment-info")
            yield Static("Loading...", id="msg-body", markup=False)
        yield ConfirmBar("", id="confirm-bar")
        yield FlagBar("", id="flag-bar")
        yield ReplyBar("", id="reply-bar")
        yield UrlPickerBar("", id="url-picker")

    def on_key(self, event: events.Key) -> None:
        """Handle key events for special keys like <."""
        if event.character == "<":
            self.action_return_to_index()
            event.prevent_default()
            event.stop()

    def on_mount(self) -> None:
        """Handle widget mount."""
        self._load_message()

    def _load_message(self) -> None:
        """Load the full message content."""
        mu = self.bor_app.mu
        # Pass msgid in case the path is stale (e.g., after marking as read)
        self._full_message = mu.view(self._message_ref.path, msgid=self._message_ref.msgid)

        if self._full_message:
            # Update the message reference path in case it changed (e.g., marked as read)
            # This keeps _current_messages in sync
            if self._full_message.path != self._message_ref.path:
                self._message_ref.path = self._full_message.path
            
            # Update flags - message was marked as read
            if "unread" in self._message_ref.flags:
                self._message_ref.flags.remove("unread")
            if "new" in self._message_ref.flags:
                self._message_ref.flags.remove("new")
            if "seen" not in self._message_ref.flags:
                self._message_ref.flags.append("seen")
            
            # Track this message index as read for later refresh
            self._read_message_indices.add(self.bor_app._current_index)
            
            # Update header
            header = self.query_one("#msg-header", MessageHeader)
            header.update_message(self._full_message)

            # Update attachment info
            attach_info = self.query_one("#attachment-info", Static)
            if self._full_message.attachments:
                count = len(self._full_message.attachments)
                attach_info.update(f"📎 {count} attachment(s) - Press 'z' to view")
                attach_info.display = True
            else:
                attach_info.display = False

            # Get body content
            if self._full_message.body_txt:
                self._content = self._full_message.body_txt
            elif self._full_message.body_html:
                self._content = html_to_text(self._full_message.body_html)
            else:
                self._content = "(No message content)"

            # Update body
            body = self.query_one("#msg-body", Static)
            body.update(self._content)

            # Update tab title
            title = self._full_message.subject[:20] + "..." if len(self._full_message.subject) > 20 else self._full_message.subject
            self.update_tab_title(title)
        else:
            body = self.query_one("#msg-body", Static)
            body.update("Error: Could not load message")

    # Navigation actions

    def action_scroll_up(self) -> None:
        """Scroll up."""
        container = self.query_one(ScrollableContainer)
        container.scroll_up()

    def action_scroll_down(self) -> None:
        """Scroll down."""
        container = self.query_one(ScrollableContainer)
        container.scroll_down()

    def action_page_up(self) -> None:
        """Page up."""
        container = self.query_one(ScrollableContainer)
        container.scroll_page_up()

    def action_page_down(self) -> None:
        """Page down."""
        container = self.query_one(ScrollableContainer)
        container.scroll_page_down()

    def action_scroll_home(self) -> None:
        """Scroll to top."""
        container = self.query_one(ScrollableContainer)
        container.scroll_home()

    def action_scroll_end(self) -> None:
        """Scroll to bottom."""
        container = self.query_one(ScrollableContainer)
        container.scroll_end()

    # Message actions

    def action_return_to_index(self) -> None:
        """Return to message index without closing tab."""
        self._refresh_index_row()
        self.switch_to_index()

    def action_close_and_return(self) -> None:
        """Close tab and return to index."""
        self._refresh_index_row()
        self.close_tab()

    def _refresh_index_row(self) -> None:
        """Refresh all read messages' rows in the index to show updated read status."""
        try:
            from bor.tabs.message_index import MessageIndexWidget
            from textual.widgets import DataTable
            index_widget = self.bor_app.query_one(MessageIndexWidget)
            # Refresh all messages that were read during this viewing session
            for idx in self._read_message_indices:
                index_widget._update_row_style(idx)
            # Move the cursor to the last viewed message position
            table = index_widget.query_one(DataTable)
            current_idx = self.bor_app._current_index
            if 0 <= current_idx < len(index_widget.messages):
                table.move_cursor(row=current_idx)
        except Exception:
            pass

    def action_next_message(self) -> None:
        """View the next message in index order.
        
        Only navigates if the current message exists in the index.
        Navigation follows the index order (threaded or date-sorted).
        """
        # Find current message's position in the index by msgid
        current_msgid = self._message_ref.msgid
        current_idx = None
        for idx, msg in enumerate(self.bor_app._current_messages):
            if msg.msgid == current_msgid:
                current_idx = idx
                break
        
        # If current message is not in index, do nothing
        if current_idx is None:
            return
        
        # Check if there's a next message
        if current_idx + 1 < len(self.bor_app._current_messages):
            self.bor_app._current_index = current_idx + 1
            next_msg = self.bor_app._current_messages[current_idx + 1]
            self._message_ref = next_msg
            self._load_message()

    def action_prev_message(self) -> None:
        """View the previous message in index order.
        
        Only navigates if the current message exists in the index.
        Navigation follows the index order (threaded or date-sorted).
        """
        # Find current message's position in the index by msgid
        current_msgid = self._message_ref.msgid
        current_idx = None
        for idx, msg in enumerate(self.bor_app._current_messages):
            if msg.msgid == current_msgid:
                current_idx = idx
                break
        
        # If current message is not in index, do nothing
        if current_idx is None:
            return
        
        # Check if there's a previous message
        if current_idx > 0:
            self.bor_app._current_index = current_idx - 1
            prev_msg = self.bor_app._current_messages[current_idx - 1]
            self._message_ref = prev_msg
            self._load_message()

    def action_reply(self) -> None:
        """Reply to this message."""
        if self._full_message:
            # Check if there are multiple recipients (CC recipients or multiple TO recipients)
            if self._full_message.cc_addrs or len(self._full_message.to_addrs) > 1:
                from bor.tabs.message_index import ReplyBar
                reply_bar = self.query_one("#reply-bar", ReplyBar)
                reply_bar.ask(self._do_reply)
            else:
                self._do_reply(reply_all=False)

    def _do_reply(self, reply_all: bool = False) -> None:
        """Actually open the reply compose."""
        if self._full_message:
            tab_id = self.get_tab_id()
            self.bor_app.open_compose(reply_to=self._full_message, replace_tab=tab_id, reply_all=reply_all)

    def action_forward(self) -> None:
        """Forward this message."""
        if self._full_message:
            tab_id = self.get_tab_id()
            self.bor_app.open_compose(forward=self._full_message, replace_tab=tab_id)

    def action_compose(self) -> None:
        """Compose new message."""
        tab_id = self.get_tab_id()
        self.bor_app.open_compose(replace_tab=tab_id)

    def action_mark_message(self) -> None:
        """Mark/unmark the current message in the index and advance to next."""
        from bor.tabs.message_index import MessageIndexWidget
        try:
            index_widget = self.bor_app.query_one(MessageIndexWidget)
            # Find the current message's index
            current_idx = self.bor_app._current_index
            if current_idx in index_widget.marked_messages:
                index_widget.marked_messages.remove(current_idx)
            else:
                index_widget.marked_messages.add(current_idx)
            index_widget._update_row_style(current_idx)
            index_widget._update_status()
        except Exception:
            pass
        
        # Advance to next message
        self.action_next_message()

    def action_apply_flag(self) -> None:
        """Apply a flag to the current message."""
        from bor.tabs.message_index import FlagBar
        flag_bar = self.query_one("#flag-bar", FlagBar)
        flag_bar.ask(self._do_apply_flag)

    def _do_apply_flag(self, flag_key: str) -> None:
        """Actually apply the selected flag to current message. Uppercase = remove."""
        if not self._full_message:
            return
        
        msg = self._message_ref
        current_idx = self.bor_app._current_index
        
        # Check if removing (uppercase) or adding (lowercase)
        is_remove = flag_key.isupper()
        flag_lower = flag_key.lower()
        
        if flag_lower == "u":
            if is_remove:
                # Mark as read (remove unread)
                self.bor_app.mu.mark_read(self._full_message.path)
                if "unread" in msg.flags:
                    msg.flags.remove("unread")
                if "seen" not in msg.flags:
                    msg.flags.append("seen")
            else:
                # Mark as unread
                self.bor_app.mu.mark_unread(self._full_message.path)
                if "unread" not in msg.flags:
                    msg.flags.append("unread")
                if "seen" in msg.flags:
                    msg.flags.remove("seen")
        elif flag_lower == "n":
            if is_remove:
                # Remove new flag
                self.bor_app.mu.mark_read(self._full_message.path)
                if "new" in msg.flags:
                    msg.flags.remove("new")
            else:
                # Mark as new
                self.bor_app.mu.mark_unread(self._full_message.path)
                if "new" not in msg.flags:
                    msg.flags.append("new")
                if "unread" not in msg.flags:
                    msg.flags.append("unread")
        elif flag_lower == "f":
            if is_remove:
                # Remove flagged
                self.bor_app.mu.mark_flagged(self._full_message.path, False)
                if "flagged" in msg.flags:
                    msg.flags.remove("flagged")
            else:
                # Mark as flagged/important
                self.bor_app.mu.mark_flagged(self._full_message.path, True)
                if "flagged" not in msg.flags:
                    msg.flags.append("flagged")
        
        # Update the row in index
        from bor.tabs.message_index import MessageIndexWidget
        try:
            index_widget = self.bor_app.query_one(MessageIndexWidget)
            index_widget._update_row_style(current_idx)
        except Exception:
            pass

    def _confirm_action(self, prompt: str, callback: Callable) -> None:
        """Show confirmation bar and execute callback if confirmed."""
        from bor.tabs.message_index import ConfirmBar
        confirm_bar = self.query_one("#confirm-bar", ConfirmBar)
        confirm_bar.ask(prompt, callback)

    def action_archive(self) -> None:
        """Archive this message with confirmation."""
        if self._full_message:
            self._confirm_action("Archive this message?", self._do_archive)

    def _do_archive(self) -> None:
        """Actually archive the message."""
        if self._full_message:
            config = get_config()
            current_idx = self.bor_app._current_index
            self.bor_app.mu.move(self._full_message.path, config.folders.archive)
            
            # Refresh the index to remove archived message
            self._refresh_index_after_move(current_idx)
            
            # Move to next message or close
            if self.bor_app._current_index < len(self.bor_app._current_messages):
                next_msg = self.bor_app._current_messages[self.bor_app._current_index]
                self._message_ref = next_msg
                self._load_message()
            else:
                self.close_tab()

    def _refresh_index_after_move(self, removed_idx: int) -> None:
        """Refresh the index after a message was moved/deleted."""
        import asyncio
        from bor.tabs.message_index import MessageIndexWidget
        try:
            index_widget = self.bor_app.query_one(MessageIndexWidget)
            # Run async refresh
            asyncio.create_task(index_widget.search(index_widget.current_query))
        except Exception:
            pass

    def action_delete(self) -> None:
        """Delete this message with confirmation."""
        if self._full_message:
            self._confirm_action("Delete this message?", self._do_delete)

    def _do_delete(self) -> None:
        """Actually delete the message."""
        if self._full_message:
            config = get_config()
            current_idx = self.bor_app._current_index
            self.bor_app.mu.move(self._full_message.path, config.folders.trash)
            
            # Refresh the index to remove deleted message
            self._refresh_index_after_move(current_idx)
            
            # Move to next message or close
            if self.bor_app._current_index < len(self.bor_app._current_messages):
                next_msg = self.bor_app._current_messages[self.bor_app._current_index]
                self._message_ref = next_msg
                self._load_message()
            else:
                self.close_tab()

    def action_attachments(self) -> None:
        """View attachments."""
        if self._full_message and self._full_message.attachments:
            tab_id = self.get_tab_id()
            self.bor_app.open_attachments(self._full_message, replace_tab=tab_id)

    def action_toggle_full_headers(self) -> None:
        """Toggle full header display."""
        self.show_full_headers = not self.show_full_headers
        if self._full_message:
            header = self.query_one("#msg-header", MessageHeader)
            header.show_full = self.show_full_headers
            header.refresh()

    def on_click(self, event: events.Click) -> None:
        """Handle clicks on links."""
        link = getattr(event, "link", None)
        if link:
            self._open_url(link)
            self.notify(f"Opening: {link[:50]}...")
            event.prevent_default()
            event.stop()

    def _extract_urls(self) -> list[str]:
        """Extract URLs from the message content."""
        if not self._content:
            return []
        
        # URL regex pattern
        url_pattern = r'https?://[^\s<>"\')\]]+'
        urls = re.findall(url_pattern, self._content)
        
        # Also check HTML body for href links
        if self._full_message and self._full_message.body_html:
            href_pattern = r'href=["\']?(https?://[^"\'>\s]+)'
            html_urls = re.findall(href_pattern, self._full_message.body_html)
            urls.extend(html_urls)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for url in urls:
            # Clean up URL (remove trailing punctuation)
            url = url.rstrip('.,;:!?')
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)
        
        return unique_urls

    def action_open_url(self) -> None:
        """Open a URL from the message."""
        urls = self._extract_urls()
        
        if not urls:
            self.notify("No URLs found in message")
            return
        
        if len(urls) == 1:
            # Only one URL, open it directly
            self._open_url(urls[0])
            self.notify(f"Opening: {urls[0][:50]}...")
        else:
            # Multiple URLs - show selection
            picker = self.query_one("#url-picker", UrlPickerBar)
            picker.ask(urls, self._open_url_from_picker)

    def _open_url_from_picker(self, url: str) -> None:
        """Open a URL selected from the picker."""
        self._open_url(url)
        self.notify(f"Opening: {url[:50]}...")

    def _open_url(self, url: str) -> None:
        """Open a URL in the system browser."""
        try:
            webbrowser.open(url)
        except Exception:
            pass
