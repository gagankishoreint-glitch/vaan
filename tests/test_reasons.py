"""BUG-042: the reason names the CAUSE, and the vocabulary is enforced.

Run: /tmp/auditenv/bin/python -m pytest -q tests/test_reasons.py

A 500 storm used to reach the user as `budget_gone` because `DeadlineExceeded`
covered four unrelated failures. `budget_gone` must now mean ONE thing: a budget was
actually refused. Everything that spent tokens and did not get an answer is
`upstream_error`.
"""
import pytest

from relay.contracts import PASSAGES_ONLY_REASONS, PassagesOnly
from relay.gateway.gateway import BreakerOpen, DeadlineExceeded, UpstreamError
from relay.gateway.stream import StreamProtocolError


# ---------------------------------------------------------------- vocabulary

def test_budget_gone_and_upstream_error_are_distinct_members():
    assert "budget_gone" in PASSAGES_ONLY_REASONS
    assert "upstream_error" in PASSAGES_ONLY_REASONS
    assert "budget_gone" != "upstream_error"


def test_an_invented_reason_is_rejected_at_construction():
    with pytest.raises(ValueError, match="not one of"):
        PassagesOnly("msg", (), "provider_unhappy")


def test_every_permitted_reason_constructs():
    for reason in sorted(PASSAGES_ONLY_REASONS):
        assert PassagesOnly("msg", (), reason).reason == reason


def test_the_two_checkers_retype_the_same_set():
    """D-006: check_events and analyze RE-TYPE the set so a library bug cannot hide.

    The price of that independence is drift. This test is the price paid: if either
    literal gains or loses a member, this fails instead of both files agreeing with
    their own typo.
    """
    from scripts.check_events import _PERMITTED_REASONS as checker_set
    from scripts.analyze import _PERMITTED_REASONS as analyze_set
    assert checker_set == PASSAGES_ONLY_REASONS
    assert analyze_set == PASSAGES_ONLY_REASONS


# ---------------------------------------------------------------- the mapping

class _FakeResp:
    def __init__(self, status, body=None, headers=None, text=""):
        self.status_code = status
        self._body = body if body is not None else {"choices": [], "usage": {}}
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._body


class _FakeClient:
    """Returns a queued response per call and counts the calls."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def post(self, url, json=None):
        self.calls += 1
        r = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if isinstance(r, Exception):
            raise r
        return r


def _gw(client, **kw):
    from relay.clock import RealClock
    from relay.config import load_config
    from relay.events import EventLog
    from relay.gateway.gateway import Gateway
    import tempfile

    cfg = load_config()
    log = EventLog(tempfile.mkdtemp(prefix="reasons_"), run_id="r", backend="standin")
    gw = Gateway.from_config(
        cfg, clock=RealClock(), log=log, base_url="http://127.0.0.1:8009/openai/v1",
        api_key="x", client=client)
    gw.max_attempts = kw.get("max_attempts", 2)
    gw.breaker.fail_threshold = 99        # keep the breaker out of the way here
    return gw


def _scope(gw):
    from relay.events import RequestScope
    return RequestScope(gw.log, "r-1")


async def _call(gw):
    return await gw.call(
        scope=_scope(gw), step="draft", model="m",
        messages=[{"role": "user", "content": "hi"}], max_tokens=8,
        deadline_s=5.0)


@pytest.mark.asyncio
async def test_a_500_storm_yields_upstream_error_not_budget_gone():
    """THE regression test. Against the old mapping this raises DeadlineExceeded."""
    gw = _gw(_FakeClient([_FakeResp(500, text="boom")]))
    with pytest.raises(UpstreamError) as ei:
        await _call(gw)
    # Explicitly not the old behaviour, and not a subclass either.
    assert not isinstance(ei.value, DeadlineExceeded)


@pytest.mark.asyncio
async def test_a_day_limit_429_still_yields_budget_gone():
    """A provider day limit IS a budget refusal and must keep its reason."""
    gw = _gw(_FakeClient([_FakeResp(
        429, headers={"retry-after": "120", "x-ratelimit-remaining-requests": "0"})]))
    with pytest.raises(DeadlineExceeded) as ei:
        await _call(gw)
    assert not isinstance(ei.value, UpstreamError)


@pytest.mark.asyncio
async def test_a_minute_limit_429_that_exhausts_retries_is_not_a_budget_refusal():
    """A minute limit we gave up retrying on is a shortage of attempts, not of budget."""
    gw = _gw(_FakeClient([_FakeResp(429, headers={"retry-after": "1"})]),
             max_attempts=1)
    with pytest.raises(UpstreamError):
        await _call(gw)


# ---------------------------------------------------------------- the user text

def test_budget_gone_text_does_not_blame_the_provider():
    from relay.pipeline.pipeline import REASON_MESSAGES
    msg = REASON_MESSAGES[DeadlineExceeded]
    assert "budget" in msg.lower()


@pytest.mark.parametrize("exc", [UpstreamError, BreakerOpen, StreamProtocolError])
def test_non_budget_texts_never_mention_budget(exc):
    """The instruction: an upstream failure must not read as a budget problem."""
    from relay.pipeline.pipeline import REASON_MESSAGES
    msg = REASON_MESSAGES[exc]
    assert "budget" not in msg.lower()
    assert "token" not in msg.lower()


def test_the_pipeline_mapping_is_exact():
    """Membership is not enough: `budget_gone` IS a permitted value.

    A test that only checks "the reason is in the set" passes when every cause is
    mapped to `budget_gone` -- which is precisely the bug. The mapping must be
    pinned by cause.
    """
    from relay.gateway.stream import StreamProtocolError
    from relay.pipeline.pipeline import REASON_NAMES
    assert REASON_NAMES[DeadlineExceeded] == "budget_gone"
    assert REASON_NAMES[UpstreamError] == "upstream_error"
    assert REASON_NAMES[StreamProtocolError] == "upstream_error"
    assert REASON_NAMES[BreakerOpen] == "breaker_open"


def test_a_subclass_does_not_crash_the_error_path():
    """`reason_for` must match by isinstance; a KeyError in the error path is worse
    than the error it is handling."""
    from relay.pipeline.pipeline import reason_for

    class MyUpstream(UpstreamError):
        pass

    assert reason_for(MyUpstream("x")) == ("upstream_error",
                                           reason_for(UpstreamError("x"))[1])


def test_every_reason_has_a_message_and_a_permitted_value():
    from relay.pipeline.pipeline import REASON_MESSAGES, REASON_NAMES
    for exc in (DeadlineExceeded, UpstreamError, StreamProtocolError, BreakerOpen):
        assert REASON_NAMES[exc] in PASSAGES_ONLY_REASONS
        assert REASON_MESSAGES[exc].strip()


# ---------------------------------------------------------------- admission
def test_admission_diagnoses_map_to_one_contract_reason():
    """`would_wait_past_deadline` is a diagnosis; the contract has no member for it.

    Two diagnoses collapse to `queue_full`, and that is deliberate: a user cannot
    act on the difference, and adding a sixth contract reason to carry a distinction
    only the log uses would grow the set the report aggregates on.
    """
    from relay.pipeline.queue import CONTRACT_REASON, contract_reason
    assert contract_reason("queue_full") == "queue_full"
    assert contract_reason("would_wait_past_deadline") == "queue_full"
    assert set(CONTRACT_REASON.values()) <= PASSAGES_ONLY_REASONS


def test_an_unknown_diagnosis_cannot_leak_into_the_contract():
    from relay.pipeline.queue import contract_reason
    with pytest.raises(ValueError, match="no contract reason"):
        contract_reason("invented_diagnosis")


# ---------------------------------------------------------------- admission
def test_admission_diagnoses_map_to_one_contract_reason():
    """`would_wait_past_deadline` is a diagnosis; the contract has no member for it.

    Two diagnoses collapse to `queue_full`, and that is deliberate: a user cannot
    act on the difference, and adding a sixth contract reason to carry a distinction
    only the log uses would grow the set the report aggregates on.
    """
    from relay.pipeline.queue import CONTRACT_REASON, contract_reason
    assert contract_reason("queue_full") == "queue_full"
    assert contract_reason("would_wait_past_deadline") == "queue_full"
    assert set(CONTRACT_REASON.values()) <= PASSAGES_ONLY_REASONS


def test_an_unknown_diagnosis_cannot_leak_into_the_contract():
    from relay.pipeline.queue import contract_reason
    with pytest.raises(ValueError, match="no contract reason"):
        contract_reason("invented_diagnosis")


# ---------------------------------------------------------------- admission
def test_admission_diagnoses_map_to_one_contract_reason():
    """`would_wait_past_deadline` is a diagnosis; the contract has no member for it.

    Two diagnoses collapse to `queue_full`, and that is deliberate: a user cannot
    act on the difference, and adding a sixth contract reason to carry a distinction
    only the log uses would grow the set the report aggregates on.
    """
    from relay.pipeline.queue import CONTRACT_REASON, contract_reason
    assert contract_reason("queue_full") == "queue_full"
    assert contract_reason("would_wait_past_deadline") == "queue_full"
    assert set(CONTRACT_REASON.values()) <= PASSAGES_ONLY_REASONS


def test_an_unknown_diagnosis_cannot_leak_into_the_contract():
    from relay.pipeline.queue import contract_reason
    with pytest.raises(ValueError, match="no contract reason"):
        contract_reason("invented_diagnosis")


# ---------------------------------------------------------------- admission
def test_admission_diagnoses_map_to_one_contract_reason():
    """`would_wait_past_deadline` is a diagnosis; the contract has no member for it.

    Two diagnoses collapse to `queue_full`, and that is deliberate: a user cannot
    act on the difference, and adding a sixth contract reason to carry a distinction
    only the log uses would grow the set the report aggregates on.
    """
    from relay.pipeline.queue import CONTRACT_REASON, contract_reason
    assert contract_reason("queue_full") == "queue_full"
    assert contract_reason("would_wait_past_deadline") == "queue_full"
    assert set(CONTRACT_REASON.values()) <= PASSAGES_ONLY_REASONS


def test_an_unknown_diagnosis_cannot_leak_into_the_contract():
    from relay.pipeline.queue import contract_reason
    with pytest.raises(ValueError, match="no contract reason"):
        contract_reason("invented_diagnosis")
