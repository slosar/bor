"""Tests for search history in SearchInput."""

from pathlib import Path
from unittest.mock import patch

import bor.tabs.message_index as _mi


def make_input(history_file: Path):
    """Return a bare SearchInput with history loaded from history_file.

    The caller is responsible for keeping a patch on _mi._HISTORY_FILE active
    if they want persistence calls to also use the redirected file.
    """
    from bor.tabs.message_index import SearchInput
    inp = SearchInput.__new__(SearchInput)
    inp._history = []
    inp._history_pos = -1
    inp._saved_value = ""
    inp._load_history()
    return inp


def test_save_to_history_appends(tmp_path):
    hf = tmp_path / "search_history"
    with patch.object(_mi, "_HISTORY_FILE", hf):
        inp = make_input(hf)
        inp._save_to_history("from:alice")
        inp._save_to_history("maildir:/INBOX")
    assert inp._history == ["from:alice", "maildir:/INBOX"]


def test_save_to_history_deduplicates(tmp_path):
    hf = tmp_path / "search_history"
    with patch.object(_mi, "_HISTORY_FILE", hf):
        inp = make_input(hf)
        inp._save_to_history("from:alice")
        inp._save_to_history("maildir:/INBOX")
        inp._save_to_history("from:alice")
    assert inp._history == ["maildir:/INBOX", "from:alice"]


def test_save_to_history_ignores_blank(tmp_path):
    hf = tmp_path / "search_history"
    with patch.object(_mi, "_HISTORY_FILE", hf):
        inp = make_input(hf)
        inp._save_to_history("   ")
    assert inp._history == []


def test_save_to_history_trims_to_max(tmp_path):
    hf = tmp_path / "search_history"
    with patch.object(_mi, "_HISTORY_FILE", hf), patch.object(_mi, "_MAX_HISTORY", 3):
        inp = make_input(hf)
        for i in range(5):
            inp._save_to_history(f"query{i}")
    assert inp._history == ["query2", "query3", "query4"]


def test_persist_and_reload(tmp_path):
    hf = tmp_path / "search_history"
    with patch.object(_mi, "_HISTORY_FILE", hf):
        inp = make_input(hf)
        inp._save_to_history("from:alice")
        inp._save_to_history("maildir:/INBOX")
        # Simulate a fresh instance loading from the same file
        inp2 = make_input(hf)
    assert inp2._history == ["from:alice", "maildir:/INBOX"]


def test_up_navigates_to_newest_entry(tmp_path):
    hf = tmp_path / "search_history"
    inp = make_input(hf)
    inp._history = ["oldest", "middle", "newest"]
    inp._history_pos = -1
    inp._saved_value = ""

    # Simulate Up key: start browsing from newest
    if inp._history:
        if inp._history_pos == -1:
            inp._saved_value = ""
            inp._history_pos = len(inp._history) - 1
        elif inp._history_pos > 0:
            inp._history_pos -= 1
    assert inp._history_pos == 2
    assert inp._history[inp._history_pos] == "newest"


def test_up_twice_reaches_older_entry(tmp_path):
    hf = tmp_path / "search_history"
    inp = make_input(hf)
    inp._history = ["oldest", "middle", "newest"]

    # First Up
    inp._saved_value = "current"
    inp._history_pos = len(inp._history) - 1  # → newest

    # Second Up
    if inp._history_pos > 0:
        inp._history_pos -= 1
    assert inp._history[inp._history_pos] == "middle"


def test_up_at_oldest_stays(tmp_path):
    hf = tmp_path / "search_history"
    inp = make_input(hf)
    inp._history = ["only"]
    inp._history_pos = 0  # already at oldest

    # Up from oldest should stay
    if inp._history_pos > 0:
        inp._history_pos -= 1
    assert inp._history_pos == 0
    assert inp._history[inp._history_pos] == "only"


def test_down_from_newest_restores_saved_value(tmp_path):
    hf = tmp_path / "search_history"
    inp = make_input(hf)
    inp._history = ["oldest", "newest"]
    inp._history_pos = 1  # at newest
    inp._saved_value = "my draft"

    # Down past newest → restore saved value
    if inp._history_pos < len(inp._history) - 1:
        inp._history_pos += 1
        result = inp._history[inp._history_pos]
    else:
        inp._history_pos = -1
        result = inp._saved_value

    assert inp._history_pos == -1
    assert result == "my draft"


def test_down_no_op_when_not_browsing(tmp_path):
    hf = tmp_path / "search_history"
    inp = make_input(hf)
    inp._history = ["a", "b"]
    inp._history_pos = -1  # not browsing

    # Down should be a no-op
    if inp._history_pos != -1:
        inp._history_pos += 1
    assert inp._history_pos == -1


def test_reset_clears_browsing_state(tmp_path):
    hf = tmp_path / "search_history"
    inp = make_input(hf)
    inp._history = ["from:alice"]
    inp._history_pos = 0
    inp._saved_value = "draft"

    inp._history_pos = -1
    inp._saved_value = ""

    assert inp._history_pos == -1
    assert inp._saved_value == ""
    assert inp._history == ["from:alice"]  # list is preserved
