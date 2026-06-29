import json
from datetime import date

from src.application.use_case import opening_grade_use_case as opening_grade


def test_opening_grade_prefers_orderbook_lastprice_over_midpoint(tmp_path, monkeypatch):
    day_dir = tmp_path / "20260618"
    day_dir.mkdir()
    (day_dir / "snapshot.json").write_text(json.dumps({
        "date": "2026-06-18",
        "capture_phase": "NCP_LOCKED",
        "capture_valid_for_opening_prediction": True,
        "capture_confidence": "HIGH",
        "candidates": [
            {
                "ticker": "BBCA",
                "opening_setup": "WATCH",
                "trend": "BULLISH",
                "iep": 6400,
                "entry_range_low": 6000,
                "entry_range_high": 6500,
                "suggested_entry": 6325,
                "atr_stop": 6200,
                "one_r": 125,
            }
        ],
    }))
    (day_dir / "track_0900.json").write_text(json.dumps({
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
    }))

    monkeypatch.setattr(opening_grade, "OPENING_DATA_DIR", tmp_path)

    result = opening_grade.compute_grade(date(2026, 6, 18))

    ticker = result["per_ticker"][0]
    assert ticker["opening_price"] == 6400
    assert ticker["opening_price_source"] == "order_book_lastprice"
    assert ticker["opening_price_confidence"] == "MEDIUM"
    assert ticker["capture_phase"] == "NCP_LOCKED"
    assert result["data_quality"]["medium_confidence_price_count"] == 1
    assert result["data_quality"]["low_confidence_price_count"] == 0
    assert result["data_quality"]["price_source_counts"]["order_book_lastprice"] == 1


def test_opening_grade_marks_midpoint_as_low_confidence_fallback(tmp_path, monkeypatch):
    day_dir = tmp_path / "20260618"
    day_dir.mkdir()
    (day_dir / "snapshot.json").write_text(json.dumps({
        "date": "2026-06-18",
        "candidates": [
            {
                "ticker": "BBCA",
                "opening_setup": "WATCH",
                "trend": "BULLISH",
                "entry_range_low": 6000,
                "entry_range_high": 6500,
            }
        ],
    }))
    (day_dir / "track_0900.json").write_text(json.dumps({
        "captured_at": "2026-06-18T09:00:01+07:00",
        "tickers": {"BBCA": {"mid_price": 6375}},
    }))

    monkeypatch.setattr(opening_grade, "OPENING_DATA_DIR", tmp_path)

    result = opening_grade.compute_grade(date(2026, 6, 18))

    ticker = result["per_ticker"][0]
    assert ticker["opening_price"] == 6375
    assert ticker["opening_price_source"] == "top_of_book_midpoint"
    assert ticker["opening_price_confidence"] == "LOW"
    assert result["data_quality"]["low_confidence_price_count"] == 1
    assert result["data_quality"]["price_source_counts"]["top_of_book_midpoint"] == 1
