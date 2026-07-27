#!/bin/zsh
# Intraday manual monitoring loop — run this at the keyboard before market open.
#
# Crontab (./install_cron.sh) owns the unattended pre-open learning path:
#   08:47 / 08:50 / 08:53 / 08:56  fetch iev   (multi-tick ΔIEV + NCP stamp)
#   08:57                          research pre-open capture  (sole decision write)
#   09:00                          research pre-open track
#   09:36 / 09:37                  research pre-open labels / evaluate
#
# This script is live display only (screen = live; no observation write):
#   08:45–08:46 → optional early screen pre-open rounds (Playwright)
#   08:46       → release Playwright so multi-tick cron can run without contention
#
# After open (human, not this loop):
#   saham analyze pre-open
#   saham trade log --type pre-open --observation-id … --opening-snapshot-id …

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

echo "  [$(TZ=Asia/Jakarta date '+%H:%M:%S')] Playwright released — cron multi-tick IEV from 08:47, capture 08:57." | tee -a "$LOGDIR/timeline.log"

echo "" | tee -a "$LOGDIR/timeline.log"
echo "─── Done at $(TZ=Asia/Jakarta date '+%H:%M:%S WIB') ───" | tee -a "$LOGDIR/timeline.log"
echo "All logs saved to: $LOGDIR"
echo "After open (human):"
echo "  saham analyze pre-open"
echo "  saham trade log --type pre-open --observation-id … --opening-snapshot-id …"
echo "Unattended path: multi-tick iev → research pre-open capture → track → labels/evaluate (see install_cron.sh)"
