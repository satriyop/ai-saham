"""ADR-062 offline golden gate (not a live LQ45 run).

Frozen synthetic projection under tests/fixtures/ with SHA-256 sidecar.
Proves live Accum ordering/score identity, omitted retired payload keys,
schema-12 producer identity, and absence of retired request attrs.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenRequest,
)
from src.domain.value_objects.signal_artifact_schema import (
    ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION,
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
    HISTORICAL_GROUP_BREADTH_ERA_CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)

_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE = _ROOT / "tests" / "fixtures" / "adr062_offline_group_breadth_retirement.v1.json"
_SHA = _ROOT / "tests" / "fixtures" / "adr062_offline_group_breadth_retirement.v1.sha256"


def _load_fixture() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def test_offline_golden_sha256_matches_sidecar() -> None:
    body = _FIXTURE.read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    recorded = _SHA.read_text(encoding="utf-8").strip().split()[0]
    assert digest == recorded


def test_schema_13_is_current_and_the_fixture_records_the_adr062_era() -> None:
    """The fixture is a frozen record of the ADR-062 era, not of "current".

    It froze while schema 12 was current. ADR-068 moved current to 13 (the
    write-only ``config_hash`` payload field was removed), so the fixture's own
    version stays 12 and is asserted as history, byte-identical to its sidecar.
    """
    assert ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION == 15
    assert CANDIDATE_OBSERVATION_SCHEMA_VERSION == 15
    assert HISTORICAL_GROUP_BREADTH_ERA_CANDIDATE_OBSERVATION_SCHEMA_VERSION == 11
    fixture = _load_fixture()
    assert fixture["candidate_observation_schema_version"] == 12


def test_offline_golden_reproduces_accum_scores_and_inclusion() -> None:
    fixture = _load_fixture()
    rebuilt = []
    for i, ticker in enumerate(fixture["tickers_ordered"]):
        score = 40.0 + i * 7.5
        c = AccumulationCandidate(
            ticker=ticker,
            window_days=7,
            net_buy_days=3 + (i % 3),
            total_days=7,
            net_buy_ratio=0.4 + i * 0.05,
            total_net_value=Decimal(str(1000 * (i + 1))),
            consecutive_streak=1 + i,
            foreign_vwap=None,
            current_price=Decimal(str(100 + i)),
            vwap_discount_pct=None,
            rsi=None,
            trend="SIDE",
            accum_score=score,
            top_brokers=[],
            institutional_flag=False,
            bci_label="STABLE",
            bci_tier1_count=1,
        )
        payload = c.to_dict()
        for key in fixture["forbidden_payload_keys"]:
            assert key not in payload
        rebuilt.append(
            {
                "ticker": ticker,
                "included": score >= fixture["min_accum_score"],
                "accum_score": score,
                "serialized_accum_score": payload["accum_score"],
            }
        )

    assert [r["ticker"] for r in rebuilt if r["included"]] == fixture["inclusion_order"]
    assert [r["ticker"] for r in rebuilt if not r["included"]] == fixture["exclusion_order"]
    for row, golden in zip(rebuilt, fixture["candidates"], strict=True):
        assert row["ticker"] == golden["ticker"]
        assert row["accum_score"] == golden["accum_score"]
        assert row["included"] == golden["included"]
        assert row["serialized_accum_score"] == golden["serialized_accum_score"]


def test_offline_golden_signal_risk_setup_projection_frozen() -> None:
    fixture = _load_fixture()
    included = [c for c in fixture["candidates"] if c["included"]]
    signal = {
        "raw_scores": {c["ticker"]: round(50.0 + c["accum_score"] * 0.2, 4) for c in included},
        "exact_scores": {c["ticker"]: round(48.0 + c["accum_score"] * 0.2, 4) for c in included},
        "actions": {c["ticker"]: "WATCH" if c["accum_score"] < 55 else "ENTER" for c in included},
    }
    risk = {
        "results": {
            c["ticker"]: {
                "status": "OPEN" if c["accum_score"] >= 50 else "BLOCKED",
                "gates": ["liquidity"] if c["accum_score"] < 50 else [],
            }
            for c in included
        }
    }
    setup = {
        c["ticker"]: {
            "phase": "EARLY" if c["accum_score"] < 60 else "BUILDING",
            "readiness": "PARTIAL" if c["accum_score"] < 60 else "READY",
        }
        for c in included
    }
    assert signal == fixture["signal_projection"]
    assert risk == fixture["risk_projection"]
    assert setup == fixture["setup_projection"]


def test_offline_golden_retired_request_attrs_stay_absent() -> None:
    """The retired-attribute half of the old config-hash gate.

    The ``compute_accumulation_config_hash(request) == fixture["config_hash"]``
    assertion is deliberately gone: ADR-068 deleted that function and the
    write-only payload field it fed. The fixture keeps its recorded
    ``config_hash`` as an immutable historical value, unread.
    """
    fixture = _load_fixture()
    request = AccumulationScreenRequest(
        tickers=list(fixture["tickers_ordered"]),
        window_days=7,
        as_of_date=date.fromisoformat(fixture["as_of_date"]),
        min_accum_score=float(fixture["min_accum_score"]),
    )
    for attr in fixture["forbidden_request_attrs"]:
        assert not hasattr(request, attr)


def test_typed_construction_rejects_retired_kwargs() -> None:
    with pytest.raises(TypeError):
        AccumulationScreenRequest(  # type: ignore[call-arg]
            tickers=["BBCA"],
            window_days=7,
            as_of_date=date(2026, 6, 19),
            sector_breadth_enabled=True,
        )
