"""Shared pytest configuration."""

import os

import pytest


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
