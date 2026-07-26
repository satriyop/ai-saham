"""IDX market structural constants — single source of truth.

These are exchange-defined facts (lot size, session boundaries, timezone).
NOT user-tunable. Every layer may import from here; no layer may redefine these.

Layer: Domain (stdlib only — no I/O, no external dependencies)
"""

from datetime import time
from zoneinfo import ZoneInfo

# ── Lot sizing ──────────────────────────────────────────────────────────────
# IDX standard: 1 lot = 100 shares. Used for shares ↔ lots conversions.
SHARES_PER_LOT: int = 100

# ── Exchange timezone ───────────────────────────────────────────────────────
IDX_TIMEZONE = ZoneInfo("Asia/Jakarta")

# ── Regular board session boundaries (Asia/Jakarta wall-clock) ─────────────
# Reference: IDX Rule II-A Kep-00196/BEI/12-2024; NCP enforced during 2025.
PRE_OPEN_START = time(8, 45)  # pre-open order input begins
NCP_LOCK_TIME = time(8, 56)  # no-withdraw/no-amend locked-input begins
PRE_OPEN_MATCHING_START = time(8, 58)  # pre-opening matching begins
REGULAR_OPEN = time(9, 0)  # continuous trading begins
OPEN_SESSION_END = time(9, 30)  # end of opening-window observation band
PRE_CLOSE_START = time(15, 50)  # pre-closing call auction begins
MARKET_CLOSE = time(16, 0)  # regular session close
