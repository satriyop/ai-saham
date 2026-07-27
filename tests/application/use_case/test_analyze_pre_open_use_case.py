"""Unit tests for AnalyzePreOpenUseCase (database-identified post-open assess)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.application.dto.analyze_pre_open import (
    AnalyzePreOpenAmbiguityError,
    AnalyzePreOpenNotFoundError,
    AnalyzePreOpenRequest,
    AnalyzePreOpenSnapshotError,
    AnalyzePreOpenStatus,
)
from src.application.use_case.analyze_pre_open_use_case import AnalyzePreOpenUseCase
from src.application.use_case.pre_open_post_open_gates_use_case import (
    PreOpenPostOpenGatesRequest,
    PreOpenPostOpenGatesUseCase,
)
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningObservation,
    LearningTrackSnapshot,
)
from src.domain.value_objects.pre_open_post_open_assessment import (
    PreOpenPostOpenCandidate,
    PreOpenPostOpenDecision,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)

WIB = ZoneInfo("Asia/Jakarta")
SESSION = date(2026, 6, 18)


def _plan_payload(
    ticker: str = "BBCA",
    *,
    market_regime: dict | None = None,
) -> dict:
    return {
        "ticker": ticker,
        "screen_result": "pass",
        "market_regime": market_regime or {"regime": "NEUTRAL"},
        "candidate": {
            "ticker": ticker,
            "iev": 200_000,
            "entry_price": "10050",
            "stop_loss_price": "9800",
            "trend_signal": "BULLISH",
            "rsi": "52",
            "gap_pct": "1.0",
            "entry_range_low": "9900",
            "entry_range_high": "10100",
            "opening_broker_backing_tag": "BACKED",
        },
        "signal": {"direction": "BULLISH", "entry_quality": "ENTER", "score": 72},
        "trade_setup": {"action": "ENTER"},
    }


def _add_observation(
    repo: SQLiteLearningArtifactRepository,
    *,
    ticker: str = "BBCA",
    compatibility_id: str = "compat-a",
    market_regime: dict | None = None,
) -> LearningObservation:
    obs = LearningObservation.create(
        purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
        policy_contract="pre_open_directional_baseline.v1",
        horizon_contract="open_30m",
        compatibility_id=compatibility_id,
        cutoff_at=datetime(2026, 6, 18, 8, 57, tzinfo=WIB),
        universe_id=f"iev:{SESSION.isoformat()}",
        window_id=f"{ticker}:{SESSION.isoformat()}",
        decision_payload=_plan_payload(ticker, market_regime=market_regime),
        captured_at=datetime(2026, 6, 18, 8, 57, tzinfo=WIB),
    )
    assert repo.add_observation(obs)
    return obs


def _add_track(
    repo: SQLiteLearningArtifactRepository,
    observation_id: str,
    *,
    sampled_at: datetime,
    payload: dict,
    source: str = "stockbit.opening_track",
) -> LearningTrackSnapshot:
    snap = LearningTrackSnapshot.create(
        observation_id=observation_id,
        sampled_at=sampled_at,
        source=source,
        snapshot_payload=payload,
        captured_at=sampled_at,
    )
    assert repo.add_track_snapshot(snap)
    return snap


def _uc(repo: SQLiteLearningArtifactRepository) -> AnalyzePreOpenUseCase:
    return AnalyzePreOpenUseCase(
        observations=repo,
        tracks=repo,
        clock_date=SESSION,
    )


def test_happy_path_matches_pure_confirm(tmp_path: Path) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "learn.db")
    obs = _add_observation(repo)
    snap = _add_track(
        repo,
        obs.observation_id,
        sampled_at=datetime(2026, 6, 18, 9, 0, 15, tzinfo=WIB),
        payload={
            "opening_price": "10050",
            "opening_price_source": "order_book_lastprice",
            "opening_price_confidence": "MEDIUM",
            "mid_price": "10060",
        },
    )

    result = _uc(repo).execute(AnalyzePreOpenRequest(observation_id=obs.observation_id))
    assert result.status is AnalyzePreOpenStatus.OK
    assert len(result.lines) == 1
    line = result.lines[0]
    assert line.observation_id == obs.observation_id
    assert line.opening_snapshot_id == snap.snapshot_id
    assert line.confirmation.decision is PreOpenPostOpenDecision.ENTER
    assert line.pre_open["direction"] == "BULLISH"
    assert line.price_provenance["opening_price_source"] == "order_book_lastprice"

    # Golden: same as hand-built PreOpenPostOpenGatesUseCase
    pure = PreOpenPostOpenGatesUseCase().execute(
        PreOpenPostOpenGatesRequest(
            candidates=[
                PreOpenPostOpenCandidate(
                    ticker="BBCA",
                    opening_price=Decimal("10050"),
                    iev=200_000,
                    entry_range_low=Decimal("9900"),
                    entry_range_high=Decimal("10100"),
                    suggested_entry=Decimal("10050"),
                    atr_stop=Decimal("9800"),
                    trend="BULLISH",
                    rsi=Decimal("52"),
                    gap_pct=Decimal("1.0"),
                    opening_broker_backing_tag="BACKED",
                )
            ],
            run_date=SESSION,
        )
    )
    assert line.confirmation.decision is pure.confirmations[0].decision
    assert line.confirmation.planned_entry == pure.confirmations[0].planned_entry


def test_mid_only_snapshot_does_not_masquerade_as_open(tmp_path: Path) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "learn.db")
    obs = _add_observation(repo)
    _add_track(
        repo,
        obs.observation_id,
        sampled_at=datetime(2026, 6, 18, 9, 1, tzinfo=WIB),
        payload={"mid_price": "10050", "best_bid": "10000", "best_offer": "10100"},
    )
    result = _uc(repo).execute(AnalyzePreOpenRequest(observation_id=obs.observation_id))
    assert result.status is AnalyzePreOpenStatus.UNAVAILABLE_OPENING
    assert result.lines[0].confirmation.decision is PreOpenPostOpenDecision.SKIP_INSUFFICIENT_DATA
    assert result.lines[0].price_provenance["opening_price"] is None


def test_missing_observation_fails(tmp_path: Path) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "learn.db")
    with pytest.raises(AnalyzePreOpenNotFoundError):
        _uc(repo).execute(AnalyzePreOpenRequest(observation_id="does-not-exist"))


def test_no_post_open_track_unavailable(tmp_path: Path) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "learn.db")
    obs = _add_observation(repo)
    _add_track(
        repo,
        obs.observation_id,
        sampled_at=datetime(2026, 6, 18, 8, 59, tzinfo=WIB),
        payload={
            "opening_price": "10050",
            "opening_price_source": "order_book_lastprice",
        },
    )
    result = _uc(repo).execute(AnalyzePreOpenRequest(observation_id=obs.observation_id))
    assert result.status is AnalyzePreOpenStatus.UNAVAILABLE_OPENING
    assert result.lines[0].opening_snapshot_id is None


def test_default_picks_earliest_open_window_sample(tmp_path: Path) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "learn.db")
    obs = _add_observation(repo)
    early = _add_track(
        repo,
        obs.observation_id,
        sampled_at=datetime(2026, 6, 18, 9, 0, 5, tzinfo=WIB),
        payload={
            "opening_price": "10000",
            "opening_price_source": "order_book_lastprice",
        },
        source="stockbit.opening_track.a",
    )
    _add_track(
        repo,
        obs.observation_id,
        sampled_at=datetime(2026, 6, 18, 9, 5, tzinfo=WIB),
        payload={
            "opening_price": "10100",
            "opening_price_source": "order_book_lastprice",
        },
        source="stockbit.opening_track.b",
    )
    result = _uc(repo).execute(AnalyzePreOpenRequest(observation_id=obs.observation_id))
    assert result.lines[0].opening_snapshot_id == early.snapshot_id
    assert result.lines[0].confirmation.opening_price == Decimal("10000")


def test_ambiguous_cohort_requires_observation_id(tmp_path: Path) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "learn.db")
    _add_observation(repo, ticker="BBCA", compatibility_id="compat-a")
    _add_observation(repo, ticker="BBRI", compatibility_id="compat-b")
    with pytest.raises(AnalyzePreOpenAmbiguityError):
        _uc(repo).execute(AnalyzePreOpenRequest(session_date=SESSION))


def test_unlinked_snapshot_id_fails(tmp_path: Path) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "learn.db")
    obs_a = _add_observation(repo, ticker="BBCA")
    obs_b = _add_observation(repo, ticker="BBRI")
    snap_b = _add_track(
        repo,
        obs_b.observation_id,
        sampled_at=datetime(2026, 6, 18, 9, 0, tzinfo=WIB),
        payload={
            "opening_price": "4000",
            "opening_price_source": "order_book_lastprice",
        },
    )
    with pytest.raises(AnalyzePreOpenSnapshotError):
        _uc(repo).execute(
            AnalyzePreOpenRequest(
                observation_id=obs_a.observation_id,
                opening_snapshot_id=snap_b.snapshot_id,
            )
        )


def test_session_selects_single_cohort(tmp_path: Path) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "learn.db")
    obs = _add_observation(repo, ticker="BBCA")
    _add_track(
        repo,
        obs.observation_id,
        sampled_at=datetime(2026, 6, 18, 9, 0, tzinfo=WIB),
        payload={
            "opening_price": "10050",
            "opening_price_source": "order_book_lastprice",
        },
    )
    result = _uc(repo).execute(AnalyzePreOpenRequest(session_date=SESSION))
    assert result.status is AnalyzePreOpenStatus.OK
    assert result.lines[0].ticker == "BBCA"


def test_application_layer_imports_are_clean() -> None:
    source = Path("src/application/use_case/analyze_pre_open_use_case.py").read_text(
        encoding="utf-8"
    )
    for forbidden in (
        "sqlite3",
        "typer",
        "rich",
        "stockbit",
        "playwright",
        "yaml",
    ):
        assert forbidden not in source.lower() or forbidden == "yaml"
    assert "import sqlite3" not in source
    assert "import typer" not in source
    assert "from rich" not in source
