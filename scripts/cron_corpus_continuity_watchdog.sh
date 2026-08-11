#!/bin/bash
# Corpus-continuity watchdog.
#
# The capture crons are fail-closed, but a fail-closed job nobody reads is just
# a quiet job. This wrapper asks the corpus itself whether any trading session
# is missing, and raises a visible macOS notification when one is.
#
# Why it matters per purpose:
#   ACCUM     replayable — `saham research accum signal-backfill-observations`
#             can rebuild a missed session from stored market data, but only if
#             somebody notices it is gone.
#   PRE_OPEN  NOT replayable — the 08:56 IEV reading exists only inside the NCP
#             lock window. A missed session is gone permanently, so the alarm's
#             job is to get the cause fixed before the next session opens.
#
# Timing constraint: run this AFTER the evening accum job, which is what calls
# `research accum sync-session-calendar`. Before that sync, today is outside
# every stored calendar coverage window, so a genuinely missed capture reports
# NO_CALENDAR_AUTHORITY (silent) instead of MISSING (alarm). A morning run would
# therefore be quietly useless.
#
# Exit codes: 0 = every audited corpus is whole; 1 = at least one has a hole;
#             2 = the watchdog itself could not run (broken environment).
# Distinguishing 1 from 2 matters: 1 sends you to the capture logs, 2 sends you
# to the venv. Collapsing them wastes the morning.

set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)" || exit 1
cd "$PROJECT_DIR" || exit 1

STAMP="$(date '+%Y-%m-%d %H:%M:%S %z')"

# Fail loudly on a broken environment. Without this the checks below all report
# "command not found" as a corpus hole, which is a true alarm for a false
# reason — the operator would go looking for missing sessions that are present.
if [ ! -f "$PROJECT_DIR/.venv/bin/activate" ]; then
    echo "WATCHDOG_BROKEN ${STAMP} no virtualenv at ${PROJECT_DIR}/.venv" >&2
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
    echo "WATCHDOG_BROKEN ${STAMP} saham CLI not on PATH after activating venv" >&2
    exit 2
fi
FAILURES=()

# Accum captures the full LQ45 book every session, so width is declared and a
# materially truncated capture is a real finding. Pre-open records only the
# candidates that pass its filters, so it has no expected width — omitting
# --expected-width there means only a wholly missing session raises the alarm.
check() {
    local label="$1"
    local purpose="$2"
    shift 2

    echo "[watchdog ${STAMP}] ${label}: checking"
    if saham audit corpus-continuity --purpose "${purpose}" --require-healthy "$@"; then
        echo "[watchdog ${STAMP}] ${label}: OK"
    else
        echo "[watchdog ${STAMP}] ${label}: HOLE DETECTED"
        FAILURES+=("${label}")
    fi
}

check "accum" "accum" --expected-width 45 --lookback 10
check "pre-open" "pre-open" --lookback 10

if [ ${#FAILURES[@]} -eq 0 ]; then
    echo "WATCHDOG_OK ${STAMP}"
    exit 0
fi

JOINED="$(
    IFS=', '
    echo "${FAILURES[*]}"
)"
echo "WATCHDOG_ALERT ${STAMP} corpora=${JOINED}"

# Visible, non-blocking alert. osascript is best-effort: a headless or locked
# session must not turn a reporting failure into a wrapper crash.
osascript -e "display notification \"Missing sessions: ${JOINED}\" with title \"ai-saham corpus hole\" sound name \"Basso\"" >/dev/null 2>&1 || true

exit 1
