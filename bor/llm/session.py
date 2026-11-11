"""The app-wide LLM state: the conversation, message handles and transcript.

It lives on the app rather than in the LLM tab, so closing the tab does not
end the conversation; only Ctrl+N (new conversation) or quitting Bor does.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bor.config import Config
from bor.llm.conversation import Conversation
from bor.llm.prompt import build_system_prompt, question_with_context
from bor.llm.tools import MailTools, MessageHandles
from bor.mu import MuInterface

API_KEY_ENV = "OPENROUTER_API_KEY"
KEYRING_SERVICE = "bor-llm"
KEYRING_USER = "api_key"
MAX_HISTORY = 100


def make_client(api_key: str, base_url: str) -> Any:
    """The API client. A module function so tests can replace it."""
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=120.0, max_retries=2)


@dataclass
class TranscriptEntry:
    """One line or block of the LLM tab, kept so a reopened tab can redraw it."""

    kind: str  # question | tool | tool_error | answer | usage | info | error
    text: str


class LLMSession:
    """State shared by the LLM tab and the rest of the app."""

    def __init__(self, mu: MuInterface, config: Config) -> None:
        self.mu = mu
        self.config = config
        self.handles = MessageHandles()
        self.tools = MailTools(mu, self.handles)
        self.transcript: list[TranscriptEntry] = []
        self.history: list[str] = []  # questions asked, for Up/Down in the input
        self._conversation: Conversation | None = None
        self._api_key: str | None = None

    # ------------------------------------------------------------------
    # Setup

    def api_key(self) -> str:
        """The key from the config, else the environment, else the keyring."""
        if self._api_key is None:
            key = self.config.llm.api_key or os.environ.get(API_KEY_ENV, "")
            if not key:
                try:
                    import keyring

                    key = keyring.get_password(KEYRING_SERVICE, KEYRING_USER) or ""
                except Exception:
                    key = ""
            self._api_key = key
        return self._api_key

    def unavailable_reason(self) -> str | None:
        """Why questions cannot be asked, or None if they can."""
        try:
            import openai  # noqa: F401
        except ImportError:
            return "The LLM assistant needs the openai package: pip install 'bormail[llm]'"
        if not self.api_key():
            return (
                "No API key. Set api_key in the [llm] section of ~/.config/bor.conf, "
                f"or the {API_KEY_ENV} environment variable."
            )
        return None

    @property
    def model(self) -> str:
        return self.config.llm.model

    def conversation(self) -> Conversation:
        """The current conversation, started on first use."""
        if self._conversation is None:
            llm = self.config.llm
            client = make_client(self.api_key(), llm.base_url)
            # OpenRouter reports the cost of each request when asked to
            extra_body = {"usage": {"include": True}} if "openrouter.ai" in llm.base_url else None
            self._conversation = Conversation(
                client,
                llm.model,
                build_system_prompt(self.config),
                self.tools,
                max_tool_calls=llm.max_tool_calls,
                extra_body=extra_body,
            )
        return self._conversation

    # ------------------------------------------------------------------
    # Questions

    def prepare_question(self, question: str) -> str:
        """The message actually sent: the question with Bor's current context."""
        return question_with_context(question, [], datetime.now())

    def remember(self, question: str) -> None:
        """Add a question to the input history (most recent last, no duplicates)."""
        if question in self.history:
            self.history.remove(question)
        self.history.append(question)
        del self.history[:-MAX_HISTORY]

    def new_conversation(self) -> None:
        """Forget the conversation, its handles and transcript (history stays)."""
        self._conversation = None
        self.handles.clear()
        self.transcript.clear()
