"""
Transaction aggregation for detailed broker CSV format.

Pure function to aggregate individual broker transactions into BrokerSummary.

Layer: Infrastructure
Dependencies: Domain entities only (no ports, no parsing logic)
"""

from datetime import date
from decimal import Decimal

from src.domain.entities.broker_flow import BrokerSummary, BrokerTransaction


def aggregate_broker_transactions(
    ticker: str,
    row_date: date,
    transactions: list[BrokerTransaction],
) -> BrokerSummary:
    """
    Aggregate broker transactions into a BrokerSummary.

    Calculates:
    - Foreign buy/sell value/lot totals
    - Total value/lot (all brokers)
    - Top 10 buyers (by net value, positive only)
    - Top 10 sellers (by net value, negative only, most negative first)

    Args:
        ticker: Stock ticker symbol
        row_date: Trading date
        transactions: List of BrokerTransaction for this ticker/date

    Returns:
        BrokerSummary with aggregated data
    """
    # Calculate foreign flow totals
    foreign_buy_value = Decimal("0")
    foreign_sell_value = Decimal("0")
    foreign_buy_lot = 0
    foreign_sell_lot = 0
    total_value = Decimal("0")
    total_lot = 0

    for t in transactions:
        total_value += t.buy_value + t.sell_value
        total_lot += t.buy_lot + t.sell_lot

        if t.is_foreign:
            foreign_buy_value += t.buy_value
            foreign_sell_value += t.sell_value
            foreign_buy_lot += t.buy_lot
            foreign_sell_lot += t.sell_lot

    # Sort by net value for top buyers/sellers
    sorted_by_net = sorted(transactions, key=lambda t: t.net_value, reverse=True)

    # Top 10 buyers (positive net value)
    top_buyers = tuple(t for t in sorted_by_net[:10] if t.net_value > 0)

    # Top 10 sellers (most negative net value)
    top_sellers = tuple(t for t in reversed(sorted_by_net[-10:]) if t.net_value < 0)

    return BrokerSummary(
        ticker=ticker,
        date=row_date,
        top_buyers=top_buyers,
        top_sellers=top_sellers,
        foreign_buy_value=foreign_buy_value,
        foreign_sell_value=foreign_sell_value,
        foreign_buy_lot=foreign_buy_lot,
        foreign_sell_lot=foreign_sell_lot,
        total_value=total_value,
        total_lot=total_lot,
        source="csv-stockbit",
    )
