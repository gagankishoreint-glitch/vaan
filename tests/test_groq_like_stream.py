"""5c follow-up: a Groq-shaped stream must count as valid and complete.

The stand-in emits a tidy stream: role frame, content deltas, a usage chunk, [DONE].
Real Groq is messier, and a parser that only accepts the tidy shape would report a
perfectly good response as a protocol failure. The shape tested here, from the
supervisor's description of real traffic:

    role chunk first
    reasoning deltas BEFORE any content
    no usage chunk at all
    then [DONE]

Under the old parser this was `first_delta` = role frame, `model_ttft` = first
CONTENT, and `[DONE]` discarded -- so it happened to work. Under the new tolerant
parser it must STILL work, and `n_malformed` must stay 0: reasoning deltas are not
malformed, they are just not content.

Run: python -m pytest -q tests/test_groq_like_stream.py  -> 6 passed
"""
from __future__ import annotations

import asyncio

from relay.gateway.stream import consume, parse_sse_line_verbose, usage_from


class FakeClock:
    def __init__(self, step: float = 0.01):
        self.t = 0.0
        self.step = step

    def now(self) -> float:
        self.t += self.step
        return self.t


async def _agen(items):
    for i in items:
        yield i


#: A stream shaped the way Groq's is reported to be.
GROQ_LIKE = [
    'data: {"id":"x","choices":[{"index":0,"delta":{"role":"assistant"}}]}',
    # reasoning BEFORE content -- these carry no `content` key at all
    'data: {"id":"x","choices":[{"index":0,"delta":{"reasoning":"Let me "}}]}',
    'data: {"id":"x","choices":[{"index":0,"delta":{"reasoning":"think."}}]}',
    # now the answer
    'data: {"id":"x","choices":[{"index":0,"delta":{"content":"The "}}]}',
    'data: {"id":"x","choices":[{"index":0,"delta":{"content":"answer."}}]}',
    # deliberately NO usage chunk
    "data: [DONE]",
]


def _run(items):
    async def go():
        return await consume(_agen(items), FakeClock(), t_sent=0.0)
    return asyncio.run(go())


def test_groq_like_stream_is_complete_and_clean():
    st = _run(GROQ_LIKE)
    assert st.text == "The answer.", st.text
    assert st.saw_done is True
    assert st.n_malformed == 0, [r.raw for r in st.raw_lines if r.kind == "malformed"]


def test_reasoning_deltas_are_not_content():
    """`model_ttft` must be the first CONTENT, not the first reasoning delta.

    Otherwise TTFT is measured against the start of the thinking block and the
    number looks better than the user's experience.
    """
    st = _run(GROQ_LIKE)
    assert st.model_ttft is not None
    # first_delta (role) < model_ttft (first content); both stamped
    assert st.first_delta is not None and st.first_delta < st.model_ttft


def test_reasoning_frame_is_classified_as_a_frame_not_malformed():
    got = parse_sse_line_verbose(GROQ_LIKE[1])
    assert got.kind == "frame"
    assert "reasoning" in got.frame["choices"][0]["delta"]


def test_missing_usage_chunk_leaves_usage_none_without_error():
    """No usage chunk is legal. It must not raise, and must not be invented."""
    st = _run(GROQ_LIKE)
    assert st.usage is None


def test_groq_usage_may_arrive_under_x_groq():
    """UNVERIFIED location, accepted anyway.

    From memory the final usage can be nested as {"x_groq": {"usage": {...}}}. A
    wrong lookup makes tokens_in/out null and the TPM reconciliation a no-op, which
    fails silently -- so both locations are accepted.
    """
    assert usage_from({"x_groq": {"usage": {"prompt_tokens": 76,
                                            "completion_tokens": 41}}}) == {
        "prompt_tokens": 76, "completion_tokens": 41}
    assert usage_from({"usage": {"prompt_tokens": 1}}) == {"prompt_tokens": 1}
    # top-level wins when both are present
    assert usage_from({"usage": {"prompt_tokens": 1},
                       "x_groq": {"usage": {"prompt_tokens": 99}}}) == {
        "prompt_tokens": 1}


def test_x_groq_usage_in_a_real_stream_is_picked_up():
    body = [
        'data: {"choices":[{"delta":{"content":"hi"}}]}',
        'data: {"choices":[],"x_groq":{"usage":{"prompt_tokens":9,"completion_tokens":3}}}',
        "data: [DONE]",
    ]
    st = _run(body)
    assert st.usage == {"prompt_tokens": 9, "completion_tokens": 3}
    assert st.n_malformed == 0
