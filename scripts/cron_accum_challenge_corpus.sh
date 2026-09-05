#!/usr/bin/env bash
# Nightly accumulation challenge-corpus operator chain (P1).
#
# Ordered, fail-closed:
#   1) fetch lq45 candles-only (EOD lag retry after the 18:30 job)
#   2) research accum catch-up (replay IHSG dates with zero observations)
#   3) research accum capture --universe lq45 --require-session
#   4) research accum sync-session-calendar --auto
#   5) research accum labels --all-label-contracts
#   6) research accum status
#
# Exit non-zero on any step failure. Emit COMPLETION_OK only after all steps
# succeed. COLLECTING from status is a successful producer state, not a failure.
# Empty capture of a traded session (IHSG candle or same-day IEV) is failure.
# Holiday (no IHSG, no IEV) is success. Stockbit/session-calendar sync failure
# prevents labels and COMPLETION_OK.
# Catch-up stays fail-closed for COMPLETION_OK, but an unfillable historical
# IHSG hole must not abort today's capture, calendar sync, or labels.
#
# Recovery after interrupt:
#   - Re-run this script for the same economic session (catch-up/capture/labels
#     are idempotent; already-captured sessions skip the screen).
#   - Or run the commands manually in the same order.
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

echo "${LOG_PREFIX} eod candle retry starting" >&2
saham fetch market --universe lq45 --candles-only --no-enrichment --no-meta --no-calendar --no-macro-calendar
echo "${LOG_PREFIX} eod candle retry ok" >&2

echo "${LOG_PREFIX} catch-up starting" >&2
catch_up_rc=0
saham research accum catch-up --universe lq45 --end "${SESSION}" --lookback-days 14 --format json || catch_up_rc=$?
if [ "${catch_up_rc}" -ne 0 ]; then
  echo "${LOG_PREFIX} catch-up failed rc=${catch_up_rc}; continuing today's capture" >&2
else
  echo "${LOG_PREFIX} catch-up ok" >&2
fi

echo "${LOG_PREFIX} capture starting" >&2
saham research accum capture --universe lq45 --session "${SESSION}" --require-session --format json
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

if [ "${catch_up_rc}" -ne 0 ]; then
  echo "${LOG_PREFIX} catch-up failed rc=${catch_up_rc}; skipping COMPLETION_OK" >&2
  exit "${catch_up_rc}"
fi

echo "COMPLETION_OK session=${SESSION}"
