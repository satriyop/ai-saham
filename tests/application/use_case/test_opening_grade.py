import json
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from src.application.services.pre_open_observation_payload import PRE_OPEN_WORKFLOW
from src.application.use_case import opening_grade_use_case as opening_grade


def _obs_row(
    *,
    ticker: str = "BBCA",
    score: int = 75,
    entry_low: str = "9900",
    entry_high: str = "10100",
    capture_phase: str = "NCP_LOCKED",
    trend: str = "BULLISH",
    direction: str = "BULLISH",
) -> SimpleNamespace:
    return SimpleNamespace(
        ticker=ticker,
        workflow=PRE_OPEN_WORKFLOW,
        payload={
            "workflow": PRE_OPEN_WORKFLOW,
            "screen_result": "pass",
            "capture_phase": capture_phase,
            "candidate": {
                "ticker": ticker,
                "trend_signal": trend,
                "entry_range_low": entry_low,
                "entry_range_high": entry_high,
                "entry_price": "10050",
                "stop_loss_price": "9800",
                "bid_offer_imbalance": 0.6,
                "iep": 6400,
            },
            "signal": {
                "contract": "pre_open_directional_baseline.v1",
                "direction": direction,
                "confidence": "HIGH",
                "auction_quality": "RELIABLE",
                "raw_score": score,
                "score": score,
                "strength": "STRONG",
                "entry_quality": "ENTER",
                "factors": {
                    "iep_direction": "UP",
                    "book_pressure_state": "BUY",
                    "participation_state": "BUILDING",
                    "delta_iev": 50_000,
                    "delta_iev_ratio": 0.1,
                    "iev_intensity": 2.0,
                    "rsi_extension": False,
                    "unusual_volume": False,
                },
                "rationale": ["direction=BULLISH"],
                "quality_reasons": [],
            },
            "trade_setup": {"action": "ENTER"},
            "risk": {"risk_level_name": "LOW_RISK"},
        },
        captured_at=datetime(2026, 6, 18, 8, 57, tzinfo=ZoneInfo("Asia/Jakarta")),
    )


def test_opening_grade_prefers_orderbook_lastprice_over_midpoint(tmp_path, monkeypatch):
    day_dir = tmp_path / "20260618"
    day_dir.mkdir()
    (day_dir / "track_0900.json").write_text(
        json.dumps(
            {
                "captured_at": "2026-06-18T09:00:01+07:00",
                "tickers": {
                    "BBCA": {
                        "mid_price": 6375,
                        "order_book": {
                            "last_price": 6400,
                            "bid_pressure_ratio": 0.7,
                            "fnet_intraday": 1_000_000_000,
                        },
                    }
                },
            }
        )
    )

    repo = SimpleNamespace(
        list_all_by_date=lambda d: [_obs_row(entry_low="6000", entry_high="6500")]
    )
    monkeypatch.setattr(opening_grade, "OPENING_DATA_DIR", tmp_path)

    result = opening_grade.compute_grade(
        date(2026, 6, 18),
        observations_repository=repo,
    )

    ticker = result["per_ticker"][0]
    assert ticker["opening_price"] == 6400
    assert ticker["opening_price_source"] == "order_book_lastprice"
    assert ticker["opening_price_confidence"] == "MEDIUM"
    assert ticker["capture_phase"] == "NCP_LOCKED"
    assert result["decision_source"] == "saved_observations"
    assert result["schema_version"] == 3
    assert result["data_quality"]["medium_confidence_price_count"] == 1
    assert result["data_quality"]["low_confidence_price_count"] == 0
    assert result["data_quality"]["price_source_counts"]["order_book_lastprice"] == 1


def test_opening_grade_marks_midpoint_as_low_confidence_fallback(tmp_path, monkeypatch):
    day_dir = tmp_path / "20260618"
    day_dir.mkdir()
    (day_dir / "track_0900.json").write_text(
        json.dumps(
            {
                "captured_at": "2026-06-18T09:00:01+07:00",
                "tickers": {"BBCA": {"mid_price": 6375}},
            }
        )
    )

    repo = SimpleNamespace(
        list_all_by_date=lambda d: [_obs_row(entry_low="6000", entry_high="6500")]
    )
    monkeypatch.setattr(opening_grade, "OPENING_DATA_DIR", tmp_path)

    result = opening_grade.compute_grade(
        date(2026, 6, 18),
        observations_repository=repo,
    )

    ticker = result["per_ticker"][0]
    assert ticker["opening_price"] == 6375
    assert ticker["opening_price_source"] == "top_of_book_midpoint"
    assert ticker["opening_price_confidence"] == "LOW"
    assert result["data_quality"]["low_confidence_price_count"] == 1
    assert result["data_quality"]["price_source_counts"]["top_of_book_midpoint"] == 1


def test_opening_grade_requires_saved_observations(tmp_path, monkeypatch):
    day_dir = tmp_path / "20260618"
    day_dir.mkdir()
    (day_dir / "track_0900.json").write_text(
        json.dumps(
            {
                "captured_at": "2026-06-18T09:00:01+07:00",
                "tickers": {"BBCA": {"opening_price": 10000}},
            }
        )
    )
    # Ops export alone is not enough
    (day_dir / "ops_session.json").write_text(
        json.dumps(
            {
                "candidates": [{"ticker": "BBCA", "entry_range_low": 1, "entry_range_high": 2}],
            }
        )
    )

    monkeypatch.setattr(opening_grade, "OPENING_DATA_DIR", tmp_path)
    try:
        opening_grade.compute_grade(
            date(2026, 6, 18),
            observations_repository=SimpleNamespace(list_all_by_date=lambda d: []),
        )
        assert False, "expected FileNotFoundError"
    except FileNotFoundError as exc:
        assert "research pre-open capture" in str(exc)


def test_opening_grade_from_saved_observations(tmp_path, monkeypatch):
    day_dir = tmp_path / "20260618"
    day_dir.mkdir()
    (day_dir / "track_0900.json").write_text(
        json.dumps(
            {
                "captured_at": "2026-06-18T09:00:01+07:00",
                "tickers": {"BBCA": {"opening_price": 10000, "opening_price_confidence": "HIGH"}},
            }
        )
    )

    repo = SimpleNamespace(list_all_by_date=lambda d: [_obs_row()])
    monkeypatch.setattr(opening_grade, "OPENING_DATA_DIR", tmp_path)
    result = opening_grade.compute_grade(
        date(2026, 6, 18),
        observations_repository=repo,
    )

    assert result["decision_source"] == "saved_observations"
    t = result["per_ticker"][0]
    assert t["signal_score"] == 75
    assert t["signal_band"] == "strong"
    assert t["trade_setup_action"] == "ENTER"
    assert t["screen_result"] == "pass"
    assert t["entry_range_hit"] is True  # 10000 in [9900, 10100]
    assert t["iep"] == 6400.0
    assert t["iep_error_pct"] == 36.0
    assert result["iep_accuracy"]["mean_error_pct"] == 36.0
    assert result["by_signal_band"]["strong"]["count"] == 1
    assert result["by_trade_setup_action"]["ENTER"]["count"] == 1


def test_opening_grade_uses_elapsed_time_for_direction_and_factor_slices(
    tmp_path,
    monkeypatch,
):
    day_dir = tmp_path / "20260618"
    day_dir.mkdir()
    observations = (
        ("track_0900.json", "2026-06-18T09:00:20+07:00", 10_000),
        ("track_0904.json", "2026-06-18T09:04:50+07:00", 10_010),
        ("track_0905.json", "2026-06-18T09:05:30+07:00", 10_100),
        ("track_0915.json", "2026-06-18T09:15:30+07:00", 10_200),
        ("track_0930.json", "2026-06-18T09:30:25+07:00", 10_300),
    )
    for filename, captured_at, price in observations:
        (day_dir / filename).write_text(
            json.dumps(
                {
                    "captured_at": captured_at,
                    "tickers": {
                        "BBCA": {
                            "opening_price": price,
                            "opening_price_confidence": "HIGH",
                        }
                    },
                }
            )
        )

    repo = SimpleNamespace(list_all_by_date=lambda d: [_obs_row()])
    monkeypatch.setattr(opening_grade, "OPENING_DATA_DIR", tmp_path)

    result = opening_grade.compute_grade(
        date(2026, 6, 18),
        observations_repository=repo,
    )

    ticker = result["per_ticker"][0]
    assert ticker["return_T5_pct"] == 1.0
    assert ticker["return_T15_pct"] == 2.0
    assert ticker["return_T30_pct"] == 3.0
    assert ticker["direction_correct_T5"] is True
    assert result["direction_accuracy_T5"] == 1.0
    assert result["by_direction"]["BULLISH"]["direction_accuracy_T30"] == 1.0
    assert result["by_direction_confidence"]["HIGH"]["count"] == 1
    assert result["by_auction_quality"]["RELIABLE"]["count"] == 1
    assert result["by_factor_state"]["iep_direction"]["UP"]["count"] == 1
    assert result["by_factor_state"]["participation_state"]["BUILDING"]["count"] == 1


@pytest.mark.parametrize(
    ("direction", "return_pct", "expected"),
    (
        ("BULLISH", 0.16, True),
        ("BULLISH", 0.15, False),
        ("BEARISH", -0.16, True),
        ("NEUTRAL", 0.15, True),
        ("NEUTRAL", -0.15, True),
        ("CONFLICTED", 1.0, None),
        ("UNKNOWN", -1.0, None),
    ),
)
def test_direction_accuracy_uses_deadband_and_excludes_non_predictions(
    direction,
    return_pct,
    expected,
):
    assert opening_grade._direction_correct(direction, return_pct) is expected
