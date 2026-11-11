"""LLM tab: ask questions about your mail and read the answers.

The conversation itself lives in the app's `LLMSession`; this tab draws its
transcript and runs one question at a time in a worker, so the rest of Bor
stays usable while the model searches.
"""

from __future__ import annotations

import asyncio

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Input, Label, Markdown, Static
from textual.worker import Worker

from bor.editing import kill_input_to_end
from bor.llm.conversation import (
    LLMError,
    TextDelta,
    Thinking,
    ToolFinished,
    ToolStarted,
    TurnFinished,
    Usage,
)
from bor.llm.session import LLMSession, TranscriptEntry
from bor.tabs.base import BaseTab

# Transcript entry kind -> CSS class of its widget
_ENTRY_CLASSES = {
    "question": "llm-question",
    "tool": "llm-tool",
    "tool_error": "llm-tool-error",
    "usage": "llm-usage",
    "info": "llm-info",
    "error": "llm-error",
}


class QuestionInput(Input):
    """The question line: Up/Down browse earlier questions, Ctrl+K kills to the end."""

    def __init__(self, history: list[str], **kwargs) -> None:
        super().__init__(placeholder="Ask about your mail…", **kwargs)
        self._history = history  # shared with the session, so it outlives the tab
        self._history_pos = -1  # -1: not browsing
        self._saved_value = ""

    def on_key(self, event: events.Key) -> None:
        if event.key == "ctrl+k":
            kill_input_to_end(self)
        elif event.key == "up":
            if not self._history:
                return
            if self._history_pos == -1:
                self._saved_value = self.value
                self._history_pos = len(self._history) - 1
            elif self._history_pos > 0:
                self._history_pos -= 1
            self.value = self._history[self._history_pos]
            self.cursor_position = len(self.value)
        elif event.key == "down":
            if self._history_pos == -1:
                return
            if self._history_pos < len(self._history) - 1:
                self._history_pos += 1
                self.value = self._history[self._history_pos]
            else:
                self._history_pos = -1
                self.value = self._saved_value
            self.cursor_position = len(self.value)
        else:
            return
        event.prevent_default()
        event.stop()

    def reset_history_browsing(self) -> None:
        self._history_pos = -1
        self._saved_value = ""


class LLMWidget(BaseTab):
    """Chat with the mail assistant."""

    BINDINGS = [
        Binding("escape", "cancel_or_back", "Cancel/Back"),
        Binding("ctrl+n", "new_conversation", "New Conversation"),
        Binding("pageup", "scroll_transcript(-1)", "Page Up", show=False),
        Binding("pagedown", "scroll_transcript(1)", "Page Down", show=False),
    ]

    DEFAULT_CSS = """
    LLMWidget {
        height: 1fr;
    }

    LLMWidget #llm-transcript {
        height: 1fr;
        padding: 0 1;
    }

    LLMWidget .llm-question {
        margin: 1 0 0 0;
        text-style: bold;
        color: $accent;
    }

    LLMWidget .llm-tool, LLMWidget .llm-usage, LLMWidget .llm-info {
        color: $text-muted;
    }

    LLMWidget .llm-usage {
        margin: 0 0 1 0;
    }

    LLMWidget .llm-tool-error, LLMWidget .llm-error {
        color: $error;
    }

    LLMWidget Markdown {
        margin: 0;
        padding: 0;
    }

    LLMWidget #llm-status {
        height: 1;
        width: 100%;
        background: $surface;
        padding: 0 1;
    }

    LLMWidget #llm-input {
        margin: 0;
    }
    """

    def __init__(self, initial_question: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._initial_question = initial_question
        self._worker: Worker | None = None

    @property
    def session(self) -> LLMSession:
        return self.bor_app.llm

    @property
    def is_running(self) -> bool:
        return self._worker is not None and self._worker.is_running

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="llm-transcript", can_focus=False)
        yield Label("", id="llm-status")
        yield QuestionInput(self.session.history, id="llm-input")

    def on_mount(self) -> None:
        transcript = self.query_one("#llm-transcript", VerticalScroll)
        for entry in self.session.transcript:
            transcript.mount(self._entry_widget(entry))
        transcript.scroll_end(animate=False)
        self._set_idle_status()
        reason = self.session.unavailable_reason()
        if reason:
            self._add("error", reason, record=False)
        if self._initial_question:
            question, self._initial_question = self._initial_question, None
            self.ask(question)
        self.query_one(QuestionInput).focus()

    def on_focus(self, event: events.Focus) -> None:
        """Focus landing on the tab itself (e.g. Alt+digit) goes to the question line."""
        self.query_one(QuestionInput).focus()

    # ------------------------------------------------------------------
    # Asking

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        question_input = self.query_one(QuestionInput)
        if self.is_running:
            self.app.notify("Still answering. Esc cancels.", markup=False)
            return
        question = event.value.strip()
        if question:
            question_input.value = ""
            question_input.reset_history_browsing()
            self.ask(question)

    def ask(self, question: str) -> None:
        """Send a question, unless one is still being answered."""
        question = question.strip()
        if not question:
            return
        if self.is_running:
            self.app.notify("Still answering. Esc cancels.", markup=False)
            return
        reason = self.session.unavailable_reason()
        if reason:
            self._add("error", reason, record=False)
            return
        self.session.remember(question)
        self._add("question", question)
        # Context is captured now, from what the index shows at this moment
        message = self.session.prepare_question(question)
        self._worker = self.run_worker(
            self._answer(message), group="llm-question", exclusive=True, exit_on_error=False
        )

    async def _answer(self, message: str) -> None:
        """Stream one answer into the transcript."""
        transcript = self.query_one("#llm-transcript", VerticalScroll)
        answer: TranscriptEntry | None = None
        stream = None
        self._set_status("Thinking…  (Esc cancels)")

        async def close_stream() -> None:
            nonlocal stream, answer
            if stream is not None:
                await stream.stop()
                stream = None
            answer = None

        try:
            async for event in self.session.conversation().ask(message):
                if isinstance(event, Thinking):
                    self._set_status("Thinking…  (Esc cancels)")
                elif isinstance(event, TextDelta):
                    if stream is None:
                        answer = TranscriptEntry("answer", "")
                        self.session.transcript.append(answer)
                        markdown = Markdown()
                        await transcript.mount(markdown)
                        stream = Markdown.get_stream(markdown)
                        self._set_status("Answering…  (Esc cancels)")
                    assert answer is not None
                    answer.text += event.text
                    await stream.write(event.text)
                    transcript.scroll_end(animate=False)
                elif isinstance(event, ToolStarted):
                    await close_stream()
                    self._set_status(f"Running {event.name}…  (Esc cancels)")
                elif isinstance(event, ToolFinished):
                    kind = "tool_error" if event.result.error else "tool"
                    self._add(kind, event.result.summary)
                    if event.name == "show_results" and not event.result.error:
                        self.bor_app.llm_results_changed()
                    self._set_status("Thinking…  (Esc cancels)")
                elif isinstance(event, TurnFinished):
                    # Text written before the last tool call is not the answer
                    had_answer = answer is not None
                    await close_stream()
                    if event.stopped_early:
                        self._add("info", "Stopped searching: tool call limit reached.")
                    elif not had_answer:
                        self._add("info", "(The model gave no answer.)")
                    self._add("usage", _usage_line(event.usage))
                    self._notify_if_away("Answer ready in the LLM tab.")
        except asyncio.CancelledError:
            self._add("info", "Cancelled.")
            raise
        except LLMError as e:
            self._add("error", str(e))
            self._notify_if_away("The LLM request failed.", severity="error")
        except Exception as e:
            self._add("error", f"{type(e).__name__}: {e}")
        finally:
            if stream is not None:
                await stream.stop()
            self._set_idle_status()

    # ------------------------------------------------------------------
    # Actions

    def action_cancel_or_back(self) -> None:
        """Esc: cancel the question being answered, otherwise go back to the index."""
        if self.is_running and self._worker is not None:
            self._worker.cancel()
        else:
            self.switch_to_index()

    async def action_new_conversation(self) -> None:
        """Ctrl+N: forget the conversation and clear the transcript."""
        if self.is_running and self._worker is not None:
            self._worker.cancel()
            await self.workers.wait_for_complete()
        self.session.new_conversation()
        await self.query_one("#llm-transcript", VerticalScroll).remove_children()
        self._add("info", "New conversation.", record=False)

    def action_scroll_transcript(self, direction: int) -> None:
        transcript = self.query_one("#llm-transcript", VerticalScroll)
        if direction < 0:
            transcript.scroll_page_up()
        else:
            transcript.scroll_page_down()

    # ------------------------------------------------------------------
    # Drawing

    def _add(self, kind: str, text: str, record: bool = True) -> None:
        """Append a non-answer entry to the transcript (and the session's copy)."""
        entry = TranscriptEntry(kind, text)
        if record:
            self.session.transcript.append(entry)
        try:
            transcript = self.query_one("#llm-transcript", VerticalScroll)
        except Exception:
            return  # the tab is being closed
        transcript.mount(self._entry_widget(entry))
        transcript.scroll_end(animate=False)

    def _entry_widget(self, entry: TranscriptEntry) -> Widget:
        if entry.kind == "answer":
            return Markdown(entry.text)
        prefix = {"question": "› ", "tool": "  ", "tool_error": "  ✗ "}.get(entry.kind, "")
        # Text, not a markup string: questions and mail subjects may contain [brackets]
        return Static(Text(prefix + entry.text), classes=_ENTRY_CLASSES.get(entry.kind, ""))

    def _set_status(self, text: str) -> None:
        try:
            self.query_one("#llm-status", Label).update(Text(f"{self.session.model} · {text}"))
        except Exception:
            pass

    def _set_idle_status(self) -> None:
        self._set_status("Enter ask · ↑/↓ history · Esc back · Ctrl+N new conversation")

    def _notify_if_away(self, message: str, severity: str = "information") -> None:
        """Tell the user an answer is ready when they are looking at another tab."""
        if self.bor_app._active_tab_id != self.get_tab_id():
            self.app.notify(message, title="LLM", severity=severity, markup=False)  # type: ignore[arg-type]


def _usage_line(usage: Usage) -> str:
    tokens = f"{_compact(usage.prompt_tokens)} in · {_compact(usage.completion_tokens)} out"
    if usage.cost is not None:
        return f"{tokens} · ${usage.cost:.4f}"
    return tokens


def _compact(count: int) -> str:
    return f"{count / 1000:.1f}k" if count >= 1000 else str(count)
