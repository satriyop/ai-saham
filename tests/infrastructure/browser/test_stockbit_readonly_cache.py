import sqlite3
from datetime import date, datetime, timedelta

from src.domain.value_objects.analyst_consensus import AnalystConsensus
from src.domain.value_objects.forward_estimates import ForwardEstimates
from src.domain.value_objects.insider_transaction import InsiderTransaction
from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
from src.infrastructure.browser.stockbit_forward_estimates import (
    StockbitForwardEstimatesProvider,
)
from src.infrastructure.browser.stockbit_insider import StockbitInsiderActivityProvider


def test_readonly_analyst_provider_returns_stale_cache_without_overwriting(tmp_path):
    provider = StockbitAnalystConsensusProvider(
        api_client=None,
        db_path=tmp_path / "stockbit.db",
    )
    provider._write_cache(
        "ASII",
        AnalystConsensus(
            ticker="ASII",
            buy_count=25,
            hold_count=6,
            sell_count=1,
            avg_price_target=6846.0,
            current_price=4760.0,
            last_updated=date(2026, 6, 22),
            fetched_at=datetime.now() - timedelta(days=1),
        ),
    )

    consensus = provider.get_consensus("ASII")

    assert consensus is not None
    assert consensus.analyst_count == 32


def test_readonly_forward_provider_returns_stale_cache(tmp_path):
    provider = StockbitForwardEstimatesProvider(
        api_client=None,
        db_path=tmp_path / "stockbit.db",
    )
    provider._write_cache(
        ForwardEstimates(
            ticker="BBCA",
            forward_eps_1y=490.46,
            revenue_forward_1y=None,
            current_price=None,
            forward_pe=None,
            fetched_at=datetime.now() - timedelta(days=1),
        )
    )

    estimates = provider.get_forward_estimates("BBCA")

    assert estimates is not None
    assert estimates.forward_eps_1y == 490.46


def test_readonly_insider_provider_does_not_write_empty_sentinel_on_cache_miss(tmp_path):
    db_path = tmp_path / "stockbit.db"
    provider = StockbitInsiderActivityProvider(
        api_client=None,
        db_path=db_path,
    )

    transactions = provider.get_insider_transactions(
        ticker="BBCA",
        from_date=date(2026, 1, 1),
        to_date=date(2026, 6, 28),
        action_type="ALL",
    )

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM insider_cache").fetchone()[0]

    assert transactions == []
    assert rows == 0


def test_readonly_insider_provider_returns_cached_transactions(tmp_path):
    provider = StockbitInsiderActivityProvider(
        api_client=None,
        db_path=tmp_path / "stockbit.db",
    )
    provider._write_cache(
        "ASII",
        [
            InsiderTransaction(
                ticker="ASII",
                name="Prijono Sugiarto",
                role="KOMISARIS",
                action_type="BUY",
                shares=130_000,
                price=4876.0,
                transaction_date=date(2026, 6, 20),
                ownership_before_pct=0.0,
                ownership_after_pct=0.0,
            )
        ],
    )

    transactions = provider.get_insider_transactions(
        ticker="ASII",
        from_date=date(2026, 1, 1),
        to_date=date(2026, 6, 28),
        action_type="ALL",
    )

    assert len(transactions) == 1
    assert transactions[0].is_buy is True
