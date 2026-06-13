# Codex Intraday Workflow Improvement Audit — 13 Jun 2026

## Scope

Vetted `docs/how_to_intraday_trading.md`, `docs/workflow_intraday_preopening.md`, the `saham intraday` CLI family, Stockbit helper commands, and adjacent existing features that can improve intraday/pre-opening workflow quality.

Commands were run as a user against local `data.db` on Saturday, 2026-06-13 Asia/Jakarta. No AI provider was used for decisions. Live market pre-open was unavailable because this was a non-trading day; manual JSON mode was used for deterministic workflow simulation.

## Documentation Updates Made

- `docs/workflow_intraday_preopening.md`
  - Replaced invalid multi-ticker `saham fetch ...` / `saham broker fetch ...` setup examples with runnable `saham update TICKER... --days 365`.
  - Marked `saham stockbit spy` as optional debugging, not a daily prerequisite.
  - Clarified `saham intraday log` / `confirm-log` and `review` / `confirm-review` aliases.
  - Clarified that confirmation review uses manual outcomes first, then daily OHLC proxy when manual outcomes are missing.
- `docs/how_to_intraday_trading.md`
  - Added the complete intraday command surface exposed by `saham intraday --help`.
  - Clarified Stockbit spy as debugging only.
  - Clarified journal/review aliases and daily-OHLC proxy behavior.
- `src/adapters/cli/screen_commands.py`
  - Corrected stale help/error examples from `saham screen intraday ...` to `saham intraday ...`.
- `config/pre_open_screener.yaml`
  - Moved the pre-open screener policy out of `strategies/` because it is not a backtest strategy package.
  - Corrected metadata from AI-required to deterministic-by-default with optional `--with-ai` research.
- `src/adapters/cli/screen_commands.py`
  - `saham intraday pre-open` now loads `config/pre_open_screener.yaml` by default.
  - Added `--config/-c` for screener policy files and kept `--strategy/-s` as a deprecated alias.

## Command Surface Verified

`saham intraday --help` exposes:

- `pre-open`
- `confirm-open`
- `log` / `confirm-log`
- `review` / `confirm-review`
- `outcome` / `confirm-outcome`
- `pre-open-log`
- `pre-open-review`
- `save-session` deprecated in favor of `saham stockbit login`

`saham stockbit --help` exposes:

- `login`
- `status`
- `spy`
- `test`
- `fetch-top5`

## Workflow Run Evidence

Local data freshness:

- `candles` latest date: `2026-06-12`.
- `broker_summaries` latest date: `2026-06-12`.
- Escalated `saham update --universe cached --days 5 --candles-only`: `83 ok`, all reported `provider-no-new-data(latest=2026-06-12)`.

Stockbit/session checks:

- `saham stockbit status`: saved session age `8.9h`, status `possibly expired`.
- `saham stockbit fetch-top5 --top 5`: failed fast with `Stockbit session is 9.0h old — likely expired`.
- `saham intraday pre-open --top 5`: failed fast for the same expired session.
- Escalated `saham stockbit test`: movers failed with expired session; orderbook failed with `Stockbit API session expired (401)`.

Manual pre-open simulation:

```bash
saham intraday pre-open \
  --movers-json '[{"ticker":"BNBR","iev":428497},{"ticker":"BUMI","iev":972420},{"ticker":"BBRI","iev":373423},{"ticker":"BBCA","iev":297068},{"ticker":"CUAN","iev":281822}]' \
  --order-books-json '{"BNBR":{"price":109,"volume":32009},"BUMI":{"price":157,"volume":409437},"BBRI":{"price":2850,"volume":219024},"BBCA":{"price":5875,"volume":33568},"CUAN":{"price":715,"volume":2923}}'
```

Result:

- `BNBR`: `PRIME`, IEV `428,497`, gap `-0.9%`, entry range `104-116`, stop `-7.2%`, RSI `43`, signal `BACKED x3d`, FVWAP `+8.8% floor`.
- `BUMI`: `WATCH`, IEV `972,420`, gap `+0.0%`, entry range `149-165`, stop `-7.0%`, RSI `42`, signal `UNCONFIRMED x2d`, FVWAP `+0.2% floor`.
- `BBRI`, `BBCA`, `CUAN`: `SKIP`, mostly distribution or sell-risk context.

Confirm-open simulation:

```bash
saham intraday confirm-open --opening-json '{"BNBR":110,"BUMI":158}'
```

Result:

- `BUMI`: `ENTER`, limit buy `158`, stop `147`, target prev high `162`.
- `BNBR`: `ENTER`, limit buy `110`, stop `103`, target prev high `114`.
- `BBRI`, `BBCA`, `CUAN`: `SKIP_INSUFFICIENT_DATA` because the sidecar still contained all pre-open rows and no opening prices were supplied for those tickers.

Journal/review:

- `saham intraday log --confirmation /tmp/codex-intraday-confirmation.json --journal /tmp/codex-intraday-confirmations.csv`: logged `5` confirmations.
- `saham intraday outcome BUMI --entry 158 --exit 162 --result target --date 2026-06-13`: recorded `+0.36R`.
- `saham intraday review --journal /tmp/codex-intraday-confirmations.csv`: `5` rows, `2` ENTER rows, `1` row with manual outcome, ENTER average `+0.36R`.
- `saham intraday pre-open-review --journal /tmp/codex-pre-open.csv --horizon 5`: `0` entries with DB data because screen date was Saturday 2026-06-13 and local candles stop at Friday 2026-06-12.

Additional analysis:

- `saham compute ATR BNBR --tail 5`: latest ATR `16.32`.
- `saham compute ATR BUMI --tail 5`: latest ATR `14.34`.
- `saham risk BNBR --all`: conservative `MODERATE`, balanced/aggressive `LOW_RISK`.
- `saham risk BUMI --all`: conservative `MODERATE`, balanced/aggressive `LOW_RISK`.
- `saham broker flow BNBR --days 20`: 8 trading rows available, total net flow `26.35B`, 6 buy days, 2 sell days, 4 consecutive buy days.
- `saham broker flow BUMI --days 20`: 8 trading rows available, total net flow `657.75B`, 6 buy days, 2 sell days, 2 consecutive buy days.
- `saham regime --format json`: market regime `WEAK`, score `2`, benchmark 20d return `-13.2845%`, breadth above SMA20 `23.5294%`.
- `saham swing screen BNBR BUMI --window 7 --breakdown`: no candidates found.
- `saham backtest BNBR --strategy pre-open-screener`: failed because `pre-open-screener` is not a backtest strategy YAML (`missing required field default_outcome`).
- `saham backtest BNBR --strategy rsi-momentum --start 2026-03-01`: 0 trades.
- `saham backtest BUMI --strategy rsi-momentum --start 2026-03-01`: 0 trades.
- `saham backtest BNBR --strategy foreign-accumulation --start 2026-03-01`: 0 trades.
- `saham chart price BNBR --days 30`: failed because optional `plotext` is not installed.

## Current Best Workflow From The Existing Application

1. Before market day: `saham update --universe lq45` or `saham update TICKER... --days 365`.
2. Check Stockbit session: `saham stockbit status`; run `saham stockbit login` if expired.
3. Optional raw-data check: `saham stockbit fetch-top5 --top 10`.
4. Pre-open screen: `saham intraday pre-open --top 5`, or manual `--movers-json` plus `--order-books-json`.
5. Cross-check only watchlist candidates with existing features:
   - `saham broker flow TICKER --days 20`
   - `saham risk TICKER --all`
   - `saham compute ATR TICKER --tail 5`
   - `saham regime`
6. At open: `saham intraday confirm-open --opening-json '{"TICKER":OPEN}'`.
7. Paper log: `saham intraday log`.
8. Record execution: `saham intraday outcome TICKER --entry X --exit Y --result target|stop|manual|breakeven`.
9. Review after enough sessions: `saham intraday review` and `saham intraday pre-open-review --horizon 1`.

## Improvements To Prioritize

### 1. Add Trading-Day And Market-Window Guards

Status: implemented after audit.

Why:

- The pre-open command ran and logged a `2026-06-13` session even though it was Saturday.
- Local candles and broker data were current only through `2026-06-12`.
- `pre-open-review` then had `0` entries with DB data because no candle exists on or after the logged Saturday screen date.

Implemented behavior:

- `saham intraday pre-open` now blocks weekend runs by default before fetching data or writing the sidecar.
- `--allow-non-trading-day` explicitly permits dry-runs/backfills and keeps a visible warning in output.
- Runs outside the configured IDX pre-open window `08:45-09:00` Asia/Jakarta emit a warning.
- Output now includes `DATA: Analysis date ... Candles through ... Broker flow through ...`.
- Freshness warnings are emitted when candle or broker-flow dates lag the analysis date or differ from each other.

Verification:

- `saham intraday pre-open --movers-json '[{"ticker":"BNBR","iev":428497}]' --fast` on Saturday 2026-06-13 exited with `Pre-open guard: 2026-06-13 is a weekend in Asia/Jakarta`.
- The same command with `--allow-non-trading-day` ran and printed data freshness through `2026-06-12` plus weekend/out-of-window warnings.
- `./.venv/bin/pytest tests/adapters/cli/test_screen_commands.py`: `10 passed`.

Benefit:

- Prevents invalid paper-journal rows and avoids mistaking a dry-run for a market session.

### 2. Fix Stale CLI Help And Error Text That Says `saham screen intraday`

Status: fixed during audit.

Why:

- Before the fix, runtime help for `saham intraday pre-open --help`, `confirm-open --help`, and several error messages displayed examples like `saham screen intraday pre-open`.
- The actual registered command is `saham intraday ...`.

Implemented behavior:

- All help text, examples, sidecar comments, and error messages should use `saham intraday ...`.
- `rg` found no remaining `saham screen intraday` or `saham screen save-session` references in the touched intraday files.

Benefit:

- Reduces copy-paste failures during the 08:45-09:05 execution window.

### 3. Move `pre-open-screener` Out Of Strategies And Correct Metadata

Status: fixed during audit.

Why:

- Before the fix, `strategies/pre-open-screener/strategy.yaml` said `Requires: ANTHROPIC_API_KEY` and `Mode: AI Mode ON`.
- Actual code only creates AI research when `--with-ai` is passed.
- The audited workflow ran deterministically without AI.
- The file was a screener policy config, not a `saham backtest --strategy` package; `saham backtest BNBR --strategy pre-open-screener` failed with `missing required field default_outcome`.

Implemented behavior:

- The screener policy now lives at `config/pre_open_screener.yaml`.
- `strategies/pre-open-screener/strategy.yaml` was removed.
- `saham intraday pre-open` defaults to `config/pre_open_screener.yaml`.
- `--config/-c` selects an alternate pre-open screener policy.
- `--strategy/-s` remains as a deprecated alias for compatibility and prints a warning.
- The config metadata now says Stockbit browser session is required only for autonomous mode, while AI research is optional and only runs with `--with-ai`.
- `mode` is `deterministic`.
- Document `--with-ai` as exploratory context only, not a decision source.

Benefit:

- Aligns with ADR-001/ADR-002 and avoids making a non-AI workflow look cloud-dependent.
- Prevents users from treating a screener config as a generic backtest strategy.

### 4. Integrate Existing Market Regime Into Intraday Screening

Why:

- `saham regime --format json` returned `WEAK`, score `2`, benchmark 20d return `-13.2845%`, and breadth above SMA20 `23.5294%`.
- The pre-open output did not show this market context.
- Intraday long setups during weak broad-market regimes should probably require stricter confirmation or smaller sizing.

Implemented behavior:

- Added optional `--with-regime` to `saham intraday pre-open`.
- Added `--regime-universe` with default `idx80` and `--benchmark` with default `^JKSE`.
- Output now prints a compact line such as:

```text
REGIME: WEAK score=2/7   ^JKSE 20d -13.28%   Breadth SMA20 23.53%   Foreign breadth 39.71%
```

- Regime context is written to `journals/.last-session.json` so later intraday logging/review can inspect the session context.
- Regime does not override deterministic candidate gates. `PRIME`, `WATCH`, and `SKIP` remain pre-open screener verdicts. `WEAK` and `RISK_OFF` add warnings to tighten confirmation or reduce size.

Verification:

- `./.venv/bin/saham intraday pre-open --movers-json '[{"ticker":"BNBR","iev":428497}]' --fast --allow-non-trading-day --with-regime --config config/pre_open_screener.yaml` printed `REGIME: WEAK score=2/7`, kept `BNBR` as `PRIME`, and added `Market regime is WEAK; require cleaner opening confirmation or reduce size.`
- `./.venv/bin/saham intraday pre-open --help` shows `--with-regime`, `--regime-universe`, and `--benchmark`.
- `./.venv/bin/pytest tests/adapters/cli/test_screen_commands.py` passed with `14 passed`.

Benefit:

- Reuses existing deterministic regime logic and helps avoid long bias on weak-market mornings.

### 5. Integrate Broker Flow Detail Into Candidate Deep Dive

Why:

- Pre-open `SIGNAL` showed compact tags, but `saham broker flow` added useful facts:
  - `BNBR`: total net flow `26.35B`, 6 buy days, 4 consecutive buy days.
  - `BUMI`: total net flow `657.75B`, 6 buy days, 2 consecutive buy days.
- This explains why `BNBR` was `BACKED` while `BUMI` stayed `UNCONFIRMED`.

Expected behavior:

- Add `saham intraday pre-open --details` or a per-candidate detail section for watchlist names.
- Include buy/sell day counts, consecutive buy days, total net flow, latest net flow, and latest broker-flow date.

Benefit:

- Users can distinguish institutional continuation from one-day IEV spikes without leaving the intraday workflow.

### 6. Make Confirm-Open Input Scope Explicit

Why:

- Passing opening prices only for watchlist names still loaded all five sidecar candidates.
- The output logged `SKIP_INSUFFICIENT_DATA` rows for skipped tickers with missing opening prices.
- `saham intraday log` then persisted all 5 rows.

Expected behavior:

- Either filter confirmation to tickers present in `--opening-json`, or add an explicit `--all-candidates` mode.
- Output should say whether missing opening prices are skipped from logging or logged as insufficient data.

Benefit:

- Cleaner journals and less distorted review buckets.

### 7. Add A Real Pre-Open Backtest/Audit Path

Why:

- `saham backtest --strategy pre-open-screener` fails because the screener YAML is not a strategy package.
- Generic strategies (`rsi-momentum`, `foreign-accumulation`) produced 0 trades for the tested candidates and do not validate the pre-open/open-confirm workflow.
- `pre-open-review` measures entry-range and direction accuracy, not trade profitability.

Expected behavior:

- Add an intraday-specific audit command over journaled pre-open/confirm rows, using manual outcomes first and daily OHLC proxy second.
- Report entry-range hit rate, ENTER win rate, average R, stop/target proxy assumptions, and sample size.
- Keep limitations explicit: exact intraday sequencing requires minute/tick data.

Benefit:

- Users can validate the actual workflow they are paper trading instead of unrelated daily strategies.

### 8. Add Position Sizing To Confirm-Open Output

Why:

- Docs teach manual lot sizing, but `confirm-open` output only shows limit, stop, and target.
- The command already has enough data to calculate risk per share from planned entry and stop.

Expected behavior:

- Add `--capital` and `--risk-pct` to `confirm-open`, or carry `capital` from pre-open sidecar.
- For each ENTER, print max lots, position value, risk amount, and stop distance.

Benefit:

- Reduces manual calculation errors during the fast opening window.

### 9. Improve Stockbit Diagnostics For Expired Sessions

Why:

- `status`, `fetch-top5`, and `pre-open` correctly detected the expired session.
- `stockbit test` continued into orderbook testing and returned a second 401.

Expected behavior:

- If session age or first API check indicates expiry, `stockbit test` should stop and print one action: `saham stockbit login`.
- Optionally add `--continue-on-failure` for adapter debugging.

Benefit:

- Cleaner operator feedback before market open.

### 10. Document Optional Chart Dependency Or Avoid Chart Step By Default

Why:

- `saham chart price BNBR --days 30` failed with `plotext not installed`.
- Charts are useful confirmation tools but are optional per README.

Expected behavior:

- If charts are included in intraday workflow docs, state `pip install plotext` or `pip install -e ".[dev]"` if that installs it.
- Otherwise keep charting as optional confirmation, not a required workflow step.

Benefit:

- Avoids a dead-end command during preparation.

## Current Candidate Assessment From This Run

This was a deterministic dry-run, not a live trading recommendation.

- `BNBR`: strongest setup from pre-open screen (`PRIME`), supported by `BACKED x3d`, FVWAP `+8.8% floor`, broker-flow total net `26.35B`, 4 consecutive buy days, daily risk balanced/aggressive `LOW_RISK`. Confirm-open at `110` produced `ENTER`, stop `103`, target prev high `114`.
- `BUMI`: valid watch setup (`WATCH`), large broker-flow total net `657.75B`, but only `UNCONFIRMED x2d` and FVWAP `+0.2% floor`. Confirm-open at `158` produced `ENTER`, stop `147`, target prev high `162`.
- Market context was weak (`saham regime`: `WEAK`, score `2`), so a stricter workflow would reduce size or demand stronger confirmation.

## DoD And Architecture Notes

- Determinism preserved: recommendations are based on observed CLI behavior and local data.
- AI remains optional and non-authoritative.
- No domain logic was changed during this audit. Adapter help text and screener metadata were updated for clarity.
- Persistence touched by command execution:
  - `journals/.last-session.json` was overwritten by the dry-run pre-open command.
  - Temporary paper journals were written under `/tmp/codex-*.csv`.
- Existing user changes were not reverted.
