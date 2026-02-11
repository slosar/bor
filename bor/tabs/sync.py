"""
Synchronization tab for Bor email reader.

Runs an external synchronization command and displays output.
"""

from __future__ import annotations

import asyncio
import subprocess
import shlex
from typing import Optional

from textual import events, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, ScrollableContainer
from textual.widgets import Static, Label, Log
from textual.reactive import reactive

from bor.tabs.base import BaseTab


class SyncOutput(Log):
    """Widget to display sync command output."""

    DEFAULT_CSS = """
    SyncOutput {
        height: 1fr;
        border: solid $primary;
        padding: 1;
    }
    """


class SyncWidget(BaseTab):
    """
    Synchronization widget.

    Runs an external synchronization command and displays its output in real-time.
    """

    BINDINGS = [
        Binding("x", "close", "Close"),
        Binding("m", "return_to_index", "To Index"),
        Binding("r", "rerun", "Re-run Sync"),
        Binding("ctrl+c", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    SyncWidget {
        height: 1fr;
    }

    SyncWidget .header-bar {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    SyncWidget .status-bar {
        height: 1;
        dock: bottom;
        background: $surface;
        padding: 0 1;
    }
    """

    running: reactive[bool] = reactive(False)
    exit_code: reactive[Optional[int]] = reactive(None)

    def __init__(self, command: str, *args, **kwargs) -> None:
        """
        Initialize the sync widget.

        Args:
            command: Shell command to run for synchronization
        """
        super().__init__(*args, **kwargs)
        self.command = command
        self._process: Optional[asyncio.subprocess.Process] = None

    def compose(self) -> ComposeResult:
        """Create the widget layout."""
        with Vertical():
            with Container(classes="header-bar"):
                yield Label(f"Running: {self.command}", id="command-label")
            yield SyncOutput(id="output")
            with Container(classes="status-bar"):
                yield Label("Starting...", id="status-label")

    async def on_mount(self) -> None:
        """Handle widget mount."""
        self.run_sync()

    @work(exclusive=True)
    async def run_sync(self) -> None:
        """Run the synchronization command."""
        self.running = True
        self.exit_code = None

        output = self.query_one("#output", SyncOutput)
        status = self.query_one("#status-label", Label)

        output.clear()
        status.update("Running...")

        try:
            # Parse command
            args = shlex.split(self.command)

            # Create subprocess
            self._process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            # Read output in real-time
            while True:
                if self._process.stdout is None:
                    break

                line = await self._process.stdout.readline()
                if not line:
                    break

                text = line.decode("utf-8", errors="replace")
                output.write_line(text.rstrip())

            # Wait for process to complete
            await self._process.wait()
            self.exit_code = self._process.returncode

            # Update status
            if self.exit_code == 0:
                status.update("✓ Completed successfully")
                output.write_line("\n--- Sync completed successfully ---")

                # Re-index after successful sync
                output.write_line("\nRunning mu index...")
                self.bor_app.mu.index()
                output.write_line("Index updated.")
                
                # Refresh the message index if it exists
                await self._refresh_message_index()
                
                # Close this tab after successful sync
                self.close_tab()
            else:
                status.update(f"✗ Failed with exit code {self.exit_code}")
                output.write_line(f"\n--- Sync failed with exit code {self.exit_code} ---")

        except FileNotFoundError:
            status.update("✗ Command not found")
            output.write_line(f"Error: Command not found: {self.command}")

        except Exception as e:
            status.update(f"✗ Error: {e}")
            output.write_line(f"Error: {e}")

        finally:
            self.running = False
            self._process = None

    async def _refresh_message_index(self) -> None:
        """Refresh the message index tab if it exists."""
        try:
            from bor.tabs.message_index import MessageIndexWidget
            
            # Find the message index widget
            index_widget = self.app.query_one("MessageIndexWidget", MessageIndexWidget)
            if index_widget:
                await index_widget.action_refresh()
        except Exception:
            # Message index might not exist or be mounted
            pass

    async def _cancel_sync(self) -> None:
        """Cancel the running sync process."""
        if self._process and self.running:
            try:
                self._process.terminate()
                await asyncio.sleep(0.5)
                if self._process.returncode is None:
                    self._process.kill()

                output = self.query_one("#output", SyncOutput)
                status = self.query_one("#status-label", Label)
                output.write_line("\n--- Cancelled by user ---")
                status.update("Cancelled")

            except Exception:
                pass

    # Actions

    def action_close(self) -> None:
        """Close this tab."""
        if self.running:
            asyncio.create_task(self._cancel_sync())
        self.close_tab()

    def action_return_to_index(self) -> None:
        """Return to message index."""
        self.switch_to_index()

    def action_rerun(self) -> None:
        """Re-run the sync command."""
        if not self.running:
            self.run_sync()  # @work decorator handles async

    def action_cancel(self) -> None:
        """Cancel the running command."""
        if self.running:
            asyncio.create_task(self._cancel_sync())
