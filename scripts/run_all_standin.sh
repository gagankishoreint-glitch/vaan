#!/usr/bin/env bash
# 5d: run every stand-in scenario in one pass, and say what did NOT run.
#
#   ./scripts/run_all_standin.sh              # everything that can run here
#   ./scripts/run_all_standin.sh --strict     # non-zero exit if a scenario is SKIPPED
#   ./scripts/run_all_standin.sh --only breaker,load
#
# Design rules, each of which is a bug this script exists to prevent:
#
# 1. A SKIPPED scenario is reported as SKIPPED, never as a pass. The corpus is
#    absent in a bare checkout (data/papers/*.pdf is git-ignored, D-005), so the
#    pipeline scenarios cannot run. A harness that quietly omits them produces a
#    green line for a system that was never exercised.
# 2. Every run is labelled UNCALIBRATED. Nothing here is a measurement of Groq.
# 3. No real Groq call. The base URL is the stand-in, and a stray GROQ_API_KEY is
#    ignored -- a harness that can accidentally spend real tokens is a hazard.
# 4. Each scenario writes into its own runs/standin/<name>/ and prints the path,
#    so a result can be traced to the command that produced it.
# 5. The stand-in's own assumptions (refund_unused_cap, seed, TPM limit) are
#    captured next to the results, so two runs that differ only in an assumption
#    are distinguishable afterwards (Q-06 is OPEN).
set -uo pipefail
cd "$(dirname "$0")/.."

PY="${PY:-.venv/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"
PORT="${PORT:-8009}"
BASE="http://127.0.0.1:${PORT}/openai/v1"
OUT_ROOT="runs/standin"
STRICT=0
ONLY=""

usage() { sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --strict) STRICT=1; shift ;;
    --only)   ONLY="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

mkdir -p "$OUT_ROOT"

# A stray key must not turn a stand-in run into a paid one.
unset GROQ_API_KEY RELAY_GROQ_KEY 2>/dev/null || true

PASS=0; FAIL=0; SKIPPED=0
: > "$OUT_ROOT/index.txt"
declare -a RESULTS=()

record () {  # name status note
  RESULTS+=("$(printf '%-26s %-8s %s' "$1" "$2" "$3")")
  printf '%s\n' "${RESULTS[${#RESULTS[@]}-1]}" >> "$OUT_ROOT/index.txt"
  case "$2" in
    PASS)    PASS=$((PASS+1)) ;;
    FAIL)    FAIL=$((FAIL+1)) ;;
    SKIPPED) SKIPPED=$((SKIPPED+1)) ;;
  esac
  echo "  [$2] $1${3:+ -- $3}"
}

want () {  # want <name>  -> 0 if selected
  [ -z "$ONLY" ] && return 0
  case ",$ONLY," in *",$1,"*) return 0 ;; *) return 1 ;; esac
}

# ---------------------------------------------------------------- stand-in lifecycle
STARTED=0
start_standin () {
  [ "$STARTED" = 1 ] && return 0
  "$PY" -m uvicorn relay.standin.server:app --host 127.0.0.1 --port "$PORT" \
      --log-level error >"$OUT_ROOT/_standin.log" 2>&1 &
  STANDIN_PID=$!
  for _ in $(seq 1 150); do
    if curl -sf "http://127.0.0.1:${PORT}/__stats" >/dev/null 2>&1; then
      STARTED=1
      # Record the ASSUMPTIONS this whole pass ran under (Q-06 is OPEN).
      curl -s "http://127.0.0.1:${PORT}/__stats" > "$OUT_ROOT/_assumptions.json"
      return 0
    fi
    sleep 0.1
  done
  echo "stand-in did not start; see $OUT_ROOT/_standin.log" >&2
  return 1
}

stop_standin () {
  [ "$STARTED" = 1 ] || return 0
  kill "$STANDIN_PID" 2>/dev/null || true
  wait "$STANDIN_PID" 2>/dev/null || true
  STARTED=0
}
trap 'stop_standin' EXIT INT TERM

reset_standin () {
  curl -sf -X POST "http://127.0.0.1:${PORT}/__reset" >/dev/null 2>&1 || true
}

have_chunks () { [ -f "data/chunks/exp900/chunks.jsonl" ]; }

echo "=== stand-in scenario pass (UNCALIBRATED, no Groq calls) ==="
echo "python: $PY   port: $PORT"
echo

# ---------------------------------------------------------------- 1. smoke
if want smoke; then
  if "$PY" -m scripts.smoke_p0 >/dev/null 2>&1; then
    record "smoke_p0" PASS "H1 contract end to end"
  else
    record "smoke_p0" FAIL "see output"
  fi
fi

# ---------------------------------------------------------------- 2. breaker cycle
if want breaker; then
  if "$PY" scripts/run_standin_breaker.py >"$OUT_ROOT/_breaker.log" 2>&1; then
    record "breaker_cycle" PASS "$OUT_ROOT/breaker_cycle.json"
  else
    record "breaker_cycle" FAIL "see $OUT_ROOT/_breaker.log"
  fi
fi

# ---------------------------------------------------------------- 3. load shapes
if want load; then
  if start_standin; then
    for SHAPE in steady burst overload; do
      reset_standin
      DIR="$OUT_ROOT/load_${SHAPE}"
      rm -rf "$DIR"
      case "$SHAPE" in
        steady)   ARGS="--rps 2  --duration 5" ;;
        burst)    ARGS="--rps 1  --burst 20" ;;
        overload) ARGS="--rps 40 --duration 6" ;;
      esac
      # shellcheck disable=SC2086
      if "$PY" -m scripts.loadgen --shape "$SHAPE" $ARGS --max-tokens 80 \
            --out "$DIR" >"$OUT_ROOT/_load_${SHAPE}.log" 2>&1; then
        N=$("$PY" - "$DIR" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]) / "arrivals.jsonl"
rows = [json.loads(l) for l in p.open() if l.strip()] if p.exists() else []
print(f"{len(rows)} arrivals")
PY
)
        record "load_${SHAPE}" PASS "$N"
      else
        record "load_${SHAPE}" FAIL "see $OUT_ROOT/_load_${SHAPE}.log"
      fi
    done
  else
    record "load" SKIPPED "stand-in did not start"
  fi
fi

# ---------------------------------------------------------------- 4. admission / shedding
if want queue; then
  if start_standin; then
    reset_standin
    DIR="$OUT_ROOT/queue_shed"
    rm -rf "$DIR"; mkdir -p "$DIR"
    # Drive the stand-in's TPM bucket past its limit so the gateway's own budget
    # refuses; the reply class is what is being checked, not the exit code.
    if "$PY" -m scripts.pipeline_overload --n 40 --base-url "$BASE" \
          --out "$DIR/replies.json" >"$OUT_ROOT/_queue.log" 2>&1; then
      record "pipeline_overload" PASS "$DIR/replies.json"
    else
      # pipeline_overload needs the chunk corpus; that absence is a SKIP, not a FAIL.
      if ! have_chunks; then
        record "pipeline_overload" SKIPPED "no corpus: data/chunks/exp900/chunks.jsonl"
      else
        record "pipeline_overload" FAIL "see $OUT_ROOT/_queue.log"
      fi
    fi
  else
    record "queue" SKIPPED "stand-in did not start"
  fi
fi

# ---------------------------------------------------------------- 5. p6 pipeline + quality
if want pipeline; then
  if ! have_chunks; then
    record "run_queries" SKIPPED "no corpus: data/chunks/exp900/chunks.jsonl"
    record "quality" SKIPPED "depends on run_queries"
  elif start_standin; then
    reset_standin
    DIR="$OUT_ROOT/p6"
    rm -rf "$DIR"
    if "$PY" -m scripts.run_queries --backend standin --base-url "$BASE" \
          --run-dir "$DIR" --limit 8 --stream >"$OUT_ROOT/_p6.log" 2>&1; then
      record "run_queries" PASS "$DIR/summary.json"
      if "$PY" -m scripts.check_events "$DIR/events.jsonl" >"$OUT_ROOT/_p6_invariants.log" 2>&1; then
        record "p6_invariants" PASS "I1-I8 hold"
      else
        record "p6_invariants" FAIL "see $OUT_ROOT/_p6_invariants.log"
      fi
      if "$PY" -m scripts.run_quality "$DIR" --json --out "$DIR/quality.json" >/dev/null 2>&1; then
        record "quality" PASS "$DIR/quality.json"
      else
        record "quality" FAIL "see $DIR"
      fi
    else
      record "run_queries" FAIL "see $OUT_ROOT/_p6.log"
      record "quality" SKIPPED "run_queries failed"
    fi
  else
    record "pipeline" SKIPPED "stand-in did not start"
  fi
fi

# ---------------------------------------------------------------- 6. streamed 5xx
if want stream_error; then
  # A 5xx must actually be injected, or the scenario proves nothing. This step runs
  # its OWN stand-in with error_rate=1.0: the shared one is healthy, and a "PASS"
  # from a healthy stand-in is the false green this harness exists to prevent --
  # the first version of this script reported outcomes ["ok"] and called it a pass.
  stop_standin
  CFG=$(mktemp -t standin_cfg)
  "$PY" - "$CFG" <<'PYCFG'
import sys, yaml
doc = yaml.safe_load(open("config/relay.yaml", encoding="utf-8"))
doc.setdefault("standin", {})["error_rate"] = 1.0
yaml.safe_dump(doc, open(sys.argv[1], "w"))
PYCFG
  RELAY_CONFIG="$CFG" "$PY" -m uvicorn relay.standin.server:app --host 127.0.0.1 \
      --port "$PORT" --log-level error >"$OUT_ROOT/_standin_err.log" 2>&1 &
  ERR_PID=$!
  for _ in $(seq 1 150); do
    curl -sf "http://127.0.0.1:${PORT}/__stats" >/dev/null 2>&1 && break
    sleep 0.1
  done
  if "$PY" scripts/_stream_error_probe.py "$BASE" >"$OUT_ROOT/_stream_error.log" 2>&1; then
    record "stream_http_error" PASS "$(tail -1 "$OUT_ROOT/_stream_error.log")"
  else
    record "stream_http_error" FAIL "see $OUT_ROOT/_stream_error.log"
  fi
  kill "$ERR_PID" 2>/dev/null || true
  wait "$ERR_PID" 2>/dev/null || true
  rm -f "$CFG"
fi

# ---------------------------------------------------------------- summary
echo
echo "=== summary ==="
echo "  pass $PASS   fail $FAIL   skipped $SKIPPED"
echo "  index: $OUT_ROOT/index.txt"
if [ -f "$OUT_ROOT/_assumptions.json" ]; then
  echo "  stand-in assumptions: $(cat "$OUT_ROOT/_assumptions.json")"
fi
if [ "$SKIPPED" -gt 0 ]; then
  echo
  echo "  $SKIPPED scenario(s) SKIPPED -- those parts of the system were NOT exercised."
  echo "  The corpus is absent in a bare checkout (data/papers/*.pdf is git-ignored,"
  echo "  D-005). Restore the PDFs and re-ingest to cover them. A skip is not a pass."
fi

if [ "$FAIL" -gt 0 ]; then exit 1; fi
if [ "$STRICT" = 1 ] && [ "$SKIPPED" -gt 0 ]; then exit 3; fi
exit 0
