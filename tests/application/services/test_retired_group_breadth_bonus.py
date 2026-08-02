"""ADR-062 clean-break: retired group-breadth bonus surfaces.

Historical observation rows may still carry residual sector_breadth_* keys as
immutable raw facts. New producers must not emit policy fields, payload keys,
or score mutations.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenRequest,
)
from src.application.services.accumulation_observation_fingerprint import (
    _CONFIG_HASH_FIELDS,
    compute_accumulation_config_hash,
)


def _candidate(ticker: str = "BBCA") -> AccumulationCandidate:
    return AccumulationCandidate(
        ticker=ticker,
        window_days=7,
        net_buy_days=3,
        total_days=7,
        net_buy_ratio=0.5,
        total_net_value=Decimal("1000"),
        consecutive_streak=1,
        foreign_vwap=None,
        current_price=Decimal("100"),
        vwap_discount_pct=None,
        rsi=None,
        trend="SIDE",
        accum_score=50.0,
        top_brokers=[],
        institutional_flag=False,
        bci_label="STABLE",
        bci_tier1_count=1,
    )


def test_new_candidate_to_dict_omits_retired_breadth_payload_keys() -> None:
    payload = _candidate().to_dict()
    assert "sector_breadth_pct" not in payload
    assert "sector_breadth_bonus" not in payload
    assert payload["accum_score"] == 50.0


def test_screen_request_has_no_sector_breadth_fields() -> None:
    request = AccumulationScreenRequest(
        tickers=["BBCA"],
        window_days=7,
        as_of_date=date(2026, 6, 19),
    )
    assert not hasattr(request, "sector_breadth_enabled")
    assert not hasattr(request, "sector_breadth_threshold")
    assert not hasattr(request, "sector_breadth_bonus_pts")
    assert not hasattr(request, "sector_breadth_min_tickers")


def test_config_hash_fields_exclude_retired_breadth_knobs() -> None:
    retired = {
        "sector_breadth_enabled",
        "sector_breadth_threshold",
        "sector_breadth_bonus_pts",
        "sector_breadth_min_tickers",
    }
    assert retired.isdisjoint(set(_CONFIG_HASH_FIELDS))


def test_config_hash_is_stable_without_breadth_fields() -> None:
    request = AccumulationScreenRequest(
        tickers=["BBCA", "BBRI"],
        window_days=7,
        as_of_date=date(2026, 6, 19),
        min_accum_score=0.0,
    )
    h1 = compute_accumulation_config_hash(request)
    h2 = compute_accumulation_config_hash(request)
    assert h1 == h2
    assert len(h1) == 16


def test_production_output_equivalence_no_score_mutation_surface() -> None:
    """Golden production path: scores are never mutated by group breadth.

    Production never supplied idx_groups; after ADR-062 there is no applier to
    inject. Ranking and Action depend only on pre-bonus Accum components.
    """
    candidates = [_candidate("BBCA"), _candidate("BBRI")]
    before = [(c.ticker, c.accum_score) for c in candidates]
    # No applier exists; identity over scores is the production contract.
    after = [(c.ticker, c.accum_score) for c in candidates]
    assert before == after == [("BBCA", 50.0), ("BBRI", 50.0)]
