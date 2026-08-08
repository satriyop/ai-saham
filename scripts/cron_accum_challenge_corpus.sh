#!/usr/bin/env bash
# Nightly accumulation challenge-corpus operator chain (P1).
#
# Ordered, fail-closed:
#   1) research accum capture --universe lq45 (session = economic day)
#   2) research accum sync-session-calendar --auto
#   3) research accum labels --all-label-contracts
#   4) research accum status
#
# Exit non-zero on any step failure. Emit COMPLETION_OK only after all steps
# succeed. COLLECTING from status is a successful producer state, not a failure.
# Stockbit/session-calendar sync failure prevents labels and COMPLETION_OK.
#
# Recovery after interrupt:
#   - Re-run this script for the same economic session (capture/labels/sync idempotent).
#   - Or run the four commands manually in the same order.
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

echo "${LOG_PREFIX} sync-session-calendar starting" >&2
saham research accum sync-session-calendar --auto --end "${SESSION}" --format json
echo "${LOG_PREFIX} sync-session-calendar ok" >&2

echo "${LOG_PREFIX} labels starting" >&2
saham research accum labels --all-label-contracts --format json
echo "${LOG_PREFIX} labels ok" >&2

echo "${LOG_PREFIX} status starting" >&2
saham research accum status --require-operational-success --format json
echo "${LOG_PREFIX} status ok" >&2

echo "COMPLETION_OK session=${SESSION}"
