#!/bin/zsh
# Intraday manual monitoring loop — run this at the keyboard before market open.
# Crontab handles the learning loop automatically (fetch iev, learn snapshot/track/grade/tune).
# This script handles: real-time screen monitoring (08:45–08:55) + confirm gate (09:00–09:05).
#
# Playwright handoff:
#   08:45–08:55 → this script owns Playwright (screen pre-open every 90s)
#   08:55       → this script releases Playwright — crontab takes over
#   08:55       → cron: fetch iev  (Playwright)
#   08:57       → cron: learn snapshot  (Playwright, NCP-locked canonical capture)
#   09:00       → cron: learn track  (Playwright, holds until 09:30)
#   09:00–09:05 → this script: trade confirm  (no Playwright — reads sidecar only)

VENV=".venv/bin/python"
LOGDIR="logs/intraday_loop_$(TZ=Asia/Jakarta date +%Y%m%d)"
mkdir -p "$LOGDIR"

# ── Guard: wait until 08:45 WIB ──────────────────────────────────────
CURRENT=$(TZ=Asia/Jakarta date +%H%M)
if [[ $CURRENT -lt 0845 ]]; then
    echo "=== Waiting for 08:45 WIB (now: $(TZ=Asia/Jakarta date '+%H:%M WIB')) ===" | tee -a "$LOGDIR/timeline.log"
    while [[ $(TZ=Asia/Jakarta date +%H%M) -lt 0845 ]]; do
        sleep 30
    done
fi

echo "=== Intraday Loop Started at $(TZ=Asia/Jakarta date '+%H:%M:%S WIB') ===" | tee -a "$LOGDIR/timeline.log"

# ── Phase 1: Pre-open monitoring (08:45 → 08:55 WIB) ─────────────────
# Stop at 08:55 — crontab takes Playwright from 08:55 onward.
# NCP locks at 08:56; crontab captures the canonical NCP snapshot at 08:57.
echo "" | tee -a "$LOGDIR/timeline.log"
echo "─── Phase 1: Pre-Open Monitoring (Playwright owned here until 08:55) ───" | tee -a "$LOGDIR/timeline.log"

# IEV snapshot — once at start
echo "  [$(TZ=Asia/Jakarta date '+%H:%M:%S')] collect-iev..." | tee -a "$LOGDIR/timeline.log"
$VENV -m src.adapters.cli.main fetch iev --top-n 50 --no-headless 2>&1 | tee -a "$LOGDIR/collect_iev.log"

# Screen loop every 90s — exit loop before 08:55 to hand off Playwright to crontab
CURRENT=$(TZ=Asia/Jakarta date +%H%M)
while [[ $CURRENT -lt 0855 ]]; do
    echo "  [$(TZ=Asia/Jakarta date '+%H:%M:%S')] pre-open round..." | tee -a "$LOGDIR/timeline.log"
    RUNFILE="$LOGDIR/preopen_$(TZ=Asia/Jakarta date +%H%M%S).txt"
    $VENV -m src.adapters.cli.main screen pre-open --top 5 --no-headless 2>&1 | tee -a "$RUNFILE"
    echo "" >> "$LOGDIR/timeline.log"
    CURRENT=$(TZ=Asia/Jakarta date +%H%M)
    if [[ $CURRENT -lt 0855 ]]; then
        echo "  [$(TZ=Asia/Jakarta date '+%H:%M:%S')] waiting 90s..." >> "$LOGDIR/timeline.log"
        sleep 90
    fi
done

echo "  [$(TZ=Asia/Jakarta date '+%H:%M:%S')] Playwright released — crontab takes over at 08:55." | tee -a "$LOGDIR/timeline.log"
echo "  Waiting for market open (09:00)..." | tee -a "$LOGDIR/timeline.log"

# ── Phase 2: Confirm gate (09:00 → 09:05 WIB) ────────────────────────
# No Playwright — trade confirm reads .last-session.json sidecar written by learn snapshot.
# learn track (crontab, 09:00–09:30) holds Playwright during this window.
echo "" | tee -a "$LOGDIR/timeline.log"
echo "─── Phase 2: Opening Auction Confirm Gate (no Playwright) ───" | tee -a "$LOGDIR/timeline.log"

while [[ $(TZ=Asia/Jakarta date +%H%M) -lt 0900 ]]; do
    sleep 10
done

CURRENT=$(TZ=Asia/Jakarta date +%H%M)
while [[ $CURRENT -lt 0905 ]]; do
    echo "  [$(TZ=Asia/Jakarta date '+%H:%M:%S')] trade confirm..." | tee -a "$LOGDIR/timeline.log"
    $VENV -m src.adapters.cli.main trade confirm 2>&1 | tee -a "$LOGDIR/confirm_$(TZ=Asia/Jakarta date +%H%M%S).txt"
    CURRENT=$(TZ=Asia/Jakarta date +%H%M)
    if [[ $CURRENT -lt 0905 ]]; then
        sleep 30
    fi
done

echo "" | tee -a "$LOGDIR/timeline.log"
echo "─── Done at $(TZ=Asia/Jakarta date '+%H:%M:%S WIB') ───" | tee -a "$LOGDIR/timeline.log"
echo "All logs saved to: $LOGDIR"
