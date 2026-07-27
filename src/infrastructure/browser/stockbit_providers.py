"""
Data container for optional Stockbit provider instances sharing one SQLite cache.

Infrastructure layer — holds references to all Stockbit providers so callers
can wire them into use-cases without importing each provider class individually.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
    from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider
    from src.infrastructure.browser.stockbit_corp_action import StockbitCorporateActionRepository
    from src.infrastructure.browser.stockbit_forward_estimates import (
        StockbitForwardEstimatesProvider,
    )
    from src.infrastructure.browser.stockbit_fundamentals import StockbitFundamentalsProvider
    from src.infrastructure.browser.stockbit_insider import StockbitInsiderActivityProvider
    from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
    from src.infrastructure.browser.stockbit_shareholding import StockbitShareholdingProvider
    from src.infrastructure.browser.stockbit_ticker_notation import StockbitTickerNotationProvider


class StockbitProviders:
    """Holds all optional Stockbit providers sharing one authenticated session."""

    __slots__ = (
        "corp_repo",
        "season_prov",
        "insider_prov",
        "analyst_prov",
        "shareholding_prov",
        "bandar_prov",
        "fundamentals_prov",
        "notation_prov",
        "forward_estimates_prov",
    )

    def __init__(
        self,
        corp_repo: "StockbitCorporateActionRepository | None",
        season_prov: "StockbitSeasonalityProvider | None",
        insider_prov: "StockbitInsiderActivityProvider | None",
        analyst_prov: "StockbitAnalystConsensusProvider | None" = None,
        shareholding_prov: "StockbitShareholdingProvider | None" = None,
        bandar_prov: "StockbitBandarDetectorProvider | None" = None,
        fundamentals_prov: "StockbitFundamentalsProvider | None" = None,
        notation_prov: "StockbitTickerNotationProvider | None" = None,
        forward_estimates_prov: "StockbitForwardEstimatesProvider | None" = None,
    ) -> None:
        self.corp_repo = corp_repo
        self.season_prov = season_prov
        self.insider_prov = insider_prov
        self.analyst_prov = analyst_prov
        self.shareholding_prov = shareholding_prov
        self.bandar_prov = bandar_prov
        self.fundamentals_prov = fundamentals_prov
        self.notation_prov = notation_prov
        self.forward_estimates_prov = forward_estimates_prov

    @classmethod
    def unavailable(cls) -> "StockbitProviders":
        return cls(
            corp_repo=None,
            season_prov=None,
            insider_prov=None,
            analyst_prov=None,
            shareholding_prov=None,
            bandar_prov=None,
            fundamentals_prov=None,
            notation_prov=None,
            forward_estimates_prov=None,
        )
