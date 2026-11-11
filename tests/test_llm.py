"""LLM search assistant: mail tools, the conversation loop, and the LLM tab."""

from __future__ import annotations

import asyncio
import json
import sys
import types
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("openai")

from textual.widgets import Markdown, Static  # noqa: E402

from bor.config import Config  # noqa: E402
from bor.llm.conversation import (  # noqa: E402
    LIMIT_NOTE,
    Conversation,
    LLMError,
    TextDelta,
    Thinking,
    ToolFinished,
    ToolStarted,
    TurnFinished,
)
from bor.llm.prompt import build_system_prompt  # noqa: E402
from bor.llm.tools import (  # noqa: E402
    HISTORY_MARKER,
    QUOTE_MARKER,
    MailTools,
    MessageHandles,
    strip_quoted,
)
from bor.mu import EmailAddress, EmailMessage  # noqa: E402
from tests.llm_fakes import FakeClient, text_response, tool_response  # noqa: E402


def _message(n: int, **kwargs) -> EmailMessage:
    defaults = dict(
        msgid=f"id{n}@example.org",
        path=f"/mail/cur/{n}",
        maildir="/INBOX",
        subject=f"Subject {n}",
        date=datetime(2025, 3, n),
        from_addr=EmailAddress(name=f"Sender {n}", email=f"s{n}@example.org"),
        to_addrs=[EmailAddress(name="Me", email="me@example.org")],
        flags=["seen"],
    )
    defaults.update(kwargs)
    return EmailMessage(**defaults)


def _mu(found=None, bodies=None, thread=None) -> MagicMock:
    """Mock mu: `find` returns `found`; `view` returns the body for each path."""
    found = found if found is not None else [_message(1), _message(2)]
    bodies = bodies or {}
    mu = MagicMock()
    mu.find.return_value = found
    mu.find_thread.return_value = thread or []

    def view(path, mark_as_read=True, msgid=""):
        base = next((m for m in found + (thread or []) if m.path == path), None)
        if base is None:
            return None
        full = EmailMessage(**{**base.__dict__})
        full.body_txt = bodies.get(path, f"Body of {base.subject}")
        return full

    mu.view.side_effect = view
    return mu


def _tools(mu) -> MailTools:
    return MailTools(mu, MessageHandles())


# ----------------------------------------------------------------------
# Tools


def test_search_lists_messages_with_handles() -> None:
    mu = _mu([_message(1, flags=["unread", "attach"]), _message(2, flags=["seen", "replied"])])
    tools = _tools(mu)

    result = tools.run("search_mail", json.dumps({"query": "from:sender"}))

    assert not result.error
    lines = result.content.splitlines()
    assert lines[0] == "2 messages:"
    assert lines[1] == (
        "m1 | 2025-03-01 00:00 | Sender 1 <s1@example.org> -> Me | Subject 1 "
        "| unread, attachment | /INBOX"
    )
    assert lines[2].startswith("m2 | 2025-03-02") and "| replied |" in lines[2]
    assert result.summary == "search: from:sender → 2"
    mu.wait_for_reindex.assert_called_once()
    mu.find.assert_called_once_with("from:sender", maxnum=51, threads=False, descending=True)


def test_search_says_when_more_messages_match() -> None:
    mu = _mu([_message(n) for n in range(1, 5)])
    result = _tools(mu).run("search_mail", json.dumps({"query": "x", "limit": 3}))

    assert result.content.startswith("3 messages (more match")
    assert len(result.content.splitlines()) == 4
    assert result.summary.endswith("→ 3+")


def test_search_clamps_limit_and_reports_no_matches() -> None:
    mu = _mu([])
    result = _tools(mu).run("search_mail", json.dumps({"query": "x", "limit": 10_000}))

    assert "No messages match" in result.content
    assert mu.find.call_args.kwargs["maxnum"] == 201


def test_handles_are_stable_per_message() -> None:
    handles = MessageHandles()
    first, second = _message(1), _message(2)

    assert handles.handle_for(first) == "m1"
    assert handles.handle_for(second) == "m2"
    assert handles.handle_for(_message(1, path="/moved/1")) == "m1"
    assert handles.get(" M1 ").path == "/moved/1"
    handles.clear()
    assert handles.get("m1") is None


def test_read_message_does_not_mark_it_read_and_drops_quotes() -> None:
    body = "Sounds good.\n\nOn Mon, Mar 3, 2025 Alice wrote:\n> Shall we meet?\n> Tuesday?\n"
    mu = _mu(bodies={"/mail/cur/1": body})
    tools = _tools(mu)
    tools.run("search_mail", json.dumps({"query": "x"}))

    result = tools.run("read_message", json.dumps({"id": "m1"}))

    assert mu.view.call_args.kwargs["mark_as_read"] is False
    assert "Message m1" in result.content
    assert "Subject: Subject 1" in result.content
    assert "Sounds good." in result.content
    assert "Shall we meet" not in result.content
    assert "wrote:" not in result.content
    assert QUOTE_MARKER in result.content
    assert result.summary == 'read: "Subject 1" (Sender 1, Mar 01, 2025)'

    quoted = tools.run("read_message", json.dumps({"id": "m1", "include_quoted": True}))
    assert "Shall we meet" in quoted.content


def test_read_message_lists_attachments_and_converts_html() -> None:
    mu = _mu()
    tools = _tools(mu)
    tools.run("search_mail", json.dumps({"query": "x"}))
    full = EmailMessage(
        subject="Report",
        body_html="<p>See <b>attached</b></p>",
        attachments=[{"filename": "report.pdf", "content_type": "application/pdf"}],
    )
    mu.view.side_effect = None
    mu.view.return_value = full

    result = tools.run("read_message", json.dumps({"id": "m2"}))

    assert "Attachments: report.pdf (application/pdf)" in result.content
    assert "attached" in result.content
    assert "<p>" not in result.content


def test_unknown_handle_and_bad_calls_become_error_results() -> None:
    tools = _tools(_mu())

    unknown = tools.run("read_message", json.dumps({"id": "m99"}))
    assert unknown.error and "unknown message handle" in unknown.content

    assert tools.run("read_message", "{not json").error
    assert tools.run("read_message", "[1, 2]").error
    assert tools.run("delete_everything", "{}").error
    assert tools.run("search_mail", json.dumps({"query": " "})).error


def test_tool_exceptions_do_not_escape() -> None:
    mu = _mu()
    mu.find.side_effect = RuntimeError("mu binary not found")

    result = _tools(mu).run("search_mail", json.dumps({"query": "x"}))

    assert result.error
    assert "mu binary not found" in result.content


def test_read_thread_is_chronological_with_handles() -> None:
    later, earlier = _message(5, subject="Re: Plan"), _message(2, subject="Plan")
    mu = _mu(found=[later], thread=[later, earlier])
    tools = _tools(mu)
    tools.run("search_mail", json.dumps({"query": "x"}))

    result = tools.run("read_thread", json.dumps({"id": "m1"}))

    assert result.content.startswith("Thread of 2 messages")
    assert result.content.index("| Plan |") < result.content.index("| Re: Plan |")
    assert "=== m2 | 2025-03-02" in result.content  # the earlier message got a new handle
    assert all(call.kwargs["mark_as_read"] is False for call in mu.view.call_args_list)
    assert result.summary == 'thread: "Re: Plan" (Sender 5, Mar 05, 2025) → 2 messages'


def test_strip_quoted_keeps_inline_replies() -> None:
    body = (
        "Hi,\n\nOn Tue, Mar 4, 2025 at 10:00 AM Alice Smith <alice@example.org>\nwrote:\n"
        "> First question?\n>\n> More detail.\n\nAnswer one.\n\n> Second question?\nAnswer two.\n"
    )

    stripped = strip_quoted(body)

    assert stripped.split("\n") == [
        "Hi,",
        "",
        QUOTE_MARKER,
        "",
        "Answer one.",
        "",
        QUOTE_MARKER,
        "Answer two.",
        "",
    ]


def test_strip_quoted_cuts_outlook_history_except_in_forwards() -> None:
    body = "Agreed.\n\nFrom: Bob <bob@example.org>\nSent: Monday\nSubject: Plan\n\nOld text"

    assert strip_quoted(body) == f"Agreed.\n\n{HISTORY_MARKER}"
    assert strip_quoted(body, cut_history=False) == body
    assert strip_quoted("Hi\n-----Original Message-----\nold") == f"Hi\n\n{HISTORY_MARKER}"


# ----------------------------------------------------------------------
# Conversation loop


def _conversation(client, mu=None, **kwargs) -> Conversation:
    return Conversation(client, "test/model", "SYSTEM", _tools(mu or _mu()), **kwargs)


async def _collect(conversation: Conversation, question: str) -> list:
    return [event async for event in conversation.ask(question)]


async def test_plain_answer_streams_text_and_usage() -> None:
    client = FakeClient([text_response("Hello there", cost=0.002)])
    conversation = _conversation(client, extra_body={"usage": {"include": True}})

    events = await _collect(conversation, "hi")

    assert isinstance(events[0], Thinking)
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "Hello there"
    finished = events[-1]
    assert isinstance(finished, TurnFinished)
    assert finished.usage.prompt_tokens == 100 and finished.usage.cost == pytest.approx(0.002)
    assert conversation.messages[1:] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "Hello there"},
    ]
    request = client.requests[0]
    assert request["model"] == "test/model" and request["stream"] is True
    assert request["tool_choice"] == "auto"
    assert request["extra_body"] == {"usage": {"include": True}}
    assert client.streams[0].closed


async def test_without_extra_body_usage_is_requested_the_standard_way() -> None:
    client = FakeClient([text_response("ok")])
    await _collect(_conversation(client), "hi")

    assert client.requests[0]["stream_options"] == {"include_usage": True}
    assert "extra_body" not in client.requests[0]


async def test_tool_call_runs_and_result_goes_back_with_reasoning() -> None:
    mu = _mu()
    client = FakeClient(
        [tool_response("search_mail", {"query": "budget"}, "call_7"), text_response("Found 2.")]
    )
    conversation = _conversation(client, mu)

    events = await _collect(conversation, "budget mail?")

    started = next(e for e in events if isinstance(e, ToolStarted))
    assert started.name == "search_mail" and json.loads(started.arguments) == {"query": "budget"}
    finished = next(e for e in events if isinstance(e, ToolFinished))
    assert finished.result.summary == "search: budget → 2"
    assert events[-1].usage.prompt_tokens == 150
    assert events[-1].usage.cost == pytest.approx(0.002)

    assistant, tool_message = conversation.messages[2], conversation.messages[3]
    assert assistant["tool_calls"][0]["id"] == "call_7"
    assert assistant["tool_calls"][0]["function"]["name"] == "search_mail"
    assert json.loads(assistant["tool_calls"][0]["function"]["arguments"]) == {"query": "budget"}
    # Streamed reasoning fragments are merged and returned to the model
    assert assistant["reasoning_details"] == [
        {"type": "reasoning.text", "text": "I should search.", "index": 0}
    ]
    assert tool_message["role"] == "tool" and tool_message["tool_call_id"] == "call_7"
    assert tool_message["content"].startswith("2 messages:")
    # The second request carried the tool result
    assert client.requests[1]["messages"][-1]["role"] == "tool"
    assert conversation.messages[-1] == {"role": "assistant", "content": "Found 2."}


async def test_tool_call_limit_forces_an_answer() -> None:
    client = FakeClient(
        [
            tool_response("search_mail", {"query": "a"}, "c1"),
            # Past the limit the model asks again; that call must not run
            tool_response("search_mail", {"query": "b"}, "c2"),
        ]
    )
    mu = _mu()
    conversation = _conversation(client, mu, max_tool_calls=1)

    events = await _collect(conversation, "q")

    assert mu.find.call_count == 1
    assert events[-1].stopped_early
    final_request = client.requests[1]
    assert final_request["tool_choice"] == "none"
    assert final_request["messages"][-1] == {"role": "user", "content": LIMIT_NOTE}
    # No tool call without a result is left in the history
    assert "tool_calls" not in conversation.messages[-1]


async def test_batched_tool_calls_past_the_limit_are_not_run() -> None:
    from tests.llm_fakes import chunk, usage_chunk

    two_calls = [
        chunk(
            tool_calls=[
                {"index": 0, "id": "a", "type": "function",
                 "function": {"name": "search_mail", "arguments": '{"query": "one"}'}},
                {"index": 1, "id": "b", "type": "function",
                 "function": {"name": "search_mail", "arguments": '{"query": "two"}'}},
            ],
            finish="tool_calls",
        ),
        usage_chunk(10, 5),
    ]
    mu = _mu()
    conversation = _conversation(FakeClient([two_calls, text_response("ok")]), mu, max_tool_calls=1)

    events = await _collect(conversation, "q")

    assert mu.find.call_count == 1
    assert [e.name for e in events if isinstance(e, ToolStarted)] == ["search_mail"]
    results = {m["tool_call_id"]: m["content"] for m in conversation.messages if m["role"] == "tool"}
    assert results["a"].startswith("2 messages")
    assert results["b"].startswith("Not run")
    assert events[-1].stopped_early


async def test_api_error_rolls_back_the_question() -> None:
    error = RuntimeError("boom")
    error.status_code = 402  # type: ignore[attr-defined]
    error.body = {"error": {"message": "Insufficient credits"}}  # type: ignore[attr-defined]
    client = FakeClient([tool_response("search_mail", {"query": "a"}), error])
    conversation = _conversation(client)

    with pytest.raises(LLMError, match="API error 402: Insufficient credits"):
        await _collect(conversation, "q")

    assert conversation.messages == [{"role": "system", "content": "SYSTEM"}]


async def test_cancelling_rolls_back_the_question() -> None:
    client = FakeClient([text_response("a long answer " * 20)], delay=0.05)
    conversation = _conversation(client)

    task = asyncio.create_task(_collect(conversation, "q"))
    await asyncio.sleep(0.12)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert conversation.messages == [{"role": "system", "content": "SYSTEM"}]
    assert client.streams[0].closed


# ----------------------------------------------------------------------
# System prompt


def test_system_prompt_has_identity_folders_and_notes(tmp_path: Path) -> None:
    notes = tmp_path / "llm.md"
    notes.write_text("SSL = Space Sciences Lab {not a format field}\n")
    config = Config()
    config.identity.name = "Ann Smith"
    config.identity.email = "ann@example.org"
    config.folders.sent = "/Sent Mail"
    config.llm.context_file = str(notes)

    prompt = build_system_prompt(config)

    assert "Ann Smith <ann@example.org>" in prompt
    assert "Mail the user sent is in /Sent Mail" in prompt
    assert prompt.rstrip().endswith("SSL = Space Sciences Lab {not a format field}")

    config.llm.context_file = str(tmp_path / "missing.md")
    assert "notes" not in build_system_prompt(config)


# ----------------------------------------------------------------------
# The LLM tab


def _llm_config(tmp_path: Path, api_key: str = "test-key") -> Config:
    config = Config()
    config.llm.api_key = api_key
    config.llm.context_file = str(tmp_path / "llm.md")
    return config


def _index_mu():
    from tests.test_app_integration import create_mock_messages

    mu = MagicMock()
    mu.find.return_value = create_mock_messages(3)
    mu.find_contacts.return_value = []
    return mu


async def _settle(pilot, app) -> None:
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


def _llm_tab(app):
    from bor.tabs.llm import LLMWidget

    return app.query_one(LLMWidget)


async def test_q_opens_one_llm_tab(tmp_path: Path) -> None:
    with patch("bor.app.get_config", return_value=_llm_config(tmp_path)):
        with patch("bor.app.MuInterface", return_value=_index_mu()):
            from bor.app import BorApp
            from bor.tabs.llm import LLMWidget, QuestionInput

            app = BorApp()
            async with app.run_test() as pilot:
                await _settle(pilot, app)
                await pilot.press("q")
                await _settle(pilot, app)
                assert isinstance(app.focused, QuestionInput)

                await pilot.press("escape")  # idle: back to the index
                await _settle(pilot, app)
                assert app.query_one("TabbedContent").active == "tab-0"

                await pilot.press("q")
                await _settle(pilot, app)
                assert len(app.query(LLMWidget)) == 1
                assert app.query_one("TabbedContent").active != "tab-0"


async def test_question_is_answered_in_the_transcript(tmp_path: Path) -> None:
    client = FakeClient(
        [tool_response("search_mail", {"query": "subject:[ext]"}), text_response("**Two** messages.")]
    )
    with patch("bor.app.get_config", return_value=_llm_config(tmp_path)):
        with patch("bor.app.MuInterface", return_value=_index_mu()):
            with patch("bor.llm.session.make_client", return_value=client):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await _settle(pilot, app)
                    await pilot.press("q")
                    await _settle(pilot, app)
                    await pilot.press(*"find [ext] mail", "enter")
                    await _settle(pilot, app)

                    kinds = [(e.kind, e.text) for e in app.llm.transcript]
                    assert kinds[0] == ("question", "find [ext] mail")
                    assert kinds[1] == ("tool", "search: subject:[ext] → 3")
                    assert kinds[2] == ("answer", "**Two** messages.")
                    assert kinds[3][0] == "usage" and kinds[3][1].endswith("$0.0020")

                    tab = _llm_tab(app)
                    texts = [str(w.render()) for w in tab.query(Static) if "llm-" in " ".join(w.classes)]
                    # Brackets in questions and queries show literally
                    assert "› find [ext] mail" in texts
                    assert "  search: subject:[ext] → 3" in texts
                    assert len(tab.query(Markdown)) == 1

                    # The question went out with Bor's context in front
                    sent = client.requests[0]["messages"][1]["content"]
                    assert sent.startswith("<bor_context>\nNow: ")
                    assert sent.endswith("\n\nfind [ext] mail")
                    assert app.llm.history == ["find [ext] mail"]


async def test_reopened_tab_redraws_the_conversation(tmp_path: Path) -> None:
    client = FakeClient([text_response("Answer one.")])
    with patch("bor.app.get_config", return_value=_llm_config(tmp_path)):
        with patch("bor.app.MuInterface", return_value=_index_mu()):
            with patch("bor.llm.session.make_client", return_value=client):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await _settle(pilot, app)
                    app.open_llm("first question")
                    await _settle(pilot, app)
                    _llm_tab(app).close_tab()
                    await _settle(pilot, app)

                    app.open_llm()
                    await _settle(pilot, app)
                    tab = _llm_tab(app)
                    assert len(tab.query(Markdown)) == 1
                    assert any("first question" in str(w.render()) for w in tab.query(Static))


async def test_ctrl_n_starts_a_new_conversation(tmp_path: Path) -> None:
    client = FakeClient([text_response("One."), text_response("Two.")])
    with patch("bor.app.get_config", return_value=_llm_config(tmp_path)):
        with patch("bor.app.MuInterface", return_value=_index_mu()):
            with patch("bor.llm.session.make_client", return_value=client):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await _settle(pilot, app)
                    app.open_llm("first")
                    await _settle(pilot, app)
                    await pilot.press("ctrl+n")
                    await _settle(pilot, app)
                    assert app.llm.transcript == []
                    assert len(_llm_tab(app).query(Markdown)) == 0

                    await pilot.press(*"second", "enter")
                    await _settle(pilot, app)
                    # The new conversation does not carry the first question
                    contents = [m["content"] for m in client.requests[1]["messages"]]
                    assert not any("first" in (c or "") for c in contents)


async def test_esc_cancels_a_running_question(tmp_path: Path) -> None:
    client = FakeClient([text_response("slow " * 50)], delay=0.05)
    with patch("bor.app.get_config", return_value=_llm_config(tmp_path)):
        with patch("bor.app.MuInterface", return_value=_index_mu()):
            with patch("bor.llm.session.make_client", return_value=client):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await _settle(pilot, app)
                    app.open_llm("slow question")
                    await pilot.pause(0.15)
                    assert _llm_tab(app).is_running
                    await pilot.press("escape")
                    await _settle(pilot, app)

                    assert not _llm_tab(app).is_running
                    assert app.query_one("TabbedContent").active != "tab-0"  # stayed
                    assert app.llm.transcript[-1].kind == "info"
                    assert app.llm.transcript[-1].text == "Cancelled."
                    assert app.llm.conversation().messages[1:] == []


async def test_missing_api_key_is_explained(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    stub = types.ModuleType("keyring")
    stub.get_password = lambda service, user: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "keyring", stub)

    with patch("bor.app.get_config", return_value=_llm_config(tmp_path, api_key="")):
        with patch("bor.app.MuInterface", return_value=_index_mu()):
            from bor.app import BorApp

            app = BorApp()
            async with app.run_test() as pilot:
                await _settle(pilot, app)
                app.open_llm("anything")
                await _settle(pilot, app)
                texts = [str(w.render()) for w in _llm_tab(app).query(Static)]
                assert any("No API key" in t for t in texts)
                assert app.llm.history == []


async def test_api_key_falls_back_to_environment(tmp_path: Path, monkeypatch) -> None:
    from bor.llm.session import LLMSession

    monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")
    session = LLMSession(MagicMock(), _llm_config(tmp_path, api_key=""))

    assert session.api_key() == "from-env"
    assert session.unavailable_reason() is None


# ----------------------------------------------------------------------
# Results view (show_results, k / K)


def test_show_results_publishes_message_ids() -> None:
    published = []
    tools = MailTools(_mu([_message(n) for n in range(1, 4)]), MessageHandles(),
                      on_results=lambda ids, title: published.append((ids, title)))
    tools.run("search_mail", json.dumps({"query": "x"}))

    result = tools.run("show_results", json.dumps({"ids": ["m3", "m1", "m3", "m9"], "title": "Picked"}))

    assert published == [(["id3@example.org", "id1@example.org"], "Picked")]
    assert result.content == "Showing 2 messages in Bor's results view. Ignored unknown handles: m9."
    assert result.summary == 'results: "Picked" → 2 messages (k in the index)'

    # A bare comma-separated string is accepted; nothing known is an error
    assert not tools.run("show_results", json.dumps({"ids": "m2, m1", "title": "t"})).error
    assert published[-1][0] == ["id2@example.org", "id1@example.org"]
    assert tools.run("show_results", json.dumps({"ids": ["m42"], "title": "t"})).error


def _results_mu(inbox):
    """mu whose find answers msgid: queries from `inbox`, and anything else with all of it."""
    mu = MagicMock()
    mu.find_contacts.return_value = []

    def find(query, maxnum=None, threads=False, **kwargs):
        if "msgid:" in query:
            return [m for m in inbox if f'msgid:"{m.msgid}"' in query]
        return list(inbox)

    mu.find.side_effect = find

    def view(path, mark_as_read=True, msgid=""):
        base = next(m for m in inbox if m.path == path)
        return EmailMessage(**{**base.__dict__, "body_txt": f"Body of {base.subject}"})

    mu.view.side_effect = view
    return mu


def _status(app) -> str:
    from textual.widgets import Label

    return str(app.query_one("#status-label", Label).render())


async def test_k_shows_the_llm_results_until_cleared(tmp_path: Path) -> None:
    from textual.widgets import DataTable

    inbox = [_message(n) for n in range(1, 5)]
    client = FakeClient(
        [
            tool_response("search_mail", {"query": "x"}, "c1"),
            tool_response("show_results", {"ids": ["m2", "m3"], "title": "Two [picked]"}, "c2"),
            text_response("Here they are."),
            tool_response("show_results", {"ids": ["m4"], "title": "Just one"}, "c3"),
            text_response("Narrowed."),
        ]
    )
    with patch("bor.app.get_config", return_value=_llm_config(tmp_path)):
        with patch("bor.app.MuInterface", return_value=_results_mu(inbox)):
            with patch("bor.llm.session.make_client", return_value=client):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await _settle(pilot, app)
                    table = app.query_one(DataTable)
                    assert table.row_count == 4

                    # Nothing to show yet
                    await pilot.press("k")
                    await _settle(pilot, app)
                    assert table.row_count == 4 and "LLM" not in _status(app)

                    app.open_llm("which two?")
                    await _settle(pilot, app)
                    assert app.llm.results == ["id2@example.org", "id3@example.org"]
                    assert any(e.text.startswith('results: "Two [picked]"') for e in app.llm.transcript)

                    await pilot.press("escape")  # back to the index
                    await _settle(pilot, app)
                    await pilot.press("k")
                    await _settle(pilot, app)
                    assert table.row_count == 2
                    assert _status(app).startswith("LLM: Two [picked] | 2 messages")

                    # Threading toggles within the view
                    await pilot.press("t")
                    await _settle(pilot, app)
                    assert table.row_count == 2 and _status(app).startswith("LLM:")

                    # Leaving for another tab and coming back keeps the view
                    await pilot.press("q")
                    await _settle(pilot, app)
                    # A new set from the model replaces the shown one
                    _llm_tab(app).ask("only the last")
                    await _settle(pilot, app)
                    await pilot.press("escape")
                    await _settle(pilot, app)
                    assert table.row_count == 1
                    assert _status(app).startswith("LLM: Just one | 1 messages")

                    # K clears and returns to the previous search
                    await pilot.press("K")
                    await _settle(pilot, app)
                    assert app.llm.results == []
                    assert table.row_count == 4 and "LLM" not in _status(app)


async def test_folder_keys_leave_the_results_view(tmp_path: Path) -> None:
    from textual.widgets import DataTable

    inbox = [_message(n) for n in range(1, 4)]
    with patch("bor.app.get_config", return_value=_llm_config(tmp_path)):
        with patch("bor.app.MuInterface", return_value=_results_mu(inbox)):
            from bor.app import BorApp

            app = BorApp()
            async with app.run_test() as pilot:
                await _settle(pilot, app)
                app.llm.set_results(["id1@example.org"], "One")
                await pilot.press("k")
                await _settle(pilot, app)
                assert app.query_one(DataTable).row_count == 1

                await pilot.press("i")
                await _settle(pilot, app)
                assert app.query_one(DataTable).row_count == 3
                assert "LLM" not in _status(app)
                # The set itself is kept for the next k
                assert app.llm.results == ["id1@example.org"]


# ----------------------------------------------------------------------
# Marked messages and Ctrl+S


async def test_ctrl_s_summarizes_the_marked_messages(tmp_path: Path) -> None:
    inbox = [_message(n) for n in range(1, 5)]
    client = FakeClient([tool_response("read_message", {"id": "m2"}), text_response("Summary.")])
    config = _llm_config(tmp_path)
    with patch("bor.app.get_config", return_value=config):
        with patch("bor.app.MuInterface", return_value=_results_mu(inbox)):
            with patch("bor.llm.session.make_client", return_value=client):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await _settle(pilot, app)
                    await pilot.press("m", "m")  # mark the first two; cursor moves to the third
                    await pilot.press("ctrl+s")
                    await _settle(pilot, app)

                    sent = client.requests[0]["messages"][1]["content"]
                    context, question = sent.split("</bor_context>\n\n")
                    assert question == config.llm.summarize_prompt
                    lines = context.splitlines()
                    assert lines[2] == "Bor's message index shows: Inbox (maildir:\"/INBOX\"), 4 messages"
                    assert lines[3].startswith("Message under the cursor: m1 | 2025-03-03")
                    assert lines[4] == "Marked messages (2):"
                    assert lines[5].startswith("m2 | 2025-03-01") and "Subject 1" in lines[5]
                    assert lines[6].startswith("m3 | 2025-03-02") and "Subject 2" in lines[6]

                    # The model can read a marked message through its handle
                    tool_line = next(e for e in app.llm.transcript if e.kind.startswith("tool"))
                    assert tool_line.kind == "tool"
                    assert tool_line.text.startswith('read: "Subject 1"')
                    assert app.query_one("TabbedContent").active != "tab-0"


async def test_ctrl_s_without_marks_uses_the_cursor_message(tmp_path: Path) -> None:
    inbox = [_message(n) for n in range(1, 3)]
    client = FakeClient([text_response("Summary.")])
    with patch("bor.app.get_config", return_value=_llm_config(tmp_path)):
        with patch("bor.app.MuInterface", return_value=_results_mu(inbox)):
            with patch("bor.llm.session.make_client", return_value=client):
                from bor.app import BorApp

                app = BorApp()
                async with app.run_test() as pilot:
                    await _settle(pilot, app)
                    await pilot.press("ctrl+s")
                    await _settle(pilot, app)

                    sent = client.requests[0]["messages"][1]["content"]
                    assert "Marked messages: none" in sent
                    assert "Message under the cursor: m1 | 2025-03-01" in sent
                    assert sent.endswith("(Nothing is marked: use the message under the cursor.)")


async def test_context_describes_searches_threads_and_results(tmp_path: Path) -> None:
    inbox = [_message(n) for n in range(1, 4)]
    with patch("bor.app.get_config", return_value=_llm_config(tmp_path)):
        with patch("bor.app.MuInterface", return_value=_results_mu(inbox)):
            from bor.app import BorApp
            from bor.tabs.message_index import MessageIndexWidget

            app = BorApp()
            async with app.run_test() as pilot:
                await _settle(pilot, app)
                index = app.query_one(MessageIndexWidget)

                await index.search("from:alice [ext]")
                assert index.llm_view_state()[0] == "search: from:alice [ext], 3 messages"

                app.llm.set_results(["id2@example.org"], "Picked")
                await index.show_llm_results()
                assert index.llm_view_state()[0] == 'LLM results "Picked", 1 messages'

                app.mu.find_thread = MagicMock(return_value=inbox[:2])
                await index._show_thread(inbox[0])
                assert index.llm_view_state()[0] == 'the thread "Subject 1", 2 messages'
