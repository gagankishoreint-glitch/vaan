"""Item H: the half-open state must admit exactly ONE probe.

Run: /tmp/auditenv/bin/python -m pytest -q tests/test_breaker_half_open.py

A breaker whose half-open state is only a *label* is worse than no breaker: the
moment the provider has been failing and the timeout expires, the whole fleet is
released at once -- the thundering herd the breaker exists to prevent, deferred by
one timeout. These tests pin the admission count, not the label.
"""
from relay.gateway.gateway import Breaker


def test_half_open_admits_exactly_one_probe():
    b = Breaker(fail_threshold=2, open_s=10.0)
    b.record(ok=False, now=0.0)
    b.record(ok=False, now=0.0)
    assert b.state(0.0) == "open"

    # Timeout expires -> half-open. First arrival is the probe.
    admitted, state = b.try_admit(10.0)
    assert admitted is True
    assert state == "half-open"

    # Everyone else is refused while the probe is in flight. This is the assertion
    # that fails if try_admit is replaced by state() == "open".
    for _ in range(20):
        admitted, state = b.try_admit(10.0)
        assert admitted is False, "half-open admitted more than one probe"


def test_successful_probe_closes_the_breaker():
    b = Breaker(fail_threshold=2, open_s=10.0)
    b.record(ok=False, now=0.0)
    b.record(ok=False, now=0.0)
    b.try_admit(10.0)
    b.record(ok=True, now=11.0)
    assert b.state(11.0) == "closed"
    assert b.try_admit(11.0) == (True, "closed")
    assert b.try_admit(11.0) == (True, "closed")


def test_failed_probe_reopens_immediately_even_below_threshold():
    # fail_threshold=5, but a failed PROBE re-opens at once. The threshold counts
    # consecutive failures on the closed path; a probe that failed is proof the
    # provider is still down and waiting for four more is wasted traffic.
    b = Breaker(fail_threshold=5, open_s=10.0)
    for _ in range(5):
        b.record(ok=False, now=0.0)
    assert b.state(0.0) == "open"

    b.try_admit(10.0)
    b.record(ok=False, now=11.0)
    assert b.state(11.0) == "open", "failed probe let the breaker stay half-open"
    assert b.state(20.9) == "open"
    assert b.state(21.0) == "half-open"


def test_probe_flag_clears_so_a_later_probe_can_run():
    b = Breaker(fail_threshold=1, open_s=10.0)
    b.record(ok=False, now=0.0)
    assert b.try_admit(10.0) == (True, "half-open")
    b.record(ok=False, now=10.5)     # probe failed, back to open
    assert b.try_admit(11.0) == (False, "open")
    # The failed probe re-opened at 10.5, so the next window starts at 20.5 -- not
    # at 20.0. Asserting 20.0 would encode the wrong reopen instant.
    assert b.try_admit(20.4) == (False, "open")
    assert b.try_admit(20.5) == (True, "half-open")


def test_closed_breaker_never_refuses():
    b = Breaker(fail_threshold=3, open_s=5.0)
    b.record(ok=False, now=0.0)
    b.record(ok=False, now=0.0)
    for _ in range(50):
        assert b.try_admit(0.0) == (True, "closed")
