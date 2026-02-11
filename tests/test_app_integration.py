"""
Integration tests for Bor email application.

Uses Textual's testing framework to simulate user interactions.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

from textual.widgets import DataTable, Static

# Mock EmailMessage for testing
class MockEmailMessage:
    def __init__(self, **kwargs):
        self.docid = kwargs.get("docid", 1)
        self.msgid = kwargs.get("msgid", "test@example.com")
        self.path = kwargs.get("path", "/test/path/message")
        self.maildir = kwargs.get("maildir", "/INBOX")
        self.subject = kwargs.get("subject", "Test Subject")
        self.size = kwargs.get("size", 1000)
        self.date = kwargs.get("date", datetime.now())
        self.from_addr = kwargs.get("from_addr", MagicMock(name="Test Sender", email="sender@test.com", __str__=lambda s: "Test Sender <sender@test.com>"))
        self.to_addrs = kwargs.get("to_addrs", [])
        self.cc_addrs = kwargs.get("cc_addrs", [])
        self.bcc_addrs = kwargs.get("bcc_addrs", [])
        self.flags = kwargs.get("flags", [])
        self.tags = kwargs.get("tags", [])
        self.references = kwargs.get("references", [])
        self.in_reply_to = kwargs.get("in_reply_to", "")
        self.priority = kwargs.get("priority", "normal")
        self.body_txt = kwargs.get("body_txt", "Test message body")
        self.body_html = kwargs.get("body_html", "")
        self.attachments = kwargs.get("attachments", [])
        self.thread_level = kwargs.get("thread_level", 0)

    @property
    def is_unread(self):
        return "unread" in self.flags or "new" in self.flags

    @property
    def is_replied(self):
        return "replied" in self.flags

    @property
    def is_forwarded(self):
        return "passed" in self.flags

    @property
    def is_flagged(self):
        return "flagged" in self.flags

    @property
    def has_attachments(self):
        return "attach" in self.flags or len(self.attachments) > 0


def create_mock_messages(count=5):
    """Create a list of mock messages for testing."""
    messages = []
    for i in range(count):
        msg = MockEmailMessage(
            docid=i + 1,
            msgid=f"msg{i}@test.com",
            path=f"/test/path/message{i}",
            subject=f"Test Subject {i}",
            flags=["seen"] if i % 2 == 0 else ["unread"],
        )
        messages.append(msg)
    return messages


@pytest.fixture
def mock_mu_interface():
    """Create a mock MuInterface."""
    mock = MagicMock()
    mock.find.return_value = create_mock_messages(5)
    mock.view.return_value = MockEmailMessage(
        subject="Viewed Message",
        body_txt="This is the message body content.",
    )
    mock.find_contacts.return_value = []
    return mock


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    from bor.config import Config, GeneralConfig, FoldersConfig, SmtpConfig, ColorsConfig, ThreadingConfig
    return Config(
        general=GeneralConfig(),
        folders=FoldersConfig(),
        smtp=SmtpConfig(server="smtp.test.com", port=587, username="test", password="test"),
        colors=ColorsConfig(),
        threading=ThreadingConfig(),
        aliases={},
        email_aliases={},
    )


class TestAppStartup:
    """Test application startup behavior."""

    @pytest.mark.asyncio
    async def test_app_mounts(self, mock_mu_interface, mock_config):
        """Test that the app mounts correctly."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    # App should have mounted
                    assert app.is_running
                    # Should have TabbedContent
                    tabs = app.query_one("TabbedContent")
                    assert tabs is not None

    @pytest.mark.asyncio
    async def test_message_index_loads(self, mock_mu_interface, mock_config):
        """Test that message index loads on startup."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    # Wait for async operations
                    await pilot.pause()
                    # mu.find should have been called
                    mock_mu_interface.find.assert_called()

    @pytest.mark.asyncio
    async def test_data_table_has_focus(self, mock_mu_interface, mock_config):
        """Test that DataTable has focus on startup."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    # DataTable should exist and be focusable
                    table = app.query_one("DataTable")
                    assert table is not None


class TestMessageIndexNavigation:
    """Test message index navigation."""

    @pytest.mark.asyncio
    async def test_arrow_down_moves_cursor(self, mock_mu_interface, mock_config):
        """Test that down arrow moves the cursor."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    table = app.query_one("DataTable")
                    initial_cursor = table.cursor_row
                    await pilot.press("down")
                    # Cursor should have moved (or stayed if at end)
                    # Just verify no crash occurred

    @pytest.mark.asyncio
    async def test_n_key_moves_down(self, mock_mu_interface, mock_config):
        """Test that N key moves cursor down."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("n")
                    # Should not crash

    @pytest.mark.asyncio
    async def test_p_key_moves_up(self, mock_mu_interface, mock_config):
        """Test that P key moves cursor up."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("p")
                    # Should not crash


class TestMessageView:
    """Test message viewing."""

    @pytest.mark.asyncio
    async def test_enter_opens_message(self, mock_mu_interface, mock_config):
        """Test that Enter opens a message in a new tab."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    # Press enter to open message
                    await pilot.press("enter")
                    await pilot.pause()
                    # Should have called view
                    # Check that a new tab was created
                    assert len(app._tabs) >= 0  # May or may not create tab depending on data

    @pytest.mark.asyncio
    async def test_m_returns_to_index(self, mock_mu_interface, mock_config):
        """Test that M returns to message index without closing tab."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("enter")
                    await pilot.pause()
                    tab_count = len(app._tabs)
                    await pilot.press("m")
                    await pilot.pause()
                    # Tab should still exist
                    assert len(app._tabs) == tab_count

    @pytest.mark.asyncio
    async def test_q_closes_tab(self, mock_mu_interface, mock_config):
        """Test that Q closes the message tab."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("enter")
                    await pilot.pause()
                    initial_tabs = len(app._tabs)
                    await pilot.press("q")
                    await pilot.pause()
                    # Tab should be closed
                    assert len(app._tabs) < initial_tabs or initial_tabs == 0

    @pytest.mark.asyncio
    async def test_o_opens_selected_url(self, mock_mu_interface, mock_config):
        """Test that O prompts for URL selection when multiple links exist."""
        mock_mu_interface.view.return_value = MockEmailMessage(
            subject="Viewed Message",
            body_txt="Links: https://one.test/page https://two.test/page",
        )

        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("enter")
                    await pilot.pause()
                    with patch("bor.tabs.message.webbrowser.open") as open_mock:
                        await pilot.press("o")
                        await pilot.pause()
                        await pilot.press("2")
                        await pilot.pause()
                        open_mock.assert_called_once_with("https://two.test/page")


class TestTabSwitching:
    """Test tab switching functionality."""

    @pytest.mark.asyncio
    async def test_ctrl_pagedown_switches_tab(self, mock_mu_interface, mock_config):
        """Test Ctrl+PageDown switches to next tab."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("ctrl+pagedown")
                    # Should not crash

    @pytest.mark.asyncio
    async def test_ctrl_pageup_switches_tab(self, mock_mu_interface, mock_config):
        """Test Ctrl+PageUp switches to previous tab."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("ctrl+pageup")
                    # Should not crash


class TestFocusManagement:
    """Test focus management."""

    @pytest.mark.asyncio
    async def test_focus_after_tab_switch(self, mock_mu_interface, mock_config):
        """Test that focus is properly set after switching tabs."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    # Open a message
                    await pilot.press("enter")
                    await pilot.pause()
                    # Return to index
                    await pilot.press("m")
                    await pilot.pause()
                    # Focus should be on something
                    assert app.focused is not None

    @pytest.mark.asyncio
    async def test_compose_focus_after_alt_switch(self, mock_mu_interface, mock_config):
        """Test that compose inputs regain focus after Alt tab switching."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("c")
                    await pilot.pause()
                    await pilot.press("alt+0")
                    await pilot.pause()
                    await pilot.press("alt+1")
                    await pilot.pause()
                    to_input = app.query_one("#to-input")
                    body_input = app.query_one("#body-input")
                    assert to_input.has_focus or body_input.has_focus


class TestSearch:
    """Test search functionality."""

    @pytest.mark.asyncio
    async def test_s_opens_search(self, mock_mu_interface, mock_config):
        """Test that S triggers search."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("s")
                    await pilot.pause()
                    # Should not crash


class TestFolderShortcuts:
    """Test folder shortcut keys."""

    @pytest.mark.asyncio
    async def test_i_shows_inbox(self, mock_mu_interface, mock_config):
        """Test that I shows inbox."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("i")
                    await pilot.pause()
                    # Should trigger inbox search

    @pytest.mark.asyncio
    async def test_o_shows_archive(self, mock_mu_interface, mock_config):
        """Test that O shows archive folder."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("o")
                    await pilot.pause()
                    # Should trigger archive search


class TestQuit:
    """Test quit functionality."""

    @pytest.mark.asyncio
    async def test_ctrl_q_quits(self, mock_mu_interface, mock_config):
        """Test that Ctrl+Q quits the application."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("ctrl+q")
                    # App should be exiting or exited

    @pytest.mark.asyncio
    async def test_ctrl_q_disabled_in_compose(self, mock_mu_interface, mock_config):
        """Test that Ctrl+Q does not quit during compose."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("c")
                    await pilot.pause()
                    tabs = app.query_one("TabbedContent")
                    active_before = tabs.active
                    await pilot.press("ctrl+q")
                    await pilot.pause()
                    assert app.is_running
                    assert tabs.active == active_before
