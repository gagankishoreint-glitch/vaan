"""Item B: one set of TPM/RPM/RPD buckets PER MODEL, reconciled per model.

Whether Groq's per-model buckets are truly independent is **UNVERIFIED**
(`models.buckets_separate_per_model` is null until the probe's `buckets` mode
exhausts one model and watches the other). It is therefore a config ASSUMPTION, and
the code says so. These tests pin the behaviour that assumption implies.

The failure mode being prevented: a single shared budget lets one model's exhaustion
refuse calls to a model that has capacity left. That fails in the expensive
direction -- the caller is told there is no budget when there is.

Run: python -m pytest -q tests/test_per_model_buckets.py  -> 6 passed
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import httpx
import pytest

from relay.config import load_config
from relay.gateway.gateway import BudgetBook, DeadlineExceeded, Gateway

SMALL = "openai/gpt-oss-20b"
LARGE = "openai/gpt-oss-120b"


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def now(self) -> float:
        return self.t

    async def sleep(self, s: float) -> None:
        self.t += s


class _Scope:
    def __init__(self, log, rid="pmb"):
        self.log = log
        self.req = log.request(rid)
        self.req_id = self.req.req_id

    def attempt_start(self, a):
        return self.req.attempt_start(a)

    def attempt_end(self, a):
        return self.req.attempt_end(a)

    def emit(self, *a, **k):
        return self.log.emit(*a, **k)


def _gw(handler, *, separate=None, policy="managed"):
    from relay.events import EventLog
    cfg = load_config()
    td = tempfile.mkdtemp()
    log = EventLog(td, run_id="pmb", backend="standin")
    clock = FakeClock()
    gw = Gateway.from_config(
        cfg, clock, log, base_url="https://x.test/openai/v1", api_key="k",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                 base_url="https://x.test/openai/v1"),
        policy=policy)
    if separate is not None:
        gw.budget = BudgetBook(tpm=cfg.get("models.small.tpm"),
                               rpd=cfg.get("models.small.rpd"),
                               separate=separate,
                               default_model=cfg.get("models.small.id"))
    gw.max_attempts = 1
    return gw, log, Path(td)


_seq = {"n": 0}


def _call(gw, log, model, *, deadline_s=5.0):
    """One logical call on the gateway's EXISTING log.

    A fresh RequestScope per call (the log rejects a second request on one scope),
    and the log is NOT closed here -- the caller may make several calls. The
    temporary directory outlives the test, so nothing leaks between tests.
    """
    _seq["n"] += 1
    scope = _Scope(log, rid=f"pmb-{_seq['n']}")

    async def go():
        return await gw.call(scope=scope, step="draft", model=model,
                             messages=[{"role": "user", "content": "hi"}],
                             max_tokens=10, deadline_s=deadline_s)

    return asyncio.run(go())


def test_models_get_independent_buckets():
    book = BudgetBook(tpm=100, rpd=10, separate=True, default_model=SMALL)
    book[SMALL].take(100, now=0.0)          # small model fully spent
    with pytest.raises(DeadlineExceeded):
        book[SMALL].take(1, now=0.1)
    # the OTHER model is untouched
    book[LARGE].take(100, now=0.1)
    assert book[LARGE].tpm_used == 100
    assert book[SMALL].tpm_used == 100


def test_shared_mode_is_available_and_is_not_the_default():
    """`buckets_separate_per_model: false` must still work; null must not mean shared."""
    shared = BudgetBook(tpm=100, rpd=10, separate=False, default_model=SMALL)
    shared[SMALL].take(100, now=0.0)
    with pytest.raises(DeadlineExceeded):
        shared[LARGE].take(1, now=0.1)      # shared: the other model is also spent

    cfg = load_config()
    assert cfg.get("models.buckets_separate_per_model") is None, (
        "this test's premise is that the setting is still UNMEASURED (null)")
    gw, _, _ = _gw(lambda r: httpx.Response(200))
    assert gw.budget.separate is True, (
        "null (unmeasured) must resolve to SEPARATE: sharing loses capacity "
        "silently in the expensive direction")


def test_each_model_reconciles_from_its_own_headers():
    """A header for one model must not move the other model's counters."""
    def handler(request):
        body = json.loads(request.content)
        model = body["model"]
        # advertise different remaining budgets per model
        remaining = "900" if model == SMALL else "10"
        return httpx.Response(200, headers={
            "x-ratelimit-limit-tokens": "1000",
            "x-ratelimit-remaining-tokens": remaining,
            "x-ratelimit-limit-requests": "100",
            "x-ratelimit-remaining-requests": "50",
        }, json={"choices": [{"message": {"content": "ok"}}],
                 "usage": {"prompt_tokens": 1, "completion_tokens": 1}})

    gw, log, td = _gw(handler, separate=True)
    _call(gw, log, SMALL)
    _call(gw, log, LARGE)

    small, large = gw.budget[SMALL], gw.budget[LARGE]
    assert small.provider_limit_tpm == 1000
    assert large.provider_limit_tpm == 1000
    # The invariant under test is ISOLATION, not the absolute reconciled figure.
    # `reconcile` deliberately works in RATIOS against the LOCAL limit rather than
    # reconstructing usage from the provider's absolute numbers (BUG-010), so the
    # exact values are 800 and 7920 here. Pinning isolation is the point:
    # The exact figures depend on reconcile's ratio arithmetic and the in-flight
    # floor; the ISOLATION is what this test is for. Assert the direction and the
    # magnitude gap, which no shared bucket could produce.
    assert small.tpm_used < large.tpm_used, (
        f"small ({small.tpm_used}) should be much less spent than large "
        f"({large.tpm_used}): each reconciled from its OWN header")
    assert large.tpm_used > 5000, large.tpm_used
    assert small.tpm_used < 1000, small.tpm_used
    # A shared bucket would have reconciled BOTH to whichever header arrived last.
    assert small.tpm_used != large.tpm_used


def test_exhausting_one_model_does_not_block_the_other():
    """The end-to-end property, through the real call path."""
    def handler(request):
        body = json.loads(request.content)
        if body["model"] == SMALL:
            return httpx.Response(429, headers={"retry-after": "1"},
                                  json={"error": {"message": "no tokens"}})
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1}})

    gw, log, td = _gw(handler, separate=True)
    with pytest.raises(Exception):
        _call(gw, log, SMALL)
    # the large model must still be callable
    body = _call(gw, log, LARGE)
    assert body["choices"][0]["message"]["content"] == "ok"


def test_shared_mode_would_block_it_and_that_is_the_documented_hazard():
    """Proves the default matters: shared mode refuses a model with capacity left."""
    def handler(request):
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1}})

    gw, log, td = _gw(handler, separate=False)
    gw.budget._shared.take(gw.budget.default_tpm, now=0.0)   # spend the shared pool
    with pytest.raises(DeadlineExceeded):
        _call(gw, log, LARGE, deadline_s=1.0)


def test_assumption_is_labelled_unverified_in_code_and_config():
    import inspect

    from relay.gateway import gateway as mod

    src = inspect.getsource(mod.BudgetBook)
    assert "UNVERIFIED" in src, "the per-model independence assumption lost its label"
    assert "buckets_separate_per_model" in src, "the config key reference was dropped"
