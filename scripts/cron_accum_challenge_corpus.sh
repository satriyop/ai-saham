#!/usr/bin/env bash
# Nightly accumulation challenge-corpus operator chain (P1).
#
# Ordered, fail-closed:
#   1) research accum capture --universe lq45 (session = economic day)
#   2) research accum labels --all-label-contracts
#   3) research accum status
#
# Exit non-zero on any step failure. Emit COMPLETION_OK only after all three
# succeed. COLLECTING from status is a successful producer state, not a failure.
#
# Recovery after interrupt:
#   - Re-run this script for the same economic session (capture/labels idempotent).
#   - Or run the three commands manually in the same order.
#   - Do not attach snapshots to legacy cohorts; do not rewrite observations.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# shellcheck disable=SC1091
source .venv/bin/activate

SESSION="${ACCUM_CORPUS_SESSION:-$(date +%Y-%m-%d)}"
LOG_PREFIX="[cron_accum_challenge_corpus session=${SESSION}]"

echo "${LOG_PREFIX} capture starting" >&2
saham research accum capture --universe lq45 --session "${SESSION}" --format json
echo "${LOG_PREFIX} capture ok" >&2

echo "${LOG_PREFIX} labels starting" >&2
saham research accum labels --all-label-contracts --format json
echo "${LOG_PREFIX} labels ok" >&2

echo "${LOG_PREFIX} status starting" >&2
saham research accum status --format json
echo "${LOG_PREFIX} status ok" >&2

echo "COMPLETION_OK session=${SESSION}"
