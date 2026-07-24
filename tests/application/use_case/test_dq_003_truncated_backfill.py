"""DQ-003 Slice C — golden truncated-DB fixture + point-in-time/idempotence proof.

Test-only slice. It builds ONE compact, deterministic, physically-truncated
SQLite fixture and runs the REAL capture path — the exact production
composition used by ``saham analyze signal-backfill-observations``:

    create_accumulation_screen_workflow_bundle(...)  # real screen + recorder
        + BackfillSignalObservationsUseCase(...)     # real capture driver

against it. Nothing about the engine, scorer, persister, or repositories is
stubbed: the only fakes are the seeded rows themselves.

Fixture (decision date T), seeded into a fresh temp SQLite DB:
  - SELECTED ticker  — has candles + net-buying broker summaries through T, so
    it is evaluated and (score filters disabled in backfill) classifies ``pass``.
  - CONTROL ticker   — a SECOND, distinct data-bearing ticker (its own candles +
    broker summaries through T). It co-exists with SELECTED under one shared PIT
    cutoff and proves non-overwrite of two distinct canonical identities.
  - MISSING ticker   — in the requested universe but with no candle/broker data,
    so the candidate evaluator returns None and it is skipped with no row.
  - A planted FUTURE candle at T+1 on the SELECTED ticker — the leakage trap.
  - IHSG candles through T for trading-date derivation + session resolution.

FINDING (production reality, not a test compromise): the real backfill
composition disables EVERY gate that could emit ``screen_result != "pass"`` —
``disable_score_filters=True`` turns off the foreign-flow and signal-score
gates, and the structural market-cap / Piotroski floors resolve to 0 in config
and in the request-builder default. So the production capture path can ONLY
emit ``screen_result="pass"``; a ``rejected_*`` canonical observation is
impossible via the real path (backfill captures the full evaluated universe as
negative-inclusive samples, not a screen-rejected subset). This test therefore
proves the CORE of "candidate/control non-overwrite" — two distinct canonical
identities co-persisting under one PIT cutoff — with two evaluated ``pass``
tickers, rather than faking a ``rejected_*`` row by stubbing the engine or
enabling a non-production filter. See test_candidate_and_control_*.

Invariants proven (negative-first):
  1. No future leakage — the SELECTED observation's semantic projection is
     identical whether or not the T+1 row physically exists in the DB.
  2. Warm-up ends at T — captured data_as_of_date <= T (and invariant 1).
  3. Rerun idempotence — a second capture against the same DB adds no rows and
     yields an identical semantic projection (captured_at excluded).
  4. Candidate/control non-overwrite — SELECTED and CONTROL are two distinct
     canonical identities that both persist, share one PIT cutoff (same
     decision_at/analysis_as_of), and neither overwrites the other.
  5. Unavailable stays unavailable — the MISSING ticker gets no observation.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from src.adapters.cli.screen_accum_workflow_factory import (
    create_accumulation_screen_workflow_bundle,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSessionResolver,
)
from src.application.services.lean_observation_identity import LeanObservationIdentity
from src.application.services.signal_observation_request_builder import (
    BuildSignalObservationScreenRequest,
)
from src.application.use_case.backfill_signal_observations_use_case import (
    BackfillSignalObservationsRequest,
    BackfillSignalObservationsUseCase,
)
from src.domain.entities.broker_flow import BrokerSummary
from src.domain.entities.candle import Candle
from src.domain.ports.candidate_observations_repository import CandidateObservation
from src.domain.value_objects.company_fundamentals import CompanyFundamentals
from src.domain.value_objects.signal_artifact_identity import SemanticCompatibilityId
from src.domain.value_objects.signal_semantic_contract import (
    ACCUMULATION_DISCOVERY_CONTRACT,
)
from src.infrastructure.browser.stockbit_fundamentals_cache import (
    StockbitFundamentalsCache,
)
from src.infrastructure.config.accumulation_screener_config import (
    load_accumulation_screener_config,
)
from src.infrastructure.config.swing_config import load_swing_config
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

# Decision date T (a Monday) and its planted future session T+1 (a Tuesday).
_T = date(2026, 6, 15)
_T_PLUS_1 = date(2026, 6, 16)

_SELECTED = "BBCA"  # evaluated -> screen_result "pass"
_CONTROL = "BMRI"  # second distinct evaluated ticker (non-overwrite partner)
_MISSING = "BBRI"  # no data -> evaluator returns None -> skipped, no row

# Fixed, fake wall-clock warm-up base far enough back to satisfy indicator
# windows (RSI/SMA/BB/MA200). Deterministic — no datetime.now() anywhere.
_WARMUP_SESSIONS = 60

# A lean identity stamped exactly as production stamps it (transported through
# the use case onto every capture context). A fixed compatibility id keeps the
# semantic projection deterministic; its VALUE is metadata, never part of the
# leakage/idempotence proof.
_IDENTITY = LeanObservationIdentity(
    observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
    semantic_compatibility_id=SemanticCompatibilityId("sha256:" + "0" * 64),
)


# --------------------------------------------------------------------------- #
# Deterministic seed builders
# --------------------------------------------------------------------------- #

def _weekdays_ending(end: date, count: int) -> list[date]:
    """`count` weekday sessions ending at `end`, oldest first."""
    days: list[date] = []
    current = end
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current -= timedelta(days=1)
    return sorted(days)


def _candle(ticker: str, day: date, close: float) -> Candle:
    price = Decimal(str(round(close, 2)))
    return Candle(
        ticker=ticker,
        date=day,
        open=price,
        high=Decimal(str(round(close * 1.005, 2))),
        low=Decimal(str(round(close * 0.995, 2))),
        close=price,
        volume=1_000_000,
    )


def _summary(ticker: str, day: date) -> BrokerSummary:
    """Net-buying foreign summary (foreign_buy_value > 0, sell = 0) so the
    candidate evaluator sees an accumulating session."""
    buy_value = Decimal("5_000_000_000")
    return BrokerSummary(
        ticker=ticker,
        date=day,
        top_buyers=(),
        top_sellers=(),
        foreign_buy_value=buy_value,
        foreign_sell_value=Decimal("0"),
        foreign_buy_lot=50_000,
        foreign_sell_lot=0,
        total_value=buy_value * Decimal("2"),
        total_lot=100_000,
    )


def _seed_db(db_path: Path, *, plant_future: bool) -> None:
    """Seed a fresh SQLite DB with the DQ-003 fixture universe.

    When `plant_future` is True, a single T+1 candle is added to the SELECTED
    ticker — the leakage trap. The row physically EXISTS; the engine must still
    ignore it because it bounds reads at the decision date T.
    """
    sessions = _weekdays_ending(_T, _WARMUP_SESSIONS)
    market_repo = SQLiteMarketRepository(db_path)
    broker_repo = SQLiteBrokerRepository(db_path)

    # IHSG benchmark + trading calendar through T (never gets the T+1 row, so
    # the session resolver deterministically resolves T as the completed session).
    market_repo.save_candles(
        [_candle("IHSG", day, 7000.0 + i * 2.0) for i, day in enumerate(sessions)]
    )

    for ticker in (_SELECTED, _CONTROL):
        candles = [
            _candle(ticker, day, 9000.0 + i * 5.0) for i, day in enumerate(sessions)
        ]
        if ticker == _SELECTED and plant_future:
            # Leakage trap: a real future row at T+1. If any read is unbounded,
            # it will surface here and change the captured observation.
            candles.append(_candle(ticker, _T_PLUS_1, 9000.0 + len(sessions) * 5.0))
        market_repo.save_candles(candles)
        # At least the last 10 sessions of net-buying broker data through T.
        broker_repo.save_broker_summaries(
            [_summary(ticker, day) for day in sessions[-10:]]
        )

    # Point-in-time fundamentals cache (realistic enrichment). fetched_at is a
    # warm-up date <= T so the PIT read (as_of_date=T) surfaces the row and
    # never a future one. NOTE: the structural market-cap/Piotroski floors
    # resolve to 0 in the real backfill composition, so these rows do NOT gate
    # pass/reject — they only exercise the enrichment path realistically. The
    # MISSING ticker gets none (it is skipped by the evaluator regardless).
    fund_cache = StockbitFundamentalsCache(db_path, cache_ttl_days=7)
    fund_cache.ensure_schema()
    fetched_at = datetime.combine(sessions[0], datetime.min.time())
    fund_cache.write(_fundamentals(_SELECTED, market_cap_idr=100_000_000_000_000, fetched_at=fetched_at))
    fund_cache.write(_fundamentals(_CONTROL, market_cap_idr=90_000_000_000_000, fetched_at=fetched_at))


def _fundamentals(ticker: str, *, market_cap_idr: int, fetched_at: datetime) -> CompanyFundamentals:
    return CompanyFundamentals(
        ticker=ticker,
        pe_ratio_ttm=12.0,
        roe_ttm=18.0,
        net_profit_margin=15.0,
        revenue_yoy_growth=8.0,
        piotroski_f_score=7,
        dividend_yield=2.0,
        week52_high=12000.0,
        week52_low=8000.0,
        near_52w_high_rank=60.0,
        market_cap_idr=market_cap_idr,
        pbv=2.0,
        fetched_at=fetched_at,
    )


# --------------------------------------------------------------------------- #
# Production-faithful capture run
# --------------------------------------------------------------------------- #

def _run_capture(db_path: Path):
    """Run the REAL production composition against `db_path`.

    Mirrors adapters/cli/research_signal_backfill_commands.py exactly, minus the
    optional market-context evaluator and label generation (both irrelevant to
    the capture invariants under test; passing them would only add non-capture
    machinery). The screen, recorder, persister, repositories, and offline
    Stockbit providers are all the production objects.
    """
    accum_cfg = load_accumulation_screener_config()
    swing_cfg = load_swing_config()

    screen_bundle = create_accumulation_screen_workflow_bundle(
        db_path=db_path,
        screener_config=accum_cfg,
        swing_config=swing_cfg,
    )
    request_builder = BuildSignalObservationScreenRequest.from_configs(
        swing_config=swing_cfg,
        accumulation_screener_config=accum_cfg,
        min_net_buy_days=1,
        disable_score_filters=True,
    )
    market_repo = SQLiteMarketRepository(db_path)
    observations_repo = SQLiteCandidateObservationsRepository(db_path)

    response = BackfillSignalObservationsUseCase(
        record_observations_use_case=screen_bundle.record_observations_use_case,
        screen_request_builder=request_builder,
        market_data_repository=market_repo,
        candidate_observations_repository=observations_repo,
        observation_identity=_IDENTITY,
        label_generation_use_case=None,
        evaluate_market_context=None,
        session_resolver=EffectiveMarketSessionResolver(market_repo),
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=(_SELECTED, _CONTROL, _MISSING),
            start_date=_T,
            end_date=_T,
            windows=(7,),
        )
    )
    return response, observations_repo


# --------------------------------------------------------------------------- #
# Canonical semantic projection — every persisted field EXCEPT volatile
# wall-clock metadata (captured_at). Comparisons in invariants 1 and 3 use this,
# never a raw row/byte compare.
# --------------------------------------------------------------------------- #

def _semantic_projection(obs: CandidateObservation) -> dict:
    payload = {k: v for k, v in obs.payload.items() if k != "captured_at"}
    return {
        "payload": payload,
        "observation_contract": obs.observation_contract,
        "semantic_compatibility_id": (
            str(obs.semantic_compatibility_id)
            if obs.semantic_compatibility_id is not None
            else None
        ),
        "config_hash": obs.config_hash,
        "workflow": obs.workflow,
        "window_sessions": obs.window_sessions,
        "data_as_of_date": (
            obs.data_as_of_date.isoformat() if obs.data_as_of_date else None
        ),
        "decision_at": obs.decision_at.isoformat() if obs.decision_at else None,
        "latest_completed_session": (
            obs.latest_completed_session.isoformat()
            if obs.latest_completed_session
            else None
        ),
        "analysis_as_of": obs.analysis_as_of.isoformat() if obs.analysis_as_of else None,
    }


def _canonical_by_ticker(repo, snapshot_date: date) -> dict[str, CandidateObservation]:
    return {obs.ticker: obs for obs in repo.list_canonical_by_date(snapshot_date)}


# --------------------------------------------------------------------------- #
# Invariant 1 — no future leakage
# --------------------------------------------------------------------------- #

def test_planted_future_row_does_not_change_captured_observation(tmp_path):
    """The SELECTED observation's semantic projection is byte-identical whether
    or not the T+1 row exists in the DB. This proves the engine bounds its reads
    at T; it does NOT rely on the DB physically lacking the future row."""
    db_with_future = tmp_path / "with_future.db"
    db_without_future = tmp_path / "without_future.db"
    _seed_db(db_with_future, plant_future=True)
    _seed_db(db_without_future, plant_future=False)

    _, repo_with = _run_capture(db_with_future)
    _, repo_without = _run_capture(db_without_future)

    obs_with = _canonical_by_ticker(repo_with, _T)
    obs_without = _canonical_by_ticker(repo_without, _T)

    assert _SELECTED in obs_with, "SELECTED ticker produced no canonical observation"
    assert _SELECTED in obs_without

    assert _semantic_projection(obs_with[_SELECTED]) == _semantic_projection(
        obs_without[_SELECTED]
    ), (
        "Planted T+1 row changed the captured observation — FUTURE LEAKAGE. "
        "The capture path read a session dated after the decision date T."
    )


# --------------------------------------------------------------------------- #
# Invariant 2 — warm-up ends at T
# --------------------------------------------------------------------------- #

def test_warmup_window_ends_at_decision_date(tmp_path):
    """No indicator/broker window consumes a row dated after T: the captured
    data_as_of_date is <= T even with the T+1 row physically present."""
    db_path = tmp_path / "warmup.db"
    _seed_db(db_path, plant_future=True)

    _, repo = _run_capture(db_path)
    canonical = _canonical_by_ticker(repo, _T)

    assert canonical, "No canonical observations captured"
    for ticker, obs in canonical.items():
        assert obs.data_as_of_date is not None, f"{ticker} missing data_as_of_date"
        assert obs.data_as_of_date <= _T, (
            f"{ticker} data_as_of_date {obs.data_as_of_date} is after decision "
            f"date {_T} — a warm-up window consumed a future row."
        )


# --------------------------------------------------------------------------- #
# Invariant 3 — rerun idempotence
# --------------------------------------------------------------------------- #

def test_rerun_is_idempotent(tmp_path):
    """Running the same capture twice against the same DB yields the same number
    of canonical rows (no growth) and identical semantic projections.
    captured_at may differ and is excluded from the projection."""
    db_path = tmp_path / "idempotent.db"
    _seed_db(db_path, plant_future=True)

    _, repo_first = _run_capture(db_path)
    first = _canonical_by_ticker(repo_first, _T)
    first_projection = {t: _semantic_projection(o) for t, o in first.items()}

    _, repo_second = _run_capture(db_path)
    second = _canonical_by_ticker(repo_second, _T)
    second_projection = {t: _semantic_projection(o) for t, o in second.items()}

    assert len(second) == len(first), (
        f"Rerun changed canonical row count {len(first)} -> {len(second)} — "
        "the upsert appended instead of replacing."
    )
    assert second_projection == first_projection, (
        "Rerun produced a different semantic projection — capture is not "
        "deterministic/idempotent."
    )


# --------------------------------------------------------------------------- #
# Invariant 4 — candidate/control non-overwrite
# --------------------------------------------------------------------------- #

def test_candidate_and_control_are_distinct_non_overwriting_identities(tmp_path):
    """SELECTED and CONTROL are two distinct canonical identities that both
    persist under one shared PIT cutoff and neither overwrites the other.

    This proves the CORE of "candidate/control non-overwrite". The task's
    original flavor (SELECTED "pass" vs CONTROL "rejected_*") is NOT provable
    against the real capture path: the production backfill composition disables
    every reject gate (disable_score_filters=True; market-cap/Piotroski floors
    resolve to 0), so it can only ever emit screen_result="pass". Faking a
    rejected_* row would require stubbing the engine or enabling a
    non-production filter — both forbidden — so we assert the real invariant:
    two distinct co-persisting canonical rows, not one collapsed/overwritten
    row.
    """
    db_path = tmp_path / "candidate_control.db"
    _seed_db(db_path, plant_future=True)

    _, repo = _run_capture(db_path)
    all_rows = repo.list_all_by_date(_T)
    canonical = _canonical_by_ticker(repo, _T)

    assert _SELECTED in canonical, "SELECTED observation missing"
    assert _CONTROL in canonical, "CONTROL observation missing"

    # Non-overwrite: two distinct rows survive, one per ticker — not collapsed.
    selected_rows = [o for o in all_rows if o.ticker == _SELECTED]
    control_rows = [o for o in all_rows if o.ticker == _CONTROL]
    assert len(selected_rows) == 1, f"expected 1 SELECTED row, got {len(selected_rows)}"
    assert len(control_rows) == 1, f"expected 1 CONTROL row, got {len(control_rows)}"

    # Both are the real production classification (all reject gates disabled).
    assert canonical[_SELECTED].payload["screen_result"] == "pass"
    assert canonical[_CONTROL].payload["screen_result"] == "pass"

    # Distinct canonical identity: different ticker => different upsert key, so
    # neither can overwrite the other even though they share every other key.
    assert canonical[_SELECTED].ticker != canonical[_CONTROL].ticker
    assert canonical[_SELECTED].payload["ticker"] != canonical[_CONTROL].payload["ticker"]

    # One shared point-in-time cutoff: identical decision_at / analysis_as_of.
    assert (
        canonical[_SELECTED].decision_at == canonical[_CONTROL].decision_at
    ), "candidate and control resolved different decision_at for the same date"
    assert (
        canonical[_SELECTED].analysis_as_of
        == canonical[_CONTROL].analysis_as_of
        == _T
    ), "candidate/control analysis_as_of not pinned to the decision date T"
    assert (
        canonical[_SELECTED].config_hash == canonical[_CONTROL].config_hash
    ), "candidate/control should share the same config identity"


# --------------------------------------------------------------------------- #
# Invariant 5 — unavailable stays unavailable
# --------------------------------------------------------------------------- #

def test_missing_input_ticker_is_not_written(tmp_path):
    """The missing-input ticker (no candle/broker data) is skipped by the
    candidate evaluator and never written as an observation."""
    db_path = tmp_path / "missing.db"
    _seed_db(db_path, plant_future=True)

    _, repo = _run_capture(db_path)

    all_rows = repo.list_all_by_date(_T)
    tickers = {obs.ticker for obs in all_rows}
    assert _MISSING not in tickers, (
        f"{_MISSING} was written despite having no candle/broker data — the "
        "evaluator should have skipped it before persistence."
    )
    # Sanity: the two data-bearing tickers ARE present.
    assert {_SELECTED, _CONTROL} <= tickers
