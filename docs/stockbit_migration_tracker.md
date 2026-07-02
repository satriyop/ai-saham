# Stockbit Migration Tracker
# Playwright-per-invocation → Persisted JWT

**Plan file:** `~/.claude/plans/lets-plan-to-migrate-wobbly-manatee.md`  
**Goal:** Eliminate Playwright from all data fetching paths. Browser kept only for `login`, `spy`, `browse`.

---

## Status Legend
- `[ ]` Not started
- `[~]` In progress
- `[x]` Done
- `[!]` Blocked

---

## Phase A — StockbitTokenStore  (PR 1)
- [x] Create `src/infrastructure/browser/stockbit_token_store.py`
  - [x] `StockbitTokenStore` class with `load()`, `save()`, `clear()`
  - [x] `_decode_exp()` — base64 JWT payload, no sig verify → `int | None`
  - [x] `_is_valid()` — JWT `exp` claim first, fallback to `fetched_at + 8h`
  - [x] Atomic write (tmp + `os.replace`), chmod 0600
  - [x] Storage: `.stockbit_profile/token.json`
- [x] Create `tests/infrastructure/browser/test_stockbit_token_store.py` — 18/18 ✓

**Entry condition:** none — can start immediately  
**Exit condition:** unit tests green

---

## Phase B — StockbitApiClient  (PR 2)
- [x] Create `src/infrastructure/browser/stockbit_api_client.py`
  - [x] `StockbitSessionExpired` (moved from `playwright_stockbit_browser.py`)
  - [x] `StockbitApiClient` class: `get(url, params) → dict | None`
  - [x] 401 → refresh once → retry (`already_refreshed` guard prevents double browser launch)
  - [x] `create_stockbit_api_client()` factory (builds shared instance)
- [x] Add `extract_exodus_token(profile_dir, headless, timeout) → str | None` to `playwright_stockbit_browser.py` (additive only)
- [x] Create `tests/infrastructure/browser/test_stockbit_api_client.py` — 9/9 ✓

**Entry condition:** Phase A complete  
**Exit condition:** unit tests green, `playwright_stockbit_browser.py` still importable

---

## Phase C — Migrate 21 data modules  (PR 3)  ✅ DONE — 680 tests green
- [x] `stockbit_analyst.py`
- [ ] `stockbit_bandar.py`
- [ ] `stockbit_broker_distribution.py`
- [ ] `stockbit_company_profile.py`
- [ ] `stockbit_corp_action.py`
- [ ] `stockbit_earnings.py`
- [ ] `stockbit_forward_estimates.py`
- [ ] `stockbit_fundamentals.py`
- [ ] `stockbit_insider.py`
- [ ] `stockbit_intraday_broker_chart.py`
- [ ] `stockbit_market_time.py`
- [ ] `stockbit_order_book.py`
- [ ] `stockbit_running_trade.py`
- [ ] `stockbit_running_trade_chart.py`
- [ ] `stockbit_seasonality.py`
- [ ] `stockbit_shareholding.py`
- [ ] `stockbit_ticker_notation.py`
- [ ] `stockbit_universe.py`
- [ ] `stockbit_valuation.py` ← also fixes `fetch_json` latent bug
- [ ] `src/infrastructure/data_providers/stockbit_historical.py`
- [ ] Update TYPE_CHECKING imports: `StockbitPlaywrightBrokerProvider` → `StockbitApiClient`
- [ ] Drop local `_exodus_get` imports from modules
- [ ] Rename `broker_provider=` → `api_client=` in ~20 test files
- [ ] Switch `monkeypatch _exodus_get` tests to inject fake api_client

**Mechanical change per module:**
1. Constructor: `broker_provider: BrowserDataProvider | None` → `api_client: StockbitApiClient | None`
2. `self._provider` → `self._api_client`
3. `token = self._provider._get_token(); _exodus_get(url, token)` → `self._api_client.get(url)`
4. Valuation only: `self._provider.fetch_json(url)` → `self._api_client.get(url)`

**Entry condition:** Phase B complete  
**Exit condition:** all existing tests still green, no browser import in data modules

---

## Phase D — Migrate IEV/OrderBook + Re-home Broker Methods  (PR 4) ✅ DONE — 2099 tests green
- [x] Modify `PlaywrightStockbitProvider` in `playwright_stockbit_provider.py`
  - [x] Constructor takes `api_client: StockbitApiClient`
  - [x] Remove browser launch from `fetch_preopen_movers`, `fetch_top5_iev_with_orderbooks`, `fetch_iev_snapshot`, `_fetch_order_book_raw`
  - [x] Refactor `_fetch_iev_all_boards(api_client)` (was token-taking)
  - [x] Delete `_scrape_movers_from_dom` (dead code)
  - [x] Delete `_scrape_best_bid_from_dom` (dead code)
  - [x] Keep `_assert_session_fresh()` (reads `.logged_in_at`, no browser)
- [x] Re-home broker methods BEFORE deleting `StockbitPlaywrightBrokerProvider`
  - [x] Create `StockbitBrokerProvider(api_client)` (in `playwright_stockbit_provider.py`)
  - [x] Move: `fetch_broker_summaries`, `fetch_foreign_top_stocks`, `fetch_foreign_flow_history`, `fetch_broker_daily_flows`
- [x] `StockbitPlaywrightBrokerProvider = StockbitBrokerProvider` alias (backward compat for Phase F)
- [x] Fix adapter cache-only path: `broker_provider=None` → `api_client=None` in `fetch_market_commands.py` and `screen_pre_open_commands.py`

## Phase E — Slim Browser Module + Delete Broker Provider  (PR 4 continued) ✅ DONE
- [x] `_exodus_get` kept in `playwright_stockbit_browser.py` (backward compat; Phase F removes last callers then we delete)
- [x] `StockbitSessionExpired` kept in `playwright_stockbit_browser.py` (same reason)
- [x] `StockbitPlaywrightBrokerProvider` replaced by alias `= StockbitBrokerProvider` (will remove after Phase F)

**Note:** Full `StockbitPlaywrightBrokerProvider` deletion and `_exodus_get` removal deferred to Phase F cleanup.

**Entry condition:** Phase C complete  
**Exit condition:** ✅ 2099 tests green

---

## Phase F — Wiring  (PR 5) ✅ DONE — 2111 tests green
- [x] CLI adapters — replaced `StockbitPlaywrightBrokerProvider()` with `create_stockbit_api_client()` + `StockbitBrokerProvider`:
  - [x] `fetch_market_commands.py` — `_create_broker_provider`, `_fetch_candles`, `_fetch_enrichment` (isinstance check + 13 providers)
  - [x] `fetch_broker_commands.py`
  - [x] `fetch_universe_commands.py` — `universe_update`, `universe_create`, `inspect`
  - [x] `view_broker_commands.py`
  - [x] `view_ticker_display.py` — 10 `api_client=None` sites
  - [x] `learn_commands.py` — 3 blocks (market time, running trade, order book)
  - [x] `trade_intraday_commands.py`
  - [x] `stockbit_market_time.py` — `fetch_and_cache_market_status`, `get_current_market_status`
- [x] `StockbitPlaywrightBrokerProvider = StockbitBrokerProvider` alias **removed**
- [x] Test updates: `test_fetch_universe_commands.py` (mocks + 5 monkeypatches), `test_trade_intraday_commands.py` (2 mock ctors + 1 monkeypatch), `test_fetch_market_commands.py` (FakeStockbitHistoricalProvider)

**Entry condition:** Phase D+E complete  
**Exit condition:** ✅ 2111 tests green, no `StockbitPlaywrightBrokerProvider` reference outside git history

---

## Phase H — Skills + ADR  (PR 6) ✅ DONE
- [x] Create `~/.claude/skills/stockbit-api-explorer/SKILL.md`
  - Auth model diagram, file map, adding a new provider, endpoint patterns, test patterns, common mistakes
- [x] Create `~/.claude/skills/codebase-known-pitfalls/SKILL.md`
  - `fetch_json` latent-bug pattern, single api_client rule, removed symbols, monkeypatching instance methods
- [x] Add ADR-036 to `ARCHITECTURE_DECISIONS.md`

**Entry condition:** Phase F complete and verified  
**Exit condition:** ✅ skills created, ADR-036 committed

---

## Verification Checklist (after Phase F)

```bash
python -m pytest tests/ -x                              # full suite green
saham fetch stockbit status                              # no browser
saham fetch stockbit login                               # browser once — creates token.json
saham fetch broker --ticker BBRI --days 30              # httpx only, no browser
saham analyze risk BBRI                                  # httpx only
saham screen accum --universe lq45                       # httpx only
python -c "from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider; print('ok')"
saham fetch stockbit spy --target orderbook --ticker BBCA  # browser still works
```

---

## Notes

- **Share one api_client per process.** Do NOT construct `StockbitApiClient` inside a data
  provider — always inject a shared instance. Failing this means per-provider browser refresh.
- **Token file path** already gitignored (`.gitignore` line 78 covers `.stockbit_profile/`).
- **Playwright stays optional** — `pyproject.toml` already has `[project.optional-dependencies].browser`.
  A valid persisted token lets the app run without Playwright installed.
- **`.logged_in_at` marker** stays as-is (separate from token.json; used for `get_session_status`).
