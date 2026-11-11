"""Shared pytest configuration."""

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_user_files(tmp_path, monkeypatch):
    """Keep tests away from the user's real config, ~/.mailrc and search history.

    Widgets read configuration through the global `get_config()`, so without
    this every app test silently loaded ~/.config/bor.conf, and pressing Enter
    in a search prompt appended to the real search history.
    """
    import bor.config as config_module
    import bor.tabs.message_index as index_module

    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", tmp_path / "bor.conf")
    monkeypatch.setattr(config_module, "MAILRC_PATH", tmp_path / ".mailrc")
    monkeypatch.setattr(config_module, "_config", None)
    monkeypatch.setattr(index_module, "_HISTORY_FILE", tmp_path / "search_history")


@pytest.fixture(autouse=True, scope="session")
def _disable_gc_tuning():
    """Keep the app's GC tuning out of the test session.

    `BorApp` freezes the startup object graph and raises the collection
    thresholds once the inbox has loaded. That is right for a long-running
    interactive process but wrong for a test run, where dozens of app fixtures
    would each reconfigure the interpreter's collector for everything after
    them. Tests that exercise the tuning itself opt back in explicitly.
    """
    previous = os.environ.get("BOR_NO_GC_TUNING")
    os.environ["BOR_NO_GC_TUNING"] = "1"
    yield
    if previous is None:
        os.environ.pop("BOR_NO_GC_TUNING", None)
    else:
        os.environ["BOR_NO_GC_TUNING"] = previous
