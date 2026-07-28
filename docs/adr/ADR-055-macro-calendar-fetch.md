# ADR-055: Macro Calendar Fetch (Sibling to Corporate Action Calendar)

## Status

Accepted — 2026-07-28

## Context

Stockbit exposes macroeconomic events at `GET /corpaction/economic` under the
same `/corpaction/*` family as dividends and RUPS. Corporate-action calendar v1
explicitly excluded this endpoint because macro events are not ticker-level
corporate actions and must not feed CA risk / label invalidation.

Local rates work (P2) needs a **policy-event spine** (e.g. BI rate decisions)
separate from continuous yield series (SBN / INDONIA).

## Decision

1. Add **`saham fetch macro-calendar`** as a first-class ingestion command.
2. Store events in **`macro_calendar_events`** + **`macro_calendar_sync`** —
   never in `corporate_action_*`.
3. Domain type: **`MacroCalendarEvent`** with `MacroEventCategory` (bi_rate,
   inflation, growth, trade, other). Category rules live in
   `config/macro_calendar.yaml` (first-match title substrings).
4. Reuse Stockbit JWT/session and the same cache-marker use-case pattern as
   `SyncCorporateActionCalendarUseCase`, but with separate ports and repository.
5. **Not authoritative** for MarketContext, RiskEngine, or TradeSetup until a
   later promotion ADR. This slice is fetch + store + query only.

## Consequences

- BI rate steps for sector-macro / rates maps can read `category=bi_rate`
  history without conflating corp-action risk.
- Continuous rates remain a different future command (`fetch rates` or similar).
- `saham fetch calendar` stays corp-actions only.
- Included in `saham fetch market` by default (Stockbit session required);
  opt out with `--no-macro-calendar`. Independent of `--no-enrichment` /
  `--no-calendar`.
- **P2a (done):** `policy_rate_steps` sector-macro factor kind scores BI hike/cut
  net steps from `macro_calendar_events`. Bank map uses `bi_rate_policy`
  (series `BI_RATE`) + `usd_idr_risk` instead of `^TNX`. Still DIAGNOSTIC.
- Optional later: view/browse CLI, TUI panel; continuous SBN/INDONIA (P2b).

## Non-goals (this ADR)

- Continuous SBN / INDONIA series (P2b)
- CA risk wiring
