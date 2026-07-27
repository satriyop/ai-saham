#!/bin/bash
# install_cron.sh — install saham IDX cron jobs
#
# Idempotent: safe to run multiple times. Removes any existing saham cron
# entries (marked between BEGIN/END tags) before writing fresh ones.
#
# Usage:
#   ./install_cron.sh                # uses current directory as project root
#   ./install_cron.sh /path/to/repo  # explicit project root

set -euo pipefail

PROJECT_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
VENV="$PROJECT_DIR/.venv/bin/activate"
LOG_DIR="$PROJECT_DIR/logs"

# ── Preflight ─────────────────────────────────────────────────────────
if [[ ! -f "$VENV" ]]; then
    echo "ERROR: virtualenv not found at $VENV"
    echo "  Run: python -m venv .venv && pip install -e ."
    exit 1
fi

if ! "$PROJECT_DIR/.venv/bin/saham" --help > /dev/null 2>&1; then
    echo "ERROR: saham CLI not found in $PROJECT_DIR/.venv/bin/"
    echo "  Run: pip install -e ."
    exit 1
fi

mkdir -p "$LOG_DIR"
echo "Project : $PROJECT_DIR"
echo "Logs    : $LOG_DIR"
echo ""

# ── Cron entries (host local time; expected host timezone: Asia/Jakarta) ─────
# Database-owned pre-open lifecycle (ADR-049):
#   screen = live only (optional keyboard loop; not in cron)
#   multi-tick fetch iev = ΔIEV + NCP stamp (perishable; SQLite history)
#   research pre-open capture = sole observation decision write
#   research pre-open track = immutable observation-linked samples
#   research pre-open labels/evaluate = database labels and cohort evaluation
# Playwright: discovery/baseline ticks are ≥3 minutes apart. The final decision
# capture begins at 08:57 and must finish before 08:58 or it fails closed.
# Swing EOD: fetch market after close.
# Accumulation: evening capture + labels (labels attach y when horizon allows;
# recent ~20 sessions may be UNAVAILABLE until forward candles exist).
# No trade confirm / grade / prompt / tune (retired).
read -r -d '' SAHAM_CRON << ENTRIES || true
# --- saham-cron-begin ---
# Multi-tick IEV discovery (diagnostic all-session ΔIEV)
47 8 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR || exit 1; if [ -f .env ]; then set -a; source .env; set +a; fi; source .venv/bin/activate && saham fetch iev' >> $LOG_DIR/iev-collector.log 2>&1
50 8 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR || exit 1; if [ -f .env ]; then set -a; source .env; set +a; fi; source .venv/bin/activate && saham fetch iev' >> $LOG_DIR/iev-collector.log 2>&1
53 8 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR || exit 1; if [ -f .env ]; then set -a; source .env; set +a; fi; source .venv/bin/activate && saham fetch iev' >> $LOG_DIR/iev-collector.log 2>&1
# Locked-input IEV baseline — existing orders cannot be withdrawn/amended
56 8 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR || exit 1; if [ -f .env ]; then set -a; source .env; set +a; fi; source .venv/bin/activate && saham fetch iev' >> $LOG_DIR/iev-collector.log 2>&1
# Final live decision — must finish before 08:58 matching; current IEV minus the
# 08:56 baseline supplies locked-input delta_iev.
57 8 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR || exit 1; if [ -f .env ]; then set -a; source .env; set +a; fi; source .venv/bin/activate && saham research pre-open capture' >> $LOG_DIR/pre-open-capture.log 2>&1
# Persist observation-linked order-book/broker samples from 09:00–09:30
0 9 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR || exit 1; if [ -f .env ]; then set -a; source .env; set +a; fi; source .venv/bin/activate && PYTHONUNBUFFERED=1 saham research pre-open track --broker-confirm' >> $LOG_DIR/pre-open-track.log 2>&1
# Generate labels once after tracking completes, then evaluate persisted labels
36 9 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR || exit 1; if [ -f .env ]; then set -a; source .env; set +a; fi; source .venv/bin/activate && saham research pre-open labels --format json' >> $LOG_DIR/pre-open-labels.log 2>&1
37 9 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR || exit 1; if [ -f .env ]; then set -a; source .env; set +a; fi; source .venv/bin/activate && saham research pre-open evaluate --format json' >> $LOG_DIR/pre-open-evaluate.log 2>&1
# Swing EOD — refresh LQ45 candles after EOD data should be available 18:30 WIB
30 18 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR || exit 1; if [ -f .env ]; then set -a; source .env; set +a; fi; source .venv/bin/activate && saham fetch market --universe lq45' >> $LOG_DIR/swing-fetch-market.log 2>&1
# Accumulation learning corpus (X then y; labels fail closed if horizon incomplete)
15 19 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR || exit 1; if [ -f .env ]; then set -a; source .env; set +a; fi; source .venv/bin/activate && saham research accumulation capture --universe lq45 --session \$(date +\%Y-\%m-\%d) --format json' >> $LOG_DIR/accumulation-capture-lq45.log 2>&1
45 19 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR || exit 1; if [ -f .env ]; then set -a; source .env; set +a; fi; source .venv/bin/activate && saham research accumulation labels --label-contract price_path.accum_20d.v1 --format json' >> $LOG_DIR/accumulation-labels.log 2>&1
# --- saham-cron-end ---
ENTRIES

# Expand $PROJECT_DIR and $LOG_DIR inside the cron entries
SAHAM_CRON=$(echo "$SAHAM_CRON" | sed "s|\$PROJECT_DIR|$PROJECT_DIR|g" | sed "s|\$LOG_DIR|$LOG_DIR|g")

# ── Remove existing saham cron block, then append fresh one ──────────
EXISTING=$(crontab -l 2>/dev/null || true)

# Strip old saham block (tagged) AND any loose saham cron lines (untagged)
CLEANED=$(echo "$EXISTING" | awk '
    /# --- saham-cron-begin ---/ { skip=1 }
    /# --- saham-cron-end ---/   { skip=0; next }
    skip                         { next }
    /saham (fetch|trade|screen|inspect|plan|assess|research|audit)/  { next }
    /# (Multi-tick IEV|IEV NCP|IEV collector|Sole decision|Same-day ops|open_30m|Opening.*learning|Opening learning|Optional paper|Session scorecard|Non-authoritative|Persist observation-linked|Generate labels once|Swing EOD|Optional multi-day|Optional research)/  { next }
    { print }
')

# Remove leading and trailing blank lines from cleaned crontab (portable, no tac)
CLEANED=$(echo "$CLEANED" | awk '
    /[^[:space:]]/ { buf = buf (buf ? "\n" : "") $0; blanks = 0; next }
    buf             { blanks++ }
    END             { print buf }
')

# Combine: existing (without saham block) + blank separator + new block
if [[ -n "$CLEANED" ]]; then
    NEW_CRONTAB="${CLEANED}

${SAHAM_CRON}"
else
    NEW_CRONTAB="$SAHAM_CRON"
fi

echo "$NEW_CRONTAB" | crontab -

# ── Timezone Synchronization ──────────────────────────────────────────
echo "Attempting to synchronize cron daemon timezone..."
if [[ "$(uname)" == "Darwin" ]]; then
    echo "Restarting macOS cron daemon (requires sudo)..."
    if sudo launchctl kickstart -k system/com.vix.cron 2>/dev/null; then
        echo "Successfully restarted macOS cron daemon (com.vix.cron)."
    elif sudo launchctl kickstart -k system/com.apple.cron 2>/dev/null; then
        echo "Successfully restarted macOS cron daemon (com.apple.cron)."
    else
        # Fallback to unload/load
        if [[ -f /System/Library/LaunchDaemons/com.vix.cron.plist ]]; then
            (sudo launchctl unload /System/Library/LaunchDaemons/com.vix.cron.plist 2>/dev/null && \
             sudo launchctl load /System/Library/LaunchDaemons/com.vix.cron.plist 2>/dev/null && \
             echo "Successfully restarted macOS cron daemon via unload/load (com.vix.cron.plist).") || {
                echo "WARNING: Failed to restart macOS cron daemon. Timezone caching issues may persist."
                echo "         You can manually run: sudo launchctl kickstart -k system/com.vix.cron"
             }
        elif [[ -f /System/Library/LaunchDaemons/com.apple.cron.plist ]]; then
            (sudo launchctl unload /System/Library/LaunchDaemons/com.apple.cron.plist 2>/dev/null && \
             sudo launchctl load /System/Library/LaunchDaemons/com.apple.cron.plist 2>/dev/null && \
             echo "Successfully restarted macOS cron daemon via unload/load (com.apple.cron.plist).") || {
                echo "WARNING: Failed to restart macOS cron daemon. Timezone caching issues may persist."
                echo "         You can manually run: sudo launchctl kickstart -k system/com.vix.cron"
             }
        else
            echo "WARNING: Failed to restart macOS cron daemon. Timezone caching issues may persist."
            echo "         You can manually run: sudo launchctl kickstart -k system/com.vix.cron"
        fi
    fi
elif [[ "$(uname)" == "Linux" ]]; then
    if systemctl is-active --quiet cron 2>/dev/null; then
        echo "Restarting Linux cron service (requires sudo)..."
        sudo systemctl restart cron || {
            echo "WARNING: Failed to restart Linux cron service. You may need to run: sudo systemctl restart cron"
        }
    elif systemctl is-active --quiet crond 2>/dev/null; then
        echo "Restarting Linux crond service (requires sudo)..."
        sudo systemctl restart crond || {
            echo "WARNING: Failed to restart Linux crond service. You may need to run: sudo systemctl restart crond"
        }
    else
        echo "WARNING: Could not detect active cron/crond systemd service to restart."
    fi
fi
echo ""

# ── Verify ────────────────────────────────────────────────────────────
echo "Installed cron jobs:"
echo ""
crontab -l | grep -A1 "saham-cron-begin" || true
crontab -l | grep "saham " || true
echo ""
echo "Done. Run 'crontab -l' to see the full crontab."
