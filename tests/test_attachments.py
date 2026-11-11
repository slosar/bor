"""Tests for attachment preview behavior."""

from pathlib import Path
from unittest.mock import PropertyMock, patch

from textual.app import App, ComposeResult
from textual.widgets import Static, TabbedContent, TabPane

from bor.config import Config
from bor.tabs.attachments import AttachmentPreview, _supports_kitty_graphics


def test_kitty_graphics_detected_from_term(monkeypatch):
    """Kitty graphics are enabled automatically in kitty."""
    monkeypatch.setenv("TERM", "xterm-kitty")

    assert _supports_kitty_graphics(Config()) is True


def test_kitty_graphics_disabled_for_other_terms_by_default(monkeypatch):
    """Kitty graphics stay disabled outside kitty by default."""
    monkeypatch.setenv("TERM", "xterm-256color")

    assert _supports_kitty_graphics(Config()) is False


def test_kitty_graphics_can_be_forced(monkeypatch):
    """Configuration can force Kitty graphics regardless of TERM."""
    monkeypatch.setenv("TERM", "xterm-256color")
    config = Config()
    config.attachments.force_kitty_support = True

    assert _supports_kitty_graphics(config) is True


async def test_kitty_image_is_hidden_and_restored_when_switching_tabs(tmp_path):
    """An image should follow its preview's visibility across tab switches."""

    class PreviewApp(App):
        def compose(self) -> ComposeResult:
            with TabbedContent(id="tabs"):
                with TabPane("Preview", id="preview-tab"):
                    yield AttachmentPreview(id="preview")
                with TabPane("Other", id="other-tab"):
                    yield Static("Other tab")

    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"image")

    with patch.object(AttachmentPreview, "_render_kitty_image") as render:
        with patch.object(AttachmentPreview, "_delete_kitty_image") as delete:
            app = PreviewApp()
            async with app.run_test() as pilot:
                preview = app.query_one(AttachmentPreview)
                tabs = app.query_one(TabbedContent)
                preview.show_image("image.png", image_path)
                await pilot.pause()
                render.assert_called_once_with()

                render.reset_mock()
                delete.reset_mock()
                tabs.active = "other-tab"
                await pilot.pause()

                delete.assert_called_once_with()
                render.assert_not_called()
                assert preview._current_image_path == image_path

                tabs.active = "preview-tab"
                await pilot.pause()

                render.assert_called_once_with()
                assert preview._current_image_path == image_path


def test_kitty_render_is_skipped_while_preview_is_off_screen():
    """A queued render must not draw an image after its preview is hidden."""
    preview = AttachmentPreview()
    preview._current_image_path = Path("image.png")

    with patch.object(
        AttachmentPreview, "is_on_screen", new_callable=PropertyMock
    ) as is_on_screen:
        with patch("bor.tabs.attachments._supports_kitty_graphics") as supports:
            is_on_screen.return_value = False
            preview._render_kitty_image()

    supports.assert_not_called()
