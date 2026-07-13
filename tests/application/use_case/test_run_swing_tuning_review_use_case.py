"""
Tests for RunSwingTuningReviewUseCase.

Uses fakes for backtest_runner/document_loader/review_journal. Real
SwingBacktestAttributionSummary and real tuning-contract builders are used
because they are pure application functions the use case itself depends on.

No imports from src.adapters or src.infrastructure.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from src.application.services.swing_backtest_attribution import (
    summarize_swing_backtest_attribution,
)
from src.application.services.swing_tuning_review_journal import (
    SwingTuningReviewSaveResult,
)
from src.application.use_case.run_swing_tuning_review_use_case import (
    RunSwingTuningReviewRequest,
    RunSwingTuningReviewUseCase,
    SwingTuningRunnerDefaults,
)
from src.application.use_case.swing_backtest_use_case import SwingBacktestResponse
from tests.application.services.swing_backtest_attribution_fixtures import (
    ObservationFixture,
    make_trade,
)


def _attribution_summary(trade_count: int = 1, observation_count: int = 1):
    trades = tuple(
        make_trade(ticker=f"T{i}", net_return_pct=5.0, pnl="500")
        for i in range(trade_count)
    )
    observations = tuple(
        ObservationFixture(forward_return_pct=1.0) for _ in range(observation_count)
    )
    return summarize_swing_backtest_attribution(trades, observations)


def _response(
    *,
    start_date=date(2026, 1, 1),
    end_date=date(2026, 1, 10),
    setup="foreign-bounce",
    attribution_summary=None,
    trade_count=1,
    total_return_pct=5.0,
    win_rate_pct=100.0,
    max_drawdown_pct=0.0,
    avg_trade_return_pct=5.0,
    profit_factor=2.0,
) -> SwingBacktestResponse:
    return SwingBacktestResponse(
        setup=setup,
        start_date=start_date,
        end_date=end_date,
        initial_capital=Decimal("100000000"),
        cost_bps=Decimal("20"),
        final_equity=Decimal("105000000"),
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        trade_count=trade_count,
        win_rate_pct=win_rate_pct,
        avg_trade_return_pct=avg_trade_return_pct,
        profit_factor=profit_factor,
        exposure_pct=50.0,
        skipped_no_cash=0,
        skipped_duplicate=0,
        skipped_no_forward_data=0,
        skipped_by_regime=0,
        attribution_summary=attribution_summary or _attribution_summary(),
    )


class FakeBacktestRunner:
    """Records every call and returns a queued response (or the same one repeatedly)."""

    def __init__(self, responses=None, default_response=None):
        self.calls: list[dict] = []
        self._responses = list(responses) if responses is not None else None
        self._default_response = default_response or _response()

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self._responses:
            return self._responses.pop(0)
        return self._default_response


def _fake_document_loader(_target_path: str):
    return None


@dataclass
class FakeReviewJournal:
    """Stands in for SwingTuningReviewJournal.append_review."""

    save_result: SwingTuningReviewSaveResult
    appended: list = None

    def __post_init__(self):
        self.appended = []

    def append_review(self, review: dict) -> SwingTuningReviewSaveResult:
        self.appended.append(review)
        return self.save_result


DEFAULTS = SwingTuningRunnerDefaults(
    capital=100_000_000,
    risk_pct=1.0,
    max_positions=5,
    take_profit_pct=5.0,
    stop_loss_pct=5.0,
    max_hold_days=10,
    cost_bps=20.0,
)


def _base_request(**overrides) -> RunSwingTuningReviewRequest:
    defaults = dict(
        tickers=["BBCA"],
        universe=None,
        setup="foreign-bounce",
        start="2026-01-01",
        end=None,
        capital=None,
        risk_pct=None,
        max_positions=None,
        take_profit=None,
        stop_loss=None,
        max_hold=None,
        cost_bps=None,
        with_regime=False,
        allow_regimes=None,
        benchmark="IHSG",
        db_path=None,
        output_format="table",
        save=False,
        export_patch=False,
        is_ratio=None,
    )
    defaults.update(overrides)
    return RunSwingTuningReviewRequest(**defaults)


def _make_use_case(
    *,
    backtest_runner=None,
    runner_defaults=None,
    document_loader=None,
    review_journal=None,
):
    return RunSwingTuningReviewUseCase(
        backtest_runner=backtest_runner or FakeBacktestRunner(),
        runner_defaults=runner_defaults or DEFAULTS,
        document_loader=document_loader or _fake_document_loader,
        review_journal=review_journal,
    )


def test_builds_base_review_payload_with_exact_top_level_keys():
    use_case = _make_use_case()
    result = use_case.execute(_base_request())

    assert set(result.payload.keys()) == {
        "schema_version",
        "artifact_type",
        "intent",
        "setup",
        "start_date",
        "end_date",
        "sample",
        "backtest_summary",
        "attribution_summary",
        "tuning_plan",
        "tuning_proposal",
        "tuning_config_diff",
        "apply",
    }
    assert result.payload["artifact_type"] == "swing_tuning_review"
    assert result.payload["schema_version"] == 1


def test_resolves_defaults_from_injected_runner_defaults_when_overrides_none():
    runner = FakeBacktestRunner()
    use_case = _make_use_case(backtest_runner=runner)

    use_case.execute(_base_request())

    call = runner.calls[0]
    assert call["capital"] == DEFAULTS.capital
    assert call["risk_pct"] == DEFAULTS.risk_pct
    assert call["max_positions"] == DEFAULTS.max_positions
    assert call["take_profit"] == DEFAULTS.take_profit_pct
    assert call["stop_loss"] == DEFAULTS.stop_loss_pct
    assert call["max_hold"] == DEFAULTS.max_hold_days
    assert call["cost_bps"] == DEFAULTS.cost_bps


def test_explicit_cli_overrides_win_over_defaults():
    runner = FakeBacktestRunner()
    use_case = _make_use_case(backtest_runner=runner)

    use_case.execute(
        _base_request(
            capital=1,
            risk_pct=0.5,
            max_positions=9,
            take_profit=1.5,
            stop_loss=2.5,
            max_hold=3,
            cost_bps=99.0,
        )
    )

    call = runner.calls[0]
    assert call["capital"] == 1
    assert call["risk_pct"] == 0.5
    assert call["max_positions"] == 9
    assert call["take_profit"] == 1.5
    assert call["stop_loss"] == 2.5
    assert call["max_hold"] == 3
    assert call["cost_bps"] == 99.0


def test_is_ratio_without_end_raises_exact_message():
    use_case = _make_use_case()

    with pytest.raises(
        ValueError,
        match=r"--is-ratio requires --end to define the full date range\.",
    ):
        use_case.execute(_base_request(is_ratio=0.7, end=None))


def test_is_ratio_outside_range_raises_exact_message():
    use_case = _make_use_case()

    with pytest.raises(
        ValueError,
        match=r"--is-ratio must be in range \(0\.0, 1\.0\) exclusive, got 1\.5",
    ):
        use_case.execute(_base_request(is_ratio=1.5, end="2026-02-01"))


def test_start_after_end_raises_exact_message():
    use_case = _make_use_case()

    with pytest.raises(ValueError, match=r"--start must be before --end\."):
        use_case.execute(
            _base_request(is_ratio=0.7, start="2026-02-01", end="2026-01-01")
        )


def test_too_small_date_range_raises_exact_message():
    use_case = _make_use_case()

    with pytest.raises(
        ValueError,
        match=(
            r"--is-ratio requires a date range large enough to produce "
            r"non-empty IS and OOS windows\."
        ),
    ):
        use_case.execute(
            _base_request(is_ratio=0.99, start="2026-01-01", end="2026-01-02")
        )


def test_walk_forward_split_calls_backtest_runner_twice_with_correct_dates():
    runner = FakeBacktestRunner(
        responses=[_response(), _response()],
    )
    use_case = _make_use_case(backtest_runner=runner)

    use_case.execute(
        _base_request(
            is_ratio=0.7,
            start="2026-01-01",
            end="2026-01-11",
            output_format="table",
        )
    )

    assert len(runner.calls) == 2
    is_call, oos_call = runner.calls
    assert is_call["start"] == "2026-01-01"
    assert is_call["end"] == "2026-01-08"
    assert is_call["announce"] is True
    assert oos_call["start"] == "2026-01-09"
    assert oos_call["end"] == "2026-01-11"
    assert oos_call["announce"] is False


def test_output_format_json_means_is_split_message_is_none():
    runner = FakeBacktestRunner(responses=[_response(), _response()])
    use_case = _make_use_case(backtest_runner=runner)

    result = use_case.execute(
        _base_request(
            is_ratio=0.7,
            start="2026-01-01",
            end="2026-01-11",
            output_format="json",
        )
    )

    assert result.is_split_message is None


def test_output_format_table_returns_exact_split_message():
    runner = FakeBacktestRunner(responses=[_response(), _response()])
    use_case = _make_use_case(backtest_runner=runner)

    result = use_case.execute(
        _base_request(
            is_ratio=0.7,
            start="2026-01-01",
            end="2026-01-11",
            output_format="table",
        )
    )

    assert result.is_split_message == (
        "Walk-forward split: IS 2026-01-01 -> 2026-01-08  "
        "OOS 2026-01-09 -> 2026-01-11"
    )


def test_oos_backtest_summary_keys_preserved_from_oos_response():
    oos_response = _response(
        trade_count=7,
        total_return_pct=1.23,
        win_rate_pct=42.0,
        max_drawdown_pct=-3.5,
        avg_trade_return_pct=0.9,
        profit_factor=1.1,
    )
    runner = FakeBacktestRunner(responses=[_response(), oos_response])
    use_case = _make_use_case(backtest_runner=runner)

    result = use_case.execute(
        _base_request(
            is_ratio=0.7,
            start="2026-01-01",
            end="2026-01-11",
            output_format="table",
        )
    )

    assert result.payload["oos_backtest_summary"] == {
        "trade_count": 7,
        "total_return_pct": 1.23,
        "win_rate_pct": 42.0,
        "max_drawdown_pct": -3.5,
        "avg_trade_return_pct": 0.9,
        "profit_factor": 1.1,
    }


def test_save_true_calls_journal_append_review_and_sets_persistence():
    save_result = SwingTuningReviewSaveResult(
        saved=True, record_count=3, recorded_at="2026-01-01T00:00:00+07:00"
    )
    journal = FakeReviewJournal(save_result=save_result)
    use_case = _make_use_case(review_journal=journal)

    result = use_case.execute(_base_request(save=True))

    assert len(journal.appended) == 1
    assert result.persistence == save_result.to_dict()
    assert "path" not in result.persistence


def test_patch_payload_includes_only_diff_items_with_non_none_proposed_value():
    use_case = _make_use_case()

    result = use_case.execute(_base_request(export_patch=True))

    assert result.patch_payload is not None
    diff_items = result.payload["tuning_config_diff"].get("diff_items") or []
    expected_count = len(
        [item for item in diff_items if item.get("proposed_value") is not None]
    )
    assert result.patch_payload["item_count"] == expected_count
    assert len(result.patch_payload["patch_items"]) == expected_count
    assert set(result.patch_payload.keys()) == {
        "schema_version",
        "artifact_type",
        "intent",
        "source_review",
        "patch_items",
        "item_count",
        "apply",
    }
    assert result.patch_payload["artifact_type"] == "swing_tuning_patch_review"


def test_patch_payload_source_review_includes_walk_forward_metadata():
    oos_response = _response(trade_count=5)
    runner = FakeBacktestRunner(responses=[_response(), oos_response])
    use_case = _make_use_case(backtest_runner=runner)

    result = use_case.execute(
        _base_request(
            is_ratio=0.7,
            start="2026-01-01",
            end="2026-01-11",
            output_format="table",
            export_patch=True,
        )
    )

    source_review = result.patch_payload["source_review"]
    assert source_review["is_ratio"] == 0.7
    assert source_review["is_end_date"] == "2026-01-08"
    assert source_review["oos_start_date"] == "2026-01-09"
    assert source_review["full_end_date"] == "2026-01-11"
    assert source_review["oos_backtest_summary"] == {
        "trade_count": 5,
        "total_return_pct": 5.0,
        "win_rate_pct": 100.0,
        "max_drawdown_pct": 0.0,
        "avg_trade_return_pct": 5.0,
        "profit_factor": 2.0,
    }
    assert source_review["walk_forward_enforced"] is True
