# Pre-Open Screening Post-Mortem: June 17, 2026

## Table 1 — IEV Snapshots Before 09:00 WIB

Data from SQLite `iev_snapshot_history` table. Three snapshots captured during
the call auction (08:45–09:00). NCP locked after 08:56.

### Snapshot 1: 08:55:13 (NCP unlocked)

| Rank | Ticker | IEV | IEP |
|------|--------|-----|-----|
| 1 | BUMI | 173,236 | 175 |
| 2 | BBCA | 163,968 | 6,250 |
| 3 | GOTO | 155,663 | 50 |
| 4 | BNBR | 141,622 | 122 |
| 5 | BRMS | 117,075 | 725 |
| 6 | BMRI | 92,535 | 4,500 |
| 7 | BBRI | 76,695 | 3,040 |

### Snapshot 2: 08:56:04 (NCP locked)

| Rank | Ticker | IEV | IEP |
|------|--------|-----|-----|
| 1 | BUMI | 368,807 | 175 |
| 2 | BBCA | 212,608 | 6,400 |
| 3 | GOTO | 155,663 | 50 |
| 4 | BNBR | 151,871 | 122 |
| 5 | BMRI | 135,897 | 4,500 |
| — | BBRI | 76,858 | 3,030 |
| — | BRMS | dropped from top 5 | — |

### Snapshot 3: 08:58:54 (NCP locked)

| Rank | Ticker | IEV | IEP |
|------|--------|-----|-----|
| 1 | BUMI | 717,031 | 175 |
| 2 | BBCA | 239,076 | 6,400 |
| 3 | BNBR | 225,924 | 122 |
| 4 | BRMS | 219,397 | 685 |
| 5 | GOTO | 158,303 | 50 |
| — | BMRI | 138,998 | 4,500 |
| — | BBRI | 103,130 | 3,020 |

### Key changes between snapshots

- **BUMI IEV exploded**: 173K → 369K → 717K (4× in 3 min). IEP unchanged at 175.
- **BBCA IEP jumped**: 6,250 → 6,400 at NCP lock. This predicted the actual
  opening price (6,400) perfectly. IEV grew from 164K → 239K.
- **BRMS entered then dropped**: #5 at 08:55 (117K), fell out at 08:56, returned
  at 08:58 to #4 (219K). Speculative filter blocked it (<20 days history).
- **BMRI climbed steadily**: #6 at 08:55 (93K) → #5 at 08:56 (136K) → #6 at
  08:58 (139K). It was the only consistent non-speculative mover outside the
  top 5 at 08:55.
- **BBRI steadily low**: 76K→77K→103K IEV. Never entered top 5.

---

## Table 2 — Real Price 5-Minute Close (09:00–09:45 WIB)

5-minute closing prices from Yahoo Finance intraday candles. Entry range from
pre-open sidecar (`journals/.last-session.json`). Grey = inside entry range.

Ticker      Entry Range      09:00   09:05   09:10   09:15   09:20   09:25   09:30   09:35   09:40   09:45
───────     ───────────────── ──────  ──────  ──────  ──────  ──────  ──────  ──────  ──────  ──────  ──────
**BBCA**    6,017 – 6,533     6,475   6,525   6,525   6,475   6,450   6,425   6,425   6,450   6,450   6,425
                            ──────── inside entry range ────────

**BMRI**    4,344 – 4,656     4,490   4,550   4,550   4,530   4,520   4,510   4,510   4,490   4,490   4,490
                            ──────── inside entry range ────────

**BUMI**      149 – 165       172     175     176     175     173     173     173     173     173     173
                            ════════ above entry range (>165) ════════

**BNBR**      104 – 116       118     121     121     119     118     117     118     115     115     116
                            ════════ above entry range (>116) ════════

**GOTO**         50 – 50       50      50      50      50      50      50      50      50      50      50
                            exactly at entry edge (flat)

**BBRI**    N/A (not in      3,030   3,090   3,120   3,100   3,080   3,090   3,090   3,070   3,080   3,060
            pre-open top 5)

### BBCA — the only false negative

- **Opened inside range** at 09:00 (6,475, first 5-min close)
- **Peaked** at 6,525 (09:05–09:10)
- **Held in range** all the way to 09:45 (6,425, still inside range)
- Pre-open SKIP was incorrect — the call auction IEP (6,400 at NCP lock)
  accurately predicted the opening, and the stock stayed within the entry
  range for the entire 45-minute window.

### BMRI — correct ENTER

- Opened inside range, peaked +1.34% at 09:05, settled back to entry.
- Valid trade, no loss, but flat by 09:45.

### BUMI & BNBR — correct SKIP

- Both opened above entry range and stayed outside it all session.
- BNBR crashed from 121 (09:05–09:10) to 115–116 (09:35–09:45),
  confirming the gap-up fade pattern.

### GOTO — correct SKIP

- Flat at 50 for the entire 45 minutes. No ATR room.

### BBRI — defensible SKIP

- Not in pre-open top 5 (IEV never broke 103K).
- DISTRIBUTING tag with -1.89T smart flow. Peaked then faded from 3,120
  (09:10) to 3,060 (09:45). Distribution pattern confirmed.

---

## Pre-Open Flow for BBCA

| Run | Time | Gap% | Trend | Accum | Verdict |
|-----|------|------|-------|-------|---------|
| #1 | 08:55 | +10.5 | BEARISH | UNCONFIRMED | SKIP |
| #2 | 08:58 | +3.6 | BULLISH | UNCONFIRMED | **WATCH** |
| **#3** | **09:01** | **+2.8** | **NEUTRAL** | **UNCONFIRMED** | **SKIP ← final** |

Context at ~09:01:
- Regime: WEAK (3/7)
- Entry range: 6,017–6,533 → **opening price 6,400 inside range** ✓
- ATR band: ~4.0%
- FVWAP sell: -14.2%
- Accum score: 38.3 (needs 50 for BACKED)

---

## Layer 1 — Pre-open Trend Classification

File: `src/application/use_case/pre_open_screen.py:560-584`

### The Gate

```python
def _classify_trend_v2(gap_pct, rsi, effective_band, ...):
    if abs(gap_pct) > effective_band * 100:
        return "BEARISH"
    if 30 < rsi < 65:
        if abs(gap_pct) <= Decimal("2"):
            return "BULLISH"
    return "NEUTRAL"
```

### Why BBCA Failed at ~09:01

- `gap=+2.8%`, `RSI=59.4`, `effective_band≈4.0%`
- gap 2.8% < band 4.0% → not BEARISH (within ATR band ✓)
- gap 2.8% > hardcoded 2% → not BULLISH ✗
- → NEUTRAL → `_verdict()` returns SKIP

### Root Cause

The BULLISH threshold `Decimal("2")` is a **hardcoded literal**, not
configurable. For BBCA at 6,400, 2% = ±128 IDR ≈ 2 ticks. A gap of 2.8%
(+179 IDR) is only ~3 ticks — well within the stock's normal ATR band.

The BEARISH check uses `effective_band * 100` (ATR-scaled). The BULLISH check
should too.

---

## Layer 2 — Regime Gate (Dead Code)

File: `src/adapters/cli/screen_commands.py:1193-1198`

The `confirm-open` CLI creates `ConfirmIntradayOpenRequest` **without** a
`regime` parameter. The request DTO defaults `regime=None`, which causes the
regime gate at `confirm_intraday_open.py:90-93` to never enter the
`regime is not None` check.

**Result:** `require_backed_in_weak: true` in `config/pre_open_screener.yaml:84`
has no effect at runtime.

---

## Layer 3 — Even If the Gate Fired

If the regime gate had worked, BBCA would STILL be SKIP in WEAK regime:

```
request.regime = "WEAK"
→ gap band tightened by 0.5× (4% → 2%)
→ require_backed_in_weak + accum_tag = "UNCONFIRMED"
→ SKIP_BEARISH_CONTEXT
```

BBCA's accum_score was 38.3 (threshold 50). Even wired correctly, BBCA would
SKIP due to weak accumulation. The +0.78% peak-from-open was retail-driven
against institutional selling (FVWAP -14.2%).

---

## Recommendations

### Fix 1 — Wire regime through confirm-open (HIGH)

File: `src/adapters/cli/screen_commands.py`
1. Read `market_regime` from session sidecar
2. Pass `regime=verdict` to `ConfirmIntradayOpenRequest`
3. Add `--regime` CLI override
4. Verify `_build_market_regime` runs during pre-open

### Fix 2 — Scale BULLISH threshold by ATR (MEDIUM)

File: `src/application/use_case/pre_open_screen.py:577`

Replace:
```python
if abs(gap_pct) <= Decimal("2"):
```
With:
```python
if abs(gap_pct) <= effective_band * Decimal("50"):
```

Or add `rsi_bullish_max_gap_pct` to `config/pre_open_screener.yaml`.

### Fix 3 — Verify regime is stored in sidecar (VERIFICATION)

Sidecar had `"market_regime": null`. Fall back to last known regime when IDX
data is unavailable.

---

## Files Affected

| File | Change |
|------|--------|
| `src/adapters/cli/screen_commands.py` | Wire regime from sidecar |
| `src/application/use_case/pre_open_screen.py` | Scale BULLISH by ATR |
| `config/pre_open_screener.yaml` | Add `rsi_bullish_max_gap_pct` |

---

## Appendix: Confirmation Log (written ~09:17 WIB)

```
2026-06-17  BMRI → ENTER  (4,500 in range 4,344–4,656, flat)
2026-06-17  BBCA → WAIT  (6,400 in range — missed)
2026-06-17  BUMI → SKIP_GAP_UP  (175 > 165 ✓)
2026-06-17  BNBR → SKIP_GAP_UP  (122 > 116 ✓, crashed to 115)
2026-06-17  GOTO → SKIP_INSUFFICIENT_DATA  (flat 50)
```
