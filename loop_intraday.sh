#!/bin/zsh
# Intraday manual monitoring loop — run this at the keyboard before market open.
#
# Crontab (./install_cron.sh) owns the unattended pre-open learning path:
#   08:47 / 08:50 / 08:53 / 08:57  fetch iev   (multi-tick ΔIEV + NCP stamp)
#   08:58                          research pre-open capture  (sole decision write)
#   09:00–09:30                    learn track
#   09:35 / 09:36 / 09:40          learn grade / research pre-open labels / learn tune
#
# This script is live display + confirm only (screen = live; no observation write):
#   08:45–08:46 → optional early screen pre-open rounds (Playwright)
#   08:46       → release Playwright so multi-tick cron can run without contention
#   09:00–09:05 → trade confirm (no Playwright — sidecar from capture)

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

# ── Phase 1: Live screen only (08:45 → 08:46 WIB) ────────────────────
# Hand off before 08:47 multi-tick fetch iev cron. Do not write observations.
echo "" | tee -a "$LOGDIR/timeline.log"
echo "─── Phase 1: Live pre-open screen (until 08:46; then cron owns Playwright) ───" | tee -a "$LOGDIR/timeline.log"

CURRENT=$(TZ=Asia/Jakarta date +%H%M)
while [[ $CURRENT -lt 0846 ]]; do
    echo "  [$(TZ=Asia/Jakarta date '+%H:%M:%S')] pre-open screen (live)..." | tee -a "$LOGDIR/timeline.log"
    RUNFILE="$LOGDIR/preopen_$(TZ=Asia/Jakarta date +%H%M%S).txt"
    $VENV -m src.adapters.cli.main screen pre-open --top 5 --no-headless 2>&1 | tee -a "$RUNFILE"
    echo "" >> "$LOGDIR/timeline.log"
    CURRENT=$(TZ=Asia/Jakarta date +%H%M)
    if [[ $CURRENT -lt 0846 ]]; then
        echo "  [$(TZ=Asia/Jakarta date '+%H:%M:%S')] waiting 30s..." >> "$LOGDIR/timeline.log"
        sleep 30
    fi
done

echo "  [$(TZ=Asia/Jakarta date '+%H:%M:%S')] Playwright released — cron multi-tick IEV from 08:47, capture 08:58." | tee -a "$LOGDIR/timeline.log"
echo "  Waiting for market open (09:00)..." | tee -a "$LOGDIR/timeline.log"

# ── Phase 2: Confirm gate (09:00 → 09:05 WIB) ────────────────────────
# No Playwright — trade confirm reads sidecar written by research pre-open capture.
# learn track (cron, 09:00–09:30) holds Playwright during this window.
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
echo "Unattended path: multi-tick iev → research pre-open capture → learn track → grade/labels (see install_cron.sh)"
