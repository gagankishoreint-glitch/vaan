#!/usr/bin/env bash
# Build the submission archive. Raw results (runs/) are REQUIRED in the submission,
# so they are force-added even though .gitignore excludes them during development
# (DECISIONS D-004). PDFs are force-added for the same reason (D-005).
#
#   ./scripts/package_submission.sh            -> dist/relay-submission-<sha>.tar.gz
#   ./scripts/package_submission.sh --verify   -> build, then unpack and assert contents
set -euo pipefail
cd "$(dirname "$0")/.."

SHA=$(git rev-parse --short HEAD)
OUT_DIR=dist
NAME="relay-submission-${SHA}"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$OUT_DIR" "$TMP/$NAME"

# Tracked files
git ls-files -z | xargs -0 -I{} cp --parents "{}" "$TMP/$NAME" 2>/dev/null || true

# Force-included: run artefacts and the exact PDF versions
for d in runs data/papers; do
  [ -d "$d" ] || continue
  find "$d" -type f ! -name '.gitkeep' -print0 \
    | xargs -0 -I{} cp --parents "{}" "$TMP/$NAME" 2>/dev/null || true
done

tar -czf "$OUT_DIR/$NAME.tar.gz" -C "$TMP" "$NAME"
echo "wrote $OUT_DIR/$NAME.tar.gz ($(du -h "$OUT_DIR/$NAME.tar.gz" | cut -f1))"

if [ "${1:-}" = "--verify" ]; then
  # The failure mode we are guarding against: an ignored directory silently missing.
  LIST=$(tar -tzf "$OUT_DIR/$NAME.tar.gz")
  fail=0
  for f in "$NAME/runs" "$NAME/data/papers/SHA256SUMS" "$NAME/docs/TOKEN_LEDGER.md"; do
    if echo "$LIST" | grep -q "^$f"; then echo "  ok   $f"; else echo "  MISS $f"; fail=1; fi
  done
  n_pdf=$(echo "$LIST" | grep -c '\.pdf$' || true)
  if [ "$n_pdf" -ge 3 ]; then echo "  ok   $n_pdf PDFs"; else echo "  MISS PDFs ($n_pdf)"; fail=1; fi
  exit $fail
fi
