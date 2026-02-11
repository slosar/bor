"""
Main Bor email application.

The main Textual application that manages tabs and coordinates
between different views (message index, message view, compose, etc.)
"""

from __future__ import annotations

from typing import Dict, List, Optional, TYPE_CHECKING

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import TabbedContent, TabPane, Footer, Header

from bor.config import get_config, Config
from bor.mu import MuInterface, EmailMessage
from bor.tabs.base import BaseTab

if TYPE_CHECKING:
    pass


# Alt+digit unicode character mapping (varies by OS/terminal)
ALT_DIGIT_MAP = {
    "¡": 1,  # Alt+1
    "™": 2,  # Alt+2
    "£": 3,  # Alt+3
    "¢": 4,  # Alt+4
    "∞": 5,  # Alt+5
    "§": 6,  # Alt+6
    "¶": 7,  # Alt+7
    "•": 8,  # Alt+8
    "ª": 9,  # Alt+9
    "º": 0,  # Alt+0 (U+00BA)
}


class BorTabbedContent(TabbedContent):
    """Extended TabbedContent with tab change notifications."""

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Handle tab activation."""
        pass


class BorApp(App):
    """
    Main Bor email application.

    A terminal-based email client using mu for email access
    and textual for the user interface.
    """

    TITLE = " 🌲 🌲 🌲 BOR 🌲 🌲 🌲"
    CSS = """
    TabbedContent {
        height: 1fr;
    }

    TabPane {
        height: 1fr;
        padding: 0;
    }

    #message-index {
        height: 1fr;
    }

    .header-row {
        height: auto;
        padding: 0 1;
        background: $surface;
    }

    .message-list {
        height: 1fr;
    }

    .message-row {
        height: 1;
    }

    .message-row.unread {
        color: $primary;
    }

    .message-row.important {
        color: $warning;
    }

    .message-row.marked {
        background: $primary-darken-1;
    }

    .status-bar {
        height: 1;
        dock: bottom;
        background: $surface;
        padding: 0 1;
    }

    .search-input {
        width: 100%;
        height: 1;
    }

    MessageView {
        height: 1fr;
    }

    .message-header {
        background: $surface;
        padding: 1;
    }

    .message-body {
        height: 1fr;
        padding: 1;
    }

    ComposeView {
        height: 1fr;
    }

    .compose-header {
        height: auto;
        padding: 1;
    }

    .compose-body {
        height: 1fr;
    }

    Input {
        margin: 0 0 1 0;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True, show=False),
        Binding("ctrl+pageup", "prev_tab", "Previous Tab", priority=True, show=False),
        Binding("ctrl+pagedown", "next_tab", "Next Tab", priority=True, show=False),
        Binding("alt+0", "switch_tab(0)", "Tab 0", priority=True, show=False),
        Binding("alt+1", "switch_tab(1)", "Tab 1", priority=True, show=False),
        Binding("alt+2", "switch_tab(2)", "Tab 2", priority=True, show=False),
        Binding("alt+3", "switch_tab(3)", "Tab 3", priority=True, show=False),
        Binding("alt+4", "switch_tab(4)", "Tab 4", priority=True, show=False),
        Binding("alt+5", "switch_tab(5)", "Tab 5", priority=True, show=False),
        Binding("alt+6", "switch_tab(6)", "Tab 6", priority=True, show=False),
        Binding("alt+7", "switch_tab(7)", "Tab 7", priority=True, show=False),
        Binding("alt+8", "switch_tab(8)", "Tab 8", priority=True, show=False),
        Binding("alt+9", "switch_tab(9)", "Tab 9", priority=True, show=False),
    ]

    def __init__(self) -> None:
        """Initialize the Bor application."""
        super().__init__()
        self.config: Config = get_config()
        self.mu: MuInterface = MuInterface()
        self._tab_counter: int = 0
        self._tabs: Dict[str, TabPane] = {}
        self._tab_order: List[str] = []
        self._current_messages: List[EmailMessage] = []
        self._current_index: int = 0
        self._marked_messages: set = set()
        self._threading_enabled: bool = self.config.threading.enabled

    def compose(self) -> ComposeResult:
        """Create the application layout."""
        yield Header()
        with BorTabbedContent(id="tabs"):
            # Tab 0: Message Index (always present)
            with TabPane("Message Index", id="tab-0"):
                from bor.tabs.message_index import MessageIndexWidget
                yield MessageIndexWidget(id="message-index")
        yield Footer()

    def on_mount(self) -> None:
        """Handle application mount."""
        # Load inbox by default, then focus
        self.call_later(self._load_inbox)

    async def _focus_message_index(self) -> None:
        """Focus the message index after loading."""
        from bor.tabs.message_index import MessageIndexWidget
        try:
            widget = self.query_one(MessageIndexWidget)
            widget.focus()
            # Also focus the data table inside
            table = widget.query_one("DataTable")
            table.focus()
        except Exception:
            pass

    def _focus_widget(self, widget: "BaseTab") -> None:
        """Focus a widget and its first focusable child."""
        try:
            widget.focus()
            # Try to focus first focusable child (e.g., ScrollableContainer)
            for child in widget.walk_children():
                if child.can_focus:
                    child.focus()
                    break
        except Exception:
            pass

    async def _load_inbox(self) -> None:
        """Load inbox messages on startup."""
        from bor.tabs.message_index import MessageIndexWidget
        widget = self.query_one(MessageIndexWidget)
        await widget.search(f'maildir:"{self.config.folders.inbox}"')
        # Focus after loading
        await self._focus_message_index()

    def on_key(self, event: events.Key) -> None:
        """Handle key events for tab switching."""
        if event.key == "ctrl+pageup":
            self.action_prev_tab()
            event.prevent_default()
            event.stop()
            return
        if event.key == "ctrl+pagedown":
            self.action_next_tab()
            event.prevent_default()
            event.stop()
            return
        if event.key and event.key.startswith("alt+"):
            alt_digit = event.key.split("+")[-1]
            if alt_digit.isdigit():
                self.action_switch_tab(int(alt_digit))
                event.prevent_default()
                event.stop()
                return
        char = event.character
        if char in ALT_DIGIT_MAP:
            index = ALT_DIGIT_MAP[char]
            self.action_switch_tab(index)
            event.prevent_default()
            event.stop()

    def _ordered_tab_ids(self) -> list[str]:
        """Get tab IDs in display order (tab-0 first)."""
        ordered = [tab_id for tab_id in self._tab_order if tab_id in self._tabs]
        return ["tab-0", *ordered]

    def action_switch_tab(self, index: int) -> None:
        """
        Switch to a specific tab by index.

        Args:
            index: Tab index (0-9)
        """
        tabs = self.query_one(BorTabbedContent)
        tab_ids = self._ordered_tab_ids()
        if 0 <= index < len(tab_ids):
            tabs.active = tab_ids[index]
            self.call_later(lambda: self._focus_active_tab())

    def _is_compose_active(self) -> bool:
        """Check if the active tab is a compose tab."""
        from bor.tabs.compose import ComposeWidget

        tabs = self.query_one(BorTabbedContent)
        active_id = tabs.active
        if not active_id or active_id == "tab-0":
            return False

        pane = self._tabs.get(active_id)
        if not pane:
            return False

        return any(isinstance(child, ComposeWidget) for child in pane.walk_children())

    def action_quit(self) -> None:
        """Quit the application unless compose is active."""
        if self._is_compose_active():
            return
        self.exit()

    def _focus_active_tab(self) -> None:
        """Focus the content of the currently active tab."""
        tabs = self.query_one(BorTabbedContent)
        active_id = tabs.active
        if active_id == "tab-0":
            # Focus message index
            from bor.tabs.message_index import MessageIndexWidget
            try:
                widget = self.query_one(MessageIndexWidget)
                table = widget.query_one("DataTable")
                table.focus()
            except Exception:
                pass
        elif active_id in self._tabs:
            # Focus the widget in the active pane
            pane = self._tabs[active_id]
            for child in pane.walk_children():
                if isinstance(child, BaseTab):
                    self._focus_widget(child)
                    break
                if hasattr(child, "can_focus") and child.can_focus:
                    child.focus()
                    break

    def action_prev_tab(self) -> None:
        """Switch to the previous tab."""
        tabs = self.query_one(BorTabbedContent)
        tab_ids = self._ordered_tab_ids()
        current = tabs.active or "tab-0"
        if current in tab_ids:
            idx = tab_ids.index(current)
            new_idx = (idx - 1) % len(tab_ids)
            tabs.active = tab_ids[new_idx]
            self.call_later(lambda: self._focus_active_tab())

    def action_next_tab(self) -> None:
        """Switch to the next tab."""
        tabs = self.query_one(BorTabbedContent)
        tab_ids = self._ordered_tab_ids()
        current = tabs.active or "tab-0"
        if current in tab_ids:
            idx = tab_ids.index(current)
            new_idx = (idx + 1) % len(tab_ids)
            tabs.active = tab_ids[new_idx]
            self.call_later(lambda: self._focus_active_tab())

    def add_tab(self, title: str, widget: "BaseTab", replace_id: Optional[str] = None) -> str:
        """
        Add a new tab to the application.

        Args:
            title: Tab title
            widget: Widget to display in the tab
            replace_id: If provided, replace this tab instead of creating new

        Returns:
            Tab ID
        """
        tabs = self.query_one(BorTabbedContent)

        # Find next available tab number
        self._tab_counter += 1
        tab_id = f"tab-{self._tab_counter}"

        # Create and add the new tab pane FIRST
        pane = TabPane(title, id=tab_id)
        tabs.add_pane(pane)

        # Now remove old tab if replacing (after new one is added to avoid focus loss)
        replace_index: Optional[int] = None
        if replace_id and replace_id in self._tabs:
            if replace_id in self._tab_order:
                replace_index = self._tab_order.index(replace_id)
            tabs.remove_pane(replace_id)
            del self._tabs[replace_id]

        # Mount the widget in the pane
        pane.mount(widget)

        self._tabs[tab_id] = pane
        if replace_index is not None:
            self._tab_order[replace_index] = tab_id
        else:
            self._tab_order.append(tab_id)
        tabs.active = tab_id
        
        # Defer focus to ensure widget is fully mounted
        self.call_later(lambda: self._focus_widget(widget))

        return tab_id

    def update_tab_title(self, tab_id: str, title: str) -> None:
        """
        Update the title of a tab.

        Args:
            tab_id: ID of the tab to update
            title: New title for the tab
        """
        if tab_id in self._tabs:
            tabs = self.query_one(BorTabbedContent)
            # Get the Tab widget (button) for this pane
            try:
                tab = tabs.get_tab(tab_id)
                tab.label = title
            except Exception:
                pass

    def close_tab(self, tab_id: str) -> None:
        """
        Close a tab.

        Args:
            tab_id: ID of the tab to close
        """
        if tab_id == "tab-0":
            # Cannot close message index
            return

        if tab_id in self._tabs:
            tabs = self.query_one(BorTabbedContent)
            pane = self._tabs[tab_id]
            # Use remove_pane to properly remove both the tab button and pane
            tabs.remove_pane(tab_id)
            del self._tabs[tab_id]
            if tab_id in self._tab_order:
                self._tab_order.remove(tab_id)

            # Switch to message index and focus it
            tabs.active = "tab-0"
            self.call_later(lambda: self._focus_active_tab())

    def open_message(self, message: EmailMessage, replace_tab: Optional[str] = None) -> None:
        """
        Open a message in a new tab.

        Args:
            message: Message to display
            replace_tab: Tab ID to replace (if returning from attachments, etc.)
        """
        from bor.tabs.message import MessageViewWidget

        # If replacing a tab, just open the message in that slot
        if replace_tab:
            import hashlib
            safe_id = hashlib.md5(message.path.encode()).hexdigest()[:12]
            widget = MessageViewWidget(message, id=f"msg-{safe_id}")
            title = message.subject[:20] + "..." if len(message.subject) > 20 else message.subject
            self.add_tab(title, widget, replace_id=replace_tab)
            return

        # Find if we already have a tab for this message
        for tab_id, pane in self._tabs.items():
            # Check if any child is a MessageViewWidget with same message
            for child in pane.walk_children():
                if isinstance(child, MessageViewWidget):
                    if child.message and child.message.path == message.path:
                        # Switch to existing tab
                        tabs = self.query_one(BorTabbedContent)
                        tabs.active = tab_id
                        return

        # Create new message view - use hash of path for ID (path contains invalid chars)
        import hashlib
        safe_id = hashlib.md5(message.path.encode()).hexdigest()[:12]
        widget = MessageViewWidget(message, id=f"msg-{safe_id}")
        title = message.subject[:20] + "..." if len(message.subject) > 20 else message.subject
        self.add_tab(title, widget)

    def open_compose(
        self,
        reply_to: Optional[EmailMessage] = None,
        forward: Optional[EmailMessage] = None,
        edit_draft: Optional[EmailMessage] = None,
        replace_tab: Optional[str] = None,
        reply_all: bool = False
    ) -> None:
        """
        Open the compose tab.

        Args:
            reply_to: Message to reply to
            forward: Message to forward
            edit_draft: Draft to edit
            replace_tab: Tab ID to replace
            reply_all: If True, include CC recipients in reply
        """
        from bor.tabs.compose import ComposeWidget

        widget = ComposeWidget(
            reply_to=reply_to,
            forward=forward,
            edit_draft=edit_draft,
            reply_all=reply_all
        )

        if reply_to:
            title = f"Re: {reply_to.subject[:15]}..."
        elif forward:
            title = f"Fwd: {forward.subject[:15]}..."
        elif edit_draft:
            title = f"Draft: {edit_draft.subject[:15]}..."
        else:
            title = "New Message"

        self.add_tab(title, widget, replace_id=replace_tab)

    def open_attachments(self, message: EmailMessage, replace_tab: Optional[str] = None) -> None:
        """
        Open the attachments tab for a message.

        Args:
            message: Message with attachments
            replace_tab: Tab ID to replace
        """
        from bor.tabs.attachments import AttachmentsWidget

        widget = AttachmentsWidget(message)
        title = f"Attachments ({len(message.attachments)})"
        self.add_tab(title, widget, replace_id=replace_tab)

    def open_sync(self) -> None:
        """Open the synchronization tab."""
        from bor.tabs.sync import SyncWidget

        widget = SyncWidget(self.config.sync.command)
        self.add_tab("Sync", widget)

    def get_current_message(self) -> Optional[EmailMessage]:
        """Get the currently focused message."""
        if 0 <= self._current_index < len(self._current_messages):
            return self._current_messages[self._current_index]
        return None

    def get_next_message(self) -> Optional[EmailMessage]:
        """Get the next message in the list."""
        if self._current_index + 1 < len(self._current_messages):
            self._current_index += 1
            return self._current_messages[self._current_index]
        return None

    def get_prev_message(self) -> Optional[EmailMessage]:
        """Get the previous message in the list."""
        if self._current_index > 0:
            self._current_index -= 1
            return self._current_messages[self._current_index]
        return None


def main() -> None:
    """Main entry point for Bor application."""
    app = BorApp()
    app.run()


if __name__ == "__main__":
    main()
