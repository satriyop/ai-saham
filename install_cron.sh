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

# ── Manage Environment Secrets (.env) ──────────────────────────────────
ENV_FILE="$PROJECT_DIR/.env"
KEYS_TO_EXPORT=(
    "DEEPSEEK_API_KEY"
    "ANTHROPIC_API_KEY"
    "OPENAI_API_KEY"
    "GEMINI_API_KEY"
    "OLLAMA_HOST"
)

for KEY in "${KEYS_TO_EXPORT[@]}"; do
    VAL=$(eval echo \${$KEY:-})
    if [[ -n "$VAL" ]]; then
        if [[ ! -f "$ENV_FILE" ]]; then
            echo "Creating $ENV_FILE..."
            touch "$ENV_FILE"
            chmod 600 "$ENV_FILE"
        fi
        if ! grep -q "^${KEY}=" "$ENV_FILE" 2>/dev/null; then
            echo "Saving $KEY from active shell environment to $ENV_FILE"
            echo "${KEY}=${VAL}" >> "$ENV_FILE"
        fi
    fi
done

if [[ ! -f "$ENV_FILE" ]] || ! grep -q "^DEEPSEEK_API_KEY=" "$ENV_FILE" 2>/dev/null; then
    if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
        echo "NOTICE: DEEPSEEK_API_KEY is not set in current environment or $ENV_FILE."
        echo "        You can add it to $ENV_FILE to configure AI tuning."
        echo ""
    fi
fi

mkdir -p "$LOG_DIR"
echo "Project : $PROJECT_DIR"
echo "Logs    : $LOG_DIR"
echo ""

# ── Cron entries (host local time; expected host timezone: Asia/Jakarta) ─────
# IDX pre-open session: 08:45–09:00 WIB
# Opening session ends: 09:30 WIB
# Swing EOD observation starts after market data should be available.
read -r -d '' SAHAM_CRON << ENTRIES || true
# --- saham-cron-begin ---
# IEV collector — 08:55 WIB
55 8 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR && [ -f .env ] && set -a && source .env && set +a && source .venv/bin/activate && saham fetch iev' >> $LOG_DIR/iev-collector.log 2>&1
# Opening learning loop — NCP-locked snapshot 08:57 WIB
57 8 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR && [ -f .env ] && set -a && source .env && set +a && source .venv/bin/activate && saham learn snapshot' >> $LOG_DIR/opening-snapshot.log 2>&1
# Opening learning loop — orderbook tracker 09:00–09:30 WIB
0 9 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR && [ -f .env ] && set -a && source .env && set +a && source .venv/bin/activate && PYTHONUNBUFFERED=1 saham learn track --broker-confirm' >> $LOG_DIR/opening-track.log 2>&1
# Opening learning loop — auto trade confirm & log 09:31 WIB
31 9 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR && [ -f .env ] && set -a && source .env && set +a && source .venv/bin/activate && saham trade confirm --track-file data/opening/\$(date +\%Y\%m\%d)/track_0900.json && saham trade log intraday' >> $LOG_DIR/trade-confirm-log.log 2>&1
# Opening learning loop — accuracy grade 09:35 WIB
35 9 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR && [ -f .env ] && set -a && source .env && set +a && source .venv/bin/activate && saham learn grade' >> $LOG_DIR/opening-grade.log 2>&1
# Opening learning loop — AI tuning 09:40 WIB
40 9 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR && [ -f .env ] && set -a && source .env && set +a && source .venv/bin/activate && saham learn tune' >> $LOG_DIR/opening-tune.log 2>&1
# Swing EOD — refresh LQ45 candles after EOD data should be available 18:30 WIB
30 18 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR && [ -f .env ] && set -a && source .env && set +a && source .venv/bin/activate && saham fetch market --universe lq45' >> $LOG_DIR/swing-fetch-market.log 2>&1
# Swing EOD — capture LQ45 accumulation observations 19:15 WIB
15 19 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR && [ -f .env ] && set -a && source .env && set +a && source .venv/bin/activate && saham screen accum --universe lq45 --multi --format json' >> $LOG_DIR/swing-observe-lq45.log 2>&1
# Swing EOD — idempotent SWING_10D label generation for eligible saved dates 19:45 WIB
45 19 * * 1-5 /bin/bash -c 'cd $PROJECT_DIR && [ -f .env ] && set -a && source .env && set +a && source .venv/bin/activate && saham analyze signal-labels --eligible-dates --horizon SWING_10D --generate-all --format json' >> $LOG_DIR/swing-labels.log 2>&1
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
    /saham (fetch|learn|trade|screen|analyze)/  { next }
    /# (IEV collector|Opening.*learning|Opening learning|Swing EOD)/  { next }
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
