"""DQ-003 Slice D — fail-closed session handling + capture/label/inspection separation.

Test-only slice (NON_SEMANTIC). It proves three independent invariants against
the REAL production composition used by
``saham analyze signal-backfill-observations`` (mirrors
``research_signal_backfill_commands.py``); nothing about the engine, scorer,
persister, session resolver, or repositories is stubbed. The only fakes are the
seeded rows and, for the persistence-failure probe, a monkeypatched
``save_many`` that raises.

Groups (acceptance criteria 4, 7, 8):

  4. Capture/label separation + idempotence — a ``generate_labels=False`` run
     writes observations and NO labels; a later ``generate_labels=True`` run
     over the same dates generates labels and creates NO duplicate observations
     (canonical row count unchanged). Capture idempotence holds independently of
     the label path. Uses the REAL ``GenerateSignalForwardLabelsUseCase``.

  7. Single-ticker inspection cannot write canonical evidence — the read-only
     assessment path (``AccumulationScreenUseCase.execute``) against a
     repo-backed DB persists nothing; a wiring guard asserts the read-only
     composition constructs no recorder while only the explicit capture bundle
     does.

  8. Fail-closed session handling with visible markers — a holiday/stale-cache
     decision date resolves to an explicitly *marked* fallback session
     (``ihsg_cache_stale_or_holiday``, ``is_eod_pending=False``) that propagates
     onto the persisted observation's provenance columns; a date with no source
     candles is skipped with a machine-readable reason. A persistence-failure
     probe documents the CURRENT swallow-all behavior of the persister (see the
     DQ-003 Slice D finding recorded in ``tasks/done/audit_data_quality.md``).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from src.adapters.composition.screen_accum_workflow_factory import (
    AccumulationScreenWorkflow,
    create_accumulation_screen_workflow,
    create_accumulation_screen_workflow_bundle,
)
from src.adapters.composition.stock_analysis_workflow_dependencies import (
    create_stock_analysis_workflow_dependencies,
)
from src.application.dto.signal_evidence_execution_context import (
    SignalEvidenceExecutionContext,
)
from src.application.services.accumulation_screen_factory import (
    AccumulationScreenUseCaseBundle,
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
from src.application.use_case.generate_signal_forward_labels_use_case import (
    GenerateSignalForwardLabelsUseCase,
)
from src.domain.entities.broker_flow import BrokerSummary
from src.domain.entities.candle import Candle
from src.domain.ports.candidate_observations_repository import CandidateObservation
from src.domain.value_objects.company_fundamentals import CompanyFundamentals
from src.domain.value_objects.corporate_action_calendar import CorporateActionType
from src.domain.value_objects.idx_market import IDX_TIMEZONE, MARKET_CLOSE
from src.domain.value_objects.signal_artifact_identity import SemanticCompatibilityId
from src.domain.value_objects.signal_forward_label import SignalLabelHorizon
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
from src.infrastructure.persistence.sqlite_corporate_action_calendar_repository import (
    SQLiteCorporateActionCalendarRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
    SQLiteSignalForwardLabelsRepository,
)

# Decision date T (a Monday).
_T = date(2026, 6, 15)

_SELECTED = "BBCA"  # evaluated -> screen_result "pass"
_CONTROL = "BMRI"  # second distinct evaluated ticker
_MISSING = "BBRI"  # no data -> evaluator returns None -> skipped, no row

_WARMUP_SESSIONS = 60
# SWING_10D needs 10 forward trading sessions; seed a comfortable margin so
# GenerateSignalForwardLabelsUseCase produces a real label in group 4.
_FORWARD_SESSIONS = 14

_IDENTITY = LeanObservationIdentity(
    observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
    semantic_compatibility_id=SemanticCompatibilityId("sha256:" + "0" * 64),
)


# --------------------------------------------------------------------------- #
# Deterministic seed builders (no datetime.now(); all dates derived from T)
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


def _weekdays_after(start: date, count: int) -> list[date]:
    """`count` weekday sessions strictly after `start`, oldest first."""
    days: list[date] = []
    current = start + timedelta(days=1)
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


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


def _seed_db(db_path: Path, *, with_forward: bool, ihsg_latest: date | None = None) -> None:
    """Seed the DQ-003 Slice D fixture universe.

    - SELECTED/CONTROL: warm-up candles + net-buying broker data through T.
    - MISSING: nothing (evaluator returns None -> skipped).
    - `with_forward`: also seed `_FORWARD_SESSIONS` candles after T on
      SELECTED/CONTROL so the real label generator has a complete forward window.
    - `ihsg_latest`: the last IHSG session to seed. Default (None) is T, giving a
      same-day resolution. Pass a date < T to seed a benchmark whose latest
      cached session predates T — the holiday/stale-cache fallback scenario.
    """
    sessions = _weekdays_ending(_T, _WARMUP_SESSIONS)
    market_repo = SQLiteMarketRepository(db_path)
    broker_repo = SQLiteBrokerRepository(db_path)

    ihsg_end = ihsg_latest if ihsg_latest is not None else _T
    ihsg_sessions = [day for day in sessions if day <= ihsg_end]
    market_repo.save_candles(
        [_candle("IHSG", day, 7000.0 + i * 2.0) for i, day in enumerate(ihsg_sessions)]
    )

    forward = _weekdays_after(_T, _FORWARD_SESSIONS) if with_forward else []
    for ticker in (_SELECTED, _CONTROL):
        candles = [
            _candle(ticker, day, 9000.0 + i * 5.0) for i, day in enumerate(sessions)
        ]
        candles.extend(
            _candle(ticker, day, 9500.0 + i * 5.0) for i, day in enumerate(forward)
        )
        market_repo.save_candles(candles)
        broker_repo.save_broker_summaries(
            [_summary(ticker, day) for day in sessions[-10:]]
        )

    fund_cache = StockbitFundamentalsCache(db_path, cache_ttl_days=7)
    fund_cache.ensure_schema()
    fetched_at = datetime.combine(sessions[0], datetime.min.time())
    fund_cache.write(_fundamentals(_SELECTED, market_cap_idr=100_000_000_000_000, fetched_at=fetched_at))
    fund_cache.write(_fundamentals(_CONTROL, market_cap_idr=90_000_000_000_000, fetched_at=fetched_at))


# --------------------------------------------------------------------------- #
# Production-faithful capture run (mirrors research_signal_backfill_commands.py)
# --------------------------------------------------------------------------- #

def _run_capture(
    db_path: Path,
    *,
    generate_labels: bool,
    dependencies=None,
):
    """Run the REAL production capture composition against `db_path`.

    The real GenerateSignalForwardLabelsUseCase is ALWAYS wired, so
    `generate_labels=False` producing zero labels proves separation rather than
    absence of the label collaborator. Returns (response, observations_repo,
    labels_repo).
    """
    accum_cfg = load_accumulation_screener_config()
    swing_cfg = load_swing_config()

    screen_bundle = create_accumulation_screen_workflow_bundle(
        db_path=db_path,
        screener_config=accum_cfg,
        swing_config=swing_cfg,
        dependencies=dependencies,
    )
    request_builder = BuildSignalObservationScreenRequest.from_configs(
        swing_config=swing_cfg,
        accumulation_screener_config=accum_cfg,
        min_net_buy_days=1,
        disable_score_filters=True,
    )
    market_repo = SQLiteMarketRepository(db_path)
    observations_repo = SQLiteCandidateObservationsRepository(db_path)
    labels_repo = SQLiteSignalForwardLabelsRepository(db_path)
    # Real calendar repo with a seeded success marker so the DQ-004 coverage gate
    # is open — this test exercises capture/label separation, not corporate
    # actions, so labels must compute their real outcomes (no events → clean).
    corp_cal = SQLiteCorporateActionCalendarRepository(db_path)
    corp_cal.mark_synced(_T, (CorporateActionType.STOCK_SPLIT,), "success")
    label_use_case = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=observations_repo,
        market_data_repository=market_repo,
        signal_forward_labels_repository=labels_repo,
        corporate_action_calendar_repository=corp_cal,
    )

    response = BackfillSignalObservationsUseCase(
        record_observations_use_case=screen_bundle.record_observations_use_case,
        screen_request_builder=request_builder,
        market_data_repository=market_repo,
        candidate_observations_repository=observations_repo,
        observation_identity=_IDENTITY,
        label_generation_use_case=label_use_case,
        evaluate_market_context=None,
        session_resolver=EffectiveMarketSessionResolver(market_repo),
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=(_SELECTED, _CONTROL, _MISSING),
            start_date=_T,
            end_date=_T,
            horizon=SignalLabelHorizon.SWING_10D,
            generate_labels=generate_labels,
            windows=(7,),
        )
    )
    return response, observations_repo, labels_repo


def _canonical_count(repo, snapshot_date: date) -> int:
    return len(repo.list_canonical_by_date(snapshot_date))


# =========================================================================== #
# Group 4 — capture/label separation + idempotence
# =========================================================================== #

def test_capture_without_labels_then_labels_run_adds_no_duplicate_observations(tmp_path):
    """generate_labels=False writes observations and NO labels; a later
    generate_labels=True run over the same dates generates labels and creates NO
    duplicate observations (canonical row count unchanged). Proven with the real
    label use case, so separation is real behavior, not a fake."""
    db_path = tmp_path / "separation.db"
    _seed_db(db_path, with_forward=True)

    # Run 1: capture only. Observations written; no labels despite the label use
    # case being fully wired.
    capture_response, obs_repo_1, labels_repo_1 = _run_capture(
        db_path, generate_labels=False
    )
    canonical_after_capture = _canonical_count(obs_repo_1, _T)
    assert canonical_after_capture > 0, "capture wrote no canonical observations"
    assert capture_response.saved_observation_count == canonical_after_capture
    assert capture_response.generated_label_count == 0
    assert labels_repo_1.get(_SELECTED, _T, SignalLabelHorizon.SWING_10D) is None

    # Run 2: label generation over the SAME dates. Labels appear; observation
    # count is UNCHANGED (real upsert by canonical identity — no duplicates).
    label_response, obs_repo_2, labels_repo_2 = _run_capture(
        db_path, generate_labels=True
    )
    assert label_response.generated_label_count >= 1, (
        "generate_labels=True produced no labels despite a complete forward window"
    )
    assert _canonical_count(obs_repo_2, _T) == canonical_after_capture, (
        "label generation run changed the canonical observation count — capture "
        "and label generation are not separate/idempotent."
    )


def test_capture_is_idempotent_independently_of_labels(tmp_path):
    """Repeating the generate_labels=False capture adds no canonical rows —
    reconfirms Slice C idempotence at the use-case level with the label path
    off, so labels cannot be the thing keeping counts stable."""
    db_path = tmp_path / "capture_idempotent.db"
    _seed_db(db_path, with_forward=False)

    _, obs_repo_first, labels_repo_first = _run_capture(db_path, generate_labels=False)
    first_count = _canonical_count(obs_repo_first, _T)
    assert first_count > 0

    _, obs_repo_second, labels_repo_second = _run_capture(db_path, generate_labels=False)
    assert _canonical_count(obs_repo_second, _T) == first_count, (
        "second capture-only run changed the canonical row count — capture is "
        "not idempotent independently of label generation."
    )
    # And no labels were ever produced by a capture-only run.
    assert labels_repo_second.get(_SELECTED, _T, SignalLabelHorizon.SWING_10D) is None


# =========================================================================== #
# Group 7 — single-ticker inspection cannot write canonical evidence
# =========================================================================== #

def test_read_only_single_ticker_assessment_writes_no_canonical_observation(tmp_path):
    """Invoking the read-only assessment path (AccumulationScreenUseCase.execute)
    for a single ticker against a repo-backed DB leaves candidate_observations
    empty. execute() is assessment-only; only the explicit record/persist use
    case writes canonical rows (criterion 7)."""
    db_path = tmp_path / "read_only.db"
    _seed_db(db_path, with_forward=False)

    accum_cfg = load_accumulation_screener_config()
    swing_cfg = load_swing_config()

    # The read-only workflow factory — the composition an analyze/inspect path
    # uses. It constructs NO recorder (see the wiring guard below).
    workflow = create_accumulation_screen_workflow(
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
    effective_session = EffectiveMarketSessionResolver(market_repo).resolve(
        run_at=datetime.combine(_T, MARKET_CLOSE, tzinfo=IDX_TIMEZONE)
    )
    # A read-only context leaves the lean identity None (interactive paths never
    # persist), exactly as the DTO documents.
    context = SignalEvidenceExecutionContext(
        effective_session=effective_session,
        source_availability_use_case=None,
    )

    workflow.use_case.execute(
        request_builder.build(
            tickers=[_SELECTED],
            window_days=7,
            as_of_date=_T,
            market_context=None,
        ),
        execution_context=context,
    )

    observations_repo = SQLiteCandidateObservationsRepository(db_path)
    assert observations_repo.list_all_by_date(_T) == [], (
        "read-only single-ticker assessment wrote a candidate observation — the "
        "inspection path leaked into the canonical population (criterion 7)."
    )


def test_only_the_explicit_capture_bundle_constructs_a_recorder(tmp_path):
    """Wiring guard: the read-only workflow exposes no recorder, while the
    explicit capture bundle does. This keeps criterion 7 true structurally —
    there is no way for an analyze/inspect composition to acquire a persister."""
    db_path = tmp_path / "wiring.db"
    _seed_db(db_path, with_forward=False)
    accum_cfg = load_accumulation_screener_config()
    swing_cfg = load_swing_config()

    read_only = create_accumulation_screen_workflow(
        db_path=db_path,
        screener_config=accum_cfg,
        swing_config=swing_cfg,
    )
    capture = create_accumulation_screen_workflow_bundle(
        db_path=db_path,
        screener_config=accum_cfg,
        swing_config=swing_cfg,
    )

    assert isinstance(read_only, AccumulationScreenWorkflow)
    assert not hasattr(read_only, "record_observations_use_case"), (
        "the read-only workflow exposes a recorder — an inspect path could write "
        "canonical evidence."
    )
    assert isinstance(capture, AccumulationScreenUseCaseBundle)
    assert capture.record_observations_use_case is not None, (
        "the explicit capture bundle must carry the recorder (the sole writer)."
    )


# =========================================================================== #
# Group 8 — fail-closed session handling with visible markers
# =========================================================================== #

def test_holiday_decision_date_resolves_to_marked_stale_session():
    """Resolving an after-close session for a decision date whose IDX candle is
    absent (holiday / stale cache) yields an EXPLICIT fallback marker and a
    pending flag, never a silently-wrong session (criterion 8)."""
    market_repo_stub = _InMemoryIhsgRepo(
        # IHSG last traded three sessions before T (a holiday at T, or a stale
        # cache) — the latest cached session predates the decision date.
        latest_session=_T - timedelta(days=3)
    )
    resolver = EffectiveMarketSessionResolver(market_repo_stub)

    session = resolver.resolve(
        run_at=datetime.combine(_T, MARKET_CLOSE, tzinfo=IDX_TIMEZONE)
    )

    assert session.resolution_source == "ihsg_cache_stale_or_holiday", (
        "a decision date with no same-day IDX candle must be marked, not "
        "silently resolved to the decision date itself."
    )
    assert session.is_eod_pending is False
    assert session.latest_completed_session == _T - timedelta(days=3)
    assert session.notes, "the stale/holiday fallback must carry a visible note"


def test_holiday_marker_propagates_onto_persisted_observation(tmp_path):
    """The stale/holiday resolution marker propagates end-to-end onto the
    persisted observation's provenance columns — the fallback is visible on the
    canonical row, not just at resolution time (criterion 8)."""
    db_path = tmp_path / "holiday.db"
    # IHSG's latest cached session predates T; the tickers still have candles at
    # T, so the date IS processed (trading dates fall back to the ticker series)
    # and the session resolves to the marked stale/holiday fallback.
    _seed_db(db_path, with_forward=False, ihsg_latest=_T - timedelta(days=3))

    _, observations_repo, _ = _run_capture(db_path, generate_labels=False)
    canonical = {obs.ticker: obs for obs in observations_repo.list_canonical_by_date(_T)}

    assert _SELECTED in canonical, "no observation captured on the holiday date"
    obs = canonical[_SELECTED]
    assert obs.resolution_source == "ihsg_cache_stale_or_holiday", (
        "the stale/holiday marker did not propagate onto the persisted "
        "observation — the fallback is invisible downstream."
    )
    assert obs.is_eod_pending is False
    assert obs.latest_completed_session == _T - timedelta(days=3)


def test_date_without_source_candles_is_skipped_with_machine_readable_reason(tmp_path):
    """A processed date with no source candles for any universe ticker is skipped
    with the machine-readable `missing_source_candles_for_universe` reason —
    visible, not a silent omission (criterion 8)."""
    db_path = tmp_path / "missing_candles.db"
    _seed_db(db_path, with_forward=False)

    # A universe of tickers that have NO seeded data at all on T. IHSG has a
    # candle at T (so T is a trading date), but none of the requested tickers do.
    accum_cfg = load_accumulation_screener_config()
    swing_cfg = load_swing_config()
    screen_bundle = create_accumulation_screen_workflow_bundle(
        db_path=db_path, screener_config=accum_cfg, swing_config=swing_cfg
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
        session_resolver=EffectiveMarketSessionResolver(market_repo),
    ).execute(
        BackfillSignalObservationsRequest(
            tickers=("NODATA1", "NODATA2"),
            start_date=_T,
            end_date=_T,
            windows=(7,),
        )
    )

    assert response.processed_date_count == 0
    assert response.saved_observation_count == 0
    assert response.skipped_dates, "a date with no source candles produced no visible skip"
    assert response.skipped_dates[0].reason == "missing_source_candles_for_universe"
    assert response.skipped_dates[0].date == _T


def test_backfill_fails_closed_on_save_failure(tmp_path):
    """DQ-003 Slice D finding RESOLVED (see tasks/done/audit_data_quality.md).

    When `save_many` raises (a locked DB / contract / infrastructure error), the
    persister no longer swallows it — the exception propagates through the
    record use case and the backfill loop so the run aborts VISIBLY instead of
    reporting a silent 0-count. A run can no longer show
    `evaluated_count > saved_observation_count` from a lost write, because it
    fails closed before returning a response at all.
    """
    import sqlite3

    import pytest

    db_path = tmp_path / "save_fails.db"
    _seed_db(db_path, with_forward=False)

    deps = create_stock_analysis_workflow_dependencies(db_path)

    def _boom(_observations):
        # A contract/infrastructure error (e.g. locked DB), NOT provider/data
        # absence — precisely the class §14 says must fail closed rather than
        # degrade to ordinary missing evidence.
        raise sqlite3.OperationalError("database is locked")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(deps.candidate_observations_repository, "save_many", _boom)

        accum_cfg = load_accumulation_screener_config()
        swing_cfg = load_swing_config()
        screen_bundle = create_accumulation_screen_workflow_bundle(
            db_path=db_path,
            screener_config=accum_cfg,
            swing_config=swing_cfg,
            dependencies=deps,
        )
        request_builder = BuildSignalObservationScreenRequest.from_configs(
            swing_config=swing_cfg,
            accumulation_screener_config=accum_cfg,
            min_net_buy_days=1,
            disable_score_filters=True,
        )
        market_repo = SQLiteMarketRepository(db_path)
        observations_repo = SQLiteCandidateObservationsRepository(db_path)

        backfill = BackfillSignalObservationsUseCase(
            record_observations_use_case=screen_bundle.record_observations_use_case,
            screen_request_builder=request_builder,
            market_data_repository=market_repo,
            candidate_observations_repository=observations_repo,
            observation_identity=_IDENTITY,
            session_resolver=EffectiveMarketSessionResolver(market_repo),
        )

        # Fail closed: the save failure propagates out of the backfill run
        # rather than being converted to a silent 0-count success.
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            backfill.execute(
                BackfillSignalObservationsRequest(
                    tickers=(_SELECTED, _CONTROL, _MISSING),
                    start_date=_T,
                    end_date=_T,
                    windows=(7,),
                )
            )

    # And nothing was persisted — the aborted run left no partial canonical rows
    # for the failed write.
    assert SQLiteCandidateObservationsRepository(db_path).list_all_by_date(_T) == []


def test_persister_empty_input_returns_zero_without_raising(tmp_path):
    """The genuine "nothing to do" path is preserved: a None repository or an
    empty candidate list returns 0 WITHOUT raising — only real failures fail
    closed, not empty input."""
    from src.application.dto.accumulation_screen import AccumulationScreenRequest
    from src.application.services.accumulation_candidate_observation_persister import (
        AccumulationCandidateObservationPersister,
    )

    request = AccumulationScreenRequest(tickers=[], window_days=7, as_of_date=_T)

    # No repository -> nothing to do -> 0, no raise. Evidence builder/setup
    # resolver are never reached, so None is safe here.
    no_repo_persister = AccumulationCandidateObservationPersister(
        candidate_observations_repository=None,
        candidate_evidence_builder=None,
        setup_family_resolver=None,
        swing_setup_catalog=None,
    )
    assert (
        no_repo_persister.persist(
            [],
            _T,
            request,
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            semantic_compatibility_id=_IDENTITY.semantic_compatibility_id,
        )
        == 0
    )

    # A repository is present but there are no evaluated candidates -> still 0,
    # still no raise (empty input is not a failure).
    class _UnusedRepo:
        def save_many(self, observations, *, risk_records=None):  # pragma: no cover - must not be called
            raise AssertionError("save_many must not run for empty input")

    empty_input_persister = AccumulationCandidateObservationPersister(
        candidate_observations_repository=_UnusedRepo(),
        candidate_evidence_builder=None,
        setup_family_resolver=None,
        swing_setup_catalog=None,
    )
    assert (
        empty_input_persister.persist(
            [],
            _T,
            request,
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            semantic_compatibility_id=_IDENTITY.semantic_compatibility_id,
        )
        == 0
    )


# --------------------------------------------------------------------------- #
# Minimal in-memory IHSG repo for the resolver unit test (no DB needed).
# --------------------------------------------------------------------------- #

class _InMemoryIhsgRepo:
    """A MarketDataRepository stub exposing only what the session resolver reads:
    the latest bounded IHSG candle. Returns one IHSG candle at `latest_session`
    for any end_date on or after it, so `_bounded_ihsg_session` sees a cached
    session that predates the (later) decision date."""

    def __init__(self, *, latest_session: date) -> None:
        self._latest = latest_session

    def get_candles(self, ticker, start_date=None, end_date=None):
        if end_date is not None and end_date < self._latest:
            return []
        return [_candle(ticker, self._latest, 7000.0)]

    def save_candles(self, candles):  # pragma: no cover - not used
        raise AssertionError("not used")

    def has_data(self, ticker, start_date, end_date):  # pragma: no cover
        raise AssertionError("not used")

    def get_date_range(self, ticker):  # pragma: no cover
        raise AssertionError("not used")
