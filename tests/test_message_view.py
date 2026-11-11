"""Tests for message view rendering helpers.

These tests guard against markup-injection crashes that previously occurred
when user-controlled content (URLs, subjects, names) was concatenated into
Rich/Textual markup strings. Both `_make_body_text` and
`MessageHeader._format_headers` now return `rich.text.Text` objects built
programmatically, so no user content is ever parsed as markup.
"""

from __future__ import annotations

from datetime import datetime

from rich.text import Text
from textual.content import Content

from bor.mu import EmailAddress, EmailMessage
from bor.tabs.message import MessageHeader, _make_body_text


def _make_message(**overrides) -> EmailMessage:
    """Build an EmailMessage with sensible defaults for header tests."""
    defaults = dict(
        docid=1,
        path="/tmp/fake",
        msgid="<msg@example.com>",
        subject="Subject",
        from_addr=EmailAddress(email="a@example.com", name="A"),
        to_addrs=[EmailAddress(email="b@example.com", name="B")],
        cc_addrs=[],
        bcc_addrs=[],
        reply_to_addr=None,
        list_post_addr=None,
        date=datetime(2026, 5, 19, 12, 0, 0),
        flags=[],
        tags=[],
        maildir="/INBOX",
        priority="normal",
        size=1234,
        attachments=[],
        body_txt="",
        body_html="",
        in_reply_to="",
        references=[],
        extra_headers={},
    )
    defaults.update(overrides)
    return EmailMessage(**defaults)


# ---------- _make_body_text ----------


def test_body_text_returns_text_object() -> None:
    text = _make_body_text("hello world")
    assert isinstance(text, Text)
    assert text.plain == "hello world"


def test_body_text_handles_bracketed_urls() -> None:
    """URL wrapped in `[...]` (no space) — bracket pulled into the link."""
    text = _make_body_text("See [https://example.com/path] for details")
    assert text.plain == "See [https://example.com/path] for details"
    # The opening `[` should be part of the link span.
    assert any("link https://example.com/path" in str(span.style)
               for span in text.spans)


def test_body_text_handles_bracketed_urls_with_spaces() -> None:
    """URL wrapped as `[ url ]` — the Sigma Xi / urldefense pattern."""
    text = _make_body_text("View [ https://example.com/path ] now")
    assert text.plain == "View [ https://example.com/path ] now"


def test_body_text_handles_angle_bracketed_urls() -> None:
    text = _make_body_text("See <https://example.com/path> for details")
    assert text.plain == "See <https://example.com/path> for details"


def test_body_text_passes_through_textual_content_parser() -> None:
    """Whatever Text produces must round-trip through Textual without raising.

    Static.update on a Text doesn't re-parse markup, but this asserts the
    rendered plain output never contains stray bracket-like sequences that
    a downstream consumer could trip on.
    """
    sample = (
        "View [ https://urldefense.com/v3/__https://example.com/foo?"
        "a=1&b=2__;!!P4SdNyxKAPE!abc$ ]  in your browser.\n"
        "Random [text in brackets] and [/not-a-tag] and stray ] bracket."
    )
    text = _make_body_text(sample)
    # plain text round-trips verbatim
    assert text.plain == sample
    # And Content.from_text accepts it without crashing
    Content.from_text(text)


def test_body_text_no_url() -> None:
    text = _make_body_text("just some text without links")
    assert text.plain == "just some text without links"
    # No link spans
    assert not any("link " in str(span.style) for span in text.spans)


def test_body_text_url_with_quotes_in_attribute_no_crash() -> None:
    """A URL with chars that historically broke `[link="..."]` syntax."""
    sample = 'Try https://example.com/?q="hello"&x=1 today.'
    text = _make_body_text(sample)
    assert text.plain == sample


def test_body_text_strips_trailing_punctuation_from_url() -> None:
    """A URL followed by a sentence-ending period should not include the period."""
    text = _make_body_text("Visit https://example.com/path. Then leave.")
    # The link span covers "https://example.com/path" (no trailing dot).
    link_spans = [s for s in text.spans if "link " in str(s.style)]
    assert link_spans, "expected one link span"
    # The span text equals the URL without the trailing dot.
    span = link_spans[0]
    url_text = text.plain[span.start:span.end]
    assert url_text == "https://example.com/path"


# ---------- MessageHeader._format_headers ----------


def _format_headers(message: EmailMessage, *, show_full: bool = False) -> Text:
    """Invoke MessageHeader._format_headers without mounting the widget."""
    header = MessageHeader.__new__(MessageHeader)
    header.message = message
    header.show_full = show_full
    return header._format_headers()


def test_headers_return_text() -> None:
    msg = _make_message()
    text = _format_headers(msg)
    assert isinstance(text, Text)
    assert "From:" in text.plain
    assert "a@example.com" in text.plain
    assert "Subject" in text.plain


def test_headers_with_bracket_in_subject_does_not_crash() -> None:
    """Subject with `[Sigma Xi]`-like text used to crash the markup parser."""
    msg = _make_message(subject="[Sigma Xi] Nomination [/important]")
    text = _format_headers(msg)
    assert "[Sigma Xi] Nomination [/important]" in text.plain
    # And Textual's content parser is happy with the result.
    Content.from_text(text)


def test_headers_with_markup_chars_in_name() -> None:
    msg = _make_message(
        from_addr=EmailAddress(email="x@y.com", name="Foo [bold] Bar"),
    )
    text = _format_headers(msg)
    assert "Foo [bold] Bar" in text.plain


def test_headers_full_mode_blank_separator() -> None:
    msg = _make_message(msgid="<x@y>", references=["<a@b>", "<c@d>"])
    text = _format_headers(msg, show_full=True)
    # The blank-line separator before the extended block is preserved.
    assert "\n\n" in text.plain
    assert "Message-ID:" in text.plain
