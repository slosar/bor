"""Tests for message index UI helpers."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable

from bor.tabs.message_index import FlagBar, ReplyBar


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


class FlagBarTestApp(App[None]):
    """Minimal app for exercising FlagBar key trapping."""

    BINDINGS = [Binding("p", "parent_previous", "Previous")]

    def __init__(self) -> None:
        super().__init__()
        self.flag_key: str | None = None
        self.parent_previous_called = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield DataTable(id="message-table")
            yield FlagBar("", id="flag-bar")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_column("Subject")
        table.add_row("Test message")
        table.focus()

    def ask_flag(self) -> None:
        self.query_one(FlagBar).ask(self.set_flag_key)

    def set_flag_key(self, flag_key: str) -> None:
        self.flag_key = flag_key

    def action_parent_previous(self) -> None:
        self.parent_previous_called = True


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


@pytest.mark.asyncio
async def test_flag_bar_ignores_unrelated_keys_without_leaving_prompt() -> None:
    app = FlagBarTestApp()

    async with app.run_test() as pilot:
        await pilot.pause()

        app.ask_flag()
        await pilot.pause()
        flag_bar = app.query_one(FlagBar)
        assert app.focused is flag_bar

        await pilot.press("p")
        await pilot.pause()

        assert flag_bar.has_class("visible")
        assert app.focused is flag_bar
        assert app.flag_key is None
        assert app.parent_previous_called is False
