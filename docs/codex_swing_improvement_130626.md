# Codex Swing Workflow Improvement Audit — 13 Jun 2026

## Scope

Vetted `docs/how_to_swing_trading.md`, `docs/workflow_swing_foreign_accumulation.md`, README swing references, and the swing CLI command family.

Commands were run as a user against local `data.db` on 2026-06-13. No AI provider was used for decisions; all conclusions below are from deterministic CLI output and source inspection.

## Workflow Run Evidence

Local data coverage before analysis:

- `candles`: 6,378 rows, date range 2025-01-30 to 2026-06-12.
- `broker_summaries`: 3,991 rows, date range 2025-12-29 to 2026-06-12.
- `saham update --universe lq45 --days 30`: 45/45 tickers originally reported cache-skip statuses. The refresh behavior later changed so default update attempts forward gap-fill; `cached-current` now means cache already reaches today, while `provider-no-new-data(latest=YYYY-MM-DD)` means the provider was checked but had no newer trading row.

Daily workflow run:

- `saham regime`: `WEAK`, score `2/7`; breadth above SMA20 `14.7%`, benchmark 20d return `-13.28%`, foreign flow breadth `26.5%`.
- `saham swing screen --universe lq45 --multi --min-score 50 --top 10`: top candidates were `GOTO`, `GGRM`, `EXCL`, `INDF`, `ACES`.
- `saham swing analyze GOTO --preset foreign-bounce --capital 10000000 --with-regime`: `WATCH`; score `68.9`, `LOW_RISK`, failed score and VWAP gates.
- `saham swing analyze GGRM --preset foreign-bounce --capital 10000000 --with-regime`: `AVOID`; score `69.8`, `HIGH_RISK`, failed score, VWAP, and trend gates.
- `saham swing size GOTO --capital 10000000`: 1,511 lots, entry `50`, stop `49`, target `51`, capital used `75.5%`.
- `saham swing backtest --universe lq45 --start 2026-01-01 --with-regime --show-trades 10`: return `+3.77%`, max drawdown `-1.78%`, 9 trades, win rate `66.7%`, PF `2.71`.
- `saham swing compare --universe lq45 --start 2026-01-01`: baseline `+3.77%`, `sideways_only` `+2.98%` with lower drawdown `-0.31%`, `weak_plus` `+2.98%`.
- `saham swing log --ticker GOTO --window 7`: wrote one journal entry with score `68.9`, pattern `sustained`.
- `saham swing review --horizon 10`: 1 entry, 0 with 10d+ data.

## Fixed During Audit

- Corrected docs from invalid `saham swing TICKER` / `saham screen accumulation` references to the actual command surface: `saham swing analyze`, `saham swing screen`, `saham swing audit`, `saham swing log`, `saham swing review`.
- Corrected invalid `saham regime --with-regime`; `--with-regime` belongs to `saham swing analyze` and `saham swing backtest`.
- Corrected multi-ticker `saham fetch BUMI GOTO BREN` / `saham broker fetch BUMI GOTO BREN`; those commands accept one ticker at a time.
- Updated CLI help strings so `saham swing analyze --help`, `saham swing screen --help`, and sizing examples match runnable commands.

## Improvements To Prioritize

### 1. Make Swing Windows Use Trading Sessions, Not Calendar Days

Status: implemented after audit.

Why:

- Before the fix, docs described 7d/30d/90d as trading windows, but `AccumulationScreenUseCase` computed `cutoff = today - timedelta(days=window_days)`.
- Live evidence before the fix: `saham swing analyze GOTO` showed `NET_DAYS 3/3` for `7d`, while `saham broker flow GOTO --days 30` showed 23 trading days and a 15-day buy streak.
- `saham swing screen --window 30 --breakdown --top 5` showed GOTO as `15/15`, confirming the current window length is calendar-driven and depends on holidays/weekends/data lag.

Implemented behavior:

- `--window 7` evaluates the latest 7 broker sessions available as of the analysis date.
- `--window 30` and `--window 90` similarly use broker-session counts.
- User-facing output now labels accumulation windows as sessions rather than calendar days.

Benefit:

- Preset gates, streaks, backtests, and journaled scores become stable and match the swing-trading concept users expect.

### 2. Display Source Data Dates And Freshness Warnings In Swing Output

Status: implemented after audit.

Why:

- The screen printed `2026-06-13`, but GOTO candle/broker data used in outputs was through `2026-06-10`.
- The regime command used `Date: 2026-06-13`, while the market was last cached on prior trading dates.
- Users need to know whether they are analyzing today, the latest market session, or stale cached data.

Implemented behavior:

- `saham swing analyze` shows a `DATA` section with `Analysis date`, `Candles through`, `Broker flow through`, and `Regime as of` when regime context is requested.
- `saham swing analyze` auto-refreshes only the requested ticker's candles and broker flow by default, reports refresh status in `DATA`, supports `--no-refresh` for cached-only/offline runs, and supports `--force-refresh` for explicit provider refresh.
- Warnings are shown when candle/broker dates differ, or when latest cached source data is older than the analysis date.
- JSON output includes the same fields under `data`.

Benefit:

- Prevents false confidence in “today” signals and makes offline/local-first behavior auditable.

### 3. Integrate Broker Flow Detail Into The Candidate Deep Dive

Why:

- `saham broker flow GOTO --days 30` exposed strong detail not present in `saham swing analyze`: total net flow `71.81B`, 19 buy days, 4 sell days, and 15 consecutive buy days.
- Before the session-window fix, the unified analyze output only showed the 7-day calendar-window view: `STREAK 3d`, `NET_DAYS 3/3`, `FLOW% +83.2%`.

Expected behavior:

- Implemented: `saham swing analyze` now includes a compact `FLOW DETAIL` section built from cached broker summaries after the single-ticker refresh path.
- The section includes 30-session buy/sell count, total net value, consecutive net-buy streak, average flow ratio, latest net flow, latest ratio, and latest flow date.
- JSON output includes the same fields under `flow_detail`.

Benefit:

- Users can distinguish a genuinely persistent institutional accumulation pattern from a short recent burst.

### 4. Add A Realistic Trading Cost Default Or Workflow Guidance

Why:

- Before this fix, `saham swing backtest` defaulted `--cost-bps 0.0`.
- The backtest output correctly warned that intraday execution/slippage is not modeled, but the docs’ main examples did not teach users to include costs.
- The observed 2026 LQ45 backtest return was only `+3.77%`; transaction costs can materially change thin-edge strategies.

Expected behavior:

- Implemented: `saham swing backtest` and `saham swing compare` default to `--cost-bps 20`, a one-way transaction-cost assumption applied on entry and exit.
- Implemented: table and JSON output record the cost assumption.
- Implemented: docs explain `20` bps as an Indonesian retail-fee approximation and document `--cost-bps 0` for intentional gross/no-cost comparisons.

Benefit:

- Backtest results become closer to executable paper/live expectations without changing deterministic strategy logic.

### 5. Improve Sentiment Failure Handling In Unified Swing Output

Why:

- `saham swing analyze GOTO` printed raw RSS/network errors before the swing table, then displayed `News unavailable`.
- `saham sentiment GOTO --no-ai` still attempted RSS/network fetch and returned zero headlines.
- Sentiment is optional context per ADR-015, but current output noise can distract from deterministic gates.

Expected behavior:

- Implemented: `saham swing analyze` suppresses optional sentiment provider stdout/stderr/log noise into a concise `SENTIMENT` warning by default.
- Implemented: `--sentiment-verbose` shows provider details for debugging.
- Documented: `--no-sentiment` is the fully offline deterministic workflow.

Benefit:

- Cleaner command output and stronger separation between deterministic swing gates and optional external news context.

### 6. Integrate Existing Chart Commands Into Confirmation Workflow

Why:

- Existing commands work: `saham chart price GOTO`, `saham chart rsi GOTO`, and `saham chart volume GOTO`.
- Current swing docs mention indicators numerically but do not guide users to visually confirm price base, RSI headroom, or volume participation.

Expected behavior:

- Implemented: added a chart-structure confirmation step after `saham swing analyze` in both swing workflow docs:
  - `saham chart price TICKER --sma 20 --days 90`
  - `saham chart rsi TICKER --days 90`
  - `saham chart volume TICKER --days 30`
- The docs now explain what to confirm or avoid for price structure, RSI, and volume.
- Optional future improvement remains: `saham swing analyze --charts` to print compact charts inline.

Benefit:

- Uses existing application features to reduce bad entries caused by unreadable price structure, without introducing AI or new dependencies.

### 7. Journal The Actual Trade Decision, Not Only The Candidate Score

Why:

- `saham swing log --ticker GOTO --window 7` logged score and pattern even though the preset classification was `WATCH`, not `ENTER`.
- The journal review later had 1 entry but 0 enriched outcomes, which is expected before 10 trading days, but the entry does not preserve the gate decision, regime, or planned stop/target.

Expected behavior:

- Implemented: `saham swing log --from-analysis` records the preset name, classification (`ENTER/WATCH/AVOID`), failed gates, planned entry, stop, target, and max hold.
- Implemented: add `--with-regime` to the log command to persist the market regime label in the same journal row.
- Implemented: `saham swing review` now includes a performance-by-preset-decision table so `ENTER`, `WATCH`, `AVOID`, and legacy `unknown` rows can be compared.
- Existing lightweight behavior remains available by omitting `--from-analysis`.

Benefit:

- Review can answer whether `ENTER` signals outperform `WATCH` signals and whether failed gates matter historically.

## Current Best Candidate From This Run

No clean `ENTER` setup was found in the tested LQ45 workflow.

- `GOTO`: strongest watchlist candidate, but `WATCH` only. Before the session-window fix it had strong accumulation context (`30d score 84.9`, `15/15` broker sessions, `FLOW% +55.0%`) but failed the 7d preset score gate (`68.9 < 70`) and VWAP defense gate (`+0.0% < +3%`) while market regime was `WEAK`.
- `GGRM`: `AVOID` before the session-window fix despite 30d score `75.9`, because trend was `DOWN`, 7d score was below 70, and risk confirmation was `HIGH_RISK`.

Ideal action from the current workflow: do not paper-enter as a confirmed preset trade; journal GOTO as a watch candidate only, then re-run after the next broker-flow update.

## DoD And Architecture Notes

- Determinism preserved: recommendations are rule/workflow/documentation focused.
- AI remains optional and non-authoritative.
- No domain logic was changed during this audit.
- Persistence touched by command execution: `journals/accumulation.csv` was created/updated by `saham swing log`, as requested by the paper workflow run.
