"""P1 probe. Raw httpx, no gateway, no retries. A failure is data.

Safety properties, in order of importance:
  * ``--dry-run`` is the default and performs ZERO network I/O. It prints the plan
    and the estimated spend, then stops.
  * Real sending requires BOTH ``--go`` and ``--max-tokens-total N``. The ceiling is
    enforced by reserve-before-send / settle-after, so it cannot be overshot by a
    request that turns out to cost more than estimated.
  * No retries, ever. A 429 is the finding, not an obstacle.
  * The Authorization header is never logged, and the key value is scrubbed from
    every artefact as a second defence.
  * Every response header is logged (not just ``x-ratelimit-*``), plus the full
    status and body for every non-200.
  * Spend is appended to ``docs/TOKEN_LEDGER.md`` automatically -- only on ``--go``.

Modes run in the supervisor's order::

    python -m scripts.probe --dry-run
    python -m scripts.probe --go --max-tokens-total 60000 --timeout 30 \\
        --mode models --mode single --mode stream

``rpd`` is excluded from ``--mode all`` because it can burn a whole day's budget.
Run it deliberately: ``--mode rpd --go ...``.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Final, Optional

import httpx

from relay.config import Config, ConfigError, load_config
from relay.ratelimit_headers import parse_rl_headers

PROBE_VERSION: Final = 1
LEDGER_PATH: Final = Path("docs/TOKEN_LEDGER.md")
RUNS_DIR: Final = Path("runs")
REDACTED: Final = "<redacted>"
#: Cap on any single logged body, so a runaway response cannot fill the disk.
MAX_BODY_LOG: Final = 64_000

MODE_ORDER: Final = ["models", "single", "stream", "reasoning", "bigctx",
                     "cache", "burst", "buckets", "rpd"]

#: Which open question each mode is expected to answer. Anything not answered is
#: printed as NOT ANSWERED -- we never mark a question answered without a log line.
EXPECTED_QUESTIONS: Final[dict[str, list[str]]] = {
    "models": ["Q-01"],
    "single": ["Q-02", "Q-05", "Q-06", "Q-11"],
    "stream": ["Q-15"],
    "reasoning": ["Q-07"],
    "bigctx": ["Q-12"],
    "cache": ["Q-13", "Q-14"],
    "burst": ["Q-08", "Q-10", "Q-11"],
    "buckets": ["Q-03"],
    "rpd": ["Q-04", "Q-09"],
}

#: Candidate parameter names for reasoning effort. UNVERIFIED: we do not know which
#: one this API accepts, so we try them and record the verbatim rejection instead of
#: asserting an answer. Confirm in the API reference for "chat completions" params.
REASONING_PARAM_CANDIDATES: Final = ("reasoning_effort", "reasoning", "reasoning.effort")


# --------------------------------------------------------------------------- utils

def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def now_mono() -> float:
    return time.monotonic()


def scrub(text: str, secret: Optional[str]) -> str:
    """Last line of defence: remove the key value from anything we write."""
    if secret and secret in text:
        return text.replace(secret, REDACTED)
    return text


def est_tokens(text: str) -> int:
    """Rough prompt-token estimate for the ceiling.

    UNVERIFIED: ~4 chars/token is a common English average. We divide by 3 to
    deliberately OVER-estimate, because the ceiling is a safety limit and must
    never be undershot. The real number replaces this once ``usage`` is observed.
    """
    return max(1, math.ceil(len(text) / 3))


def classify_day_429(r: Result, min_retry_after_s: Optional[float] = None) -> tuple[bool, str]:
    """Is this 429 a DAY limit? Returns (verdict, why).

    Three signals, in order of reliability, and the reason is recorded so the
    classification is auditable rather than asserted:
      1. `remaining-rpd <= 0` -- the daily request count is provably exhausted.
      2. the body says so ("per day" / "daily") -- the provider's own words.
      3. `retry-after >= min_retry_after_s`, only if that threshold is configured.
    An arbitrary `retry-after > 3600` test is NOT used: 3600.0 is a plausible
    exact value for a day limit, and a `>` there misclassifies it (found by a test).
    """
    rl = r.rl or {}
    rem_rpd = rl.get("remaining_rpd")
    if rem_rpd is not None and rem_rpd <= 0:
        return True, "remaining_rpd<=0"
    body = (r.body or "").lower()
    for token in ("per day", "daily", "day limit", "per-day"):
        if token in body:
            return True, f"body contains {token!r}"
    ra = rl.get("retry_after_s")
    if min_retry_after_s is not None and ra is not None and ra >= min_retry_after_s:
        return True, f"retry_after={ra}s >= configured {min_retry_after_s}s"
    if ra is not None:
        return False, f"retry_after={ra}s, no day evidence"
    return False, "no day evidence and no retry_after"


def _which_limit(r: Result) -> str:
    """Classify a 429 by the remaining values, not by the wording of the body.

    UNVERIFIED heuristic, and deliberately reported as a classification with its
    inputs attached: if requests remain but tokens do not, the token bucket is the
    one that tripped.
    """
    rem_rpd = (r.rl or {}).get("remaining_rpd")
    rem_tpm = (r.rl or {}).get("remaining_tpm")
    if rem_rpd is not None and rem_rpd <= 0:
        return "rpd"
    if rem_tpm is not None and rem_tpm <= 0:
        return "tpd_or_tpm"
    body = (r.body or "").lower()
    if "token" in body and "request" not in body:
        return "tpd_or_tpm"
    if "request" in body:
        return "rpd"
    return "unclassified"


def truncate(text: str, limit: int = MAX_BODY_LOG) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text) - limit} more chars]"


# --------------------------------------------------------------------------- ledger

_LEDGER_RE: Final = re.compile(
    r"<!-- LEDGER:DATA -->\s*```json\s*(\{.*?\})\s*```\s*<!-- /LEDGER:DATA -->",
    re.DOTALL,
)


@dataclass
class DayEntry:
    date: str
    plan: int                       # tokens we allow ourselves today
    cap_tpd_unverified: int         # the docs-table TPD, until the probe confirms it
    spent: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.plan - self.spent)


class Ledger:
    """The token plan, stored as a machine-readable block inside TOKEN_LEDGER.md.

    One file, two audiences: the fenced JSON block is the source of truth for the
    runner, the markdown tables stay readable for humans. Parsing prose tables
    would be fragile; a fenced block cannot drift.
    """

    def __init__(self, path: Path = LEDGER_PATH):
        self.path = path
        self._lock = threading.Lock()
        self.days: list[DayEntry] = []
        self.rows: list[dict] = []
        if path.is_file():
            self._read()

    def _read(self) -> None:
        text = self.path.read_text(encoding="utf-8")
        m = _LEDGER_RE.search(text)
        if not m:
            self.days = []
            return
        data = json.loads(m.group(1))
        self.days = [DayEntry(**d) for d in data.get("days", [])]
        self.rows = list(data.get("runs", []))

    def _render(self) -> str:
        payload = {
            "probe_version": PROBE_VERSION,
            "days": [asdict(d) for d in self.days],
            "runs": self.rows,
        }
        return json.dumps(payload, indent=2, sort_keys=False)

    def save(self, path: Optional[Path] = None) -> None:
        target = path or self.path
        text = target.read_text(encoding="utf-8") if target.is_file() else ""
        block = ("<!-- LEDGER:DATA -->\n```json\n"
                 f"{self._render()}\n```\n<!-- /LEDGER:DATA -->")
        if _LEDGER_RE.search(text):
            text = _LEDGER_RE.sub(block, text, count=1)
        else:
            text = text.rstrip() + "\n\n" + block + "\n"
        target.write_text(text, encoding="utf-8")

    def today(self, plan: Optional[int] = None,
              cap: Optional[int] = None) -> DayEntry:
        d = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for entry in self.days:
            if entry.date == d:
                if plan is not None:
                    entry.plan = plan
                return entry
        entry = DayEntry(date=d, plan=plan or 0,
                         cap_tpd_unverified=cap or 200_000)
        self.days.append(entry)
        return entry

    def spend(self, tokens: int, row: Optional[dict] = None) -> None:
        with self._lock:
            self.today().spent += max(0, tokens)
            if row:
                self.rows.append(row)


# ---------------------------------------------------------------------- the ceiling

class CeilingReached(RuntimeError):
    """Sending would exceed the hard budget. The probe aborts; it never truncates."""


class TokenCeiling:
    """Hard token ceiling with reserve-before-send semantics.

    ``reserve`` is synchronous and lock-guarded: the check and the take happen with
    no await and no other coroutine/thread able to interleave (rule 9's spirit,
    applied to threads as well because ``burst`` uses one).
    """

    def __init__(self, cap: int, day_remaining: int):
        self.cap = cap
        self.day_remaining = day_remaining
        self.reserved = 0
        self.settled = 0
        self._lock = threading.Lock()

    @property
    def effective_cap(self) -> int:
        return min(self.cap, self.day_remaining)

    @property
    def spent(self) -> int:
        return self.settled

    def reserve(self, est: int) -> None:
        with self._lock:
            if self.settled + self.reserved + est > self.effective_cap:
                raise CeilingReached(
                    f"reserving {est} would exceed the cap: settled={self.settled} "
                    f"reserved={self.reserved} cap={self.effective_cap} "
                    f"(hard cap {self.cap}, day remaining {self.day_remaining})"
                )
            self.reserved += est

    def settle(self, est: int, actual: Optional[int]) -> int:
        """Release the reservation and charge the real cost (or the estimate)."""
        charge = est if actual is None else actual
        with self._lock:
            self.reserved -= est
            self.settled += charge
        return charge


# --------------------------------------------------------------------------- result

@dataclass
class Result:
    mode: str
    label: str
    model: str
    status: Optional[int] = None
    headers: dict = field(default_factory=dict)
    rl: dict = field(default_factory=dict)
    body: str = ""
    usage: Optional[dict] = None
    t_sent: float = 0.0
    t_first_byte: Optional[float] = None
    t_first_token: Optional[float] = None
    t_end: Optional[float] = None
    gaps: list[float] = field(default_factory=list)
    raw_lines: list[str] = field(default_factory=list)
    est_tokens: int = 0
    charged: int = 0
    error: Optional[str] = None
    dry_run: bool = False
    refused: bool = False
    reason: str = ""

    @property
    def ttft_s(self) -> Optional[float]:
        if self.t_first_token is None:
            return None
        return self.t_first_token - self.t_sent

    @property
    def total_s(self) -> Optional[float]:
        if self.t_end is None:
            return None
        return self.t_end - self.t_sent

    def to_record(self) -> dict:
        d = asdict(self)
        d["ttft_s"] = self.ttft_s
        d["total_s"] = self.total_s
        return d


# ------------------------------------------------------------------------ recorder

class Recorder:
    """Writes one JSONL per mode. Thread-safe because ``burst`` uses threads."""

    def __init__(self, run_dir: Path, secret: Optional[str], dry_run: bool):
        self.run_dir = run_dir
        self.secret = secret
        self.dry_run = dry_run
        self._lock = threading.Lock()
        (run_dir / "raw").mkdir(parents=True, exist_ok=True)

    def write(self, mode: str, record: dict) -> None:
        line = scrub(json.dumps(record, default=str), self.secret)
        with self._lock:
            with open(self.run_dir / f"{mode}.jsonl", "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def raw(self, name: str, content: str) -> Path:
        p = self.run_dir / "raw" / name
        p.write_text(scrub(content, self.secret), encoding="utf-8")
        return p


# ----------------------------------------------------------------------------- probe

class Probe:
    def __init__(
        self,
        *,
        cfg: Config,
        base_url: str,
        api_key: Optional[str],
        ceiling: TokenCeiling,
        recorder: Recorder,
        dry_run: bool,
        timeout: Optional[float],
        models: dict[str, str],
        sleeper: Callable[[float], None] = time.sleep,
        client: Optional[httpx.Client] = None,
    ):
        self.cfg = cfg
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.ceiling = ceiling
        self.rec = recorder
        self.dry_run = dry_run
        self.timeout = timeout
        self.models = models
        self.sleep = sleeper
        self.plan_lines: list[str] = []
        self.evidence: list[tuple[str, str, str]] = []   # (Q, claim, artifact)
        self._client = client
        self._lock = threading.Lock()

    # -- client / headers ---------------------------------------------------
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                # NOTE: no `transport=HTTPTransport(retries=...)` -- retries are the
                # gateway's job, and inside the probe a failure is data.
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _loggable_request_headers(self) -> dict[str, str]:
        """Never derive this from self.headers: the key must not reach a file."""
        return {"authorization": REDACTED, "content-type": "application/json"}

    # -- evidence -----------------------------------------------------------
    def note(self, q: str, claim: str, artifact: str) -> None:
        with self._lock:
            self.evidence.append((q, claim, artifact))

    # -- one request --------------------------------------------------------
    def chat(
        self,
        *,
        mode: str,
        label: str,
        model: str,
        messages: list[dict],
        max_tokens: int,
        stream: bool = False,
        extra: Optional[dict] = None,
        record: bool = True,
    ) -> Result:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0,
            "stream": stream,
        }
        if extra:
            body.update(extra)

        prompt = "".join(m.get("content", "") for m in messages)
        est = est_tokens(prompt) + max_tokens
        res = Result(mode=mode, label=label, model=model, est_tokens=est,
                     dry_run=self.dry_run)

        if self.dry_run:
            try:
                self.ceiling.reserve(est)
            except CeilingReached as e:
                res.refused = True
                res.reason = str(e)
                self.plan_lines.append(
                    f"  REFUSED {mode}/{label}: {e}")
                return res
            self.ceiling.settle(est, None)
            self.plan_lines.append(
                f"  {mode:<9} {label:<22} model={model:<22} "
                f"max_tokens={max_tokens:<5} est≈{est} tokens"
                + ("  [stream]" if stream else ""))
            return res

        self.ceiling.reserve(est)          # raises -> the whole probe aborts
        charge = est
        try:
            if stream:
                res = self._send_stream(res, body)
            else:
                res = self._send_plain(res, body)
        finally:
            charge = self.ceiling.settle(est, (res.usage or {}).get("total_tokens"))
            res.charged = charge
        if record:
            self.rec.write(mode, res.to_record())
        return res

    def _send_plain(self, res: Result, body: dict) -> Result:
        res.t_sent = now_mono()
        try:
            r = self.client.post("/chat/completions", json=body,
                                 headers=self.headers)
            res.t_first_byte = now_mono()
            text = r.text
        except httpx.HTTPError as e:
            res.t_end = now_mono()
            res.error = f"{type(e).__name__}: {e}"
            res.body = ""
            return res
        res.t_end = now_mono()
        res.status = r.status_code
        res.headers = dict(r.headers)          # ALL headers, not just x-ratelimit-*
        res.rl = parse_rl_headers(r.headers)
        res.body = truncate(scrub(text, self.api_key))
        if r.status_code == 200:
            try:
                payload = r.json()
                res.usage = payload.get("usage")
            except json.JSONDecodeError as e:
                res.error = f"invalid JSON on 200: {e}"
        return res

    def _send_stream(self, res: Result, body: dict) -> Result:
        """Consume SSE line by line, recording arrival time of every line.

        We do not assume the chunk shape (Q-15). Raw lines are stored verbatim and
        parsing is best-effort, so a wrong guess shows up as unparsed lines in the
        artefact rather than as a silent zero.
        """
        res.t_sent = now_mono()
        prev = res.t_sent
        try:
            with self.client.stream("POST", "/chat/completions", json=body,
                                    headers=self.headers) as r:
                res.status = r.status_code
                res.headers = dict(r.headers)
                res.rl = parse_rl_headers(r.headers)
                for line in r.iter_lines():
                    t = now_mono()
                    if res.t_first_byte is None:
                        res.t_first_byte = t
                    if len(res.raw_lines) < 200:
                        res.raw_lines.append(line)
                    if line.startswith("data:"):
                        payload = line[5:].strip()
                        if payload and payload != "[DONE]":
                            if res.t_first_token is None:
                                res.t_first_token = t
                            res.gaps.append(round(t - prev, 6))
                            prev = t
                            try:
                                chunk = json.loads(payload)
                            except json.JSONDecodeError:
                                res.error = "unparseable SSE data line"
                                continue
                            if chunk.get("usage"):
                                res.usage = chunk["usage"]
        except httpx.HTTPError as e:
            res.t_end = now_mono()
            res.error = f"{type(e).__name__}: {e}"
            return res
        res.t_end = now_mono()
        return res

    # -- modes --------------------------------------------------------------
    def mode_models(self) -> list[Result]:
        if self.dry_run:
            self.plan_lines.append("  models    GET /models  (no tokens)")
            return []
        t0 = now_mono()
        try:
            r = self.client.get("/models", headers=self.headers)
        except httpx.HTTPError as e:
            self.rec.write("models", {"error": f"{type(e).__name__}: {e}"})
            return []
        p = self.rec.raw("models.json", scrub(r.text, self.api_key))
        ids = []
        if r.status_code == 200:
            try:
                ids = [m.get("id") for m in r.json().get("data", [])]
            except (json.JSONDecodeError, AttributeError):
                pass
        self.rec.write("models", {
            "status": r.status_code, "headers": dict(r.headers),
            "n_models": len(ids), "model_ids": ids,
            "elapsed_s": now_mono() - t0, "artifact": str(p),
        })
        if ids:
            self.note("Q-01",
                      f"{len(ids)} model ids visible to this key",
                      f"raw/models.json")
        return []

    def _msgs(self, text: str) -> list[dict]:
        return [{"role": "user", "content": text}]

    def mode_single(self, n: int) -> list[Result]:
        out = []
        model = self.models["small"]
        for i in range(n):
            r = self.chat(mode="single", label=f"single-{i}", model=model,
                          messages=self._msgs("Reply with exactly: ok"),
                          max_tokens=self.cfg.get("pipeline.max_tokens.rewrite", 16))
            out.append(r)
            if not self.dry_run and r.status == 200:
                # Q-05: does a per-minute REQUEST header exist at all?
                if r.rl.get("remaining_tpm") is not None:
                    self.note("Q-02",
                              f"limit_tpm={r.rl.get('limit_tpm')} "
                              f"limit_rpd={r.rl.get('limit_rpd')} from live headers",
                              f"runs/{self.rec.run_dir.name}/single.jsonl")
                pm = [k for k in r.headers
                      if k.lower().startswith("x-ratelimit") and "request" in k.lower()]
                self.note("Q-05",
                          f"request-related rate-limit headers present: {sorted(pm)}",
                          f"runs/{self.rec.run_dir.name}/single.jsonl")
                if r.rl.get("retry_after_s") is not None:
                    self.note("Q-11", "retry-after observed on a 200 path",
                              "single.jsonl")
            if r.status in (429,) and not self.dry_run:
                break
            if not self.dry_run:
                self.sleep(0.5)
        if not self.dry_run:
            self._analyse_tpm_reserve(out)
        return out

    def _analyse_tpm_reserve(self, rs: list[Result]) -> None:
        """Q-06: is TPM charged on actual tokens or reserved as max_tokens up front?

        Inference, not proof: between two back-to-back responses the TPM bucket also
        refills, which biases the observed drop *downwards*. A drop close to
        max_tokens is therefore strong evidence for reservation; a drop close to
        usage is weaker evidence for charge-on-actual because refill masks it.
        The verdict is printed with the residuals so it can be judged, not trusted.
        """
        pairs = [a for a in rs if a.usage and a.rl.get("remaining_tpm") is not None]
        if len(pairs) < 2:
            return
        a, b = pairs[-2], pairs[-1]
        drop = a.rl["remaining_tpm"] - b.rl["remaining_tpm"]
        used = b.usage.get("total_tokens") or 0
        cost_vs_actual = abs(drop - used)
        cost_vs_reserve = abs(drop - (b.est_tokens or 0))
        verdict = ("looks like max_tokens reservation" if cost_vs_reserve < cost_vs_actual
                   else "looks like charge-on-actual (refill may mask this)")
        line = (f"Q-06 tpm drop={drop} usage={used} est_with_max_tokens={b.est_tokens} "
                f"-> {verdict}")
        self.note("Q-06", line, "single.jsonl")

    def mode_stream(self) -> list[Result]:
        r = self.chat(mode="stream", label="stream-0", model=self.models["small"],
                      messages=self._msgs("Count from 1 to 20, one number per line."),
                      max_tokens=200, stream=True)
        if not self.dry_run and r.raw_lines:
            first = next((ln for ln in r.raw_lines if ln.strip()), "")
            last = next((ln for ln in reversed(r.raw_lines) if ln.strip()), "")
            self.note("Q-15",
                      f"first SSE line={first[:120]!r} last={last[:60]!r} "
                      f"n_lines={len(r.raw_lines)}",
                      "runs/%s/stream.jsonl" % self.rec.run_dir.name)
        return [r]

    def mode_reasoning(self, param: str, values: list[str]) -> list[Result]:
        """UNVERIFIED parameter name. A rejection is recorded verbatim, not retried."""
        out = []
        base = "A bat is a kind of animal, not a piece of sports equipment. Explain why."
        for v in values:
            r = self.chat(mode="reasoning", label=f"reasoning-{v}",
                          model=self.models["large"],
                          messages=self._msgs(base), max_tokens=300,
                          extra={param: v})
            out.append(r)
            if r.status == 200 and r.usage:
                self.note("Q-07",
                          f"{param}={v}: tokens_out={r.usage.get('completion_tokens')} "
                          f"ttft={r.ttft_s}",
                          "reasoning.jsonl")
            elif r.status is not None and r.status >= 400:
                self.rec.raw(f"reasoning_{v}_error.txt", r.body)
        return out

    def mode_bigctx(self, target_tokens: int) -> list[Result]:
        """One request just over the per-minute token limit.

        The question is narrow: what happens when a SINGLE request exceeds TPM?
        Sizing by a repeat count made that depend on a chars/token guess (a
        400-repeat prompt estimated at 240K -- 4x the day plan). Sizing by a token
        target ties the prompt to the limit read off the limits page, so the request
        is 'just over TPM' by construction. A rejection costs almost nothing; an
        acceptance costs about target_tokens.
        """
        # est_tokens() assumes chars/3, so this builds a prompt whose ESTIMATE
        # lands on the target. Deliberately over-shoots rather than undershoots.
        chars = max(1, target_tokens * 3)
        filler_unit = "The quick brown fox jumps over the lazy dog. "
        prompt = "Summarise in one word.\n" + (filler_unit * (chars // len(filler_unit) + 1))[:chars]
        r = self.chat(mode="bigctx", label=f"bigctx-{target_tokens}", model=self.models["large"],
                      messages=self._msgs(prompt), max_tokens=16)
        if not self.dry_run and r.status is not None:
            verdict = ("accepted despite exceeding TPM" if r.status == 200
                       else "rejected up front (cheap)")
            self.note("Q-12",
                      f"status={r.status} ({verdict}) "
                      f"estimated_prompt_tokens={target_tokens} "
                      f"actual_usage={r.usage} body={r.body[:300]!r}",
                      "bigctx.jsonl")
        return [r]

    def mode_cache(self) -> list[Result]:
        prefix = ("You are a careful assistant. " * 60)
        msg = [{"role": "user", "content": prefix + "\nQuestion: say ok"}]
        a = self.chat(mode="cache", label="cache-1", model=self.models["small"],
                      messages=msg, max_tokens=16)
        self.sleep(1.0) if not self.dry_run else None
        b = self.chat(mode="cache", label="cache-2", model=self.models["small"],
                      messages=msg, max_tokens=16)
        if not self.dry_run and a.usage and b.usage:
            self.note("Q-13",
                      f"usage1={a.usage} usage2={b.usage} "
                      f"(look for a cached-token field)",
                      "cache.jsonl")
            if a.rl.get("remaining_tpm") is not None and b.rl.get("remaining_tpm") is not None:
                self.note("Q-14",
                          f"tpm remaining after 1st={a.rl['remaining_tpm']} "
                          f"after 2nd={b.rl['remaining_tpm']}",
                          "cache.jsonl")
        return [a, b]

    def _parallel(self, mode: str, model: str, n: int, max_tokens: int,
                  prefix: str) -> list[Result]:
        results: list[Optional[Result]] = [None] * n
        barrier = threading.Barrier(n)

        def one(i: int) -> None:
            barrier.wait()          # fire together: we want the burst, not a queue
            results[i] = self.chat(mode=mode, label=f"{prefix}-{i}", model=model,
                                   messages=self._msgs("ok"), max_tokens=max_tokens)

        with ThreadPoolExecutor(max_workers=n) as ex:
            list(ex.map(one, range(n)))
        return [r for r in results if r is not None]

    def mode_burst(self, n: int, tiny: int) -> list[Result]:
        rs = self._parallel("burst", self.models["small"], n, tiny, "burst")
        if self.dry_run:
            return rs
        first_429 = next((i for i, r in enumerate(rs) if r.status == 429), None)
        if first_429 is not None:
            hit = rs[first_429]
            self.rec.raw("burst_first_429.json",
                         json.dumps({"status": hit.status, "headers": hit.headers,
                                     "body": hit.body}, indent=2))
            self.note("Q-10",
                      f"first 429 after {first_429} successes; headers="
                      f"{json.dumps(hit.rl, default=str)[:400]}",
                      "raw/burst_first_429.json")
            self.note("Q-11",
                      f"retry-after={hit.headers.get('retry-after')!r} "
                      f"parsed={hit.rl.get('retry_after_s')}",
                      "raw/burst_first_429.json")
        # refill shape: poll until a success follows the first 429
        if first_429 is not None:
            t429 = rs[first_429].t_end or now_mono()
            for i in range(40):
                self.sleep(1.0)
                probe = self.chat(mode="burst", label=f"refill-{i}",
                                  model=self.models["small"],
                                  messages=self._msgs("ok"), max_tokens=tiny)
                if probe.status == 200:
                    self.note("Q-08",
                              f"next success {round((probe.t_sent - t429), 2)}s after "
                              f"the first 429; remaining_tpm="
                              f"{probe.rl.get('remaining_tpm')}",
                              "burst.jsonl")
                    break
        return rs

    def mode_buckets(self, n: int, tiny: int) -> list[Result]:
        """Exhaust the per-minute limit on model A, then immediately call model B."""
        a = self._parallel("buckets", self.models["small"], n, tiny, "bucket-a")
        hit = any(r.status == 429 for r in a)
        b = self.chat(mode="buckets", label="bucket-b", model=self.models["large"],
                      messages=self._msgs("ok"), max_tokens=tiny)
        if not self.dry_run and hit:
            self.note("Q-03",
                      f"after exhausting small: 429={sum(1 for r in a if r.status == 429)}; "
                      f"large returned status={b.status} "
                      f"remaining_tpm={b.rl.get('remaining_tpm')} "
                      f"-> {'shared' if b.status == 429 else 'separate'} bucket",
                      "buckets.jsonl")
        return a + [b]

    def mode_rpd(self, tiny: int, rpm: int, max_requests: int) -> list[Result]:
        """Tiny calls until a DAY-limit 429 or the ceiling stops us.

        Deliberately last, and excluded from ``--mode all``: it can burn the day.
        """
        out: list[Result] = []
        interval = 60.0 / max(1, rpm)
        for i in range(max_requests):
            r = self.chat(mode="rpd", label=f"rpd-{i}", model=self.models["small"],
                          messages=self._msgs("1"), max_tokens=tiny)
            out.append(r)
            if self.dry_run:
                break
            if r.status == 429:
                self.rec.raw("rpd_first_429.json",
                             json.dumps({"status": r.status, "headers": r.headers,
                                         "body": r.body,
                                         "wall_clock_utc": datetime.now(timezone.utc)
                                         .isoformat()}, indent=2))
                ra = r.rl.get("retry_after_s")
                is_day, why_day = classify_day_429(
                    r, self.cfg.get("gateway.day_429_min_retry_after_s", None))
                # WHICH limit tripped is itself the finding: if TPD goes before
                # RPD, tokens are the binding constraint and the budget model
                # changes. Both remaining values are recorded to decide it.
                which = _which_limit(r)
                self.note("Q-09" if is_day else "Q-04",
                          f"429 after {i + 1} tiny calls; day_limit={is_day} ({why_day}); "
                          f"first limit tripped={which} "
                          f"retry_after={ra}s reset_requests={r.rl.get('reset_rpd_s')} "
                          f"remaining_rpd={r.rl.get('remaining_rpd')} "
                          f"remaining_tpm={r.rl.get('remaining_tpm')} "
                          f"wall={datetime.now(timezone.utc).isoformat()} "
                          f"body={r.body[:200]!r}",
                          "raw/rpd_first_429.json")
                if which == "tpd_or_tpm":
                    self.rec.raw("rpd_limit_order.txt",
                                 "TPD/TPM tripped before RPD: tokens are the binding "
                                 f"constraint. remaining_rpd={r.rl.get('remaining_rpd')} "
                                 f"body={r.body[:300]}")
                break
            self.sleep(interval)
        return out

    # -- reporting ----------------------------------------------------------
    def report_mode(self, mode: str) -> None:
        got = {q for q, _, _ in self.evidence}
        print(f"\n--- {mode}: open questions ---")
        for q in EXPECTED_QUESTIONS.get(mode, []):
            hits = [(qq, c, a) for qq, c, a in self.evidence if qq == q]
            if hits:
                for _, claim, art in hits[-1:]:
                    print(f"  {q} ANSWERED  {claim}")
                    print(f"      evidence: {art}")
            else:
                print(f"  {q} NOT answered -- no raw log line produced by this mode")
        if not self.dry_run and not any(q in got for q in EXPECTED_QUESTIONS.get(mode, [])):
            pass  # silence is the honest answer; the line above already says so


# ------------------------------------------------------------------------------ cli

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scripts.probe",
        description="P1 probe against the real API. Dry-run unless --go.",
    )
    p.add_argument("--go", action="store_true",
                   help="actually send requests (requires --max-tokens-total)")
    p.add_argument("--max-tokens-total", type=int, default=None,
                   help="HARD ceiling for the whole session, in tokens")
    p.add_argument("--timeout", type=float, default=None,
                   help="per-request timeout in seconds (required with --go)")
    p.add_argument("--mode", action="append", default=None, choices=MODE_ORDER + ["all"],
                   help="repeatable; default is every mode except rpd")
    p.add_argument("--model-role", default="small", choices=["small", "large"],
                   help="which configured model to use as model A")
    p.add_argument("--n-single", type=int, default=3)
    p.add_argument("--n-burst", type=int, default=40)
    p.add_argument("--tiny-max-tokens", type=int, default=3)
    p.add_argument("--reasoning-param", default="reasoning_effort",
                   help="UNVERIFIED: confirm in the API reference before trusting")
    p.add_argument("--reasoning-values", default="low,medium,high")
    p.add_argument("--bigctx-tokens", type=int, default=None,
                   help="estimated prompt tokens for bigctx; default is "
                        "1.25 x models.small.tpm, i.e. just over the per-minute limit")
    # Kept so old invocations fail loudly rather than silently doing the wrong thing.
    p.add_argument("--bigctx-repeat", type=int, default=None, help=argparse.SUPPRESS)
    p.add_argument("--rpd-max-requests", type=int, default=2000)
    p.add_argument("--plan-today", type=int, default=None,
                   help="today's token plan; written to the ledger")
    p.add_argument("--config", default="config/relay.yaml")
    p.add_argument("--base-url", default=None)
    p.add_argument("--run-dir", default=None)
    return p


def resolve_modes(requested: Optional[list[str]]) -> list[str]:
    if not requested:
        return [m for m in MODE_ORDER if m != "rpd"]
    if "all" in requested:
        return [m for m in MODE_ORDER if m != "rpd"]
    seen: list[str] = []
    for m in MODE_ORDER:                     # always run in the canonical order
        if m in requested:
            seen.append(m)
    return seen


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    dry_run = not args.go

    if args.go and args.max_tokens_total is None:
        print("error: --go requires --max-tokens-total N (a hard ceiling). "
              "Refusing to spend an uncapped budget.", file=sys.stderr)
        return 2
    if args.go and args.timeout is None:
        print("error: --go requires --timeout S (no unmeasured default exists).",
              file=sys.stderr)
        return 2

    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    api_key = os.environ.get("GROQ_API_KEY") or None
    if args.go and not api_key:
        print("error: GROQ_API_KEY is not set. Copy .env.example to .env.",
              file=sys.stderr)
        return 2

    base_url = args.base_url or os.environ.get("GROQ_BASE_URL") or ""
    if args.go and not base_url:
        print("error: GROQ_BASE_URL is not set.", file=sys.stderr)
        return 2

    models = {"small": cfg.get("models.small.id"),
              "large": cfg.get("models.large.id")}
    if args.model_role == "large":
        models = {"small": models["large"], "large": models["small"]}

    ledger = Ledger()
    day = ledger.today(plan=args.plan_today,
                       cap=cfg.get("models.small.tpd"))
    remaining_plan = day.remaining
    if args.go and remaining_plan <= 0:
        print(f"error: today's plan is exhausted ({day.spent}/{day.plan}). "
              f"Raise --plan-today deliberately, or wait for the reset.",
              file=sys.stderr)
        return 2

    run_dir = Path(args.run_dir) if args.run_dir else (
        RUNS_DIR / f"probe_{'dryrun_' if dry_run else ''}{utc_stamp()}")
    # In a dry run with no explicit ceiling, plan against what the day allows --
    # cap=0 would refuse every request and make the dry run worthless.
    dry_cap = (args.max_tokens_total if args.max_tokens_total is not None
               else max(1, remaining_plan))
    ceiling = TokenCeiling(cap=args.max_tokens_total if args.go else dry_cap,
                           day_remaining=remaining_plan if args.go else 10**9)
    rec = Recorder(run_dir, api_key, dry_run)
    probe = Probe(cfg=cfg, base_url=base_url or "http://dry-run.invalid",
                  api_key=api_key, ceiling=ceiling, recorder=rec, dry_run=dry_run,
                  timeout=args.timeout, models=models)

    if args.bigctx_repeat is not None:
        print("error: --bigctx-repeat is gone. bigctx is now sized in tokens so it "
              "can be tied to the measured TPM limit. Use --bigctx-tokens.",
              file=sys.stderr)
        return 2
    tpm = cfg.get("models.small.tpm")
    bigctx_tokens = args.bigctx_tokens or int(tpm * 1.25)
    if args.bigctx_tokens is None and cfg.get("models.small.tpm") is None:
        print("error: models.small.tpm is null, so bigctx cannot be sized. Pass "
              "--bigctx-tokens explicitly.", file=sys.stderr)
        return 2

    modes = resolve_modes(args.mode)
    print(f"probe v{PROBE_VERSION}  {'DRY RUN (no network)' if dry_run else 'LIVE'}")
    print(f"  run_dir   {run_dir}")
    print(f"  base_url  {base_url or '(unset)'}")
    print(f"  key       {'<set, ' + str(len(api_key)) + ' chars>' if api_key else '(unset)'}")
    print(f"  models    small={models['small']}  large={models['large']}")
    print(f"  ceiling   {args.max_tokens_total if args.max_tokens_total else '(none)'}"
          f"   day plan remaining={remaining_plan}")
    print(f"  modes     {modes}")
    if "bigctx" in modes:
        print(f"  bigctx    ~{bigctx_tokens} est tokens "
              f"({bigctx_tokens / max(1, tpm):.2f}x TPM of {tpm})")

    started = now_mono()
    spent_before = ceiling.spent
    try:
        for mode in modes:
            print(f"\n=== {mode} ===")
            probe.evidence.clear()
            if mode == "models":
                probe.mode_models()
            elif mode == "single":
                probe.mode_single(args.n_single)
            elif mode == "stream":
                probe.mode_stream()
            elif mode == "reasoning":
                probe.mode_reasoning(args.reasoning_param,
                                     [v.strip() for v in args.reasoning_values.split(",")
                                      if v.strip()])
            elif mode == "bigctx":
                probe.mode_bigctx(bigctx_tokens)
            elif mode == "cache":
                probe.mode_cache()
            elif mode == "burst":
                probe.mode_burst(args.n_burst, args.tiny_max_tokens)
            elif mode == "buckets":
                probe.mode_buckets(args.n_burst, args.tiny_max_tokens)
            elif mode == "rpd":
                probe.mode_rpd(args.tiny_max_tokens,
                               cfg.get("models.small.rpm", 30),
                               args.rpd_max_requests)
            if dry_run:
                for line in probe.plan_lines:
                    print(line)
                probe.plan_lines.clear()
            else:
                probe.report_mode(mode)
    except CeilingReached as e:
        print(f"\nABORT: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    finally:
        probe.close()

    spent = ceiling.spent
    elapsed = now_mono() - started
    print(f"\n=== session ===")
    print(f"  tokens charged  {spent} (before={spent_before})")
    print(f"  ceiling         {args.max_tokens_total if args.max_tokens_total else '(dry run)'}")
    print(f"  elapsed         {elapsed:.1f}s")

    if not dry_run and spent > 0:
        ledger.spend(spent, row={
            "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "modes": modes,
            "tokens": spent,
            "ceiling": args.max_tokens_total,
        })
        ledger.save()
        print(f"  ledger          docs/TOKEN_LEDGER.md updated (+{spent})")
    else:
        print("  ledger          not written (dry run or zero spend)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
