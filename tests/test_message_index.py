"""Tests for message index UI helpers."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable

from bor.tabs.message_index import ReplyBar


class ReplyBarTestApp(App[None]):
    """Minimal app for exercising ReplyBar focus behavior."""

    def __init__(self) -> None:
        super().__init__()
        self.reply_all: bool | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield DataTable(id="message-table")
            yield ReplyBar("", id="reply-bar")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_column("Subject")
        table.add_row("Test message")
        table.focus()

    def ask_reply(self) -> None:
        self.query_one(ReplyBar).ask(self.set_reply_all)

    def set_reply_all(self, reply_all: bool) -> None:
        self.reply_all = reply_all


@pytest.mark.asyncio
async def test_reply_bar_escape_restores_previous_focus() -> None:
    app = ReplyBarTestApp()

    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(DataTable)

        app.ask_reply()
        await pilot.pause()
        assert app.focused is app.query_one(ReplyBar)

        await pilot.press("escape")
        await pilot.pause()

        assert app.focused is table
        assert app.reply_all is None


@pytest.mark.asyncio
async def test_reply_bar_accept_restores_previous_focus_and_calls_callback() -> None:
    app = ReplyBarTestApp()

    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(DataTable)

        app.ask_reply()
        await pilot.pause()

        await pilot.press("a")
        await pilot.pause()

        assert app.focused is table
        assert app.reply_all is True
