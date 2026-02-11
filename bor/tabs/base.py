"""
Base tab widget for Bor email reader.

Provides common functionality for all tab types.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widget import Widget

if TYPE_CHECKING:
    from bor.app import BorApp


class BaseTab(Widget):
    """
    Base class for all tab widgets.

    Provides common functionality and access to the main application.
    """

    can_focus = True

    def __init__(self, *args, **kwargs) -> None:
        """Initialize the base tab."""
        super().__init__(*args, **kwargs)

    @property
    def bor_app(self) -> "BorApp":
        """Get the Bor application instance."""
        from bor.app import BorApp
        app = self.app
        assert isinstance(app, BorApp)
        return app

    def close_tab(self) -> None:
        """Close this tab."""
        # Find our tab pane
        parent = self.parent
        while parent is not None:
            if hasattr(parent, "id") and parent.id and parent.id.startswith("tab-"):
                self.bor_app.close_tab(parent.id)
                return
            parent = parent.parent

    def get_tab_id(self) -> str:
        """Get the ID of this tab."""
        parent = self.parent
        while parent is not None:
            if hasattr(parent, "id") and parent.id and parent.id.startswith("tab-"):
                return parent.id
            parent = parent.parent
        return ""

    def update_tab_title(self, title: str) -> None:
        """Update the title of this tab."""
        tab_id = self.get_tab_id()
        if tab_id:
            self.bor_app.update_tab_title(tab_id, title)

    def switch_to_index(self) -> None:
        """Switch to the message index tab."""
        self.bor_app.action_switch_tab(0)
