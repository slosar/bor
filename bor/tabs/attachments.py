"""
Attachments tab for Bor email reader.

Displays and manages email attachments.
"""

from __future__ import annotations

import base64
import mimetypes
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets import Static, Label, Button, DataTable, ListView, ListItem

from bor.tabs.base import BaseTab
from bor.mu import EmailMessage
from bor.config import get_config


class AttachmentItem(ListItem):
    """List item representing an attachment."""

    def __init__(self, index: int, attachment: Dict[str, Any], **kwargs) -> None:
        """
        Initialize attachment list item.

        Args:
            index: Attachment index (1-based)
            attachment: Attachment metadata dictionary
        """
        super().__init__(**kwargs)
        self.index = index
        self.attachment = attachment

    def compose(self) -> ComposeResult:
        """Create the item layout."""
        filename = self.attachment.get("filename", "attachment")
        content_type = self.attachment.get("content_type", "application/octet-stream")
        size = self.attachment.get("size", 0)
        is_inline = self.attachment.get("inline", False)

        # Format size
        if size < 1024:
            size_str = f"{size} B"
        elif size < 1024 * 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size / (1024 * 1024):.1f} MB"

        inline_marker = " [inline]" if is_inline else ""
        yield Static(f"[{self.index}] {filename} ({content_type}, {size_str}){inline_marker}")


class AttachmentPreview(ScrollableContainer):
    """Widget to preview attachment content."""

    DEFAULT_CSS = """
    AttachmentPreview {
        height: 1fr;
        border: solid $primary;
        padding: 1;
    }

    AttachmentPreview .preview-title {
        text-style: bold;
        margin-bottom: 1;
    }
    
    AttachmentPreview #image-placeholder {
        height: auto;
        min-height: 10;
    }
    """

    def __init__(self, **kwargs) -> None:
        """Initialize attachment preview."""
        super().__init__(**kwargs)
        self._content: str = "Select an attachment to preview"
        self._title: str = ""
        self._current_image_path: Optional[Path] = None
        self._image_id_counter: int = 0

    def compose(self) -> ComposeResult:
        """Create the preview layout."""
        yield Label(self._title, classes="preview-title", id="preview-title")
        yield Static(self._content, id="preview-content")

    def show_text(self, title: str, content: str) -> None:
        """
        Show text content in preview.

        Args:
            title: Preview title
            content: Text content to display
        """
        self.clear_image()  # Clear any previous image
        self._title = title
        self._content = content
        self._current_image_path = None
        self.query_one("#preview-title", Label).update(title)
        self.query_one("#preview-content", Static).update(content)

    def show_message(self, message: str) -> None:
        """
        Show a status message.

        Args:
            message: Message to display
        """
        self.clear_image()  # Clear any previous image
        self._title = ""
        self._content = message
        self._current_image_path = None
        self.query_one("#preview-title", Label).update("")
        self.query_one("#preview-content", Static).update(message)

    def show_image(self, title: str, image_path: Path) -> None:
        """
        Show an image in the preview using Kitty graphics protocol.

        Args:
            title: Image title/filename
            image_path: Path to the image file
        """
        self.clear_image()  # Clear any previous image first
        self._title = title
        self._current_image_path = image_path
        self.query_one("#preview-title", Label).update(title)
        
        # Display a placeholder and trigger image render
        self.query_one("#preview-content", Static).update(
            f"[Image: {title}]\n\n"
            "Press Enter to open with system viewer\n"
            "Press 's' to save to disk"
        )
        
        # Render the image using Kitty graphics after a brief delay
        self.call_later(self._render_kitty_image)

    def _render_kitty_image(self) -> None:
        """Render the current image using Kitty's graphics protocol."""
        if not self._current_image_path or not self._current_image_path.exists():
            return
        
        # Check if we're in kitty
        if os.environ.get("TERM") != "xterm-kitty":
            return
        
        try:
            # Read the image file
            with open(self._current_image_path, "rb") as f:
                image_data = f.read()
            
            # Kitty graphics protocol only supports PNG natively (f=100)
            # For JPEG and other formats, we need to convert to PNG first
            # Check if it's PNG by magic bytes
            if image_data[:4] != b'\x89PNG':
                # Try to convert to PNG using PIL if available
                try:
                    from PIL import Image
                    import io
                    
                    # Open image and convert to PNG
                    img = Image.open(io.BytesIO(image_data))
                    # Convert to RGBA if necessary (handles various formats)
                    if img.mode not in ('RGB', 'RGBA'):
                        img = img.convert('RGBA')
                    
                    # Save as PNG to bytes
                    png_buffer = io.BytesIO()
                    img.save(png_buffer, format='PNG')
                    image_data = png_buffer.getvalue()
                except ImportError:
                    # PIL not available, try using convert command
                    try:
                        result = subprocess.run(
                            ['convert', str(self._current_image_path), 'png:-'],
                            capture_output=True,
                            timeout=5
                        )
                        if result.returncode == 0:
                            image_data = result.stdout
                        else:
                            return  # Can't convert, skip
                    except (subprocess.TimeoutExpired, FileNotFoundError):
                        return  # ImageMagick not available
            
            # Get image dimensions from PNG data (we converted to PNG above)
            # PNG dimensions are at bytes 16-24 (width: 16-20, height: 20-24)
            img_width, img_height = 0, 0
            if image_data[:4] == b'\x89PNG' and len(image_data) >= 24:
                img_width = int.from_bytes(image_data[16:20], 'big')
                img_height = int.from_bytes(image_data[20:24], 'big')
            
            encoded = base64.standard_b64encode(image_data).decode("ascii")
            
            # Get the preview container's region (self is AttachmentPreview)
            # Use the container size, not the content widget which just has text
            container_region = self.region
            
            # Calculate available space (in terminal cells)
            # Leave margin for borders, padding, and title
            avail_width = max(10, container_region.width - 4)
            avail_height = max(5, container_region.height - 6)  # -6 for border, padding, title
            
            # Determine which dimension to constrain to fit image in available space
            # Terminal cells are roughly 2:1 (height:width in pixels), so 1 row ≈ 2 cols
            # If image is W×H pixels, it would need W columns and H/2 rows (approx)
            if img_width > 0 and img_height > 0:
                # Calculate what rows we'd need if we use full available width
                scale = avail_width / img_width
                needed_rows = int((img_height * scale) / 2)  # /2 for cell aspect ratio
                
                if needed_rows > avail_height:
                    # Image would be too tall, constrain by height instead
                    size_params = f",r={avail_height}"
                else:
                    # Image fits, constrain by width
                    size_params = f",c={avail_width}"
            else:
                # Can't determine dimensions, just use width
                size_params = f",c={avail_width}"
            
            # Position cursor at the image location (inside the container)
            left = container_region.x + 2
            top = container_region.y + 4  # +4 for border, padding, title
            
            # Build the Kitty graphics escape sequence
            # Format: ESC_G<key>=<value>,...;<base64 data>ESC\
            # a=T means transmit and display
            # f=100 means PNG format
            # c=cols, r=rows for size in cells
            # q=2 means suppress responses
            
            # First, position the cursor
            cursor_pos = f"\033[{top};{left}H"
            
            # Send the image in chunks (Kitty protocol requires chunking for large images)
            chunk_size = 4096
            chunks = [encoded[i:i+chunk_size] for i in range(0, len(encoded), chunk_size)]
            
            # Use a unique image ID to avoid caching issues
            self._image_id_counter += 1
            img_id = self._image_id_counter % 255 + 1  # Keep ID in range 1-255
            
            # Write directly to terminal (bypass Textual's output)
            with open("/dev/tty", "w") as tty:
                # First delete any previous image with this ID
                tty.write(f"\033_Ga=d,d=I,i={img_id}\033\\")
                
                tty.write(cursor_pos)
                
                for i, chunk in enumerate(chunks):
                    # m=1 means more chunks coming, m=0 means last chunk
                    more = 1 if i < len(chunks) - 1 else 0
                    
                    if i == 0:
                        # First chunk includes all the parameters
                        # i=<id> assigns an image ID
                        tty.write(f"\033_Ga=T,f=100,i={img_id}{size_params},q=2,m={more};{chunk}\033\\")
                    else:
                        # Subsequent chunks just have m parameter and image ID
                        tty.write(f"\033_Gi={img_id},m={more};{chunk}\033\\")
                
                tty.flush()
                
        except Exception:
            pass

    def clear_image(self) -> None:
        """Clear any displayed Kitty image."""
        self._current_image_path = None
        if os.environ.get("TERM") == "xterm-kitty":
            try:
                # Clear all images using Kitty graphics protocol
                # a=d means delete, d=A means all images
                with open("/dev/tty", "w") as tty:
                    tty.write("\033_Ga=d,d=A\033\\")
                    tty.flush()
            except Exception:
                pass


class AttachmentsWidget(BaseTab):
    """
    Attachments widget.

    Displays and manages email attachments with preview capabilities.
    """

    BINDINGS = [
        # Selection
        Binding("1", "select_1", "Select 1", show=False),
        Binding("2", "select_2", "Select 2", show=False),
        Binding("3", "select_3", "Select 3", show=False),
        Binding("4", "select_4", "Select 4", show=False),
        Binding("5", "select_5", "Select 5", show=False),
        Binding("6", "select_6", "Select 6", show=False),
        Binding("7", "select_7", "Select 7", show=False),
        Binding("8", "select_8", "Select 8", show=False),
        Binding("9", "select_9", "Select 9", show=False),

        # Navigation
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),

        # Actions
        Binding("enter", "open_attachment", "Open", priority=True),
        Binding("s", "save_attachment", "Save"),
        Binding("S", "save_all", "Save All"),
        Binding("q", "close", "Close"),
        Binding("escape", "close", "Close"),
        # < for return_to_index is handled in on_key
    ]

    DEFAULT_CSS = """
    AttachmentsWidget {
        height: 1fr;
    }

    AttachmentsWidget #attachment-list {
        height: auto;
        max-height: 50%;
        border: solid $primary;
        margin-bottom: 1;
    }

    AttachmentsWidget .info-bar {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    def __init__(self, message: EmailMessage, *args, **kwargs) -> None:
        """
        Initialize the attachments widget.

        Args:
            message: Email message with attachments
        """
        super().__init__(*args, **kwargs)
        self.message = message
        self.attachments: List[Dict[str, Any]] = message.attachments
        self._selected_index: int = 0
        self._temp_dir: Optional[Path] = None

    def compose(self) -> ComposeResult:
        """Create the widget layout."""
        with Vertical():
            with Horizontal(classes="info-bar"):
                yield Label(f"Attachments for: {self.message.subject}", id="info-label")

            yield ListView(id="attachment-list")
            yield AttachmentPreview(id="preview")

    def on_mount(self) -> None:
        """Handle widget mount."""
        list_view = self.query_one("#attachment-list", ListView)

        # Populate attachment list
        for i, attach in enumerate(self.attachments):
            item = AttachmentItem(i + 1, attach)
            list_view.append(item)

        if self.attachments:
            list_view.focus()

    def on_key(self, event: events.Key) -> None:
        """Handle key events for special keys like <."""
        if event.character == "<":
            self.action_return_to_index()
            event.prevent_default()
            event.stop()

    def on_unmount(self) -> None:
        """Handle widget unmount - cleanup temp files and clear images."""
        # Clear any Kitty images
        try:
            preview = self.query_one("#preview", AttachmentPreview)
            preview.clear_image()
        except Exception:
            pass
        
        if self._temp_dir and self._temp_dir.exists():
            import shutil
            try:
                shutil.rmtree(self._temp_dir)
            except Exception:
                pass

    def _get_temp_dir(self) -> Path:
        """Get or create a temporary directory for attachments."""
        if self._temp_dir is None:
            self._temp_dir = Path(tempfile.mkdtemp(prefix="bor_attach_"))
        return self._temp_dir

    def _extract_attachment(self, index: int) -> Optional[Path]:
        """
        Extract an attachment to a temporary file.

        Args:
            index: Attachment index (0-based)

        Returns:
            Path to extracted file, or None on error
        """
        if index < 0 or index >= len(self.attachments):
            return None

        attach = self.attachments[index]
        # Use the MIME part index from mu, not our list index
        part_index = attach.get("part_index", index + 1)
        temp_dir = self._get_temp_dir()

        # mu extract returns the actual path of the extracted file
        # (mu may normalize filenames, so we can't assume the exact name)
        result = self.bor_app.mu.extract_attachment(
            self.message.path,
            part_index,
            str(temp_dir)
        )

        if result:
            return Path(result)
        return None

    def _preview_attachment(self, index: int) -> None:
        """
        Preview an attachment.

        Args:
            index: Attachment index (0-based)
        """
        if index < 0 or index >= len(self.attachments):
            return

        attach = self.attachments[index]
        filename = attach.get("filename", "attachment")
        content_type = attach.get("content_type", "application/octet-stream")
        preview = self.query_one("#preview", AttachmentPreview)

        # Check if we can preview this type
        if content_type.startswith("text/") or content_type in ["application/json", "application/xml"]:
            # Text-based content - extract and display
            file_path = self._extract_attachment(index)
            if file_path:
                try:
                    content = file_path.read_text(errors="replace")
                    preview.show_text(filename, content)
                except Exception as e:
                    preview.show_message(f"Error reading file: {e}")
            else:
                preview.show_message("Could not extract attachment")

        elif content_type.startswith("image/"):
            # Image - try to display inline with Kitty graphics
            config = get_config()
            if config.attachments.use_kitty_icat and self._check_kitty():
                file_path = self._extract_attachment(index)
                if file_path:
                    # Display image inline in the preview area
                    preview.show_image(filename, file_path)
                else:
                    preview.show_message("Could not extract image")
            else:
                preview.show_message(
                    f"Image: {filename}\n\n"
                    "Press Enter to open with system viewer"
                )

        else:
            # Other types - show info
            size = attach.get("size", 0)
            preview.show_message(
                f"Attachment: {filename}\n"
                f"Type: {content_type}\n"
                f"Size: {size} bytes\n\n"
                "Press Enter to open with system viewer\n"
                "Press 's' to save to disk"
            )

    def _check_kitty(self) -> bool:
        """Check if we're running in kitty terminal."""
        return os.environ.get("TERM") == "xterm-kitty"

    def _open_with_kitty_icat(self, index: int) -> None:
        """
        Open an image attachment with kitty icat.

        Args:
            index: Attachment index (0-based)
        """
        file_path = self._extract_attachment(index)
        if file_path:
            try:
                subprocess.run(["kitty", "+kitten", "icat", str(file_path)])
            except Exception:
                pass

    def _open_with_system(self, index: int) -> None:
        """
        Open an attachment with the system's default handler.

        Args:
            index: Attachment index (0-based)
        """
        file_path = self._extract_attachment(index)
        if file_path:
            try:
                # Linux/Unix
                subprocess.Popen(
                    ["xdg-open", str(file_path)],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                preview = self.query_one("#preview", AttachmentPreview)
                preview.show_message(f"Error opening attachment: {e}")
        else:
            preview = self.query_one("#preview", AttachmentPreview)
            preview.show_message("Could not extract attachment")

    def _save_attachment(self, index: int, target_dir: Optional[str] = None) -> Optional[Path]:
        """
        Save an attachment to disk.

        Args:
            index: Attachment index (0-based)
            target_dir: Target directory (uses config default if None)

        Returns:
            Path to saved file, or None on error
        """
        if index < 0 or index >= len(self.attachments):
            return None

        attach = self.attachments[index]
        # Use the MIME part index from mu, not our list index
        part_index = attach.get("part_index", index + 1)
        
        config = get_config()
        save_dir = Path(target_dir or config.attachments.save_directory).expanduser()
        save_dir.mkdir(parents=True, exist_ok=True)

        # mu extract saves with normalized filename, so we use the returned path
        result = self.bor_app.mu.extract_attachment(
            self.message.path,
            part_index,
            str(save_dir)
        )

        if result:
            return Path(result)
        return None

    # Actions

    def _select_attachment(self, index: int) -> None:
        """Select an attachment by index (1-based for user display)."""
        idx = index - 1  # Convert to 0-based
        if 0 <= idx < len(self.attachments):
            self._selected_index = idx
            list_view = self.query_one("#attachment-list", ListView)
            list_view.index = idx
            self._preview_attachment(idx)

    def action_select_1(self) -> None:
        """Select attachment 1."""
        self._select_attachment(1)

    def action_select_2(self) -> None:
        """Select attachment 2."""
        self._select_attachment(2)

    def action_select_3(self) -> None:
        """Select attachment 3."""
        self._select_attachment(3)

    def action_select_4(self) -> None:
        """Select attachment 4."""
        self._select_attachment(4)

    def action_select_5(self) -> None:
        """Select attachment 5."""
        self._select_attachment(5)

    def action_select_6(self) -> None:
        """Select attachment 6."""
        self._select_attachment(6)

    def action_select_7(self) -> None:
        """Select attachment 7."""
        self._select_attachment(7)

    def action_select_8(self) -> None:
        """Select attachment 8."""
        self._select_attachment(8)

    def action_select_9(self) -> None:
        """Select attachment 9."""
        self._select_attachment(9)

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        list_view = self.query_one("#attachment-list", ListView)
        list_view.action_cursor_up()
        self._selected_index = list_view.index or 0
        self._preview_attachment(self._selected_index)

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        list_view = self.query_one("#attachment-list", ListView)
        list_view.action_cursor_down()
        self._selected_index = list_view.index or 0
        self._preview_attachment(self._selected_index)

    def action_open_attachment(self) -> None:
        """Open the selected attachment with system viewer."""
        self._open_with_system(self._selected_index)

    def action_save_attachment(self) -> None:
        """Save the selected attachment."""
        path = self._save_attachment(self._selected_index)
        preview = self.query_one("#preview", AttachmentPreview)
        if path:
            preview.show_message(f"Saved to: {path}")
        else:
            preview.show_message("Error saving attachment")

    def action_save_all(self) -> None:
        """Save all attachments."""
        config = get_config()
        save_dir = Path(config.attachments.save_directory).expanduser()
        saved = self.bor_app.mu.extract_all_attachments(self.message.path, str(save_dir))
        preview = self.query_one("#preview", AttachmentPreview)
        if saved:
            preview.show_message(f"Saved {len(saved)} file(s) to: {save_dir}")
        else:
            preview.show_message("Error saving attachments")

    def action_close(self) -> None:
        """Close this tab and return to the message view."""
        # Clear any displayed image first
        try:
            preview = self.query_one("#preview", AttachmentPreview)
            preview.clear_image()
        except Exception:
            pass
        # Reopen the message in this tab's position
        tab_id = self.get_tab_id()
        self.bor_app.open_message(self.message, replace_tab=tab_id)

    def action_return_to_index(self) -> None:
        """Return to message index."""
        # Clear any displayed image first
        try:
            preview = self.query_one("#preview", AttachmentPreview)
            preview.clear_image()
        except Exception:
            pass
        self.switch_to_index()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle attachment selection from list."""
        if event.item:
            index = event.item.index if hasattr(event.item, "index") else 0
            self._selected_index = index - 1  # Convert from 1-based
            self._preview_attachment(self._selected_index)
