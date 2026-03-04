"""Tests for mu interface module."""

import tempfile
from pathlib import Path
from datetime import datetime

import pytest

from bor.mu import EmailAddress, EmailMessage, MuInterface


class TestEmailAddress:
    """Tests for EmailAddress class."""

    def test_empty_address(self):
        """Test empty email address."""
        addr = EmailAddress()
        assert addr.name == ""
        assert addr.email == ""
        assert str(addr) == ""

    def test_email_only(self):
        """Test email address without name."""
        addr = EmailAddress(email="test@example.com")
        assert addr.name == ""
        assert addr.email == "test@example.com"
        assert str(addr) == "test@example.com"

    def test_name_and_email(self):
        """Test email address with name."""
        addr = EmailAddress(name="John Doe", email="john@example.com")
        assert addr.name == "John Doe"
        assert addr.email == "john@example.com"
        assert str(addr) == "John Doe <john@example.com>"

    def test_name_with_comma(self):
        """Test email address with comma in name (should be quoted)."""
        addr = EmailAddress(name="Smith, Jane", email="jsmith@example.com")
        assert addr.name == "Smith, Jane"
        assert addr.email == "jsmith@example.com"
        assert str(addr) == '"Smith, Jane" <jsmith@example.com>'

    def test_name_with_quotes(self):
        """Test email address with quotes in name (should be escaped)."""
        addr = EmailAddress(name='Joe "The Boss" Smith', email="joe@example.com")
        assert str(addr) == '"Joe \\"The Boss\\" Smith" <joe@example.com>'

    def test_name_with_multiple_special_chars(self):
        """Test email address with multiple special characters."""
        addr = EmailAddress(name="Smith, Dr.", email="smith@example.com")
        assert str(addr) == '"Smith, Dr." <smith@example.com>'

    def test_comma_in_name_parses_correctly(self):
        """Test that comma in name parses correctly with email.utils."""
        import email.utils

        # Create address with comma in name
        addr = EmailAddress(name="Smith, Jane", email="jsmith@example.com")
        addr_str = str(addr)

        # Parse it back using email.utils.getaddresses
        parsed = email.utils.getaddresses([addr_str])

        # Should parse as single address with correct name and email
        assert len(parsed) == 1
        name, email = parsed[0]
        assert name == "Smith, Jane"
        assert email == "jsmith@example.com"

    def test_from_mu_string(self):
        """Test parsing from string."""
        addr = EmailAddress.from_mu("John Doe <john@example.com>")
        assert addr.name == "John Doe"
        assert addr.email == "john@example.com"

    def test_from_mu_quoted_string(self):
        """Test parsing from string with quoted name (from mu output)."""
        # Mu may provide names with quotes if they contain special chars
        addr = EmailAddress.from_mu('"Brown, Adam" <abrown@example.org>')
        assert addr.name == "Brown, Adam"
        assert addr.email == "abrown@example.org"
        # When converted back to string, should have single layer of quotes
        assert str(addr) == '"Brown, Adam" <abrown@example.org>'

    def test_from_mu_escaped_quotes(self):
        """Test parsing from string with escaped quotes in name."""
        addr = EmailAddress.from_mu(r'"Joe \"The Boss\" Smith" <joe@example.com>')
        assert addr.name == 'Joe "The Boss" Smith'
        assert addr.email == "joe@example.com"

    def test_from_mu_email_only(self):
        """Test parsing email-only string."""
        addr = EmailAddress.from_mu("john@example.com")
        assert addr.name == ""
        assert addr.email == "john@example.com"

    def test_from_mu_dict(self):
        """Test parsing from dictionary."""
        data = {"name": "Jane Doe", "email": "jane@example.com"}
        addr = EmailAddress.from_mu(data)
        assert addr.name == "Jane Doe"
        assert addr.email == "jane@example.com"

    def test_from_mu_none(self):
        """Test parsing None."""
        addr = EmailAddress.from_mu(None)
        assert addr.name == ""
        assert addr.email == ""

    def test_header_parsing_with_comma_in_name(self):
        """Test that email headers with commas in names parse correctly.

        Regression test for bug where splitting on comma would break
        quoted names like "Smith, Alice" <alice@example.com> into two
        malformed addresses.
        """
        import email.utils as email_utils

        # Simulate what happens when reading a To: header from an email file
        to_header = '"Smith, Alice" <alice@example.com>'

        # Parse using email.utils.getaddresses (the correct way)
        parsed_addrs = email_utils.getaddresses([to_header])
        to_addrs = [EmailAddress(name=name, email=email)
                    for name, email in parsed_addrs if email]

        # Should result in exactly one address with correct name
        assert len(to_addrs) == 1
        assert to_addrs[0].name == "Smith, Alice"
        assert to_addrs[0].email == "alice@example.com"

        # Display should be properly formatted
        assert str(to_addrs[0]) == '"Smith, Alice" <alice@example.com>'

    def test_header_parsing_multiple_addresses_with_commas(self):
        """Test parsing multiple addresses where some have commas in names."""
        import email.utils as email_utils

        to_header = '"Smith, Alice" <alice@example.com>, "O\'Brien, Paul" <paul@example.org>, simple@example.com'

        parsed_addrs = email_utils.getaddresses([to_header])
        to_addrs = [EmailAddress(name=name, email=email)
                    for name, email in parsed_addrs if email]

        # Should result in exactly three addresses
        assert len(to_addrs) == 3
        assert to_addrs[0].name == "Smith, Alice"
        assert to_addrs[0].email == "alice@example.com"
        assert to_addrs[1].name == "O'Brien, Paul"
        assert to_addrs[1].email == "paul@example.org"
        assert to_addrs[2].name == ""
        assert to_addrs[2].email == "simple@example.com"


class TestEmailMessage:
    """Tests for EmailMessage class."""

    def test_empty_message(self):
        """Test empty message defaults."""
        msg = EmailMessage()
        assert msg.docid == 0
        assert msg.subject == ""
        assert msg.flags == []
        assert not msg.is_unread
        assert not msg.is_replied
        assert not msg.is_flagged

    def test_flags(self):
        """Test message flag properties."""
        msg = EmailMessage(flags=["unread", "flagged", "attach"])
        assert msg.is_unread
        assert msg.is_flagged
        assert msg.has_attachments
        assert not msg.is_replied
        assert not msg.is_forwarded

    def test_new_flag(self):
        """Test that 'new' flag counts as unread."""
        msg = EmailMessage(flags=["new"])
        assert msg.is_unread

    def test_passed_flag_is_forwarded(self):
        """Test that 'passed' flag means forwarded."""
        msg = EmailMessage(flags=["passed"])
        assert msg.is_forwarded

    def test_from_mu_json(self):
        """Test creating message from mu JSON output."""
        data = {
            "docid": 123,
            "msgid": "<msg123@example.com>",
            "path": "/mail/inbox/cur/123",
            "maildir": "/inbox",
            "subject": "Test Subject",
            "date": 1609459200,  # 2021-01-01 00:00:00
            "size": 1024,
            "from": [{"name": "Sender", "email": "sender@example.com"}],
            "to": [{"name": "Recipient", "email": "recipient@example.com"}],
            "flags": ["unread", "attach"],
            "priority": "high",
        }

        msg = EmailMessage.from_mu_json(data)
        assert msg.docid == 123
        assert msg.msgid == "<msg123@example.com>"
        assert msg.subject == "Test Subject"
        assert msg.size == 1024
        assert msg.from_addr.email == "sender@example.com"
        assert len(msg.to_addrs) == 1
        assert msg.is_unread
        assert msg.has_attachments
        assert msg.priority == "high"

    def test_from_mu_json_with_reply_to_list(self):
        """Test that Reply-To is parsed from mu JSON when present as a list."""
        data = {
            "from": [{"name": "Sender", "email": "sender@example.com"}],
            "to": [{"name": "Recipient", "email": "recipient@example.com"}],
            ":reply-to": [{"name": "Test List", "email": "list@example.org"}],
        }
        msg = EmailMessage.from_mu_json(data)
        assert msg.reply_to_addr is not None
        assert msg.reply_to_addr.email == "list@example.org"

    def test_from_mu_json_with_reply_to_dict(self):
        """Test that Reply-To is parsed when mu returns it as a dict (not list)."""
        data = {
            "from": [{"name": "Sender", "email": "sender@example.com"}],
            ":reply-to": {"name": "Test List", "email": "list@example.org"},
        }
        msg = EmailMessage.from_mu_json(data)
        assert msg.reply_to_addr is not None
        assert msg.reply_to_addr.email == "list@example.org"

    def test_from_mu_json_no_reply_to(self):
        """Test that reply_to_addr is None when Reply-To is absent."""
        data = {
            "from": [{"name": "Sender", "email": "sender@example.com"}],
        }
        msg = EmailMessage.from_mu_json(data)
        assert msg.reply_to_addr is None

    def test_from_mu_json_with_list_post(self):
        """Test that List-Post is parsed from mu JSON (mailing list emails).

        Models a mailing list where the sender's address is hidden: From shows
        the list address, Reply-To has the individual sender, List-Post has the
        list address.
        """
        data = {
            "from": [{":name": "'sender@example.com' via Test List", ":email": "list@example.org"}],
            ":reply-to": [{":email": "sender@example.com", ":name": "sender@example.com"}],
            ":list-post": [{":email": "list@example.org"}],
        }
        msg = EmailMessage.from_mu_json(data)
        assert msg.list_post_addr is not None
        assert msg.list_post_addr.email == "list@example.org"
        # reply_to_addr points to the individual sender
        assert msg.reply_to_addr is not None
        assert msg.reply_to_addr.email == "sender@example.com"

    def test_view_reply_to_parsing(self):
        """Test that view() correctly parses Reply-To header from raw email."""
        import tempfile
        from unittest.mock import patch

        raw = (
            b"From: Alice Example <alice@example.com>\r\n"
            b"To: me@example.com\r\n"
            b"Subject: Test\r\n"
            b"Reply-To: Test List <list@example.org>\r\n"
            b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
            b"\r\n"
            b"Test body\r\n"
        )

        with tempfile.NamedTemporaryFile(suffix=".eml", delete=False, mode="wb") as f:
            f.write(raw)
            tmp_path = f.name

        try:
            mu = MuInterface()
            with patch.object(mu, "_run_mu", return_value=None):
                msg = mu.view(tmp_path, mark_as_read=False)

            assert msg is not None
            assert msg.from_addr.email == "alice@example.com"
            assert msg.reply_to_addr is not None
            assert msg.reply_to_addr.email == "list@example.org"
            assert msg.reply_to_addr.name == "Test List"
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_view_list_post_parsing(self):
        """Test view() handles mailing list format: From=list, Reply-To=individual, List-Post=list.

        This models the case where a mailing list hides the sender's address:
        From has the list address, Reply-To has the individual, List-Post has the list.
        Replies should go to the list (via List-Post), not the individual.
        """
        import tempfile
        from unittest.mock import patch

        raw = (
            b"From: \"'sender@example.com' via Test List\" <list@example.org>\r\n"
            b"To: Test List <list@example.org>\r\n"
            b"Subject: Some discussion topic\r\n"
            b"Reply-To: \"sender@example.com\" <sender@example.com>\r\n"
            b"List-Post: <https://groups.example.org/group/testlist/post>, <mailto:list@example.org>\r\n"
            b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
            b"\r\n"
            b"Test body\r\n"
        )

        with tempfile.NamedTemporaryFile(suffix=".eml", delete=False, mode="wb") as f:
            f.write(raw)
            tmp_path = f.name

        try:
            mu = MuInterface()
            with patch.object(mu, "_run_mu", return_value=None):
                msg = mu.view(tmp_path, mark_as_read=False)

            assert msg is not None
            # From has list address in angle brackets
            assert msg.from_addr.email == "list@example.org"
            # Reply-To points to individual sender
            assert msg.reply_to_addr is not None
            assert msg.reply_to_addr.email == "sender@example.com"
            # List-Post points to the list
            assert msg.list_post_addr is not None
            assert msg.list_post_addr.email == "list@example.org"
        finally:
            Path(tmp_path).unlink(missing_ok=True)


class TestMuInterface:
    """Tests for MuInterface class."""

    def test_init_default(self):
        """Test default initialization."""
        mu = MuInterface()
        assert mu.muhome is None

    def test_init_with_muhome(self):
        """Test initialization with custom muhome."""
        mu = MuInterface(muhome="/custom/mu")
        assert mu.muhome == "/custom/mu"

    def test_undo_empty_history(self):
        """Test undo with empty history."""
        mu = MuInterface()
        assert not mu.undo_move()
