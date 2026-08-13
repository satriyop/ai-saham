#!/bin/bash
# Pre-open lane pre-flight.
#
# The corpus-continuity watchdog runs at 19:30 and is structurally unable to
# help the pre-open lane: the 08:56-08:58 NCP capture cannot be replayed, so by
# evening the only available action is to record that the day is lost. Session
# 2026-08-07 is absent from iev_snapshots for exactly this reason.
#
# This wrapper moves the same question to where it can still change the outcome.
# Two slots, each with a stated margin before the window closes:
#
#   08:41  --as-of pre-flight  token state + horizon      15 min of margin
#   08:48  --as-of verify      IEV rows actually stored     8 min of margin
#
# The 08:41 slot is predictive and local (no network): the measured token TTL is
# exactly 24h from each 08:40 reauth, so a failed reauth leaves a token expiring
# *inside* the pre-open lane while still reading "valid" for a few more minutes.
# The 08:48 slot is the proof the local check cannot give — `saham fetch iev`
# prints "No movers returned" and exits 0, so from outside a rejected token
# looks exactly like a healthy run. Stored rows are the only honest evidence.
#
# Remediation is deliberately manual: `reauth --mode headed` needs a UI, and
# headless recovery is precisely what already failed. This alarms; it does not
# self-heal.
#
# Known false alarm: no offline same-day IDX holiday authority exists in this
# repo, so on a public holiday the 08:48 slot will fire. The notification says
# so, so a holiday alarm stays recognisable instead of eroding trust.
#
# Exit codes: 0 = lane on track (or not yet due); 1 = lane at risk;
#             2 = the pre-flight itself could not run (broken environment).
# Distinguishing 1 from 2 matters: 1 sends you to Stockbit auth, 2 sends you to
# the venv. Collapsing them wastes the only 16 minutes you have.

set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)" || exit 1
cd "$PROJECT_DIR" || exit 1

STAMP="$(date '+%Y-%m-%d %H:%M:%S %z')"
SLOT="${1:-preflight}"

if [ ! -f "$PROJECT_DIR/.venv/bin/activate" ]; then
    echo "PREFLIGHT_BROKEN ${STAMP} no virtualenv at ${PROJECT_DIR}/.venv" >&2
    exit 2
fi

if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# shellcheck disable=SC1091
source "$PROJECT_DIR/.venv/bin/activate"

if ! command -v saham >/dev/null 2>&1; then
    echo "PREFLIGHT_BROKEN ${STAMP} saham CLI not on PATH after activating venv" >&2
    exit 2
fi

echo "[preflight ${STAMP}] slot=${SLOT}"

if saham audit preopen-readiness --require-ready; then
    echo "PREFLIGHT_OK ${STAMP} slot=${SLOT}"
    exit 0
fi

echo "PREFLIGHT_ALERT ${STAMP} slot=${SLOT}"

# Visible, non-blocking alert. osascript is best-effort: a locked or headless
# session must not turn a reporting failure into a wrapper crash. The message
# carries the remediation because the operator has minutes, not time to read
# a log and work out what to run.
osascript -e "display notification \"Run: saham fetch stockbit reauth --mode headed (or IDX holiday)\" with title \"ai-saham pre-open lane AT RISK\" sound name \"Basso\"" >/dev/null 2>&1 || true

exit 1
