"""Regression test: flush() must wait for the WRITE, not for the dequeue.

Deterministic, not schedulable: it widens the writer's get()->write() window, so
the old queue.empty() poll returns early every single time. No timing luck.
"""
import json
import time

import pytest

from relay.events import EventLog


@pytest.fixture
def slow_write(monkeypatch):
    """Make the writer's serialisation slow, widening get()->write() to 50 ms."""
    import relay.events as ev_mod
    real = json.dumps

    def slow(*a, **k):
        time.sleep(0.05)
        return real(*a, **k)

    monkeypatch.setattr(ev_mod.json, "dumps", slow)
    return slow


def test_flush_waits_for_the_write_not_the_dequeue(tmp_path, slow_write):
    """BUG-026. Fails on the old `while not self._q.empty()` poll."""
    lg = EventLog(str(tmp_path), run_id="r1", backend="standin")
    try:
        lg.emit("hello", req_id="q1")
        lg.flush()
        lines = [ln for ln in lg.path.read_text().splitlines() if ln.strip()]
    finally:
        lg.close()
    assert len(lines) == 1, (
        "flush() returned while an event was still queued-or-in-flight: "
        f"{len(lines)} events readable. It must wait for the WRITE.")
    assert json.loads(lines[0])["type"] == "hello"
