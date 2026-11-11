"""Read-only mail tools the LLM can call: search and read messages through mu.

Every tool runs on a worker thread (they spawn mu or parse whole messages) and
returns a `ToolResult`: the text the model sees plus a one-line summary for
the transcript. Nothing here changes the mailbox; reading a message does not
mark it read.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bor.mu import EmailAddress, EmailMessage, MuInterface

SEARCH_DEFAULT_LIMIT = 50
SEARCH_MAX_LIMIT = 200
MESSAGE_MAX_CHARS = 12_000
THREAD_MAX_CHARS = 40_000
THREAD_MAX_MESSAGES = 40
# Below this, a per-message share of the thread budget is too small to be useful
THREAD_MIN_CHARS_PER_MESSAGE = 1_500

QUOTE_MARKER = "[quoted text omitted]"
HISTORY_MARKER = "[earlier messages in the thread omitted]"


@dataclass
class ToolResult:
    """What a tool call produced."""

    content: str  # sent to the model
    summary: str  # one line for the transcript
    error: bool = False


class ToolError(Exception):
    """A tool call that cannot be carried out; the message goes back to the model."""


class MessageHandles:
    """Short names (m1, m2, ...) for the messages the model has been shown.

    Message-IDs are long and easy for a model to garble. A handle it was given
    either resolves or fails loudly, and costs a fraction of the tokens.
    """

    def __init__(self) -> None:
        self._messages: dict[str, EmailMessage] = {}
        self._by_identity: dict[str, str] = {}

    def handle_for(self, message: EmailMessage) -> str:
        """Return the message's handle, assigning the next one if it is new."""
        identity = message.msgid or message.path
        handle = self._by_identity.get(identity)
        if handle is None:
            handle = f"m{len(self._by_identity) + 1}"
            self._by_identity[identity] = handle
        # Keep the latest copy: its path and flags are the freshest
        self._messages[handle] = message
        return handle

    def get(self, handle: str) -> EmailMessage | None:
        """Look up a handle, tolerating stray whitespace, brackets and case."""
        return self._messages.get(handle.strip().strip("[]()").lower())

    def clear(self) -> None:
        """Forget all handles (a new conversation)."""
        self._messages.clear()
        self._by_identity.clear()


# Tool schemas in the OpenAI function-calling format
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_mail",
            "description": (
                "Search the user's mail with a mu query. Returns one line per message, "
                "newest first: handle | date | from -> to | subject | flags | folder."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "mu query"},
                    "limit": {
                        "type": "integer",
                        "description": (
                            f"Maximum messages to return (default {SEARCH_DEFAULT_LIMIT}, "
                            f"at most {SEARCH_MAX_LIMIT})"
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_message",
            "description": (
                "Read one message: headers, attachment names and body text. Quoted "
                "earlier messages are left out unless include_quoted is true."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Message handle, e.g. m3"},
                    "include_quoted": {
                        "type": "boolean",
                        "description": "Keep quoted text from earlier messages (default false)",
                    },
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_thread",
            "description": (
                "Read the whole conversation a message belongs to, oldest first, "
                "with quoted text left out. Prefer this over reading replies one by one."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Handle of any message in the thread"},
                },
                "required": ["id"],
            },
        },
    },
]


class MailTools:
    """Carries out the model's tool calls against mu."""

    def __init__(self, mu: MuInterface, handles: MessageHandles) -> None:
        self.mu = mu
        self.handles = handles
        self._handlers: dict[str, Callable[[dict[str, Any]], ToolResult]] = {
            "search_mail": self._search_mail,
            "read_message": self._read_message,
            "read_thread": self._read_thread,
        }

    @property
    def definitions(self) -> list[dict[str, Any]]:
        """Tool schemas to send with each request."""
        return TOOL_DEFINITIONS

    def run(self, name: str, arguments: str) -> ToolResult:
        """Run one tool call. Blocking: call it from a worker thread.

        Never raises: problems become an error result the model can react to.
        """
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError as e:
            return _error(f"{name}: arguments are not valid JSON ({e})")
        if not isinstance(args, dict):
            return _error(f"{name}: arguments must be a JSON object")
        handler = self._handlers.get(name)
        if handler is None:
            return _error(f"Unknown tool {name!r}")
        try:
            return handler(args)
        except ToolError as e:
            return _error(f"{name}: {e}")
        except Exception as e:  # a bug or a mu failure must not end the conversation
            return _error(f"{name} failed: {type(e).__name__}: {e}")

    # ------------------------------------------------------------------
    # Tools

    def _search_mail(self, args: dict[str, Any]) -> ToolResult:
        query = str(args.get("query", "")).strip()
        if not query:
            raise ToolError("query is required")
        limit = _int_arg(args, "limit", SEARCH_DEFAULT_LIMIT, 1, SEARCH_MAX_LIMIT)

        # A search right after an archive or flag change must see it
        self.mu.wait_for_reindex()
        # One extra result tells us whether the list was cut off
        found = self.mu.find(query, maxnum=limit + 1, threads=False, descending=True)
        more = len(found) > limit
        found = found[:limit]

        if not found:
            content = "No messages match. (A malformed query also returns nothing.)"
        else:
            lines = [self._summary_line(msg) for msg in found]
            note = " (more match: narrow the query or raise limit)" if more else ""
            content = f"{len(found)} messages{note}:\n" + "\n".join(lines)
        count = f"{len(found)}{'+' if more else ''}"
        return ToolResult(content, f"search: {query} → {count}")

    def _read_message(self, args: dict[str, Any]) -> ToolResult:
        handle, msg = self._resolve(args.get("id"))
        include_quoted = bool(args.get("include_quoted", False))
        full = self._view(msg)
        body = message_body_text(full, keep_quoted=include_quoted)
        body = _cap(body, MESSAGE_MAX_CHARS)
        content = f"{self._headers(handle, msg, full)}\n\n{body}"
        return ToolResult(content, f"read: {_describe(msg)}")

    def _read_thread(self, args: dict[str, Any]) -> ToolResult:
        handle, msg = self._resolve(args.get("id"))
        self.mu.wait_for_reindex()
        thread = self.mu.find_thread(msg) or [msg]
        thread.sort(key=lambda m: _sort_date(m.date))

        omitted = max(0, len(thread) - THREAD_MAX_MESSAGES)
        thread = thread[omitted:]
        per_message = max(THREAD_MIN_CHARS_PER_MESSAGE, THREAD_MAX_CHARS // len(thread))

        parts = []
        if omitted:
            parts.append(f"[{omitted} older messages in this thread not shown]")
        for item in thread:
            item_handle = self.handles.handle_for(item)
            try:
                full = self._view(item)
            except ToolError as e:
                parts.append(f"=== {self._summary_line(item)} ===\n[{e}]")
                continue
            body = _cap(message_body_text(full, keep_quoted=False), per_message)
            parts.append(f"=== {self._summary_line(item, item_handle)} ===\n{body}")
        content = f"Thread of {len(thread) + omitted} messages:\n\n" + "\n\n".join(parts)
        total = len(thread) + omitted
        noun = "message" if total == 1 else "messages"
        return ToolResult(content, f"thread: {_describe(msg)} → {total} {noun}")

    # ------------------------------------------------------------------
    # Helpers

    def _resolve(self, handle: Any) -> tuple[str, EmailMessage]:
        if not isinstance(handle, str) or not handle.strip():
            raise ToolError("id is required (a handle such as m3)")
        msg = self.handles.get(handle)
        if msg is None:
            raise ToolError(f"unknown message handle {handle!r}; use handles from search results")
        return handle.strip().strip("[]()").lower(), msg

    def _view(self, msg: EmailMessage) -> EmailMessage:
        """Parse the full message without marking it read."""
        full = self.mu.view(msg.path, mark_as_read=False, msgid=msg.msgid)
        if full is None:
            raise ToolError(f"message {msg.subject!r} could not be read (moved or deleted?)")
        return full

    def _summary_line(self, msg: EmailMessage, handle: str | None = None) -> str:
        handle = handle or self.handles.handle_for(msg)
        recipients = _short_addresses(msg.to_addrs)
        sender = _address(msg.from_addr)
        parties = f"{sender} -> {recipients}" if recipients else sender
        flags = ", ".join(_flag_words(msg)) or "-"
        return " | ".join(
            [
                handle,
                _format_date(msg.date),
                parties,
                msg.subject or "(no subject)",
                flags,
                msg.maildir or "-",
            ]
        )

    def _headers(self, handle: str, msg: EmailMessage, full: EmailMessage) -> str:
        lines = [
            f"Message {handle}",
            f"From: {_address(full.from_addr)}",
            f"To: {_addresses(full.to_addrs)}",
        ]
        if full.cc_addrs:
            lines.append(f"Cc: {_addresses(full.cc_addrs)}")
        lines += [
            f"Date: {_format_date(full.date or msg.date)}",
            f"Subject: {full.subject or msg.subject}",
            f"Folder: {msg.maildir or '-'}",
            f"Flags: {', '.join(_flag_words(msg)) or '-'}",
        ]
        if full.attachments:
            names = ", ".join(
                f"{a.get('filename', 'attachment')} ({a.get('content_type', '?')})"
                for a in full.attachments
            )
            lines.append(f"Attachments: {names}")
        event = full.calendar_event
        if event is not None:
            when = f"{event.start} – {event.end}" if event.end else f"{event.start}"
            lines.append(
                f"Calendar {event.method.lower() or 'event'}: {event.summary} | {when}"
                + (f" | {event.location}" if event.location else "")
                + (f" | organizer {event.organizer}" if event.organizer else "")
            )
        return "\n".join(lines)


def message_body_text(msg: EmailMessage, keep_quoted: bool = False) -> str:
    """The message body as plain text, the way bor's message view shows it."""
    if msg.body_txt:
        text = msg.body_txt
    elif msg.body_html:
        # Imported here: the message tab module pulls in the widget stack
        from bor.tabs.message import html_to_text

        text = html_to_text(msg.body_html)
    else:
        text = ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not keep_quoted:
        is_forward = bool(re.match(r"\s*(fwd?|fw)\s*:", msg.subject or "", re.I))
        text = strip_quoted(text, cut_history=not is_forward)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text or "(no text body)"


# Outlook-style quoted history: everything after one of these is earlier mail
_HISTORY_PATTERNS = [
    re.compile(r"^[ \t]*-{3,}[ \t]*Original Message[ \t]*-{3,}[ \t]*$", re.I | re.M),
    re.compile(r"^[ \t]*\**From:\**[ \t].*\n[ \t]*\**Sent:\**[ \t]", re.I | re.M),
]


def strip_quoted(text: str, cut_history: bool = True) -> str:
    """Drop quoted earlier messages from a body.

    `>`-quoted runs become one marker line (the reply's own text between
    quotes is kept), along with the "On ... wrote:" line introducing them.
    With `cut_history`, an Outlook-style history block ("-----Original
    Message-----", or From:/Sent: headers) and everything after it goes too;
    pass False for forwards, where that block is the content.
    """
    if cut_history:
        cut = min((m.start() for p in _HISTORY_PATTERNS if (m := p.search(text))), default=-1)
        if cut > 0:
            text = text[:cut].rstrip() + f"\n\n{HISTORY_MARKER}"

    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if not lines[i].lstrip().startswith(">"):
            out.append(lines[i])
            i += 1
            continue
        _drop_attribution(out)
        out.append(QUOTE_MARKER)
        # Skip the quote run, including blank lines inside it
        while i < len(lines) and (lines[i].lstrip().startswith(">") or not lines[i].strip()):
            if not lines[i].strip():
                # A blank line ends the run unless more quoted lines follow
                j = i
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j >= len(lines) or not lines[j].lstrip().startswith(">"):
                    break
            i += 1
    return "\n".join(out)


def _drop_attribution(out: list[str]) -> None:
    """Remove a trailing "On <date>, <name> wrote:" (possibly wrapped) from `out`.

    Blank lines between it and the quote go with it; otherwise they stay.
    """
    end = len(out)
    while end and not out[end - 1].strip():
        end -= 1
    if not end or not out[end - 1].rstrip().lower().endswith("wrote:"):
        return
    start = end - 1
    # Mail clients wrap long attributions: "On ..., Alice <a@x>\nwrote:"
    if not out[start].lstrip().lower().startswith("on ") and start:
        if out[start - 1].lstrip().lower().startswith("on "):
            start -= 1
    del out[start:]


def _error(message: str) -> ToolResult:
    return ToolResult(f"Error: {message}", message, error=True)


def _int_arg(args: dict[str, Any], name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(args.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(value, high))


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"\n[… {len(text) - limit} more characters not shown]"


def _sort_date(value: datetime | None) -> float:
    return value.timestamp() if value else 0.0


def _format_date(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "-"


def _address(addr: EmailAddress | None) -> str:
    if addr is None:
        return "-"
    if addr.name and addr.email:
        return f"{addr.name} <{addr.email}>"
    return addr.name or addr.email or "-"


def _addresses(addrs: list[EmailAddress]) -> str:
    return ", ".join(_address(a) for a in addrs) or "-"


def _short_addresses(addrs: list[EmailAddress], limit: int = 2) -> str:
    """First few recipients by name (or address), then "+N"."""
    names = [a.name or a.email for a in addrs if a.name or a.email]
    shown = ", ".join(names[:limit])
    if len(names) > limit:
        shown += f" +{len(names) - limit}"
    return shown


def _flag_words(msg: EmailMessage) -> list[str]:
    words = []
    if msg.is_unread:
        words.append("unread")
    if msg.is_replied:
        words.append("replied")
    if msg.is_forwarded:
        words.append("forwarded")
    if msg.is_flagged:
        words.append("flagged")
    if "attach" in msg.flags:
        words.append("attachment")
    if "draft" in msg.flags:
        words.append("draft")
    return words


def _describe(msg: EmailMessage) -> str:
    """Short human description of a message for the transcript."""
    sender = msg.from_addr.name or msg.from_addr.email if msg.from_addr else ""
    date = msg.date.strftime("%b %d, %Y") if msg.date else ""
    details = ", ".join(part for part in (sender, date) if part)
    subject = msg.subject or "(no subject)"
    return f'"{subject}" ({details})' if details else f'"{subject}"'
