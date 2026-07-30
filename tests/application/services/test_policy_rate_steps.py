"""Tests for policy_rate_steps application helpers and sector-macro scoring."""

from datetime import date, timedelta
from decimal import Decimal

from src.application.services.policy_rate_steps import (
    BI_RATE_SERIES_KEY,
    filter_steps_on_or_before,
    macro_events_to_policy_steps,
    net_step_delta,
)
from src.application.services.sector_macro_context_evidence_builder import (
    SectorMacroContextConfig,
    SectorMacroContextEvidenceBuilder,
    SectorMacroContextRequest,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.macro_calendar_event import (
    MacroCalendarEvent,
    MacroEventCategory,
)
from src.domain.value_objects.policy_rate_step import (
    PolicyRateDirection,
    PolicyRateStep,
)


def _event(
    eid: str,
    d: date,
    title: str = "BI Rate",
    actual: str = "5.50%",
    previous: str = "5.75%",
) -> MacroCalendarEvent:
    return MacroCalendarEvent(
        source_event_id=eid,
        event_date=d,
        category=MacroEventCategory.BI_RATE,
        title=title,
        actual=actual,
        previous=previous,
        raw_payload_json="{}",
        fetched_at="2026-07-01T00:00:00",
    )


class TestMacroToSteps:
    def test_cut_maps_to_cut_direction(self):
        steps = macro_events_to_policy_steps([_event("1", date(2026, 6, 1))])
        assert len(steps) == 1
        assert steps[0].direction is PolicyRateDirection.CUT

    def test_net_delta_one_cut(self):
        steps = macro_events_to_policy_steps([_event("1", date(2026, 6, 1))])
        assert net_step_delta(steps) == -1.0

    def test_net_delta_hike_and_cut(self):
        steps = macro_events_to_policy_steps(
            [
                _event("1", date(2026, 1, 1), actual="6.00%", previous="5.75%"),
                _event("2", date(2026, 4, 1), actual="5.75%", previous="6.00%"),
            ]
        )
        assert net_step_delta(steps) == 0.0

    def test_filter_as_of(self):
        steps = (
            PolicyRateStep(date(2026, 1, 1), "A", PolicyRateDirection.HIKE),
            PolicyRateStep(date(2026, 6, 1), "B", PolicyRateDirection.CUT),
        )
        assert len(filter_steps_on_or_before(steps, date(2026, 3, 1))) == 1


def _candle(ticker: str, d: date, close: float) -> Candle:
    return Candle(
        ticker=ticker,
        date=d,
        open=Decimal(str(close)),
        high=Decimal(str(close)),
        low=Decimal(str(close)),
        close=Decimal(str(close)),
        volume=1000,
    )


def _bank_config() -> SectorMacroContextConfig:
    return SectorMacroContextConfig.from_mapping(
        {
            "sector_macro_context": {
                "evidence_status": "DIAGNOSTIC",
                "lookback_sessions": 10,
                "min_valid_sessions": 5,
                "min_coverage_to_label": 0.5,
                "score_labels": {"favorable_min": 0.65, "neutral_min": 0.35},
                "regime_thresholds": {"supportive_min": 0.65, "headwind_max": 0.35},
                "factor_library": {
                    "bi_rate_policy": {
                        "series": BI_RATE_SERIES_KEY,
                        "kind": "policy_rate_steps",
                        "invert": True,
                        "lookback_days": 180,
                        "thresholds": {"supportive_min": 1.0, "headwind_max": -1.0},
                    },
                    "usd_idr_risk": {
                        "series": "IDR=X",
                        "kind": "return_sessions",
                        "invert": True,
                        "thresholds": {"supportive_min": 0.01, "headwind_max": -0.01},
                    },
                },
                "sector_maps": {
                    "bank": {
                        "factors": [
                            {"ref": "bi_rate_policy", "weight": 0.55},
                            {"ref": "usd_idr_risk", "weight": 0.45},
                        ]
                    }
                },
            }
        }
    )


class TestBankPolicyPilot:
    def test_required_series_excludes_bi_rate(self):
        cfg = _bank_config()
        assert BI_RATE_SERIES_KEY not in cfg.required_series_tickers()
        assert "IDR=X" in cfg.required_series_tickers()
        assert cfg.policy_series_for_group("bank") == (BI_RATE_SERIES_KEY,)

    def test_bi_cut_is_supportive_for_bank(self):
        cfg = _bank_config()
        builder = SectorMacroContextEvidenceBuilder(cfg)
        as_of = date(2026, 7, 1)
        # Stable IDR (no FX stress) so BI factor dominates regime
        idr = [_candle("IDR=X", as_of - timedelta(days=i), 16000.0) for i in range(20)]
        cut = PolicyRateStep(
            event_date=date(2026, 6, 15),
            title="BI Rate",
            direction=PolicyRateDirection.CUT,
            actual="5.25%",
            previous="5.50%",
        )
        ev = builder.build(
            SectorMacroContextRequest(
                ticker="BBCA",
                snapshot_date=as_of,
                sector_group="bank",
                series_candles={"IDR=X": tuple(reversed(idr))},
                policy_steps={BI_RATE_SERIES_KEY: (cut,)},
            )
        )
        bi = next(f for f in ev.factors if f.name == "bi_rate_policy")
        assert bi.label == "FAVORABLE"
        assert bi.value == -1.0
        assert bi.score == 1.0

    def test_bi_hike_is_stressed_for_bank(self):
        cfg = _bank_config()
        builder = SectorMacroContextEvidenceBuilder(cfg)
        as_of = date(2026, 7, 1)
        idr = [_candle("IDR=X", as_of - timedelta(days=i), 16000.0) for i in range(20)]
        hike = PolicyRateStep(
            event_date=date(2026, 6, 15),
            title="BI Rate",
            direction=PolicyRateDirection.HIKE,
            actual="5.75%",
            previous="5.50%",
        )
        ev = builder.build(
            SectorMacroContextRequest(
                ticker="BBCA",
                snapshot_date=as_of,
                sector_group="bank",
                series_candles={"IDR=X": tuple(reversed(idr))},
                policy_steps={BI_RATE_SERIES_KEY: (hike,)},
            )
        )
        bi = next(f for f in ev.factors if f.name == "bi_rate_policy")
        assert bi.label == "STRESSED"
        assert bi.score == 0.0

    def test_missing_policy_steps_unavailable(self):
        cfg = _bank_config()
        builder = SectorMacroContextEvidenceBuilder(cfg)
        as_of = date(2026, 7, 1)
        idr = [_candle("IDR=X", as_of - timedelta(days=i), 16000.0) for i in range(20)]
        ev = builder.build(
            SectorMacroContextRequest(
                ticker="BBCA",
                snapshot_date=as_of,
                sector_group="bank",
                series_candles={"IDR=X": tuple(reversed(idr))},
                policy_steps={BI_RATE_SERIES_KEY: ()},
            )
        )
        bi = next(f for f in ev.factors if f.name == "bi_rate_policy")
        assert bi.label == "UNAVAILABLE"
        assert any("no_policy_steps" in r for r in ev.unavailable_reasons)


class TestStockbitCorridorTitles:
    """P0: only Interest Rate Decision enters bi_rate; facilities would 3× net steps."""

    def test_interest_rate_decision_title_produces_steps(self):
        steps = macro_events_to_policy_steps(
            [
                _event(
                    "ird",
                    date(2026, 6, 18),
                    title="Interest Rate Decision",
                    actual="5.75%",
                    previous="5.50%",
                )
            ]
        )
        assert steps[0].direction is PolicyRateDirection.HIKE
        assert net_step_delta(steps) == 1.0

    def test_same_day_facility_rows_would_triple_count_if_all_bi_rate(self):
        d = date(2026, 6, 18)
        # What would happen if Deposit/Lending were also category=bi_rate
        triple = macro_events_to_policy_steps(
            [
                _event("ird", d, "Interest Rate Decision", "5.75%", "5.50%"),
                _event("dep", d, "Deposit Facility Rate", "4.75%", "4.50%"),
                _event("lend", d, "Lending Facility Rate", "6.5%", "6.25%"),
            ]
        )
        assert net_step_delta(triple) == 3.0
        # Correct ingest: only Interest Rate Decision is bi_rate → net 1
        only_ird = macro_events_to_policy_steps(
            [_event("ird", d, "Interest Rate Decision", "5.75%", "5.50%")]
        )
        assert net_step_delta(only_ird) == 1.0
