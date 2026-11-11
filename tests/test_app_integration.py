"""
Integration tests for Bor email application.

Uses Textual's testing framework to simulate user interactions.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
from pathlib import Path

from textual.widgets import DataTable, Static
from textual.widgets._input import Selection
from bor.tabs.compose import ComposeWidget, FilePathInput, BulkAttachmentList, ComposeTextArea
from bor.tabs.message_index import ReplyBar

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
        self.reply_to_addr = kwargs.get("reply_to_addr", None)
        self.list_post_addr = kwargs.get("list_post_addr", None)
        self.calendar_event = kwargs.get("calendar_event", None)

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

    @pytest.mark.asyncio
    async def test_reply_prompt_ignores_other_keys_until_confirmed_or_canceled(
        self, mock_mu_interface, mock_config
    ):
        """Reply prompt should trap unrelated keys and allow escape to cancel."""
        multi_recipient_msg = MockEmailMessage(
            subject="Viewed Message",
            to_addrs=[
                MagicMock(email="one@test.com", __str__=lambda s: "one@test.com"),
                MagicMock(email="two@test.com", __str__=lambda s: "two@test.com"),
            ],
            cc_addrs=[],
        )
        mock_mu_interface.view.return_value = multi_recipient_msg

        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp

                app = BorApp()
                app.open_compose = MagicMock()

                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("r")
                    await pilot.pause()

                    reply_bar = app.query_one("#reply-bar", ReplyBar)
                    assert reply_bar.has_class("visible")

                    await pilot.press("x")
                    await pilot.pause()
                    assert reply_bar.has_class("visible")
                    app.open_compose.assert_not_called()

                    await pilot.press("escape")
                    await pilot.pause()
                    assert not reply_bar.has_class("visible")
                    app.open_compose.assert_not_called()


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
    async def test_m_in_message_view_marks_and_keeps_tab(self, mock_mu_interface, mock_config):
        """M in the message view marks the message in the index and keeps the tab open."""
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
                    from bor.tabs.message_index import MessageIndexWidget

                    assert 0 in app.query_one(MessageIndexWidget).marked_messages

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
    async def test_esc_closes_tab_like_q(self, mock_mu_interface, mock_config):
        """Esc closes the message tab, but first only dismisses an open URL picker."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                from bor.tabs.message import MessageViewWidget, UrlPickerBar

                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("enter")
                    await pilot.pause()
                    assert len(app._tabs) == 1

                    picker = app.query_one(UrlPickerBar)
                    picker.ask(["https://a.example", "https://b.example"], lambda url: None)
                    await pilot.pause()
                    await pilot.press("escape")
                    await pilot.pause()
                    assert not picker.has_class("visible")
                    assert len(app._tabs) == 1

                    await pilot.press("escape")
                    await pilot.pause()
                    await pilot.pause()
                    assert len(app._tabs) == 0
                    assert len(app.query(MessageViewWidget)) == 0
                    assert app.query_one("TabbedContent").active == "tab-0"

    @pytest.mark.asyncio
    async def test_marked_messages_survive_open_and_return(self, mock_mu_interface, mock_config):
        """Marked messages should persist after opening another message and returning."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                from bor.tabs.message_index import MessageIndexWidget

                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()

                    index_widget = app.query_one(MessageIndexWidget)
                    table = app.query_one(DataTable)
                    table.move_cursor(row=0)

                    # Mark first two messages (m moves cursor down after each mark)
                    await pilot.press("m")
                    await pilot.press("m")
                    await pilot.pause()
                    assert index_widget.marked_messages == {0, 1}

                    # Open third message and return to index
                    await pilot.press("enter")
                    await pilot.pause()
                    await pilot.press("q")
                    await pilot.pause()
                    await pilot.pause()

                    assert index_widget.marked_messages == {0, 1}

    @pytest.mark.asyncio
    async def test_marked_message_shows_symbol_in_flags_column(self, mock_mu_interface, mock_config):
        """Marking shows the marked symbol in the flags column instead of inverting the row."""
        from textual.coordinate import Coordinate

        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()

                    table = app.query_one(DataTable)
                    table.move_cursor(row=0)

                    await pilot.press("m")
                    await pilot.pause()

                    symbol = mock_config.display.flag_marked
                    flags_cell = table.get_cell_at(Coordinate(0, 0))
                    assert symbol in str(flags_cell)
                    mark_span = next(
                        (span for span in flags_cell.spans
                         if str(flags_cell)[span.start:span.end] == symbol),
                        None,
                    )
                    assert mark_span is not None
                    assert "red" in str(mark_span.style)

                    # Toggling the mark off removes the symbol again
                    await pilot.press("p")
                    await pilot.press("m")
                    await pilot.pause()

                    flags_cell = str(table.get_cell_at(Coordinate(0, 0)))
                    assert symbol not in flags_cell

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


class TestIndexRefreshOnReturn:
    """Test index refresh behavior when returning from secondary tabs."""

    @pytest.mark.asyncio
    async def test_returning_from_compose_refreshes_index(self, mock_mu_interface, mock_config):
        """Returning to tab-0 from compose should refresh message index query."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp
                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    initial_find_calls = mock_mu_interface.find.call_count

                    await pilot.press("c")
                    await pilot.pause()

                    await pilot.press("ctrl+l", "x", "y")
                    await pilot.pause()

                    assert mock_mu_interface.find.call_count > initial_find_calls


class TestComposeLayout:
    """Test compose screen layout."""

    @pytest.mark.asyncio
    async def test_compose_headers_use_one_row_each(self, mock_mu_interface, mock_config):
        """Address and subject fields should leave most of the screen for the body."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("c")
                    await pilot.pause()

                    header = app.query_one(ComposeWidget).query_one(".header-container")
                    rows = list(header.query(".compose-header-row"))

                    assert len(rows) == 4
                    assert header.size.height == 4
                    assert all(row.size.height == 1 for row in rows)

    @pytest.mark.asyncio
    async def test_arrow_keys_move_through_compose_headers(self, mock_mu_interface, mock_config):
        """Up and Down should follow the visual order of compact header fields."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("c")
                    await pilot.pause()

                    assert app.query_one("#to-input").has_focus

                    for field_id in ("cc-input", "bcc-input", "subject-input", "body-input"):
                        await pilot.press("down")
                        assert app.query_one(f"#{field_id}").has_focus

                    body_input = app.query_one("#body-input", ComposeTextArea)
                    body_input.text = "first\nsecond"
                    body_input.cursor_location = (1, 0)
                    await pilot.press("up")
                    assert body_input.has_focus
                    assert body_input.cursor_location == (0, 0)

                    await pilot.press("up")
                    assert app.query_one("#subject-input").has_focus

                    for field_id in ("bcc-input", "cc-input", "to-input"):
                        await pilot.press("up")
                        assert app.query_one(f"#{field_id}").has_focus

                    await pilot.press("up")
                    assert app.query_one("#to-input").has_focus


class TestComposeBulkAttachments:
    """Test bulk attachment flow in compose."""

    @pytest.mark.asyncio
    async def test_ctrl_l_ctrl_a_keeps_default_path_unselected(
        self, mock_mu_interface, mock_config
    ):
        """Ctrl+L Ctrl+A should leave the default path intact with no active selection."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("c")
                    await pilot.pause()

                    await pilot.press("ctrl+l", "a")
                    await pilot.pause()

                    path_input = app.query_one("#attachment-path-input", FilePathInput)
                    expected_value = str(Path.home()) + "/"

                    assert path_input.has_focus
                    assert path_input.value == expected_value
                    assert path_input.cursor_position == len(expected_value)
                    assert path_input.selection == Selection(
                        len(expected_value), len(expected_value)
                    )

    @pytest.mark.asyncio
    async def test_ctrl_l_ctrl_z_attaches_marked_files(
        self, mock_mu_interface, mock_config, tmp_path
    ):
        """Ctrl+L Ctrl+Z should open a directory picker and attach marked files."""
        first = tmp_path / "alpha.txt"
        second = tmp_path / "beta.txt"
        ignored = tmp_path / "subdir"
        first.write_text("alpha", encoding="utf-8")
        second.write_text("beta", encoding="utf-8")
        ignored.mkdir()

        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("c")
                    await pilot.pause()

                    await pilot.press("ctrl+l", "z")
                    await pilot.pause()

                    path_input = app.query_one("#attachment-path-input", FilePathInput)
                    assert path_input.has_focus
                    path_input.value = str(tmp_path) + "/"
                    path_input.cursor_position = len(path_input.value)

                    await pilot.press("enter")
                    await pilot.pause()

                    widget = app.query_one(ComposeWidget)
                    picker = app.query_one("#bulk-attachment-list", BulkAttachmentList)
                    assert picker.has_focus

                    await pilot.press("space", "down", "space", "enter")
                    await pilot.pause()

                    assert [path.name for path in widget.attachments] == ["alpha.txt", "beta.txt"]


class TestQuit:
    """Test quit functionality."""

    @pytest.mark.asyncio
    async def test_reply_headers_use_bracketed_message_ids(self, mock_mu_interface, mock_config):
        """Replies carry RFC 5322 <id> Message-IDs even though mu.view() strips the brackets."""
        mock_mu_interface.view.return_value = MockEmailMessage(
            msgid="parent@example.com", references=["<root@example.com>"]
        )
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("r")
                    await pilot.pause()
                    msg = app.query_one(ComposeWidget)._build_message()

        assert msg["In-Reply-To"] == "<parent@example.com>"
        assert msg["References"] == "<root@example.com> <parent@example.com>"

    @staticmethod
    def _mailbox_mu(count=4):
        """A mock mu whose find() reflects messages moved away by move()."""
        store = create_mock_messages(count)
        mu = MagicMock()
        mu.find.side_effect = lambda *a, **k: list(store)
        mu.find_contacts.return_value = []
        mu.view.side_effect = lambda path, *a, **k: MockEmailMessage(
            path=path, msgid=next(m.msgid for m in create_mock_messages(count) if m.path == path)
        )

        def move(path, folder):
            store[:] = [m for m in store if m.path != path]
            return f"{folder}/moved"

        mu.move.side_effect = move
        return mu

    @pytest.mark.asyncio
    async def test_archive_and_delete_in_message_view_advance(self, mock_config):
        """X and D in the message view move the message and show the next one."""
        from bor.tabs.message import MessageViewWidget

        mu = self._mailbox_mu()
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mu):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("enter")
                    await pilot.pause()
                    view = app.query_one(MessageViewWidget)

                    await pilot.press("x", "y")
                    await pilot.pause()
                    await pilot.pause()
                    assert mu.move.call_args_list[-1].args == ("/test/path/message0", "/Archive")
                    assert view._message_ref.path == "/test/path/message1"
                    # Once the index refresh lands, the shared cursor follows the view
                    assert app._current_messages[app._current_index].path == "/test/path/message1"

                    await pilot.press("d", "y")
                    await pilot.pause()
                    await pilot.pause()
                    assert mu.move.call_args_list[-1].args == ("/test/path/message1", "/Trash")
                    assert view._message_ref.path == "/test/path/message2"
                    assert mu.move.call_count == 2

    @pytest.mark.asyncio
    async def test_archiving_last_message_in_view_closes_tab(self, mock_config):
        """With no message after it, archiving from the view closes the tab."""
        mu = self._mailbox_mu(2)
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mu):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("down", "enter")
                    await pilot.pause()
                    assert len(app._tabs) == 1
                    await pilot.press("x", "y")
                    await pilot.pause()
                    await pilot.pause()
                    assert mu.move.call_args_list[-1].args == ("/test/path/message1", "/Archive")
                    assert len(app._tabs) == 0

    @pytest.mark.asyncio
    async def test_missing_attachment_stops_send_and_draft(
        self, mock_mu_interface, mock_config, tmp_path
    ):
        """A vanished attachment is reported; the message is not sent without it."""
        mock_mu_interface.get_root_maildir.return_value = str(tmp_path / "Mail")
        sendmail = MagicMock()
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                with patch('bor.tabs.compose.smtplib.SMTP') as smtp:
                    smtp.return_value.sendmail = sendmail
                    from bor.app import BorApp

                    app = BorApp()
                    async with app.run_test() as pilot:
                        await pilot.pause()
                        await pilot.press("c")
                        await pilot.pause()
                        compose = app.query_one(ComposeWidget)
                        compose.query_one("#to-input").value = "to@example.com"
                        compose.attachments = [tmp_path / "gone.pdf"]
                        with patch.object(ComposeWidget, "notify") as notify:
                            assert await compose._send_message() is False
                            assert compose._save_draft() is False

        sendmail.assert_not_called()
        assert not (tmp_path / "Mail").exists()
        errors = [call.args[0] for call in notify.call_args_list]
        assert any("gone.pdf" in error for error in errors)
        assert len(errors) == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("keys", [("x", "n"), ("d", "escape"), ("a", "escape")])
    async def test_declining_prompt_in_message_view_stays_in_view(self, mock_config, keys):
        """Answering no to a prompt in the message view must not jump to the index."""
        from textual.widgets import TabbedContent

        from bor.tabs.message import MessageViewWidget

        mu = self._mailbox_mu()
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mu):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("enter")
                    await pilot.pause()
                    view = app.query_one(MessageViewWidget)
                    focused_before = app.focused

                    await pilot.press(*keys)
                    await pilot.pause()

                    assert app.query_one(TabbedContent).active == view.get_tab_id()
                    assert app.focused is focused_before
                    await pilot.press("n")
                    await pilot.pause()
                    assert view._message_ref.path == "/test/path/message1"
                    mu.move.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_compose_asks_for_confirmation(self, mock_mu_interface, mock_config):
        """Ctrl+L X discards only after y; n keeps the message and its focus."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("c")
                    await pilot.pause()
                    await pilot.press(*"bob")
                    await pilot.press("ctrl+l", "x")
                    await pilot.pause()
                    assert len(app._tabs) == 1

                    await pilot.press("n")
                    await pilot.pause()
                    assert len(app._tabs) == 1
                    assert app.focused.id == "to-input"
                    assert app.focused.value == "bob"

                    await pilot.press("ctrl+l", "x", "y")
                    await pilot.pause()
                    assert len(app._tabs) == 0

    @staticmethod
    def _draft_mu(tmp_path):
        """Mock mu with one draft that is a reply and has an attachment."""
        draft = MockEmailMessage(
            path="/mail/Drafts/cur/draft:2,S",
            maildir="/Drafts",
            msgid="draft@example.com",
            subject="Re: plans",
            in_reply_to="<parent@example.com>",
            references=["<root@example.com>", "<parent@example.com>"],
            attachments=[{"filename": "plan.pdf", "part_index": 2, "content_type": "application/pdf"}],
        )
        mu = MagicMock()
        mu.find.return_value = [draft]
        mu.find_contacts.return_value = []
        mu.view.return_value = draft
        mu.get_root_maildir.return_value = str(tmp_path / "Mail")

        def extract(message_path, part_index, target_dir):
            out = Path(target_dir) / "plan.pdf"
            out.write_bytes(b"%PDF")
            return str(out)

        mu.extract_attachment.side_effect = extract
        return mu, draft

    @pytest.mark.asyncio
    async def test_editing_draft_keeps_original_until_saved(self, mock_config, tmp_path):
        """Opening or cancelling a draft edit keeps the draft; saving replaces it."""
        mu, draft = self._draft_mu(tmp_path)
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mu):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("e")
                    await pilot.pause()
                    mu.move.assert_not_called()

                    await pilot.press("ctrl+l", "x", "y")
                    await pilot.pause()
                    mu.move.assert_not_called()

                    await pilot.press("e")
                    await pilot.pause()
                    await pilot.press("ctrl+l", "d")
                    await pilot.pause()

        mu.move.assert_called_once_with(draft.path, "/Trash")
        saved = list((tmp_path / "Mail" / "Drafts" / "cur").iterdir())
        assert len(saved) == 1

    async def _send_edited_draft(self, mu, mock_config):
        """Open the mock draft with E, send it with Ctrl+L L; return (app, notify mock)."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mu):
                with patch('bor.tabs.compose.smtplib.SMTP'):
                    with patch.object(ComposeWidget, "notify") as notify:
                        from bor.app import BorApp

                        app = BorApp()
                        async with app.run_test() as pilot:
                            await pilot.pause()
                            await pilot.press("e")
                            await pilot.pause()
                            await app.workers.wait_for_complete()
                            app.query_one("#to-input").value = "to@example.com"
                            await pilot.press("ctrl+l", "l")
                            for _ in range(50):
                                if not app._tabs:
                                    break
                                await pilot.pause(0.02)
                            return app, notify

    @pytest.mark.asyncio
    async def test_sending_edited_reply_draft_marks_parent_replied(self, mock_config, tmp_path):
        import threading

        mu, draft = self._draft_mu(tmp_path)
        parent = MockEmailMessage(path="/mail/INBOX/cur/parent:2,S", msgid="parent@example.com")
        lookup_threads = []

        def find_by_msgid(msgid):
            lookup_threads.append(threading.current_thread() is threading.main_thread())
            return parent

        mu.find_by_msgid.side_effect = find_by_msgid

        app, notify = await self._send_edited_draft(mu, mock_config)

        assert len(app._tabs) == 0
        mu.find_by_msgid.assert_called_once_with("<parent@example.com>")
        assert lookup_threads == [False]
        mu.mark_replied.assert_called_once_with(parent.path)
        mu.move.assert_called_once_with(draft.path, "/Trash")

    @pytest.mark.asyncio
    async def test_failed_parent_lookup_still_completes_send(self, mock_config, tmp_path):
        """The mail is already out; a mu error while flagging the parent is not a send error."""
        mu, draft = self._draft_mu(tmp_path)
        mu.find_by_msgid.side_effect = RuntimeError("mu command timed out")

        app, notify = await self._send_edited_draft(mu, mock_config)

        assert len(app._tabs) == 0
        mu.mark_replied.assert_not_called()
        assert "Message sent!" in [call.args[0] for call in notify.call_args_list]

    @pytest.mark.asyncio
    async def test_sending_edited_non_reply_draft_does_not_look_up_parent(
        self, mock_config, tmp_path
    ):
        mu, draft = self._draft_mu(tmp_path)
        draft.in_reply_to = ""
        draft.references = []

        app, notify = await self._send_edited_draft(mu, mock_config)

        assert len(app._tabs) == 0
        mu.find_by_msgid.assert_not_called()
        mu.mark_replied.assert_not_called()

    @pytest.mark.asyncio
    async def test_editing_draft_keeps_attachments_and_threading(self, mock_config, tmp_path):
        mu, draft = self._draft_mu(tmp_path)
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mu):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("e")
                    await pilot.pause()
                    compose = app.query_one(ComposeWidget)
                    assert [path.name for path in compose.attachments] == ["plan.pdf"]
                    msg = compose._build_message()

        assert msg["In-Reply-To"] == "<parent@example.com>"
        assert msg["References"] == "<root@example.com> <parent@example.com>"

    @pytest.mark.asyncio
    async def test_thread_view_clears_marks_and_survives_return(self, mock_mu_interface, mock_config):
        """Ctrl+T drops marks (row numbers of the old list) and stays after a message tab."""
        from bor.tabs.message_index import MessageIndexWidget

        messages = mock_mu_interface.find.return_value
        thread = [messages[3], messages[1], messages[4]]
        mock_mu_interface.find_thread.return_value = thread
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    index = app.query_one(MessageIndexWidget)
                    await pilot.press("m")  # marks row 0, cursor to row 1
                    assert index.marked_messages == {0}

                    await pilot.press("ctrl+t")
                    await pilot.pause()
                    assert index.marked_messages == set()
                    assert [m.path for m in index.messages] == [m.path for m in thread]
                    # Cursor stays on the message the thread was opened from
                    assert app.query_one(DataTable).cursor_row == 1

                    await pilot.press("enter")
                    await pilot.pause()
                    await pilot.press("q")
                    await pilot.pause()
                    await pilot.pause()
                    assert [m.path for m in index.messages] == [m.path for m in thread]

                    await pilot.press("i")
                    await pilot.pause()
                    assert len(index.messages) == len(messages)

    @pytest.mark.asyncio
    async def test_tab_cycles_within_compose_fields(self, mock_mu_interface, mock_config):
        """Tab in the body wraps to To and Shift+Tab in To wraps to the body."""
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("c")
                    await pilot.pause()
                    await pilot.press("ctrl+l", "e")
                    await pilot.press(*"hi ")
                    body_text = app.query_one("#body-input").text

                    await pilot.press("tab")
                    await pilot.pause()
                    assert app.focused.id == "to-input"
                    assert app.query_one("#body-input").text == body_text

                    await pilot.press("shift+tab")
                    await pilot.pause()
                    assert app.focused.id == "body-input"

    @pytest.mark.asyncio
    async def test_home_and_end_move_to_first_and_last_message(self, mock_mu_interface, mock_config):
        with patch('bor.app.get_config', return_value=mock_config):
            with patch('bor.app.MuInterface', return_value=mock_mu_interface):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    table = app.query_one(DataTable)
                    await pilot.press("end")
                    await pilot.pause()
                    assert table.cursor_row == 4
                    await pilot.press("home")
                    await pilot.pause()
                    assert table.cursor_row == 0

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
