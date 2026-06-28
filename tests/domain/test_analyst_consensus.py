from src.domain.value_objects.analyst_consensus import AnalystConsensus


def test_analyst_consensus_buy_ratio_uses_total_analyst_count():
    consensus = AnalystConsensus(
        ticker="BBCA",
        buy_count=2,
        hold_count=1,
        sell_count=1,
        avg_price_target=None,
        current_price=None,
        last_updated=None,
    )

    assert consensus.buy_ratio == 0.5


def test_analyst_consensus_buy_ratio_none_when_no_analysts():
    consensus = AnalystConsensus(
        ticker="BBCA",
        buy_count=0,
        hold_count=0,
        sell_count=0,
        avg_price_target=None,
        current_price=None,
        last_updated=None,
    )

    assert consensus.buy_ratio is None
