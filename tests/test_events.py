import json
import threading

import pytest

from relay.events import (
    EventLog,
    RequestScope,
    TerminalEventAlreadyEmitted,
    TERMINAL,
)


@pytest.fixture
def log(tmp_path):
    lg = EventLog(str(tmp_path), run_id="r1", backend="standin")
    yield lg
    lg.close()
    lg.flush()


def read_events(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_envelope_fields_present(tmp_path):
    with EventLog(str(tmp_path), run_id="r1", backend="standin") as lg:
        lg.emit("hello", req_id="q1")
        lg.flush()
        ev = read_events(lg.path)[0]
    assert ev["type"] == "hello"
    assert ev["run_id"] == "r1"
    assert ev["backend"] == "standin"
    assert ev["req_id"] == "q1"
    assert isinstance(ev["t_mono"], float)
    assert isinstance(ev["t_wall"], float)


def test_exactly_one_terminal(tmp_path):
    with EventLog(str(tmp_path), run_id="r1", backend="standin") as lg:
        s = lg.request("q1")
        s.terminal("answered")
        with pytest.raises(TerminalEventAlreadyEmitted):
            s.terminal("answered")
    assert "terminal" in TERMINAL


def test_no_event_after_terminal(tmp_path):
    with EventLog(str(tmp_path), run_id="r1", backend="standin") as lg:
        s = lg.request("q1")
        s.terminal("passages_only")
        for call in (lambda: s.emit("late"), lambda: s.abandon()):
            with pytest.raises(TerminalEventAlreadyEmitted):
                call()


def test_no_attempt_after_terminal(tmp_path):
    from relay.contracts import Attempt

    with EventLog(str(tmp_path), run_id="r1", backend="standin") as lg:
        s = lg.request("q1")
        a = Attempt("a2", "q1", "draft", "standin", "m", t_sent=0.0)
        s.terminal("answered")
        with pytest.raises(TerminalEventAlreadyEmitted):
            s.attempt_start(a)


def test_attempt_lifecycle_fields_survive_json(tmp_path):
    from relay.contracts import Attempt, Outcome

    with EventLog(str(tmp_path), run_id="r1", backend="standin") as lg:
        s = lg.request("q1")
        a = Attempt("a1", "q1", "draft", "groq", "openai/gpt-oss-20b", t_sent=1.0)
        s.attempt_start(a)
        a.t_end, a.status, a.outcome = 2.0, 200, Outcome.OK
        a.tokens_in, a.tokens_out, a.tokens_cached = 100, 50, 20
        a.rl_headers_raw = {"x-ratelimit-reset-requests": "2m59.56s"}
        s.attempt_end(a)
        s.terminal("answered")
        lg.flush()
        evs = read_events(lg.path)
    ends = [e for e in evs if e["type"] == "attempt.end"]
    assert len(ends) == 1
    assert ends[0]["outcome"] == "ok"
    assert ends[0]["rl_headers_raw"]["x-ratelimit-reset-requests"] == "2m59.56s"
    # exactly one terminal, and it is last
    terms = [e for e in evs if e["type"] in TERMINAL]
    assert len(terms) == 1 and evs[-1] is not None and evs[-1]["type"] in TERMINAL


def test_abandon_then_terminal_is_allowed_and_flagged(tmp_path):
    with EventLog(str(tmp_path), run_id="r1", backend="standin") as lg:
        s = lg.request("q1")
        s.abandon("user")
        assert s.abandoned
        s.terminal("abandoned")
    assert True


def test_request_scope_is_idempotent_per_id(tmp_path):
    with EventLog(str(tmp_path), run_id="r1", backend="standin") as lg:
        assert lg.request("q1") is lg.request("q1")
        assert lg.request("q1") is not lg.request("q2")


def test_emit_does_not_block_caller(tmp_path):
    """Rule 8: emit() is an enqueue, not a write. It must be fast and non-blocking."""
    import time

    with EventLog(str(tmp_path), run_id="r1", backend="standin") as lg:
        t0 = time.perf_counter()
        for i in range(2000):
            lg.emit("counter", name="x", i=i)
        dt = time.perf_counter() - t0
        lg.flush()
    assert dt < 1.0, f"2000 emits took {dt:.3f}s; emit() is blocking"


def test_emit_after_close_raises(tmp_path):
    lg = EventLog(str(tmp_path), run_id="r1", backend="standin")
    lg.close()
    with pytest.raises(RuntimeError):
        lg.emit("x")


def test_concurrent_terminals_exactly_one(tmp_path):
    """Two threads racing for the terminal: exactly one wins, file has one line."""
    with EventLog(str(tmp_path), run_id="r1", backend="standin") as lg:
        s = lg.request("q1")
        wins, loses = [], []

        def go(name):
            try:
                s.terminal("answered", by=name)
                wins.append(name)
            except TerminalEventAlreadyEmitted:
                loses.append(name)

        threads = [threading.Thread(target=go, args=(f"t{i}",)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        lg.flush()
        terms = [e for e in read_events(lg.path) if e["type"] in TERMINAL]
    assert len(wins) == 1 and len(loses) == 1
    assert len(terms) == 1


# ---------------------------------------------------------------- ordering (BUG-001)

def test_finish_emits_end_before_terminal(tmp_path):
    with EventLog(str(tmp_path), run_id="r1", backend="standin") as lg:
        s = lg.request("q1")
        s.finish("answered", total_elapsed_s=0.5,
                 waiting_s=0.1, working_s=0.4, retrying_s=0.0)
        lg.flush()
        types = [e["type"] for e in read_events(lg.path)]
    assert types == ["request.end", "terminal"], types


def test_finish_twice_raises(tmp_path):
    with EventLog(str(tmp_path), run_id="r1", backend="standin") as lg:
        s = lg.request("q1")
        kw = dict(total_elapsed_s=0.5, waiting_s=0.1, working_s=0.4, retrying_s=0.0)
        s.finish("answered", **kw)
        with pytest.raises(TerminalEventAlreadyEmitted):
            s.finish("answered", **kw)


def test_emit_after_finish_raises(tmp_path):
    with EventLog(str(tmp_path), run_id="r1", backend="standin") as lg:
        s = lg.request("q1")
        s.finish("passages_only", total_elapsed_s=0.1,
                 waiting_s=0.0, working_s=0.1, retrying_s=0.0)
        with pytest.raises(TerminalEventAlreadyEmitted):
            s.emit("request.end")


def test_flush_after_close_is_noop(tmp_path):
    """BUG-002: shutdown order (close then flush) must not raise."""
    lg = EventLog(str(tmp_path), run_id="r1", backend="standin")
    lg.emit("x")
    lg.close()
    lg.flush()            # must not raise
    lg.close()            # idempotent


def test_close_is_idempotent(tmp_path):
    lg = EventLog(str(tmp_path), run_id="r1", backend="standin")
    lg.emit("x")
    lg.close()
    lg.close()
    assert lg.path.exists()


# ------------------------------------------------- reserved envelope fields (BUG-005)

def test_reserved_field_collision_raises(tmp_path):
    from relay.events import ReservedFieldError

    with EventLog(str(tmp_path), run_id="r1", backend="standin") as lg:
        for bad in ({"run_id": "spoofed"}, {"t_mono": 0.0}, {"t_wall": 0.0},
                    {"type": "spoofed"}, {"backend": "spoofed"}):
            with pytest.raises(ReservedFieldError):
                lg.emit("x", **bad)


def test_req_id_is_not_reserved(tmp_path):
    with EventLog(str(tmp_path), run_id="r1", backend="standin") as lg:
        lg.emit("x", req_id="q9")       # must not raise
        lg.flush()
        assert read_events(lg.path)[0]["req_id"] == "q9"


def test_attempt_timestamps_are_not_reserved(tmp_path):
    """attempt.end legitimately carries t_first_byte/t_sent; only the envelope's
    own keys are reserved."""
    from relay.contracts import Attempt

    with EventLog(str(tmp_path), run_id="r1", backend="standin") as lg:
        s = lg.request("q1")
        a = Attempt("a1", "q1", "draft", "groq", "m", t_sent=0.0)
        s.attempt_start(a)
        a.t_end, a.t_first_byte, a.t_first_token = 1.0, 0.1, 0.2
        s.attempt_end(a)
        lg.flush()
        end = [e for e in read_events(lg.path) if e["type"] == "attempt.end"][0]
    assert end["t_first_byte"] == 0.1


# ------------------------------------------------------ backend scope (D-008)

def test_attempt_backend_is_the_attempt_value_and_backend_is_run_scope(tmp_path):
    from relay.contracts import Attempt

    with EventLog(str(tmp_path), run_id="r1", backend="standin") as lg:
        s = lg.request("q1")
        a = Attempt("a1", "q1", "draft", "groq", "m", t_sent=0.0)
        s.attempt_start(a)
        a.t_end = 1.0
        s.attempt_end(a)
        s.finish("answered", total_elapsed_s=1.0, waiting_s=0.0,
                 working_s=1.0, retrying_s=0.0)
        lg.flush()
        evs = read_events(lg.path)
    start = [e for e in evs if e["type"] == "attempt.start"][0]
    assert start["attempt_backend"] == "groq"   # per attempt
    assert start["backend"] == "standin"        # run scope, not overwritten
    assert "backend" not in start or start["backend"] == "standin"


def test_primary_backend_is_majority(tmp_path):
    from relay.contracts import Attempt

    with EventLog(str(tmp_path), run_id="r1", backend="mixed") as lg:
        s = lg.request("q1")
        for i, be in enumerate(["groq", "standin", "standin"]):
            a = Attempt(f"a{i}", "q1", "draft", be, "m", t_sent=0.0)
            s.attempt_start(a)
            a.t_end = 1.0
            s.attempt_end(a)
        assert s.primary_backend == "standin"
        s.finish("answered", total_elapsed_s=1.0, waiting_s=0.0,
                 working_s=1.0, retrying_s=0.0)
        lg.flush()
        term = [e for e in read_events(lg.path) if e["type"] == "terminal"][0]
    assert term["primary_backend"] == "standin"


def test_primary_backend_tie_falls_back_to_first_appearance(tmp_path):
    from relay.contracts import Attempt

    with EventLog(str(tmp_path), run_id="r1", backend="mixed") as lg:
        s = lg.request("q1")
        for i, be in enumerate(["groq", "standin"]):
            a = Attempt(f"a{i}", "q1", "draft", be, "m", t_sent=0.0)
            s.attempt_start(a)
            a.t_end = 1.0
            s.attempt_end(a)
        assert s.primary_backend == "groq"


def test_primary_backend_none_without_attempts(tmp_path):
    with EventLog(str(tmp_path), run_id="r1", backend="standin") as lg:
        s = lg.request("q1")
        assert s.primary_backend is None
        s.finish("no_evidence", total_elapsed_s=0.1, waiting_s=0.0,
                 working_s=0.1, retrying_s=0.0)
        lg.flush()
        term = [e for e in read_events(lg.path) if e["type"] == "terminal"][0]
    assert term["primary_backend"] is None
