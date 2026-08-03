"""Tests for the UI-latency fixes: deferred mu reindexing and targeted repaints.

These cover the two behaviours that used to freeze the UI:
  * flag changes ran `mu remove` + `mu add` synchronously on the event loop
  * every cursor move in the compose editor repainted the whole widget
"""

import gc
import threading
import time

import pytest

from bor.mu import MuInterface


@pytest.fixture
def gc_sandbox(monkeypatch):
    """Let a test run the app's GC tuning without leaking it into the session.

    Restores the thresholds, unfreezes, and resets the module's idempotence
    flag afterwards. The session-wide fixture in conftest.py sets
    BOR_NO_GC_TUNING, so tests here have to opt back in.
    """
    import bor.app

    thresholds = gc.get_threshold()
    monkeypatch.delenv("BOR_NO_GC_TUNING", raising=False)
    monkeypatch.setattr(bor.app, "_gc_tuned", False)
    gc.unfreeze()
    yield bor.app
    gc.unfreeze()
    gc.set_threshold(*thresholds)


class TestGCTuning:
    """Full collections were the largest stall source once mu work moved off-loop."""

    def test_raises_thresholds_and_freezes(self, gc_sandbox):
        """Startup objects are frozen and full collections made rarer."""
        before = gc.get_threshold()
        gc_sandbox._tune_gc()
        after = gc.get_threshold()

        # Generation 0 is deliberately untouched: it is already sub-millisecond.
        assert after[0] == before[0]
        assert after[1] == gc_sandbox._GC_GEN1_THRESHOLD > before[1]
        assert after[2] == gc_sandbox._GC_GEN2_THRESHOLD > before[2]
        assert gc.get_freeze_count() > 0

    def test_tuning_is_idempotent(self, gc_sandbox):
        """Repeat calls must not compound the thresholds into an overflow."""
        gc_sandbox._tune_gc()
        after_first = gc.get_threshold()
        for _ in range(20):
            gc_sandbox._tune_gc()

        assert gc.get_threshold() == after_first

    def test_env_var_disables_tuning(self, gc_sandbox, monkeypatch):
        """BOR_NO_GC_TUNING leaves the collector completely alone."""
        monkeypatch.setenv("BOR_NO_GC_TUNING", "1")
        before = gc.get_threshold()
        gc_sandbox._tune_gc()

        assert gc.get_threshold() == before
        assert gc.get_freeze_count() == 0


class TestDeferredReindex:
    """The mu database update must happen off the calling thread, and batched."""

    def _interface(self, calls, block=None):
        """A MuInterface whose _run_mu records calls instead of running mu."""
        mu = MuInterface()

        def fake_run_mu(args, capture_output=True):
            if block is not None:
                block.wait(5)
            calls.append((threading.current_thread().name, list(args)))

        mu._run_mu = fake_run_mu
        return mu

    def test_queue_does_not_run_on_calling_thread(self):
        """queue_reindex must return before mu is invoked."""
        calls = []
        gate = threading.Event()
        mu = self._interface(calls, block=gate)

        mu.queue_reindex("/old/path", "/new/path")
        # The worker is parked inside fake _run_mu; nothing has run here yet.
        assert calls == []

        gate.set()
        assert mu.wait_for_reindex(timeout=5)
        assert calls, "reindex never ran"
        assert all(name != threading.current_thread().name for name, _ in calls)

    def test_batches_pending_paths_into_one_command(self):
        """A burst of flag changes must not cost two subprocesses per message."""
        calls = []
        gate = threading.Event()
        mu = self._interface(calls, block=gate)

        # First call starts the worker and blocks it, so the rest queue up.
        mu.queue_reindex("/old/0", "/new/0")
        for i in range(1, 6):
            mu.queue_reindex(f"/old/{i}", f"/new/{i}")
        gate.set()
        assert mu.wait_for_reindex(timeout=5)

        removes = [args for _, args in calls if args[0] == "remove"]
        adds = [args for _, args in calls if args[0] == "add"]
        assert removes and adds
        # Six messages, but far fewer than six remove/add pairs.
        assert len(removes) < 6 and len(adds) < 6
        assert {p for args in removes for p in args[1:]} == {f"/old/{i}" for i in range(6)}
        assert {p for args in adds for p in args[1:]} == {f"/new/{i}" for i in range(6)}

    def test_wait_for_reindex_returns_when_idle(self):
        """An empty queue is immediately idle."""
        mu = MuInterface()
        assert mu.wait_for_reindex(timeout=0.1)

    def test_failure_does_not_propagate(self):
        """A broken mu must not take down the worker thread."""
        mu = MuInterface()

        def boom(args, capture_output=True):
            raise RuntimeError("mu exploded")

        mu._run_mu = boom
        mu.queue_reindex("/old", "/new")
        assert mu.wait_for_reindex(timeout=5)

    def test_set_flag_renames_without_blocking(self, tmp_path):
        """_set_flag renames immediately and defers the database update."""
        new_dir = tmp_path / "new"
        new_dir.mkdir()
        message = new_dir / "1234.host:2,"
        message.write_text("body")

        calls = []
        gate = threading.Event()
        mu = self._interface(calls, block=gate)

        result = mu._set_flag(str(message), "+S-N")

        # The rename - the part that actually changes message state - is done.
        assert result is not None
        assert not message.exists()
        assert (tmp_path / "cur" / "1234.host:2,S").exists()
        # ...while mu has not been invoked on this thread.
        assert calls == []

        gate.set()
        assert mu.wait_for_reindex(timeout=5)
        assert calls


class TestComposeTextAreaRepaint:
    """Cursor moves must dirty only the affected lines, not the whole widget."""

    @pytest.fixture
    def text_area(self):
        from bor.tabs.compose import ComposeTextArea

        return ComposeTextArea("\n".join(f"line {i}" for i in range(200)))

    def test_row_span_is_bounded(self, text_area):
        """A one-row span maps to a one-line refresh, not the document."""
        top, bottom = text_area._row_span(10, 10)
        assert bottom - top == 0

    def test_row_span_covers_range(self, text_area):
        """A multi-row span covers every row in it."""
        top, bottom = text_area._row_span(10, 14)
        assert bottom - top == 4

    def test_row_span_clamps_out_of_range_rows(self, text_area):
        """Rows past the end of the document must not raise."""
        top, bottom = text_area._row_span(0, 10_000)
        assert 0 <= top <= bottom

    def test_row_span_covers_all_wrap_segments(self):
        """With soft wrap, a row occupying several visual lines is fully covered.

        Anchoring on the cursor's own wrap segment left the other segments of
        the same row stale, which showed up as a torn cursor-line highlight.
        """
        from bor.tabs.compose import ComposeTextArea

        long_line = "x" * 400
        area = ComposeTextArea(f"short\n{long_line}\nshort")
        area.soft_wrap = True
        area.wrapped_document.wrap(40)

        top, bottom = area._row_span(1, 1)
        # The wrapped row spans several visual lines, all of them refreshed.
        assert bottom > top
        expected = area.wrapped_document.location_to_offset((1, len(long_line))).y
        assert bottom == expected
        assert top == area.wrapped_document.location_to_offset((1, 0)).y

    def test_selection_span_is_order_independent(self, text_area):
        """A backwards selection covers the same lines as a forwards one."""
        from textual.widgets.text_area import Selection

        forward = text_area._selection_line_span(Selection((5, 0), (9, 3)))
        backward = text_area._selection_line_span(Selection((9, 3), (5, 0)))
        assert forward == backward

    def test_selection_reactive_does_not_repaint_whole_widget(self):
        """The reactive itself must not carry the blanket repaint flag."""
        from textual.widgets import TextArea

        from bor.tabs.compose import ComposeTextArea

        assert TextArea.selection._repaint is True, "upstream default changed"
        assert ComposeTextArea.selection._repaint is False
        # Still always_update, so the watcher runs even when the value repeats.
        assert ComposeTextArea.selection._always_update is True
