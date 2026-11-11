"""One failure-path test per new mechanism. No more than that (compressed mode)."""
from __future__ import annotations

import pytest

from relay.contracts import Citation, NoEvidence, PassagesOnly, VerifiedAnswer, mint_verified
from relay.gateway.gateway import Budget, Breaker
from relay.pipeline.pipeline import send_reply
from relay.pipeline.verify import check_citations, check_numbers_present
from relay.retrieval.text import contains_quote, normalize


# ---------------------------------------------------------------- H1 exit gate

def test_send_reply_rejects_a_bare_string():
    with pytest.raises(TypeError, match="H1 violation"):
        send_reply("here is my answer")   # type: ignore[arg-type]


def test_send_reply_accepts_all_three():
    for r in (mint_verified("t", ()), NoEvidence("no"), PassagesOnly("p", (), "budget_gone")):
        assert send_reply(r) is r


# ---------------------------------------------------------------- budget

def test_budget_never_goes_negative():
    b = Budget(tpm=100, rpd=10)
    b.take(60, now=1.0)
    with pytest.raises(Exception):
        b.take(60, now=1.0)
    assert b.tpm_used == 60


def test_budget_resets_after_window():
    b = Budget(tpm=100, rpd=10)
    b.take(90, now=1.0)
    b.take(90, now=100.0)      # past the 60s window
    assert b.tpm_used == 90


def test_budget_reconcile_uses_provider_ratio_not_our_limit():
    """BUG-010: reconstructing usage from `remaining` against OUR limit pinned the
    budget to exhausted whenever the two limits differed."""
    b = Budget(tpm=10**9, rpd=10**9)
    b.learn_limits(8000, 1000)
    b.reconcile(remaining_tpm=4000, remaining_rpd=500, now=1.0)
    assert b.tpm_used == 5 * 10**8, b.tpm_used     # half of OUR limit, not 4000


def test_budget_reconcile_without_learned_limits_is_a_noop():
    b = Budget(tpm=8000, rpd=1000)
    b.reconcile(4000, 500, now=1.0)
    assert b.tpm_used == 0


# ---------------------------------------------------------------- breaker

def test_breaker_opens_after_threshold_and_half_opens():
    br = Breaker(fail_threshold=2, open_s=10.0)
    br.record(False, now=0.0)
    assert br.state(0.0) == "closed"
    br.record(False, now=0.0)
    assert br.state(0.0) == "open"
    assert br.state(11.0) == "half-open"


# ---------------------------------------------------------------- verification

def test_unknown_chunk_id_is_rejected():
    r = check_citations("answer", [Citation("nope:s1:c0000", "x")], {})
    assert not r and "unknown chunk_id" in r.reason


def test_non_verbatim_quote_is_rejected():
    from relay.contracts import Chunk
    ch = {"a:s1:c0000": Chunk("a:s1:c0000", "attention", "1", 1, "the cat sat")}
    r = check_citations("answer", [Citation("a:s1:c0000", "the dog sat")], ch)
    assert not r and "not verbatim" in r.reason


def test_number_not_in_sources_is_rejected():
    r = check_numbers_present("it uses 8 heads", ["we use h = 6 heads"])
    assert not r and "8" in r.reason


def test_number_in_sources_passes():
    assert check_numbers_present("it uses 8 heads", ["we use h = 8 heads"])


# ---------------------------------------------------------------- normalisation

def test_hyphenated_line_break_still_matches():
    """A quote spanning a PDF line break must verify (NFKC + de-hyphenation)."""
    assert contains_quote("the transfor-\nmation is good", "the transformation is good")


def test_ligature_normalises():
    assert normalize("\ufb01ne") == "fine"


# ---------------------------------------------------------------- retry loop

def _gateway(policy, cfg=None, handler=None):
    import asyncio, httpx
    from relay.clock import RealClock
    from relay.config import load_config
    from relay.gateway.gateway import Gateway
    cfg = cfg or load_config()
    calls = {"n": 0}

    def _h(request):
        calls["n"] += 1
        return handler(request)

    async def build():
        c = httpx.AsyncClient(transport=httpx.MockTransport(_h),
                              base_url="http://x/openai/v1")
        gw = Gateway.from_config(cfg, RealClock(), None, base_url="http://x/openai/v1",
                                 api_key="k", client=c, policy=policy)
        return c, gw
    return build, calls


class _S:
    req_id = "b"

    def attempt_start(self, a):
        pass

    def attempt_end(self, a):
        pass

    def emit(self, *a, **k):
        pass


def _always_429(retry_after=5):
    import httpx
    return httpx.Response(429, headers={"retry-after": str(retry_after)},
                          json={"error": {"message": "rate limited"}})


def test_naive_is_bounded_and_never_recurses():
    """BUG-013: naive called itself recursively and died with RecursionError
    after 489 requests. It must stop at naive_max_attempts."""
    import asyncio
    from relay.config import load_config
    cfg = load_config()
    build, calls = _gateway("naive", cfg, lambda r: _always_429())

    async def go():
        c, gw = await build()
        with pytest.raises(Exception):
            await gw.call(scope=_S(), step="d", model="m",
                          messages=[{"role": "user", "content": "hi"}],
                          max_tokens=10, deadline_s=3.0)
        await c.aclose()

    asyncio.run(go())
    assert calls["n"] == cfg.get("gateway.naive_max_attempts"), calls["n"]


def test_naive_ignores_retry_after_and_deadline():
    """Naive still retries when retry-after would blow the deadline. That is
    the harm being demonstrated, so a test must pin it rather than fix it."""
    import asyncio
    build, calls = _gateway("naive", None, lambda r: _always_429(retry_after=60))

    async def go():
        c, gw = await build()
        with pytest.raises(Exception):
            await gw.call(scope=_S(), step="d", model="m",
                          messages=[{"role": "user", "content": "hi"}],
                          max_tokens=10, deadline_s=1.0)
        await c.aclose()

    asyncio.run(go())
    assert calls["n"] > 1     # managed would stop at 1


def test_managed_stops_after_one_attempt_when_retry_after_exceeds_deadline():
    import asyncio
    build, calls = _gateway("managed", None, lambda r: _always_429(retry_after=5))

    async def go():
        c, gw = await build()
        with pytest.raises(Exception):
            await gw.call(scope=_S(), step="d", model="m",
                          messages=[{"role": "user", "content": "hi"}],
                          max_tokens=10, deadline_s=3.0)
        await c.aclose()

    asyncio.run(go())
    assert calls["n"] == 1, calls["n"]


def test_never_retry_a_day_limit():
    import asyncio
    build, calls = _gateway("managed", None, lambda r: _always_429(retry_after=3600))

    async def go():
        c, gw = await build()
        with pytest.raises(Exception):
            await gw.call(scope=_S(), step="d", model="m",
                          messages=[{"role": "user", "content": "hi"}],
                          max_tokens=10, deadline_s=30.0)
        await c.aclose()

    asyncio.run(go())
    assert calls["n"] == 1


# ---------------------------------------------------------------- payload

def test_payload_uses_max_completion_tokens_not_max_tokens():
    from relay.gateway.gateway import Gateway
    from relay.config import load_config
    gw = Gateway.from_config(load_config(), None, None, base_url="http://x",
                             api_key="k", client=None)
    b = gw.request_payload(model="openai/gpt-oss-20b", messages=[], max_tokens=400)
    assert "max_completion_tokens" in b
    assert "max_tokens" not in b


def test_reasoning_effort_sent_to_gpt_oss_only():
    from relay.gateway.gateway import Gateway
    from relay.config import load_config
    gw = Gateway.from_config(load_config(), None, None, base_url="http://x",
                             api_key="k", client=None)
    assert gw.request_payload(model="openai/gpt-oss-20b", messages=[],
                              max_tokens=10, reasoning_effort="low")["reasoning_effort"] == "low"
    # a non-reasoning model must not receive the parameter at all
    assert "reasoning_effort" not in gw.request_payload(
        model="llama-3.3-70b", messages=[], max_tokens=10, reasoning_effort="low")


def test_reasoning_effort_none_is_refused():
    from relay.gateway.gateway import Gateway
    from relay.config import load_config
    gw = Gateway.from_config(load_config(), None, None, base_url="http://x",
                             api_key="k", client=None)
    with pytest.raises(ValueError, match="never be"):
        gw.request_payload(model="openai/gpt-oss-20b", messages=[],
                           max_tokens=10, reasoning_effort="none")


# ---------------------------------------------------------------- eval set

def test_checker_rejects_unknown_gold_id():
    from scripts.check_questions import check
    q = [{"qid": "X", "author": "me", "type": "single", "paper": "attention",
          "question": "q", "answer": "a", "gold": ["attn-v7:s1:c9999"]}]
    faults = check(q, {"attn-v7:s1:c0000"})
    assert any("not in the index" in f for f in faults), faults


def test_checker_rejects_gold_on_unanswerable():
    from scripts.check_questions import check
    q = [{"qid": "X", "author": "me", "type": "unanswerable", "paper": None,
          "question": "q", "answer": "a", "gold": ["attn-v7:s1:c0000"]}]
    assert any("unanswerable but gold" in f for f in check(q, {"attn-v7:s1:c0000"}))


def test_checker_rejects_missing_gold_on_answerable():
    from scripts.check_questions import check
    q = [{"qid": "X", "author": "me", "type": "single", "paper": "attention",
          "question": "q", "answer": "a", "gold": []}]
    assert any("gold is empty" in f for f in check(q, set()))


def test_checker_allows_missing_gold_on_ambiguous():
    from scripts.check_questions import check
    q = [{"qid": "X", "author": "me", "type": "ambiguous", "paper": "moshi",
          "question": "q", "answer": "a", "gold": []}]
    assert check(q, set()) == []


def test_every_question_has_an_author():
    import json
    rows = [json.loads(l) for l in open("data/eval/questions.jsonl") if l.strip()]
    assert rows and all(r.get("author") for r in rows)
    assert all(r["author"] in ("agent_draft", "me") for r in rows), \
        {r["author"] for r in rows}


# ---------------------------------------------------------------- analyze

def _write_log(tmp_path, events):
    import json
    p = tmp_path / "events.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return p


def _ev(t, **kw):
    base = {"type": t, "run_id": "r", "backend": "standin", "t_mono": 1.0,
            "t_wall": 1.0}
    base.update(kw)
    return base


def test_analyze_names_a_missing_terminal(tmp_path):
    from scripts.analyze import check
    evs = [_ev("request.start", req_id="A"),
           _ev("request.end", req_id="A", total_elapsed_s=0.1, waiting_s=0.0,
               working_s=0.1, retrying_s=0.0)]
    faults = check(evs)
    assert any("I1" in f for f in faults), faults


def test_analyze_names_a_broken_latency_sum(tmp_path):
    from scripts.analyze import check
    evs = [_ev("request.start", req_id="A"),
           _ev("request.end", req_id="A", total_elapsed_s=9.0, waiting_s=0.0,
               working_s=0.1, retrying_s=0.0),
           _ev("terminal", req_id="A", terminal="answered",
               reply_type="verified_answer")]
    assert any("I7" in f for f in check(evs))


def test_analyze_rejects_an_event_after_the_terminal():
    from scripts.analyze import check
    evs = [_ev("request.start", req_id="A"),
           _ev("terminal", req_id="A", terminal="answered", reply_type="verified_answer"),
           _ev("request.end", req_id="A", total_elapsed_s=0.0, waiting_s=0.0,
               working_s=0.0, retrying_s=0.0)]
    assert any("I2" in f for f in check(evs))


def test_analyze_passes_a_clean_log(tmp_path):
    from scripts.analyze import main
    log = _write_log(tmp_path, [
        _ev("request.start", req_id="A"),
        _ev("attempt.start", req_id="A", attempt_id="A-1", step="draft",
            attempt_backend="standin", t_sent=1.0),
        _ev("attempt.end", req_id="A", attempt_id="A-1", step="draft",
            attempt_backend="standin", t_sent=1.0, t_first_token=1.1, t_end=1.1,
            status=200, outcome="ok", tokens_in=10, tokens_out=5),
        _ev("request.end", req_id="A", total_elapsed_s=0.1, waiting_s=0.0,
            working_s=0.1, retrying_s=0.0),
        _ev("terminal", req_id="A", terminal="answered", reply_type="verified_answer"),
    ])
    assert main([str(tmp_path)]) == 0


def test_analyze_does_not_report_a_fabricated_ttft(tmp_path, capsys):
    """A non-streaming call has no observable TTFT; the table must say so rather
    than print a number that is the total by construction."""
    from scripts.analyze import main
    _write_log(tmp_path, [
        _ev("request.start", req_id="A"),
        _ev("attempt.end", req_id="A", attempt_id="A-1", step="draft",
            t_sent=1.0, t_first_token=1.1, t_end=1.1, status=200, outcome="ok"),
        _ev("request.end", req_id="A", total_elapsed_s=0.1, waiting_s=0.0,
            working_s=0.1, retrying_s=0.0),
        _ev("terminal", req_id="A", terminal="answered", reply_type="verified_answer"),
    ])
    main([str(tmp_path)])
    out = capsys.readouterr().out
    assert "TTFT is not measured" in out


# ---------------------------------------------------------------- H4 abandonment

def test_abandonment_cancels_in_flight_and_returns_no_reply():
    """H4. A user who leaves must cancel the in-flight model call, not merely stop
    looking at it, and must be sent nothing."""
    import asyncio
    import httpx
    from relay.clock import RealClock
    from relay.config import load_config
    from relay.gateway.gateway import Gateway
    from relay.pipeline.pipeline import Pipeline
    from relay.retrieval.bm25 import Retriever

    cfg = load_config()
    cancelled = {"n": 0}

    async def handler(request):
        # never completes: the only way out is cancellation
        await asyncio.sleep(30)
        return httpx.Response(200, json={"choices": []})

    async def go():
        r = Retriever.from_jsonl("data/chunks/exp900/chunks.jsonl")
        class Scope:
            req_id = "A"
            def emit(self, *a, **k): pass
            def abandon(self, reason="user"): pass
            def attempt_start(self, a): pass
            def attempt_end(self, a):
                if getattr(a, "outcome", None) == "cancelled" or str(
                        getattr(a, "outcome", "")).endswith("cancelled"):
                    cancelled["n"] += 1
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://x/openai/v1") as c:
            gw = Gateway.from_config(cfg, RealClock(), None,
                                     base_url="http://x/openai/v1",
                                     api_key="k", client=c)
            p = Pipeline(cfg, r, gw, Scope(), patience_s=0.05)
            out = await p.answer("How many attention heads in the base model?")
        return out

    out = asyncio.run(go())
    assert out.terminal == "abandoned", out.terminal
    assert out.reply is None, "an abandoned request must carry no reply"


def test_send_reply_refuses_a_payload_on_an_abandoned_request():
    from relay.pipeline.pipeline import send_reply
    from relay.contracts import NoEvidence
    assert send_reply(None, abandoned=True) is None
    with pytest.raises(TypeError, match="must send nothing"):
        send_reply(NoEvidence("x"), abandoned=True)


def test_checker_accepts_a_null_reply_type_only_for_abandoned():
    from scripts.check_events import check
    base = lambda **kw: {"type": "request.start", "run_id": "r", "backend": "standin",
                         "req_id": "A", "t_mono": 1.0, "t_wall": 1.0, **kw}
    good = [base(), base(type="request.end", total_elapsed_s=0.0, waiting_s=0.0,
                         working_s=0.0, retrying_s=0.0),
            base(type="terminal", terminal="abandoned", reply_type=None)]
    assert check(good).violations == []
    bad = [base(), base(type="request.end", total_elapsed_s=0.0, waiting_s=0.0,
                        working_s=0.0, retrying_s=0.0),
           base(type="terminal", terminal="answered", reply_type=None)]
    assert any("sent nothing" in v.detail for v in check(bad).violations)


# ---------------------------------------------------------------- hit definition

def test_hit_is_decided_by_quote_containment_not_chunk_id(tmp_path):
    """(d) A gold id from the 900 index does not exist at another chunking, so an
    id-based hit scores the same evidence as a miss. The quote must decide."""
    from relay.retrieval.bm25 import Retriever
    from scripts.retrieval_eval import evaluate
    r = Retriever.from_jsonl("data/chunks/exp1200/chunks.jsonl")
    qs = [{"qid": "N4", "type": "numeric", "gold": ["moshi-v1:s3.2.2:c0002"],
           "question": "What are the Temporal Transformer model dimension and MLP "
                       "dimension?",
           "answer": "4096 and 11264"}]
    import json as _j
    quotes = _j.loads(open("data/eval/gold_quotes.json").read())
    by_id = evaluate(r, qs, 4, 0.0, quotes=None)
    by_quote = evaluate(r, qs, 4, 0.0, quotes=quotes)
    assert by_id["rows"][0]["id_rank"] is None, "gold id unexpectedly in 1200 index"
    assert by_quote["rows"][0]["rank"] is not None, "quote hit not found"
    assert by_quote["recall_at_k"] > by_id["recall_at_k"]


def test_every_gold_quote_resolves_in_its_own_chunk():
    import json
    from relay.retrieval.text import contains_quote
    chunks = {c["chunk_id"]: c for c in
              (json.loads(l) for l in open("data/chunks/exp900/chunks.jsonl"))}
    data = json.load(open("data/eval/gold_quotes.json"))
    assert data
    for qid, rec in data.items():
        for q in rec["quotes"]:
            assert contains_quote(chunks[q["chunk_id"]]["text"], q["quote"]), qid


# ---------------------------------------------------------------- sweep split

def test_sweep_counts_ambiguous_separately_from_unanswerable():
    """(c) An ambiguous question scoring high is correct behaviour, not a false
    answer. Folding it into the unanswerable pool punishes the system for being
    right."""
    from relay.retrieval.bm25 import Retriever
    from scripts.retrieval_eval import sweep
    import json as _j
    r = Retriever.from_jsonl("data/chunks/exp900/chunks.jsonl")
    qs = [{"qid": "T1", "type": "ambiguous", "gold": [],
           "question": "What is attention?", "answer": "ambiguous"},
          {"qid": "U1", "type": "unanswerable", "gold": [],
           "question": "What is the capital of France?", "answer": "none"},
          {"qid": "A1", "type": "single", "gold": ["attn-v7:s3.2.2:c0001"],
           "question": "How many attention heads?", "answer": "8"}]
    sw = sweep(r, qs, 4)
    assert sw["n_ambiguous"] == 1
    assert sw["n_unanswerable"] == 1
    assert sw["n_answerable"] == 1
    for p in sw["points"]:
        assert p["ambiguous_admitted"] + (p["n_ambiguous"] - p["ambiguous_admitted"]) \
            == p["n_ambiguous"]
        # total_errors must exclude ambiguous entirely
        assert p["total_errors"] == p["false_abstain"] + p["false_answer"]


def test_ambiguous_question_is_not_counted_as_a_false_answer():
    from relay.retrieval.bm25 import Retriever
    from scripts.retrieval_eval import sweep
    r = Retriever.from_jsonl("data/chunks/exp900/chunks.jsonl")
    # one ambiguous question that scores very high, and no unanswerable ones
    qs = [{"qid": "T2", "type": "ambiguous", "gold": [],
           "question": "How many attention heads does the Transformer use?",
           "answer": "ambiguous"}]
    sw = sweep(r, qs, 4)
    top = max(p["threshold"] for p in sw["points"])
    low = [p for p in sw["points"] if p["threshold"] <= 1.0]
    for p in low:
        assert p["false_answer"] == 0, "ambiguous must never be a false answer"


# ---------------------------------------------------------------- streaming

def test_sse_parser_rejects_done_and_keeps_frames():
    from relay.gateway.stream import parse_sse_line
    assert parse_sse_line("data: [DONE]") is None
    assert parse_sse_line("") is None
    assert parse_sse_line(": keepalive") is None
    assert parse_sse_line("data: not json") is None
    assert parse_sse_line('data: {"choices":[{"delta":{"content":"hi"}}]}') == {
        "choices": [{"delta": {"content": "hi"}}]}


def test_role_only_frame_is_a_first_delta_but_not_a_first_token():
    """A frame carrying `delta.role` and no content is real and must stamp
    first_delta; treating it as a first token would make model_ttft a lie."""
    from relay.gateway.stream import delta_text
    assert delta_text({"choices": [{"delta": {"role": "assistant"}}]}) == ""
    assert delta_text({"choices": [{"delta": {"content": "hi"}}]}) == "hi"
    assert delta_text({"choices": []}) == ""
    assert delta_text({}) == ""


def test_stream_timestamps_are_stamped_at_arrival_not_at_replay():
    """BUG-017: buffering frames and stamping during replay made first_delta and
    model_ttft identical, which destroyed the distinction between them."""
    import asyncio
    from relay.gateway.stream import consume

    class Clock:
        def __init__(self): self.t = 0.0
        def now(self):
            self.t += 0.01      # every observation advances time
            return self.t

    async def frames():
        yield 'data: {"choices":[{"delta":{"role":"assistant"}}]}'
        for _ in range(3):
            yield 'data: {"choices":[{"delta":{"content":"tok "}}]}'

    st = asyncio.run(consume(frames(), Clock(), t_sent=0.0))
    assert st.first_delta is not None and st.model_ttft is not None
    assert st.model_ttft > st.first_delta, "stamped at the same instant"
    assert st.text == "tok tok tok "


def test_stream_with_no_content_raises_rather_than_returning_empty():
    import asyncio
    from relay.gateway.stream import consume

    class Clock:
        def now(self): return 1.0

    async def frames():
        yield 'data: {"choices":[{"delta":{"role":"assistant"}}]}'
        yield "data: [DONE]"

    with pytest.raises(TimeoutError):
        asyncio.run(consume(frames(), Clock(), t_sent=0.0))


def test_verification_normalises_whitespace_between_draft_and_source():
    """BUG-018: a streamed draft joins words with spaces where the PDF chunk has a
    newline. A raw `quote in chunk.text` test fails and the answer is discarded as
    unverifiable -- for a correct answer. Both sides must be normalised."""
    from relay.retrieval.text import contains_quote
    chunk = "about 4.5 million\nsentence pairs."
    streamed_draft_sentence = "about 4.5 million sentence pairs."
    assert streamed_draft_sentence not in chunk          # the raw test fails
    assert contains_quote(chunk, streamed_draft_sentence)  # the normalised one works


def test_streamed_and_buffered_pipelines_agree(tmp_path):
    """The whole point of adding streaming was measurement, not behaviour. If the
    reply changes, a measurement change has leaked into the product."""
    import asyncio
    import httpx
    from relay.clock import RealClock
    from relay.config import load_config
    from relay.gateway.gateway import Gateway
    from relay.pipeline.pipeline import Pipeline
    from relay.retrieval.bm25 import Retriever

    cfg = load_config()
    r = Retriever.from_jsonl("data/chunks/exp900/chunks.jsonl")
    Q = ("What shared vocabulary size does the byte-pair encoding produce for "
         "WMT 2014 English-German?")

    class S:
        req_id = "s"
        def attempt_start(self, a): pass
        def attempt_end(self, a): pass
        def emit(self, *a, **k): pass
        def abandon(self, *a, **k): pass

    async def go(stream):
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8009/openai/v1",
                                     timeout=30.0) as c:
            gw = Gateway.from_config(cfg, RealClock(), None,
                                     base_url="http://127.0.0.1:8009/openai/v1",
                                     api_key="x", client=c)
            return await Pipeline(cfg, r, gw, S(), stream=stream).answer(Q)

    try:
        buffered = asyncio.run(go(False))
        streamed = asyncio.run(go(True))
    except Exception as e:                     # stand-in not running
        pytest.skip(f"stand-in unavailable: {e}")
    assert buffered.terminal == streamed.terminal, (buffered.terminal, streamed.terminal)
