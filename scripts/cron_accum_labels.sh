#!/usr/bin/env bash
# ADR-056: nightly accum path labels (all contracts via CLI).
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1
if [ -f .env ]; then set -a; source .env; set +a; fi
# shellcheck disable=SC1091
source .venv/bin/activate
exec saham research accum labels --all-label-contracts --format json
