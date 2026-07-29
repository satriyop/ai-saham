#!/usr/bin/env bash
# ADR-056: run all accum path label contracts (3d / 10d primary / 20d).
# Continues remaining contracts if one fails; exits non-zero if any failed hard.
set -u
cd "$(dirname "$0")/.." || exit 1
if [ -f .env ]; then set -a; source .env; set +a; fi
# shellcheck disable=SC1091
source .venv/bin/activate

status=0
for contract in \
  price_path.accum_3d.v1 \
  price_path.accum_10d.v1 \
  price_path.accum_20d.v1
do
  echo "=== research accum labels --label-contract ${contract} ==="
  if ! saham research accum labels --label-contract "${contract}" --format json; then
    echo "[error] labels failed for ${contract}" >&2
    status=1
  fi
done
exit "${status}"
