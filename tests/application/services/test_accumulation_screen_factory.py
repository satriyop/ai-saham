from types import SimpleNamespace
from unittest.mock import Mock

from src.application.services.accumulation_screen_factory import (
    create_accumulation_screen_use_case,
)


def test_create_accumulation_screen_use_case_wires_stockbit_providers():
    broker_repo = Mock()
    market_repo = Mock()
    risk_use_case = Mock()
    signal_engine = Mock()
    providers = SimpleNamespace(
        corp_repo=Mock(),
        season_prov=Mock(),
        insider_prov=Mock(),
        analyst_prov=Mock(),
        forward_estimates_prov=Mock(),
        shareholding_prov=Mock(),
        bandar_prov=Mock(),
        fundamentals_prov=Mock(),
        notation_prov=Mock(),
    )

    use_case = create_accumulation_screen_use_case(
        broker_repository=broker_repo,
        market_repository=market_repo,
        stockbit_providers=providers,
        risk_use_case=risk_use_case,
        signal_engine=signal_engine,
        foreign_flow_score_policy=Mock(),
    )

    assert use_case._broker_repo is broker_repo
    assert use_case._market_repo is market_repo
    assert use_case._corp_action_repo is providers.corp_repo
    assert use_case._seasonality_provider is providers.season_prov
    assert use_case._insider_provider is providers.insider_prov
    assert use_case._analyst_provider is providers.analyst_prov
    assert use_case._forward_estimates_provider is providers.forward_estimates_prov
    assert use_case._shareholding_provider is providers.shareholding_prov
    assert use_case._bandar_provider is providers.bandar_prov
    assert use_case._fundamentals_provider is providers.fundamentals_prov
    assert use_case._ticker_notation_provider is providers.notation_prov
    assert use_case._risk_use_case is risk_use_case
    assert use_case._signal_engine is signal_engine
