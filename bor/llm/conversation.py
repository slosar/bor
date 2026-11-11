"""A tool-calling conversation over an OpenAI-compatible chat completions API.

`Conversation.ask()` streams one question to the model, runs the tools it asks
for (on worker threads), feeds the results back, and repeats until the model
answers. It yields events for the UI as it goes. If the question fails or is
cancelled part way, the history is rolled back to before it, so a half-finished
tool exchange never poisons the next request.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from bor.llm.tools import MailTools, ToolResult

# Sent once the tool-call budget for a question is spent
LIMIT_NOTE = (
    "The tool call limit for this question has been reached. Answer now with what you "
    "have found, and say what you could not check."
)
SKIPPED_NOTE = "Not run: the tool call limit for this question was reached."


@dataclass
class TextDelta:
    """A piece of the visible answer."""

    text: str


@dataclass
class Thinking:
    """The model is reasoning before it writes or calls a tool."""


@dataclass
class ToolStarted:
    name: str
    arguments: str


@dataclass
class ToolFinished:
    name: str
    result: ToolResult


@dataclass
class Usage:
    """Token use and cost of one question, summed over its requests."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float | None = None  # USD, when the provider reports it (OpenRouter does)

    def add(self, usage: Any) -> None:
        data = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)
        self.prompt_tokens += int(data.get("prompt_tokens") or 0)
        self.completion_tokens += int(data.get("completion_tokens") or 0)
        cost = data.get("cost")
        if cost is not None:
            self.cost = (self.cost or 0.0) + float(cost)


@dataclass
class TurnFinished:
    usage: Usage
    stopped_early: bool = False  # the tool call limit was reached


Event = TextDelta | Thinking | ToolStarted | ToolFinished | TurnFinished


class LLMError(Exception):
    """The API request failed; the message is fit to show the user."""


@dataclass
class _ToolCall:
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class _Round:
    """One streamed response, accumulated from its chunks."""

    content: str = ""
    calls: dict[int, _ToolCall] = field(default_factory=dict)
    reasoning: dict[tuple[Any, Any], dict[str, Any]] = field(default_factory=dict)

    def add_tool_call_delta(self, delta: Any) -> None:
        index = delta.index if delta.index is not None else 0
        call = self.calls.setdefault(index, _ToolCall())
        if delta.id:
            call.id = delta.id
        function = delta.function
        if function is not None:
            if function.name and function.name != call.name:
                call.name += function.name
            if function.arguments:
                call.arguments += function.arguments

    def add_reasoning(self, details: list[Any]) -> None:
        """Merge streamed reasoning_details fragments, keyed by type and index."""
        for detail in details:
            if not isinstance(detail, dict):
                continue
            key = (detail.get("type"), detail.get("index", 0))
            merged = self.reasoning.get(key)
            if merged is None:
                self.reasoning[key] = dict(detail)
                continue
            for name, value in detail.items():
                if name in ("text", "summary") and isinstance(value, str):
                    merged[name] = (merged.get(name) or "") + value
                elif value not in (None, ""):
                    merged[name] = value

    @property
    def tool_calls(self) -> list[_ToolCall]:
        calls = [self.calls[i] for i in sorted(self.calls)]
        for n, call in enumerate(calls):
            if not call.id:
                call.id = f"call_{n}"
        return [call for call in calls if call.name]

    def assistant_message(self, with_tool_calls: bool) -> dict[str, Any]:
        message: dict[str, Any] = {"role": "assistant", "content": self.content}
        calls = self.tool_calls if with_tool_calls else []
        if calls:
            message["content"] = self.content or None
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments or "{}"},
                }
                for call in calls
            ]
            # Reasoning models (Kimi, Claude, ...) expect their reasoning back
            # on tool-call turns to continue the same line of thought
            if self.reasoning:
                message["reasoning_details"] = list(self.reasoning.values())
        return message


class Conversation:
    """The message history with one model, and the loop that answers a question."""

    def __init__(
        self,
        client: Any,
        model: str,
        system_prompt: str,
        tools: MailTools,
        max_tool_calls: int = 30,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.tools = tools
        self.max_tool_calls = max_tool_calls
        self.extra_body = extra_body
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    async def ask(self, question: str) -> AsyncIterator[Event]:
        """Answer `question`, yielding events until a `TurnFinished`."""
        start = len(self.messages)
        self.messages.append({"role": "user", "content": question})
        usage = Usage()
        calls_made = 0
        finished = False
        try:
            while True:
                limit_reached = calls_made >= self.max_tool_calls
                if limit_reached:
                    self.messages.append({"role": "user", "content": LIMIT_NOTE})
                response = _Round()
                async for event in self._stream(response, usage, allow_tools=not limit_reached):
                    yield event

                calls = response.tool_calls
                if calls and not limit_reached:
                    self.messages.append(response.assistant_message(with_tool_calls=True))
                    # One at a time: the tools share mu and the handle table
                    for call in calls:
                        if calls_made >= self.max_tool_calls:
                            # Models batch calls; every call still needs a result
                            self.messages.append(
                                {"role": "tool", "tool_call_id": call.id, "content": SKIPPED_NOTE}
                            )
                            continue
                        yield ToolStarted(call.name, call.arguments)
                        result = await asyncio.to_thread(self.tools.run, call.name, call.arguments)
                        calls_made += 1
                        self.messages.append(
                            {"role": "tool", "tool_call_id": call.id, "content": result.content}
                        )
                        yield ToolFinished(call.name, result)
                    continue

                # The answer. Tool calls past the limit are not run.
                self.messages.append(response.assistant_message(with_tool_calls=False))
                finished = True
                yield TurnFinished(usage, stopped_early=limit_reached)
                return
        finally:
            if not finished:
                del self.messages[start:]

    async def _stream(self, response: _Round, usage: Usage, allow_tools: bool):
        """Send the history and accumulate the streamed reply into `response`."""
        request: dict[str, Any] = {
            "model": self.model,
            "messages": self.messages,
            "tools": self.tools.definitions,
            "tool_choice": "auto" if allow_tools else "none",
            "stream": True,
        }
        if self.extra_body:
            request["extra_body"] = self.extra_body
        else:
            request["stream_options"] = {"include_usage": True}

        try:
            stream = await self.client.chat.completions.create(**request)
            try:
                thinking = False
                async for chunk in stream:
                    if getattr(chunk, "usage", None):
                        usage.add(chunk.usage)
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    extra = getattr(delta, "model_extra", None) or {}
                    if (
                        extra.get("reasoning")
                        or extra.get("reasoning_content")
                        or extra.get("reasoning_details")
                    ):
                        response.add_reasoning(extra.get("reasoning_details") or [])
                        if not thinking:
                            thinking = True
                            yield Thinking()
                    if delta.content:
                        response.content += delta.content
                        yield TextDelta(delta.content)
                    for call_delta in delta.tool_calls or []:
                        response.add_tool_call_delta(call_delta)
            finally:
                # Release the HTTP connection promptly, also on cancel
                close = getattr(stream, "close", None)
                if close is not None:
                    with contextlib.suppress(Exception):
                        await close()
        except asyncio.CancelledError:
            raise
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(describe_api_error(e)) from e


def describe_api_error(error: Exception) -> str:
    """A one-line description of an API failure, with the provider's message if any."""
    status = getattr(error, "status_code", None)
    body = getattr(error, "body", None)
    message = ""
    if isinstance(body, dict):
        inner = body.get("error", body)
        if isinstance(inner, dict):
            message = str(inner.get("message") or "")
        if not message:
            message = str(body.get("message") or "")
    if not message:
        message = str(error) or type(error).__name__
    if status:
        return f"API error {status}: {message}"
    return f"{type(error).__name__}: {message}"
