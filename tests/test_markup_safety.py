"""Text from mail and the filesystem must never be parsed as Textual/Rich markup.

Plain strings handed to DataTable cells, Static/Label and TabPane titles are
parsed as markup: "[ext] Meeting" lost its "[ext]" and "[/x]" raised a
MarkupError while rendering.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static, TabbedContent
from textual.widgets._data_table import default_cell_formatter

from bor.config import Config
from bor.tabs.attachments import AttachmentItem, AttachmentPreview
from bor.tabs.compose import BulkAttachmentItem
from bor.tabs.message import UrlPickerBar
from tests.test_app_integration import create_mock_messages


def _mock_mu(messages):
    mu = MagicMock()
    mu.find.return_value = messages
    mu.find_contacts.return_value = []
    mu.view.side_effect = lambda path, *a, **k: next(m for m in messages if m.path == path)
    return mu


def _cell_text(table: DataTable, row: int, column: int) -> str:
    return default_cell_formatter(table.get_row_at(row)[column]).plain


async def test_index_shows_bracketed_subjects_and_names_literally() -> None:
    messages = create_mock_messages(3)
    # Read (unstyled) rows used to be passed to DataTable as plain strings
    messages[0].flags = ["seen"]
    messages[0].subject = "[mu-discuss] Re: hello"
    messages[0].from_addr = MagicMock(name="x", email="a@x.org")
    messages[0].from_addr.name = "[ext] Bob"
    messages[1].flags = ["seen"]
    messages[1].subject = "see [/x] for details"

    with patch("bor.app.get_config", return_value=Config()):
        with patch("bor.app.MuInterface", return_value=_mock_mu(messages)):
            from bor.app import BorApp

            app = BorApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                table = app.query_one(DataTable)
                assert _cell_text(table, 0, 3) == "[mu-discuss] Re: hello"
                assert _cell_text(table, 0, 2) == "[ext] Bob"
                assert _cell_text(table, 1, 3) == "see [/x] for details"

                # Marking re-renders the row through the single-row update path
                await pilot.press("m")
                await pilot.pause()
                assert _cell_text(table, 0, 3) == "[mu-discuss] Re: hello"
                assert app.is_running


async def test_tab_title_keeps_brackets() -> None:
    messages = create_mock_messages(2)
    messages[0].subject = "[/x] odd"

    with patch("bor.app.get_config", return_value=Config()):
        with patch("bor.app.MuInterface", return_value=_mock_mu(messages)):
            from bor.app import BorApp

            app = BorApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                tab_id = next(iter(app._tabs))
                label = app.query_one(TabbedContent).get_tab(tab_id).label
                assert str(label).startswith("[/x] odd")


def test_bulk_attachment_item_shows_selected_marker() -> None:
    item = BulkAttachmentItem(Path("/nonexistent/notes[ext].txt"), selected=True)

    assert item._render_label().plain == "[x] notes[ext].txt (0 B)"


class _Harness(App):
    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


async def test_attachment_item_shows_inline_marker() -> None:
    attachment = {"filename": "logo[1].png", "content_type": "image/png", "size": 10, "inline": True}
    app = _Harness(AttachmentItem(1, attachment))
    async with app.run_test() as pilot:
        await pilot.pause()
        rendered = str(app.query_one(Static).render())
    assert rendered == "[1] logo[1].png (image/png, 10 B) [inline]"


async def test_attachment_text_preview_is_literal() -> None:
    app = _Harness(AttachmentPreview(id="preview"))
    async with app.run_test() as pilot:
        await pilot.pause()
        preview = app.query_one(AttachmentPreview)
        preview.show_text("code.py", "x = a[i] + b[/x]")
        await pilot.pause()
        rendered = str(preview.query_one("#preview-content", Static).render())
    assert rendered == "x = a[i] + b[/x]"


async def test_url_picker_shows_urls_literally() -> None:
    app = _Harness(UrlPickerBar(id="picker"))
    async with app.run_test() as pilot:
        await pilot.pause()
        picker = app.query_one(UrlPickerBar)
        picker.ask(["https://example.org/a[/b]", "https://example.org/[ext]"], lambda url: None)
        await pilot.pause()
        rendered = str(picker.render())
    assert "https://example.org/a[/b]" in rendered
    assert "https://example.org/[ext]" in rendered

