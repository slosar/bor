"""
UI latency profiler for bor.

Runs bor normally but instruments the whole input-to-pixels pipeline, so a
stall can be attributed to a specific cause rather than guessed at. It records:

  compose_ms  - Python time turning dirty regions into an ANSI byte string
                (compositor render_update + render_segments)
  write_ms    - time spent handing that string to Textual's WriterThread queue.
                That queue has maxsize=30, so if the terminal cannot drain
                output fast enough this blocks and the number goes up.
  drain_ms    - time the writer thread spent in write/flush to the tty
  bytes       - size of the ANSI sequence per frame, which is what matters
                over SSH or in a slow terminal
  mu          - duration of every mu subprocess and message parse, flagged
                with whether it ran on the UI thread (where it freezes the app)
  gc          - duration of every garbage collection, by generation
  stall       - event-loop gaps over 80ms, with the main-thread stack sampled
                during the gap and any GC that overlapped it

Also records key-press -> first-frame latency and per-widget render cost.

Usage:
    python -m bor.profiling            # run bor with instrumentation
    python -m bor.profiling --report   # summarise the last log

Log file: $BORPROF_LOG, default /tmp/borprof.jsonl
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict

LOG = os.environ.get("BORPROF_LOG", "/tmp/borprof.jsonl")


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------
def report(path: str = LOG) -> int:
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    if not rows:
        print("no samples")
        return 1

    frames = [r for r in rows if r["t"] == "frame"]
    keys = [r for r in rows if r["t"] == "key"]
    renders = [r for r in rows if r["t"] == "render"]

    def pct(vals, p):
        if not vals:
            return 0.0
        vals = sorted(vals)
        return vals[min(len(vals) - 1, int(len(vals) * p))]

    print(f"session: {len(frames)} frames, {len(keys)} keys\n")

    if frames:
        t0, t1 = frames[0]["ts"], frames[-1]["ts"]
        span = max(t1 - t0, 1e-9)
        total_bytes = sum(f["bytes"] for f in frames)
        print(f"{'':22}{'mean':>9}{'p50':>9}{'p90':>9}{'p99':>9}{'max':>9}")
        for field, label in (
            ("compose_ms", "compose (python)"),
            ("write_ms", "write (enqueue)"),
            ("bytes", "bytes/frame"),
        ):
            v = [f[field] for f in frames]
            print(
                f"  {label:20}{sum(v)/len(v):9.1f}{pct(v,.5):9.1f}"
                f"{pct(v,.9):9.1f}{pct(v,.99):9.1f}{max(v):9.1f}"
            )
        print()
        print(f"  frame rate            {len(frames)/span:6.1f} fps over {span:.1f}s")
        print(f"  output throughput     {total_bytes/span/1024:6.1f} KiB/s"
              f"  ({total_bytes/1024/1024:.1f} MiB total)")
        full = sum(1 for f in frames if f.get("full"))
        print(f"  full-screen repaints  {full} / {len(frames)}"
              f"  ({100*full/len(frames):.0f}%)")

    drains = [r for r in rows if r["t"] == "drain"]
    if drains:
        v = [d["drain_ms"] for d in drains]
        tot = sum(v)
        print(f"  tty drain total       {tot/1000:6.2f}s"
              f"   mean {sum(v)/len(v):.2f}ms  max {max(v):.1f}ms")

    if keys:
        v = [k["latency_ms"] for k in keys if k.get("latency_ms") is not None]
        if v:
            print(f"\n  key -> first frame    mean {sum(v)/len(v):6.1f}ms"
                  f"  p90 {pct(v,.9):6.1f}ms  max {max(v):6.1f}ms")
        nf = [k["frames"] for k in keys if k.get("frames") is not None]
        if nf:
            print(f"  frames per keypress   mean {sum(nf)/len(nf):6.1f}"
                  f"  max {max(nf)}")

    if renders:
        by_widget: dict[str, list[float]] = defaultdict(list)
        for r in renders:
            by_widget[r["widget"]].append(r["ms"])
        print("\n  widget render_lines (ms, only >1ms samples logged):")
        for name, v in sorted(by_widget.items(), key=lambda kv: -sum(kv[1]))[:12]:
            print(f"    {name:32} n={len(v):5d}  total={sum(v):8.1f}"
                  f"  mean={sum(v)/len(v):6.2f}  max={max(v):7.1f}")

    mus = [r for r in rows if r["t"] in ("mu", "muview")]
    if mus:
        print("\n  mu / message-parse calls (blocking the event loop when main=True):")
        agg: dict[tuple, list[float]] = defaultdict(list)
        for m in mus:
            agg[(m["t"], m.get("cmd", "view"), m["main"])].append(m["ms"])
        for (kind, cmd, main), v in sorted(agg.items(), key=lambda kv: -sum(kv[1])):
            flag = "MAIN THREAD" if main else "thread"
            print(f"    {cmd:28} {flag:12} n={len(v):4d}  total={sum(v):8.1f}ms"
                  f"  mean={sum(v)/len(v):7.1f}  max={max(v):8.1f}ms")

    gcs = [r for r in rows if r["t"] == "gc" and r.get("ms") is not None]
    if gcs:
        by_gen: dict[int, list[float]] = defaultdict(list)
        for g in gcs:
            by_gen[g.get("gen", -1)].append(g["ms"])
        print("\n  garbage collection:")
        for gen in sorted(by_gen):
            v = by_gen[gen]
            print(f"    gen{gen}  n={len(v):5d}  total={sum(v):8.1f}ms"
                  f"  mean={sum(v)/len(v):6.2f}  p99={pct(v,.99):7.1f}  max={max(v):7.1f}ms")
        big = sorted(gcs, key=lambda g: -g["ms"])[:5]
        print("    slowest collections:")
        for g in big:
            print(f"      gen{g.get('gen')}  {g['ms']:7.1f}ms  "
                  f"tracked={g.get('tracked')}  collected={g.get('collected')}")

    slow = [r for r in rows if r["t"] == "stall"]
    if slow:
        print(f"\n  main-loop stalls >80ms: {len(slow)}")
        for s in sorted(slow, key=lambda x: -x["ms"])[:8]:
            # was a gc running inside this stall?
            lo, hi = s["ts"] - s["ms"] / 1000, s["ts"]
            inside = [g for g in gcs if lo <= g["ts"] <= hi]
            tag = (f"  [gc: {len(inside)} colls, {sum(g['ms'] for g in inside):.0f}ms]"
                   if inside else "")
            print(f"\n    {s['ms']:7.1f}ms  ({s.get('nsamples', 0)} samples){tag}")
            for st in s.get("stacks", [])[:3]:
                print(f"        {st}")
    return 0


# --------------------------------------------------------------------------
# instrumentation
# --------------------------------------------------------------------------
def install() -> None:
    fh = open(LOG, "w", buffering=1)

    def emit(**kw):
        kw["ts"] = time.perf_counter()
        fh.write(json.dumps(kw) + "\n")

    import textual.app as tapp
    from textual._compositor import Compositor
    from textual.drivers import linux_driver
    from textual.drivers._writer_thread import WriterThread
    from textual.widget import Widget

    state = {"key_ts": None, "key_name": None, "key_frames": 0, "logged": False}

    # ---- 1. writer thread: measure real tty drain + queue depth ----------
    orig_run = WriterThread.run

    def run(self):
        write, flush, get, qsize = (
            self._file.write, self._file.flush, self._queue.get, self._queue.qsize
        )
        while True:
            text = get()
            if text is None:
                break
            t0 = time.perf_counter()
            write(text)
            if qsize() == 0:
                flush()
            dt = (time.perf_counter() - t0) * 1000
            if dt > 0.5:
                emit(t="drain", drain_ms=dt, bytes=len(text), q=qsize())
        flush()

    WriterThread.run = run

    # ---- 2. compositor: is this a full repaint? -------------------------
    orig_render_update = Compositor.render_update

    def render_update(self, full=False, screen_stack=None, simplify=False):
        screen_region = self.size.region
        state["full"] = bool(full or screen_region in self._dirty_regions)
        state["dirty"] = len(self._dirty_regions)
        return orig_render_update(self, full=full, screen_stack=screen_stack,
                                  simplify=simplify)

    Compositor.render_update = render_update

    # ---- 3. _display: split python-compose vs terminal-enqueue ----------
    orig_write = linux_driver.LinuxDriver.write
    write_cost = {"ms": 0.0, "bytes": 0}

    def drv_write(self, data: str) -> None:
        t0 = time.perf_counter()
        orig_write(self, data)
        write_cost["ms"] += (time.perf_counter() - t0) * 1000
        write_cost["bytes"] += len(data)

    linux_driver.LinuxDriver.write = drv_write

    orig_display = tapp.App._display

    def _display(self, screen, renderable):
        write_cost["ms"] = 0.0
        write_cost["bytes"] = 0
        t0 = time.perf_counter()
        try:
            orig_display(self, screen, renderable)
        finally:
            total = (time.perf_counter() - t0) * 1000
            if write_cost["bytes"]:
                emit(
                    t="frame",
                    compose_ms=round(total - write_cost["ms"], 3),
                    write_ms=round(write_cost["ms"], 3),
                    bytes=write_cost["bytes"],
                    full=state.get("full"),
                    dirty=state.get("dirty"),
                )
                if state["key_ts"] is not None:
                    state["key_frames"] += 1
                    if not state["logged"]:
                        emit(t="key", key=state["key_name"],
                             latency_ms=round((time.perf_counter() - state["key_ts"]) * 1000, 3))
                        state["logged"] = True

    tapp.App._display = _display

    # ---- 4. key events: latency + frames generated ----------------------
    from textual import events

    orig_on_event = tapp.App.on_event

    async def on_event(self, event):
        if isinstance(event, events.Key):
            if state["key_ts"] is not None:
                emit(t="key", key=state["key_name"], frames=state["key_frames"])
            state["key_ts"] = time.perf_counter()
            state["key_name"] = event.key
            state["key_frames"] = 0
            state["logged"] = False
        await orig_on_event(self, event)

    tapp.App.on_event = on_event

    # ---- 5. per-widget render cost --------------------------------------
    orig_render_lines = Widget.render_lines

    def render_lines(self, crop):
        t0 = time.perf_counter()
        try:
            return orig_render_lines(self, crop)
        finally:
            dt = (time.perf_counter() - t0) * 1000
            if dt > 1.0:
                emit(t="render", widget=type(self).__name__, ms=round(dt, 3),
                     h=crop.height)

    Widget.render_lines = render_lines

    # ---- 5b. blocking work on the event loop ----------------------------
    import threading as _th

    _main_ident = _th.main_thread().ident

    def _on_main() -> bool:
        return _th.current_thread().ident == _main_ident

    from bor import mu as bor_mu

    orig_run_mu = bor_mu.MuInterface._run_mu

    def _run_mu(self, args, capture_output=True):
        t0 = time.perf_counter()
        try:
            return orig_run_mu(self, args, capture_output)
        finally:
            emit(t="mu", cmd=" ".join(args[:3]),
                 ms=round((time.perf_counter() - t0) * 1000, 1), main=_on_main())

    bor_mu.MuInterface._run_mu = _run_mu

    orig_view = bor_mu.MuInterface.view

    def view(self, path, mark_as_read=True, msgid=""):
        t0 = time.perf_counter()
        try:
            return orig_view(self, path, mark_as_read, msgid)
        finally:
            emit(t="muview", ms=round((time.perf_counter() - t0) * 1000, 1),
                 main=_on_main())

    bor_mu.MuInterface.view = view

    # ---- 6. garbage collector ------------------------------------------
    import gc

    gc_state = {"t0": 0.0}

    def gc_cb(phase, info):
        if phase == "start":
            gc_state["t0"] = time.perf_counter()
        else:
            dt = (time.perf_counter() - gc_state["t0"]) * 1000
            emit(t="gc", gen=info.get("generation"), ms=round(dt, 3),
                 collected=info.get("collected"), uncollectable=info.get("uncollectable"),
                 tracked=len(gc.get_objects()) if dt > 50 else None)

    gc.callbacks.append(gc_cb)

    # ---- 7. event-loop stall detector with main-thread stack -------------
    import asyncio
    import threading
    import traceback

    main_ident = threading.main_thread().ident
    ring: list[tuple[float, str]] = []

    def sampler():
        while True:
            fr = sys._current_frames().get(main_ident)
            if fr is not None:
                ring.append((
                    time.perf_counter(),
                    " <- ".join(
                        f"{f.filename.rsplit('/', 1)[-1]}:{f.lineno}:{f.name}"
                        for f in reversed(traceback.extract_stack(fr)[-14:])
                    ),
                ))
                del ring[:-400]
            time.sleep(0.01)

    threading.Thread(target=sampler, daemon=True, name="borprof-sampler").start()

    def watchdog(loop):
        last = time.perf_counter()

        def tick():
            nonlocal last
            now = time.perf_counter()
            gap = (now - last) * 1000
            if gap > 80:
                # what was the main thread doing during the gap?
                during = [s for ts, s in ring if last <= ts <= now]
                emit(t="stall", ms=round(gap, 1), nsamples=len(during),
                     stacks=during[:6])
            last = now
            loop.call_later(0.02, tick)

        loop.call_soon_threadsafe(lambda: loop.call_later(0.02, tick))

    orig_process = tapp.App._process_messages

    async def _process_messages(self, *a, **kw):
        watchdog(asyncio.get_running_loop())
        return await orig_process(self, *a, **kw)

    tapp.App._process_messages = _process_messages


def main(argv: list[str] | None = None) -> int:
    """Run bor under instrumentation, or report on a previous run."""
    args = list(sys.argv[1:] if argv is None else argv)
    if "--report" in args:
        return report()
    install()
    from bor.app import main as bor_main
    print(f"[bor.profiling] logging to {LOG}", file=sys.stderr)
    return bor_main(args)


if __name__ == "__main__":
    sys.exit(main())
