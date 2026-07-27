import json
from datetime import date

from src.application.use_case import opening_tune_use_case as opening_tune
from src.application.use_case.opening_tune_use_case import OpeningTuneRequest, OpeningTuneUseCase


def _write_grade(day_dir, *, phase="POST_OPEN", valid=False, confidence="LOW"):
    day_dir.mkdir(parents=True)
    (day_dir / "grade.json").write_text(
        json.dumps(
            {
                "date": "2026-06-18",
                "capture_phase": phase,
                "capture_valid_for_opening_prediction": valid,
                "capture_confidence": confidence,
                "data_quality": {
                    "capture_phase": phase,
                    "capture_valid_for_opening_prediction": valid,
                    "capture_confidence": confidence,
                },
                "per_ticker": [],
                "config_snapshot": {},
            }
        )
    )


def test_opening_tune_skips_invalid_snapshot_before_ai_call(tmp_path, monkeypatch):
    day_dir = tmp_path / "20260618"
    _write_grade(day_dir)
    monkeypatch.setattr(opening_tune, "OPENING_DATA_DIR", tmp_path)

    called = False

    def fake_call(*args, **kwargs):
        nonlocal called
        called = True
        return "{}", 0

    monkeypatch.setattr(opening_tune, "_call_deepseek", fake_call)

    result = OpeningTuneUseCase().execute(
        OpeningTuneRequest(
            run_date=date(2026, 6, 18),
            deepseek_api_key="test",
        )
    )

    assert result["skipped"] is True
    assert result["requires_override"] == "--allow-invalid-snapshot"
    assert called is False


def test_opening_tune_allows_invalid_snapshot_with_explicit_override(tmp_path, monkeypatch):
    day_dir = tmp_path / "20260618"
    _write_grade(day_dir)
    monkeypatch.setattr(opening_tune, "OPENING_DATA_DIR", tmp_path)
    monkeypatch.setattr(
        opening_tune,
        "_call_deepseek",
        lambda **kwargs: (
            """```json
{"summary":"ok","top_finding":"none","config_recommendations":{},"watch_next_session":[]}
```""",
            12,
        ),
    )

    result = OpeningTuneUseCase().execute(
        OpeningTuneRequest(
            run_date=date(2026, 6, 18),
            deepseek_api_key="test",
            allow_invalid_snapshot=True,
        )
    )

    assert result["summary"] == "ok"
    assert result["tokens_used"] == 12
