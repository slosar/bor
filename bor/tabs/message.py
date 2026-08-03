"""
Message View tab for Bor email reader.

Displays a single email message with headers and body.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import re
import tempfile
import webbrowser
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Optional, Union

from rich.text import Text

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, ScrollableContainer
from textual.widgets import Static, Label, Markdown
from textual.reactive import reactive

from bor.tabs.base import BaseTab
from bor.ical import CalendarEvent
from bor.mu import EmailMessage, MuInterface
from bor.config import get_config


_URL_RE = re.compile(r'(https?://\S+)')


def _make_body_text(content: str) -> Text:
    """Build a Rich Text for the message body with clickable URL spans.

    The Text is constructed programmatically via `.append()` so user content
    is never parsed as Rich/Textual markup. This avoids markup-injection
    crashes on messages containing characters the parser treats specially
    (stray `[`, `[/...]` look-alikes, quotes inside URLs, etc.).
    """
    text = Text()
    parts = _URL_RE.split(content)
    for i, part in enumerate(parts):
        if not part:
            continue
        if i % 2 == 1:  # URL
            url = part.rstrip('.,;:!?)]>')
            trailing = part[len(url):]
            # If the prior chunk ends with `[` (style: `[https://...]`), pull
            # the bracket into the link span so it's part of the clickable
            # affordance, matching the prior behavior.
            if text.plain.endswith("["):
                text.right_crop(1)
                text.append("[" + url, style=f"link {url}")
            else:
                text.append(url, style=f"link {url}")
            if trailing:
                text.append(trailing)
        else:
            text.append(part)
    return text


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


_METHOD_TITLES = {
    "REQUEST": "Calendar Invitation",
    "CANCEL": "Calendar Invitation — CANCELLED",
    "REPLY": "Calendar Reply",
    "COUNTER": "Calendar Counter-Proposal",
    "PUBLISH": "Calendar Event",
}


def _cal_day(d: Union[datetime, date]) -> str:
    """Format the date portion, e.g. 'Wednesday, June 24, 2026' (no leading zero)."""
    return d.strftime("%A, %B ") + str(d.day) + d.strftime(", %Y")


def _cal_clock(dt: datetime) -> str:
    """Format a 12-hour clock time, e.g. '9:30 AM' (platform-independent)."""
    hour = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{hour}:{dt.minute:02d} {ampm}"


def _cal_offset(dt: datetime) -> str:
    """Format a UTC offset, e.g. 'UTC-04:00'. Empty for naive datetimes."""
    off = dt.utcoffset()
    if off is None:
        return ""
    total = int(off.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"UTC{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"


def _cal_tz_label(dt: datetime) -> str:
    """Build a timezone label like 'EDT (UTC-04:00)', or 'UTC-04:00', or ''."""
    abbrev = dt.strftime("%Z") if dt.tzinfo else ""
    offset = _cal_offset(dt)
    if abbrev and offset:
        return f"{abbrev} ({offset})"
    return abbrev or offset


def _cal_when_lines(ev: CalendarEvent) -> list[str]:
    """Build the human-readable 'When' line(s) for an event."""
    start = ev.start
    end = ev.end
    if start is None:
        return []

    if ev.all_day:
        # All-day DTEND is exclusive; subtract a day so a 1-day event reads as
        # a single date rather than spanning into the next morning.
        if end is not None and (end - start).days > 1:
            from datetime import timedelta
            last = end - timedelta(days=1)
            return [f"{_cal_day(start)}  →  {_cal_day(last)}  (all day)"]
        return [f"{_cal_day(start)}  (all day)"]

    # Timed event
    tz = _cal_tz_label(start)
    tz_suffix = f" {tz}" if tz else ""

    if end is not None and end.date() != start.date():
        return [
            f"{_cal_day(start)} · {_cal_clock(start)}",
            f"  through {_cal_day(end)} · {_cal_clock(end)}{tz_suffix}",
        ]

    if end is not None:
        return [f"{_cal_day(start)} · {_cal_clock(start)} – {_cal_clock(end)}{tz_suffix}"]
    return [f"{_cal_day(start)} · {_cal_clock(start)}{tz_suffix}"]


def _cal_local_line(ev: CalendarEvent) -> Optional[str]:
    """Return a 'your local time' line if it differs from the invite's timezone."""
    start = ev.start
    if ev.all_day or not isinstance(start, datetime) or start.tzinfo is None:
        return None
    local_tz = datetime.now().astimezone().tzinfo
    local_start = start.astimezone(local_tz)
    if local_start.utcoffset() == start.utcoffset():
        return None  # Same offset → identical wall-clock time, nothing to add.

    tz = _cal_tz_label(local_start)
    tz_suffix = f" {tz}" if tz else ""
    end = ev.end
    if isinstance(end, datetime):
        local_end = end.astimezone(local_tz)
        if local_end.date() != local_start.date():
            return (
                f"{_cal_day(local_start)} · {_cal_clock(local_start)} – "
                f"{_cal_day(local_end)} · {_cal_clock(local_end)}{tz_suffix}"
            )
        return (
            f"{_cal_day(local_start)} · "
            f"{_cal_clock(local_start)} – {_cal_clock(local_end)}{tz_suffix}"
        )
    return f"{_cal_day(local_start)} · {_cal_clock(local_start)}{tz_suffix}"


def format_calendar_event(ev: CalendarEvent) -> Text:
    """Render a calendar invite as a styled Rich Text block.

    Built programmatically via `.append()` so user-supplied values (summary,
    location, organizer) are never interpreted as Rich/Textual markup.
    """
    text = Text()
    title = _METHOD_TITLES.get(ev.method, "Calendar Invitation")
    text.append(f"📅  {title}", style="bold")

    def add_row(label: str, value: str) -> None:
        if not value:
            return
        text.append("\n")
        text.append(label, style="bold")
        text.append(value)

    if ev.summary:
        add_row("Event:      ", ev.summary)

    when_lines = _cal_when_lines(ev)
    if when_lines:
        add_row("When:       ", when_lines[0])
        for extra in when_lines[1:]:
            text.append("\n")
            text.append(" " * 12)
            text.append(extra)

    local_line = _cal_local_line(ev)
    if local_line:
        add_row("Your time:  ", local_line)

    if ev.recurrence:
        add_row("Repeats:    ", ev.recurrence)

    add_row("Where:      ", ev.location)
    add_row("Organizer:  ", ev.organizer)

    if ev.status:
        add_row("Status:     ", ev.status.capitalize())

    return text


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

    def _format_headers(self) -> Text:
        """Format headers as a Rich Text.

        Built programmatically via `.append()` so user-supplied header values
        (subjects, names, message-ids, etc.) can never be interpreted as
        markup. Static.update accepts a Text directly.
        """
        text = Text()
        first = True

        def add_row(label: str, value: str) -> None:
            nonlocal first
            if not first:
                text.append("\n")
            first = False
            text.append(label, style="bold")
            text.append(value)

        add_row("From:    ", str(self.message.from_addr))

        # Show effective reply address when it differs from From
        if self.message.list_post_addr and self.message.list_post_addr.email:
            if self.message.list_post_addr.email != self.message.from_addr.email:
                add_row("List:    ", self.message.list_post_addr.email)
        elif (self.message.reply_to_addr and
                self.message.reply_to_addr.email != self.message.from_addr.email):
            add_row("Reply-To: ", str(self.message.reply_to_addr))

        add_row("To:      ", ", ".join(str(addr) for addr in self.message.to_addrs))

        if self.message.cc_addrs:
            add_row("CC:      ", ", ".join(str(addr) for addr in self.message.cc_addrs))

        if self.show_full and self.message.bcc_addrs:
            add_row("BCC:     ", ", ".join(str(addr) for addr in self.message.bcc_addrs))

        date_str = ""
        if self.message.date:
            date_str = self.message.date.strftime("%Y-%m-%d %H:%M:%S %Z")
        add_row("Date:    ", date_str)

        add_row("Subject: ", self.message.subject)

        if self.message.attachments:
            count = len(self.message.attachments)
            add_row("Attach:  ", f"{count} attachment(s)")

        if self.show_full:
            # Blank visual separator: finish previous line + one empty line.
            text.append("\n\n")
            first = True  # next add_row should not prepend another newline

            if self.message.msgid:
                add_row("Message-ID: ", self.message.msgid)
            if self.message.in_reply_to:
                add_row("In-Reply-To: ", self.message.in_reply_to)
            if self.message.references:
                n = len(self.message.references)
                sample = " ".join(self.message.references[-2:])
                suffix = f" (… {n} total)" if n > 2 else ""
                add_row("References: ", sample + suffix)

            if self.message.priority and self.message.priority != "normal":
                add_row("Priority:   ", self.message.priority)

            if self.message.size:
                size = self.message.size
                if size >= 1024 * 1024:
                    size_str = f"{size / (1024 * 1024):.1f} MB"
                elif size >= 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size} B"
                add_row("Size:       ", size_str)

            if self.message.maildir:
                add_row("Folder:     ", self.message.maildir)

            if self.message.flags:
                add_row("Flags:      ", ", ".join(self.message.flags))

            if self.message.tags:
                add_row("Tags:       ", ", ".join(self.message.tags))

            for hdr_name, val in self.message.extra_headers.items():
                display_val = val if len(val) <= 100 else val[:97] + "…"
                add_row(f"{hdr_name}: ", display_val)

        return text


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
        Binding("v", "view_in_browser", "View in Browser"),
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

    MessageViewWidget .calendar-info {
        display: none;
        background: $primary-darken-2;
        color: $text;
        border: round $primary;
        padding: 0 1;
        margin: 1 0;
    }

    MessageViewWidget .calendar-info.visible {
        display: block;
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
            yield Static("", id="calendar-info", classes="calendar-info")
            yield Static("", id="attachment-info", classes="attachment-info")
            yield Static("Loading...", id="msg-body")
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
        """Start loading the full message.

        Parsing a message with `email.parser` costs 100-200ms for a typical
        mail and marking it read spawns mu subprocesses, so all of it runs on a
        worker thread. Headers we already have are shown immediately.
        """
        ref = self._message_ref
        self._show_pending(ref)
        self.run_worker(
            self._load_message_worker(ref),
            name="load-message",
            group=f"load-message-{id(self)}",
            exclusive=True,
        )

    def _show_pending(self, ref: EmailMessage) -> None:
        """Render what we know from the index row while the body loads."""
        try:
            self.query_one("#msg-header", MessageHeader).update_message(ref)
            self.query_one("#msg-body", Static).update("Loading...")
            self.query_one("#calendar-info", Static).remove_class("visible")
            self.query_one("#attachment-info", Static).display = False
        except Exception:
            pass

    async def _load_message_worker(self, ref: EmailMessage) -> None:
        """Parse and format the message off the UI thread, then render it."""
        full_message, content, body_text = await asyncio.to_thread(self._read_message, ref)

        # A newer load may have superseded this one, or the tab may be gone.
        if not self.is_mounted or self._message_ref is not ref:
            return

        self._apply_message(ref, full_message, content, body_text)

    def _read_message(self, ref: EmailMessage) -> tuple[Optional[EmailMessage], str, Optional[Text]]:
        """Do the expensive part of loading a message. Runs on a worker thread.

        Everything here is CPU/IO bound and touches no widgets: MIME parsing,
        the HTML-to-text conversion, and building the Rich Text for the body.
        """
        # mu.view() also renames the file to drop the "new"/unread flag.
        full_message = self.bor_app.mu.view(ref.path, True, ref.msgid)
        if full_message is None:
            return None, "", None

        if full_message.body_txt:
            content = full_message.body_txt
        elif full_message.body_html:
            content = html_to_text(full_message.body_html)
        else:
            content = "(No message content)"

        try:
            body_text = _make_body_text(content)
        except Exception:
            body_text = Text(content)

        return full_message, content, body_text

    def _apply_message(
        self,
        ref: EmailMessage,
        full_message: Optional[EmailMessage],
        content: str,
        body_text: Optional[Text],
    ) -> None:
        """Render a loaded message. Runs on the UI thread."""
        self._full_message = full_message

        if self._full_message:
            if self._full_message.path != ref.path:
                ref.path = self._full_message.path

            if "unread" in ref.flags:
                ref.flags.remove("unread")
            if "new" in ref.flags:
                ref.flags.remove("new")
            if "seen" not in ref.flags:
                ref.flags.append("seen")

            self._read_message_indices.add(self.bor_app._current_index)

            header = self.query_one("#msg-header", MessageHeader)
            header.update_message(self._full_message)

            cal_info = self.query_one("#calendar-info", Static)
            if self._full_message.calendar_event:
                try:
                    cal_info.update(format_calendar_event(self._full_message.calendar_event))
                    cal_info.add_class("visible")
                except Exception:
                    cal_info.remove_class("visible")
            else:
                cal_info.remove_class("visible")

            attach_info = self.query_one("#attachment-info", Static)
            if self._full_message.attachments:
                count = len(self._full_message.attachments)
                attach_info.update(f"📎 {count} attachment(s) - Press 'z' to view")
                attach_info.display = True
            else:
                attach_info.display = False

            self._content = content

            body = self.query_one("#msg-body", Static)
            body.update(body_text if body_text is not None else Text(content))

            subject = self._full_message.subject
            title = subject[:20] + "..." if len(subject) > 20 else subject
            self.update_tab_title(title)
        else:
            self.query_one("#msg-body", Static).update("Error: Could not load message")

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
        current_msgid = self._message_ref.msgid.strip().strip("<>")
        current_idx = None
        for idx, msg in enumerate(self.bor_app._current_messages):
            if msg.msgid.strip().strip("<>") == current_msgid:
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
        current_msgid = self._message_ref.msgid.strip().strip("<>")
        current_idx = None
        for idx, msg in enumerate(self.bor_app._current_messages):
            if msg.msgid.strip().strip("<>") == current_msgid:
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
            header.update_message(self._full_message)

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

    def action_view_in_browser(self) -> None:
        """Open the current message as HTML in the system browser."""
        if not self._full_message:
            self.notify("No message loaded")
            return

        msg = self._full_message

        if msg.body_html:
            body_html = msg.body_html
            # If the HTML doesn't have a full document structure, wrap it
            if "<html" not in body_html.lower():
                body_html = f"<html><body>{body_html}</body></html>"
        else:
            # Wrap plain text in a minimal HTML page
            plain = msg.body_txt or "(No message content)"
            escaped = html.escape(plain)
            body_html = (
                "<html><body>"
                f"<pre style='font-family:monospace;white-space:pre-wrap'>{escaped}</pre>"
                "</body></html>"
            )

        # Build header block to prepend
        from_str = html.escape(str(msg.from_addr))
        to_str = html.escape(", ".join(str(a) for a in msg.to_addrs))
        date_str = html.escape(msg.date.strftime("%Y-%m-%d %H:%M:%S %Z") if msg.date else "")
        subject_str = html.escape(msg.subject)

        header_html = (
            "<div style='font-family:sans-serif;border-bottom:1px solid #ccc;"
            "padding:8px;margin-bottom:12px;background:#f5f5f5'>"
            f"<b>From:</b> {from_str}<br>"
            f"<b>To:</b> {to_str}<br>"
            f"<b>Date:</b> {date_str}<br>"
            f"<b>Subject:</b> {subject_str}"
            "</div>"
        )

        # Inject header just after <body> (or prepend if not found)
        lower = body_html.lower()
        body_tag_end = lower.find("<body")
        if body_tag_end != -1:
            body_tag_end = body_html.find(">", body_tag_end) + 1
            full_html = body_html[:body_tag_end] + header_html + body_html[body_tag_end:]
        else:
            full_html = header_html + body_html

        try:
            config = get_config()
            tmp_dir_str = config.html.browser_tmp_dir
            tmp_dir = (
                Path(tmp_dir_str).expanduser()
                if tmp_dir_str
                else Path(tempfile.gettempdir())
            )
            tmp_dir.mkdir(parents=True, exist_ok=True)

            # Use a deterministic filename based on the message identifier so
            # that re-opening the same message reuses the file instead of
            # accumulating many bor_msg_*.html files.
            key = msg.msgid or (str(msg.docid) if msg.docid else full_html)
            file_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
            tmp_path = tmp_dir / f"bor_msg_{file_hash}.html"
            tmp_path.write_text(full_html, encoding="utf-8")
            webbrowser.open(tmp_path.as_uri())
            self.notify("Message opened in browser")
        except Exception as e:
            self.notify(f"Could not open browser: {e}")
