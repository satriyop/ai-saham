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

# ── Cron entries (all times in UTC; IDX = UTC+7) ─────────────────────
# IDX pre-open session: 08:45–09:00 WIB = 01:45–02:00 UTC
# Opening session ends: 09:30 WIB = 02:30 UTC
read -r -d '' SAHAM_CRON << ENTRIES || true
# --- saham-cron-begin ---
# IEV collector — 08:55 WIB (01:55 UTC)
55 1 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR && source .venv/bin/activate && saham fetch iev' >> $LOG_DIR/iev-collector.log 2>&1
# Opening learning loop — NCP-locked snapshot 08:57 WIB (01:57 UTC)
57 1 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR && source .venv/bin/activate && saham learn snapshot' >> $LOG_DIR/opening-snapshot.log 2>&1
# Opening learning loop — orderbook tracker 09:00–09:30 WIB (02:00 UTC)
0 2 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR && source .venv/bin/activate && saham learn track' >> $LOG_DIR/opening-track.log 2>&1
# Opening learning loop — accuracy grade 09:35 WIB (02:35 UTC)
35 2 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR && source .venv/bin/activate && saham learn grade' >> $LOG_DIR/opening-grade.log 2>&1
# Opening learning loop — AI tuning 09:40 WIB (02:40 UTC)
40 2 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR && source .venv/bin/activate && saham learn tune' >> $LOG_DIR/opening-tune.log 2>&1
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
    /saham (fetch|learn|trade)/  { next }
    /# (IEV collector|Opening.*learning|Opening learning)/  { next }
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

# ── Verify ────────────────────────────────────────────────────────────
echo "Installed cron jobs:"
echo ""
crontab -l | grep -A1 "saham-cron-begin" || true
crontab -l | grep "saham " || true
echo ""
echo "Done. Run 'crontab -l' to see the full crontab."
