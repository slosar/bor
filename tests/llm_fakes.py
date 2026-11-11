"""A scripted stand-in for the OpenAI-compatible streaming client.

Responses are built from real `ChatCompletionChunk` objects, so the parsing in
`bor.llm.conversation` is exercised against the SDK's own types (extra fields
such as `reasoning` land in `model_extra`, exactly as with OpenRouter).
"""

from __future__ import annotations

import asyncio
import copy
import json
from types import SimpleNamespace
from typing import Any

from openai.types.chat import ChatCompletionChunk


def chunk(
    content: str | None = None,
    reasoning: str | None = None,
    reasoning_details: list[dict] | None = None,
    tool_calls: list[dict] | None = None,
    finish: str | None = None,
) -> ChatCompletionChunk:
    delta: dict[str, Any] = {}
    if content is not None:
        delta["content"] = content
    if reasoning is not None:
        delta["reasoning"] = reasoning
    if reasoning_details is not None:
        delta["reasoning_details"] = reasoning_details
    if tool_calls is not None:
        delta["tool_calls"] = tool_calls
    return ChatCompletionChunk.model_validate(
        {
            "id": "gen-1",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "test/model",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
    )


def usage_chunk(prompt: int, completion: int, cost: float | None = None) -> ChatCompletionChunk:
    usage: dict[str, Any] = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }
    if cost is not None:
        usage["cost"] = cost
    return ChatCompletionChunk.model_validate(
        {
            "id": "gen-1",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "test/model",
            "choices": [],
            "usage": usage,
        }
    )


def text_response(text: str, prompt: int = 100, completion: int = 20, cost: float | None = 0.001):
    """A plain answer, streamed in two pieces, with a reasoning fragment first."""
    half = len(text) // 2
    return [
        chunk(reasoning="Let me think.", reasoning_details=[{"type": "reasoning.text", "text": "Let me think.", "index": 0}]),
        chunk(content=text[:half]),
        chunk(content=text[half:], finish="stop"),
        usage_chunk(prompt, completion, cost),
    ]


def tool_response(name: str, arguments: dict, call_id: str = "call_1", cost: float | None = 0.001):
    """One tool call, its arguments streamed in two fragments, after some reasoning."""
    args = json.dumps(arguments)
    half = len(args) // 2
    return [
        chunk(reasoning="I should search.", reasoning_details=[{"type": "reasoning.text", "text": "I should ", "index": 0}]),
        chunk(reasoning_details=[{"type": "reasoning.text", "text": "search.", "index": 0}]),
        chunk(
            tool_calls=[
                {"index": 0, "id": call_id, "type": "function", "function": {"name": name, "arguments": args[:half]}}
            ]
        ),
        chunk(tool_calls=[{"index": 0, "function": {"arguments": args[half:]}}], finish="tool_calls"),
        usage_chunk(50, 10, cost),
    ]


class FakeStream:
    def __init__(self, chunks: list, delay: float = 0.0) -> None:
        self._chunks = chunks
        self._delay = delay
        self.closed = False

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for item in self._chunks:
            await asyncio.sleep(self._delay)
            if isinstance(item, Exception):
                raise item
            yield item

    async def close(self) -> None:
        self.closed = True


class FakeClient:
    """Replays scripted responses in order and records every request."""

    def __init__(self, responses: list, delay: float = 0.0) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.streams: list[FakeStream] = []
        self.delay = delay
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **request: Any) -> FakeStream:
        # The history list is mutated afterwards; keep what was actually sent
        self.requests.append(copy.deepcopy(request))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        stream = FakeStream(response, self.delay)
        self.streams.append(stream)
        return stream
