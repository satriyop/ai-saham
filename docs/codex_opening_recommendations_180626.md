# Codex Opening Workflow Recommendations - 18 Jun 2026

## Scope

This document reviews the current `saham trade opening` and related
`saham trade intraday pre-open` workflow for the objective:

- screen potential IDX tickers during pre-opening,
- identify signal quality,
- produce actionable entry/skip guidance for short opening trades and scalping,
- preserve deterministic-first behavior and repository architecture guardrails.

Initial review was documentation-only. Critical fixes were later implemented
after the review; status is tracked below.

## Deletion Verdict

**Not safe to delete.** Items 3–10 are unimplemented and represent the only
written specification for IEP-first scoring, opening signal score, richer
confirmation gates, grade split, IEV velocity, board filters, regime in
confirmation, and constrained AI tuning. This doc is the backlog for that work.

Safe to delete when Items 3–10 are implemented or converted to tracked tasks.

## Implementation Status

Last updated: 18 Jun 2026 (re-vetted against code 20 Jun 2026)

| Item | Status | Verified |
|------|--------|---------|
| 1. Separate auction/open price from midpoint | **Implemented (core)** | ✅ Code-verified: `opening_track.py` writes `mid_price_source="top_of_book_midpoint"`, `mid_price_confidence="LOW"`; `opening_grade.py:290–316` priority chain: explicit `opening_price` → `order_book.last_price` → `mid_price` LOW. |
| 1A. Automate confirm-open from Stockbit session | **Implemented (core)** | ✅ Code-verified: `ResolveOpeningPricesUseCase` (`resolve_opening_prices.py:54`) implements running-trade → orderbook lastprice → midpoint chain with source/confidence/timestamp. `confirm-open` auto-resolves by default (`intraday_workflow_commands.py:842–874`). |
| 2. Fix NCP window validation | **Implemented** | ✅ Code-verified: `classify_opening_capture_phase()` in `opening_snapshot.py` correctly bounds the NCP window (`NCP_LOCK_TIME <= current < REGULAR_OPEN_TIME`). Snapshot writes `capture_phase`, `capture_valid_for_opening_prediction`, `capture_confidence`. `opening_tune.py:78–84` gates tuning on validity and confidence. Note: on-disk files under `data/opening/20260617/` are stale (generated before this implementation) — a fresh `saham learn snapshot && saham learn grade` will produce files with the new fields. |
| Critical gap: auto/manual confirmation metadata | **Implemented** | ✅ Code-verified: live `.last-confirmation.json` contains `opening_price_source`, `opening_price_confidence`, `opening_price_timestamp`, `auto_confirmed`, `manual_override`. |
| Critical gap: grade data-quality counts | **Implemented** | ✅ Code-verified: `opening_grade.py:263–288` computes `data_quality` with phase, validity, and price source/confidence counts. Existing `grade.json` files are stale; new runs will include the section. |
| 3. Make IEP first-class entry anchor | **Pending** | IEP is still captured/enriched, but it has not yet been promoted into first-class scoring/gating. |
| 4–10. High/medium recommendations | **Pending** | These remain future tasks. See sections below for full specifications. |

Known remaining gaps from the critical set:

- Auto confirmation does not yet use the running-trade chart endpoint as a
  fallback.
- The current implementation resolves the first available post-09:00 running
  trade from the provider result window; extremely liquid names may still need
  provider-side pagination or a wider endpoint strategy if 500 ticks is not
  enough.

## Executive Summary

The current opening workflow is a strong foundation. It already has the right
macro shape:

1. collect or fetch pre-open IEV/IEP movers,
2. run deterministic screening,
3. capture an opening snapshot,
4. track post-open order book and broker confirmation,
5. grade accuracy,
6. optionally use AI only for tuning recommendations.

After the critical implementation pass, the workflow is materially safer for
opening confirmation: midpoint is no longer treated as the primary opening
label, and `confirm-open` can resolve prices automatically from Stockbit.
Remaining work is now mainly signal quality: IEP-first scoring, richer
post-open liquidity gates, and better separation between prediction,
execution, and trade-outcome metrics.

The current implementation is now an improved pre-open watchlist plus
auto-confirmation loop. It is closer to an opening-entry workflow, but should
not yet be considered production-quality until the pending signal-quality gates
are implemented.

## Current Strengths

- Deterministic-first core is mostly preserved. Screening, confirmation,
  tracking, and grading live primarily in application use cases.
- AI is optional and non-authoritative. The tuning loop is advisory and does
  not replace rule-based screening.
- IDX call-auction awareness is already present in docs and workflow design.
  Entry is conditional on opening price being inside a calculated range.
- The system records local artifacts under `data/opening/YYYYMMDD/`, which is
  valuable for auditability and daily review.
- Existing signals are relevant for IDX opening trades:
  - IEV/IEP,
  - ATR-scaled entry range,
  - RSI overbought gate,
  - broker accumulation tag,
  - foreign VWAP context,
  - bid/offer imbalance,
  - post-open order book depth,
  - optional running-trade broker attribution.

## Critical Recommendations

### 1. Separate Auction Open From Post-Open Midpoint

Priority: Critical
Status: Implemented (core), with remaining gap for true auction print source

Current issue:

- `opening_grade.py` builds `price_series` from tracked `mid_price`.
- The first `mid_price` is then assigned to `opening_price`.
- `mid_price = (best_bid + best_offer) / 2` is not the IDX auction clearing
  price and may not be executable.
- The system already has access to better Stockbit order book fields through
  the full-depth order book provider: `lastprice`, best bid/offer, aggregate
  bid/offer lots, top-5 depth, `fnet/fbuy/fsell`, IEP, and IEV.

Why it matters:

- Entry-range hit rate can be wrong.
- IEP accuracy can be wrong.
- Trend accuracy can be wrong.
- Clean-trade rate can be wrong.
- AI tuning may optimize thresholds against the wrong label.

Recommendation:

- Keep full-depth bid pressure as the primary order book quality signal. It is
  better than top-of-book midpoint for detecting liquidity support because it
  uses aggregate depth across price levels.
- Do not replace full-depth pressure with top/mid data. Use top bid, top offer,
  and midpoint only for spread, executable friction, and fallback diagnostics.
- Store these as separate fields:
  - `auction_open_price`: actual 09:00 auction/opening print where available.
  - `first_trade_price`: first regular-session traded price after open.
  - `last_price`: Stockbit order book `lastprice`.
  - `top_bid`: best bid after open.
  - `top_offer`: best offer after open.
  - `mid_price`: diagnostic only, not a trade label.
  - `bid_pressure_ratio`: aggregate full-book pressure.
  - `depth_ratio_5`: top-5-level pressure.
  - `fnet_intraday`: live foreign net context.
- Grade entry accuracy against `auction_open_price` or `first_trade_price`,
  never against midpoint unless explicitly marked as a fallback.
- If only midpoint is available, grade should mark `price_source =
  "top_of_book_midpoint"` and lower confidence.

Layer plan for future implementation:

- Domain: add or extend value object for opening price observation if needed.
- Application: update `OpeningTrackUseCase` and `compute_grade` to preserve
  price-source semantics.
- Infrastructure: fetch actual open/last trade from a provider where available.
- Adapter: display price source and confidence only.

Implemented status:

- Added price-source-aware observation handling in `opening_track` and
  `opening_grade`.
- `opening_grade` now prefers explicit `opening_price`, then nested orderbook
  `last_price`, then low-confidence midpoint fallback.
- `mid_price` is preserved only as diagnostic/fallback data.

### 1A. Automate Confirm-Open From Stockbit Session

Priority: Critical
Status: Implemented (core), with manual override retained

Current issue:

- `confirm-open` still requires manual `--opening-json`.
- Manual input is slow and error-prone during the 09:00-09:05 decision window.
- The repository already has Stockbit session support and relevant endpoints:
  - `/company-price-feed/v2/orderbook/companies/{ticker}` for `lastprice`,
    best bid/offer, full depth, IEP/IEV, and foreign flow.
  - `/order-trade/running-trade?...` for executed ticks.
  - `/order-trade/running-trade/chart/{ticker}?...` for intraday bucket data.

Recommendation:

- Add an automatic confirmation path that reads tickers from the latest snapshot
  or sidecar and fetches post-open data through the Stockbit session.
- Prefer executed trade data as the price label:
  1. first regular-board running-trade tick at or after 09:00,
  2. Stockbit orderbook `lastprice`,
  3. historical intraday chart first bucket,
  4. top-of-book midpoint only as explicit low-confidence fallback.
- Keep manual `--opening-json` as an override and fallback for provider failure.
- Persist `price_source`, `source_timestamp`, and `auto_confirmed: true/false`.
- Fail loudly when the session is expired rather than silently falling back to
  stale or midpoint-only data.

Layer plan for future implementation:

- Domain: optional value object for `OpeningPriceObservation`.
- Application: new or extended confirmation use case owns source precedence,
  fallback policy, and confidence labels.
- Infrastructure: reuse Stockbit order book/running trade providers behind
  ports; add chart provider only if needed.
- Adapter: expose `--auto` or make auto default with `--opening-json` override.

Implemented status:

- Added `ResolveOpeningPricesUseCase`.
- `confirm-open` now auto-fetches by default and uses:
  1. first post-09:00 running-trade tick,
  2. orderbook `lastprice`,
  3. midpoint fallback when no execution/last price is available.
- `--opening-json` still overrides automatic prices.
- Confirmation output and sidecar now include price source, confidence, and
  timestamp metadata.

### 2. Fix NCP Window Validation

Priority: Critical
Status: Implemented (core), with tune-exclusion still pending

Current issue:

- `OpeningSnapshotUseCase` marks `is_ncp_locked = now.time() >= 08:56`.
- A snapshot captured at 12:56 or 17:26 is still marked NCP locked.

Why it matters:

- Backfilled or dry-run data can contaminate the learning loop.
- Tuning can learn from non-opening data.
- Users may trust a stale or post-market snapshot as an NCP signal.

Recommendation:

- Replace the boolean with explicit session metadata:
  - `capture_phase`: `PRE_NCP`, `NCP_LOCKED`, `OPEN`, `POST_OPEN`,
    `OUT_OF_SESSION`.
  - `capture_valid_for_opening_prediction`: boolean.
  - `capture_confidence`: `HIGH`, `MEDIUM`, `LOW`.
- Only mark NCP locked when capture time is inside the configured NCP window.
- Require `--force` snapshots to include a visible invalid/dry-run marker.
- Exclude invalid snapshots from `opening tune` unless explicitly overridden.

Layer plan for future implementation:

- Domain: optional enum/value object for opening session phase.
- Application: own phase classification and tuning eligibility.
- Infrastructure: not touched.
- Adapter: show phase and warnings.

Implemented status:

- Added deterministic capture phase classification:
  `PRE_NCP`, `NCP_LOCKED`, `OPEN`, `POST_OPEN`, `OUT_OF_SESSION`.
- Snapshot artifacts now include:
  - `capture_phase`,
  - `capture_valid_for_opening_prediction`,
  - `capture_confidence`,
  - compatibility field `is_ncp_locked`.
- `is_ncp_locked` is now true only inside the NCP window.

### 3. Make IEP A First-Class Entry Anchor

Priority: Critical
Status: Pending

Current issue:

- IEP is captured and stored, but entry logic is still mostly anchored to
  previous close plus range and suggested limit.
- For a call auction, IEP is the most direct pre-open estimate of the clearing
  price when it is captured during the locked period.

Recommendation:

- Treat IEP as a primary prediction input when source quality is high:
  - `iep_available`,
  - `iep_source_time`,
  - `iep_is_ncp_locked`,
  - `iep_vs_prev_close_pct`,
  - `iep_inside_entry_range`,
  - `iep_distance_to_range_edge_pct`.
- If NCP-locked IEP is outside the allowed range, downgrade or skip before
  waiting for post-open confirmation.
- If IEP is inside range and bid pressure persists into 09:00, upgrade
  confidence.
- Keep fallback behavior for missing IEP, but label confidence lower.

Layer plan for future implementation:

- Domain: value object fields only if needed.
- Application: scoring/gating belongs in `PreOpenScreenUseCase` or a dedicated
  opening signal use case.
- Infrastructure: ensure providers preserve IEP and timestamp.
- Adapter: display IEP confidence and reason codes.

## High-Priority Recommendations

### 4. Define A Dedicated Opening Signal Score

Priority: High

Current issue:

- `PRIME`, `WATCH`, and `SKIP` are derived from a small set of conditions:
  trend, accumulation tag, and unusual volume.
- That is too coarse for a fast opening scalping workflow.

Recommendation:

Create a deterministic opening score with explicit components, for example:

- IEP quality and range fit.
- IEV rank and IEV velocity.
- Gap size relative to ATR.
- Spread and tick friction.
- Bid/offer pressure during NCP.
- Post-open bid pressure persistence.
- Foreign/broker absorption.
- Market regime.
- Distribution risk.
- FCA/Rp50/special board risk.

The score should output:

- `ENTER_NOW`: only after actual open confirms.
- `WATCH`: candidate has setup but needs post-open confirmation.
- `WAIT_PULLBACK`: opening is extended but not invalid.
- `SKIP_GAP_EXTENDED`: auction/open is too far above range.
- `SKIP_LIQUIDITY`: spread/tick friction too high.
- `SKIP_DISTRIBUTION`: flow context is bearish.
- `SKIP_INVALID_BOARD`: FCA/Rp50/warrant/right/etc.

This keeps trader behavior explicit and avoids forcing all cases into
`PRIME/WATCH/SKIP`.

Layer plan for future implementation:

- Domain: decision enum/value object can live here if pure.
- Application: scoring policy and workflow orchestration.
- Infrastructure: not touched unless more fields are required.
- Adapter: render decisions and reason codes.

### 5. Add True Entry Confirmation Gates

Priority: High

Current issue:

- `confirm-open` checks opening price against entry range, trend, accumulation,
  stop width, and tick friction.
- It does not yet use enough post-open microstructure for scalping.

Recommendation:

Add deterministic gates after 09:00:

- Actual opening price is inside range.
- Spread is below max threshold in ticks or percent.
- Best bid does not collapse within the first 1-5 minutes.
- Bid pressure remains above minimum threshold or improves.
- Foreign net / broker absorption is not negative when required.
- First pullback holds above open or above predefined invalidation level.
- Stop distance and target distance both cover transaction cost and tick
  friction.

For IDX scalping, `ENTER` should mean more than "open is inside range"; it
should mean "open is inside range and liquidity confirms the setup."

Layer plan for future implementation:

- Domain: pure confirmation result fields and decision enum.
- Application: `ConfirmIntradayOpenUseCase` or a new
  `ConfirmOpeningScalpUseCase`.
- Infrastructure: provider support for last trade, spread, depth, running trade.
- Adapter: parse inputs and display decisions only.

### 6. Separate Prediction Metrics From Trade Metrics

Priority: High

Current issue:

- `opening grade` mixes prediction accuracy, trend correctness, and trade
  quality into one report.

Recommendation:

Split grade into sections:

- Prediction quality:
  - IEP error,
  - range hit,
  - gap classification,
  - trend direction.
- Execution quality:
  - spread at entry,
  - slippage from open,
  - fill feasibility,
  - available target ticks,
  - stop ticks.
- Trade outcome:
  - MFE,
  - MAE,
  - 1R available,
  - stop hit,
  - clean trade,
  - exit after 5/15/30 minutes.
- Data quality:
  - price source,
  - snapshot phase,
  - missing fields,
  - provider confidence.

This prevents the tuning loop from improving a statistical metric that does not
map to tradable outcomes.

Layer plan for future implementation:

- Domain: optional grade value objects.
- Application: `opening_grade` owns deterministic metric calculation.
- Infrastructure: not touched.
- Adapter: display sections.

## Medium-Priority Recommendations

### 7. Use IEV Velocity Carefully

Priority: Medium

IEV velocity is useful but should not blindly upgrade candidates. A late IEV
surge can mean institutional commitment, but it can also mark exhaustion or
gap-fade distribution when IEP is too extended.

Recommendation:

- Track IEV at multiple timestamps: pre-NCP, NCP start, final pre-open.
- Compute:
  - `delta_iev_abs`,
  - `delta_iev_pct`,
  - `rank_change`,
  - `iep_change_pct`,
  - `iev_velocity_phase`.
- Upgrade only when:
  - IEP remains inside ATR entry range,
  - spread is acceptable,
  - bid pressure is not one-sided and fragile,
  - stock is not FCA/Rp50/special board,
  - post-open confirmation holds.
- Downgrade when IEV velocity is high but IEP is outside range.

### 8. Strengthen Board And Instrument Filters

Priority: Medium

Current filters exclude suffixes like warrants and rights and require minimum
history, which is good. Opening scalping also needs stricter IDX instrument and
board awareness.

Recommendation:

- Explicitly identify and gate:
  - FCA / full call auction names,
  - Rp50 floor names,
  - special monitoring board,
  - newly listed IPOs,
  - suspension/reopening names,
  - stocks under unusual market activity flags where data is available.
- Do not rely only on suffix filters.
- Use deterministic `SKIP_INVALID_BOARD` or `SKIP_MICROSTRUCTURE` reason codes.

### 9. Make Market Regime Operational In Confirmation

Priority: Medium

The pre-open docs and config discuss regime gates, but the important question is
whether the final confirmation decision receives and applies regime context.

Recommendation:

- Persist regime in the snapshot and session sidecar.
- Pass regime into opening confirmation.
- In `WEAK` or `RISK_OFF` regimes:
  - require stronger IEP/range fit,
  - tighten gap tolerance,
  - require broker/foreign confirmation for second liners,
  - reduce position size or force `WAIT`.

### 10. Keep AI Tuning Advisory And Constrained

Priority: Medium

The AI tuning loop is useful, but it must never become the source of truth.

Recommendation:

- AI may propose config changes only.
- Proposed changes must include:
  - old value,
  - new value,
  - reason,
  - affected metric,
  - minimum sample size.
- Application should reject or flag recommendations from insufficient sample
  size.
- The system should support a non-AI deterministic tuning summary.

## Architecture Recommendations

### 11. Keep Adapters Thin

Priority: High

Observed risk:

- Some enrichment around strategy signals, data freshness, and regime context
  is assembled in CLI adapter code.

Recommendation:

- If a field only affects display, adapter code is acceptable.
- If a field affects screening, confirmation, grading, tuning, persistence, or
  warning severity, move it into application use cases.

Target layering:

- Domain: pure value objects, enums, indicators, and deterministic primitives.
- Application: opening workflow, scoring, gating, phase classification, grading,
  persistence decisions, and tuning eligibility.
- Infrastructure: Stockbit/Yahoo/IDX providers, SQLite repositories, browser
  automation, AI clients.
- Adapter: CLI parsing, dependency wiring, output formatting.

### 12. Create A Task Template Before Implementation

Priority: High

Before making changes, convert each recommendation into a compliant task with:

- problem statement,
- desired outcome,
- non-goals,
- affected layers,
- data read/write behavior,
- AI usage declaration,
- acceptance criteria,
- tests required.

This is required by the repository Prompt Contract and Definition of Done.

## Suggested Implementation Order

1. Fix NCP/session phase classification.
2. Separate actual opening price from top-of-book midpoint.
3. Add price source and confidence to track and grade artifacts.
4. Make IEP a first-class prediction anchor.
5. Split grade into prediction, execution, trade, and data-quality sections.
6. Add deterministic opening signal score and richer reason codes.
7. Strengthen post-open confirmation gates.
8. Persist and apply market regime in confirmation.
9. Add board/instrument microstructure filters.
10. Keep AI tuning constrained to auditable config recommendations.

## Research Notes

- IDX opening is a call-auction-style mechanism around the pre-opening window
  before the regular market opens at 09:00 WIB. The exact current NCP timing
  should be verified against the latest IDX circular before implementation.
- Public search results describe IDX pre-opening as `08:45-08:55`, followed by
  JATS price processing until `09:00`; local docs/config currently assume NCP
  lock around `08:56-09:00`.
- General opening-auction research shows indicative auction prices can move as
  order imbalance changes near the auction end, so NCP-locked IEP should be
  treated as higher quality than earlier pre-open snapshots.

References checked during review:

- Indonesia Stock Exchange trading hours summary:
  https://en.wikipedia.org/wiki/Indonesia_Stock_Exchange
- Challet, "Strategic behaviour and indicative price diffusion in Paris Stock
  Exchange auctions":
  https://arxiv.org/abs/1807.00573

## Final Recommendation

Proceed, but treat the current workflow as a calibration-grade watchlist engine
until the two critical data-quality issues are fixed:

1. true opening price must be captured separately from midpoint,
2. NCP/session validity must be classified correctly.

After those are fixed, the next highest leverage improvement is to promote IEP,
spread, bid-pressure persistence, and broker absorption into explicit entry
confirmation gates. That will align the feature with the stated objective:
screening potential tickers and producing usable signal plus entry guidance for
IDX opening scalping.
