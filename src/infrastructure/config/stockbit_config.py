"""
Stockbit / Exodus API configuration — loaded from config/stockbit.yaml.

Single source of truth for all Exodus API endpoint URL templates, browser
timeout values, and broker code lists. All fields carry hardcoded defaults so
the system works even when the YAML is absent or malformed.

Edit config/stockbit.yaml to update endpoint URLs or broker codes without
touching Python source. Run `saham fetch stockbit spy` to discover new URLs.

Layer: Infrastructure
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

STOCKBIT_CONFIG_PATH = Path("config/stockbit.yaml")


@dataclass(frozen=True)
class StockbitConfig:
    """Runtime config for Stockbit Exodus API. All fields carry safe defaults."""

    # ── Market mover / IEV endpoints ──────────────────────────────────────
    iev_movers_main_url: str = (
        "https://exodus.stockbit.com/order-trade/market-mover"
        "?mover_type=MOVER_TYPE_IEV_TOP_GAINER"
        "&filter_stocks=FILTER_STOCKS_TYPE_MAIN_BOARD"
        "&filter_stocks=FILTER_STOCKS_TYPE_DEVELOPMENT_BOARD"
        "&filter_stocks=FILTER_STOCKS_TYPE_ACCELERATION_BOARD"
        "&filter_stocks=FILTER_STOCKS_TYPE_NEW_ECONOMY_BOARD"
    )
    iev_movers_special_url: str = (
        "https://exodus.stockbit.com/order-trade/market-mover"
        "?mover_type=MOVER_TYPE_IEV_TOP_GAINER"
        "&filter_stocks=FILTER_STOCKS_TYPE_SPECIAL_MONITORING_BOARD"
    )
    # ── Order book ────────────────────────────────────────────────────────
    orderbook_url: str = (
        "https://exodus.stockbit.com/company-price-feed/v2/orderbook/companies/{ticker}"
    )
    # ── Broker flow endpoints ─────────────────────────────────────────────
    marketdetectors_url: str = "https://exodus.stockbit.com/marketdetectors"  # broker-level
    broker_activity_url: str = "https://exodus.stockbit.com/order-trade/broker/activity"
    broker_historical_url: str = "https://exodus.stockbit.com/order-trade/broker/activity/historical"
    historical_summary_url: str = (
        "https://exodus.stockbit.com/company-price-feed/historical/summary/{ticker}"
    )
    # ── Per-ticker enrichment endpoints ───────────────────────────────────
    bandar_detector_url: str = (
        "https://exodus.stockbit.com/marketdetectors/{ticker}"
        "?transaction_type=TRANSACTION_TYPE_NET"
        "&market_board=MARKET_BOARD_REGULER"
        "&investor_type=INVESTOR_TYPE_ALL"
        "&limit=25"
        "&period=BROKER_SUMMARY_PERIOD_LATEST"
    )
    corp_action_url: str = "https://exodus.stockbit.com/corpaction/{ticker}?limit=50"
    running_trade_url: str = (
        "https://exodus.stockbit.com/order-trade/running-trade"
        "?symbols[]={ticker}&sort=DESC&limit={limit}&order_by=RUNNING_TRADE_ORDER_BY_TIME"
    )
    running_trade_chart_url: str = (
        "https://exodus.stockbit.com/order-trade/running-trade/chart/{ticker}"
    )
    intraday_broker_chart_url: str = (
        "https://exodus.stockbit.com/order-trade/broker/activity-chart"
        "?period=RT_PERIOD_LAST_1_DAY"
        "&brokers_code={broker_code}"
        "&investor_type=INVESTOR_TYPE_ALL"
        "&market_board=MARKET_TYPE_REGULER"
    )
    company_profile_url: str = "https://exodus.stockbit.com/emitten/{ticker}/profile"
    seasonality_url: str = (
        "https://exodus.stockbit.com/company-price-feed/seasonality/{ticker}"
        "?year={year}&back_year={back_years}"
    )
    analyst_url: str = "https://exodus.stockbit.com/analyst-ratings/{ticker}"
    analyst_consensus_url: str = "https://exodus.stockbit.com/analyst-ratings/{ticker}/consensus"
    emitten_info_url: str = "https://exodus.stockbit.com/emitten/{ticker}/info"
    keystats_url: str = "https://exodus.stockbit.com/keystats/ratio/v1/{ticker}?year_limit=10"
    shareholding_url: str = (
        "https://exodus.stockbit.com/insider/shareholding/composition/companies/{ticker}"
    )
    insider_url: str = (
        "https://exodus.stockbit.com/insider/company/majorholder"
        "?symbols={ticker}&date_start={from_date}&date_end={to_date}"
        "&page=1&limit=50&action_type={action_param}&source_type=SOURCE_TYPE_UNSPECIFIED"
    )
    market_time_url: str = "https://exodus.stockbit.com/company-price-feed/market-time"
    # ── Universe endpoints ─────────────────────────────────────────────────
    universe_sector_88_url: str = "https://exodus.stockbit.com/emitten/sectors/88/subsectors"
    universe_sector_70_url: str = "https://exodus.stockbit.com/emitten/sectors/70/subsectors"
    universe_company_url: str = (
        "https://exodus.stockbit.com/emitten/v3/sector/{sector}/subsector/{id}/company"
    )
    universe_screener_url: str = "https://exodus.stockbit.com/screener/universe"
    # ── Browser timeouts (ms) ──────────────────────────────────────────────
    nav_timeout_ms: int = 30_000
    element_timeout_ms: int = 15_000
    spa_settle_ms: int = 4_000
    # ── Broker code lists ──────────────────────────────────────────────────
    institutional_proxy_codes: tuple[str, ...] = (
        "AK", "ZP", "YP", "BK", "YU", "CP", "KZ", "HD", "RX", "DR"
    )
    tracked_broker_codes: tuple[str, ...] = (
        "AK", "ZP", "YP", "BK", "YU", "CP", "KZ", "HD", "RX", "DR",
        "XL", "PD", "MS", "DB", "ML",
    )


def load_stockbit_config(
    config_path: Path = STOCKBIT_CONFIG_PATH,
) -> StockbitConfig:
    """Load Stockbit API config from YAML. Returns hardcoded defaults on any error."""
    defaults = StockbitConfig()
    try:
        with open(config_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:
        return defaults

    try:
        eps = data.get("endpoints") or {}
        codes = data.get("broker_codes") or {}
        tmo = data.get("timeouts") or {}

        def _url(key: str, default: str) -> str:
            raw = (eps.get(key) or {}).get("url", "")
            return str(raw).strip() if raw else default

        def _codes(key: str, default: tuple[str, ...]) -> tuple[str, ...]:
            raw = codes.get(key) or []
            parsed = tuple(str(c).strip().upper() for c in raw if c)
            return parsed if parsed else default

        def _ms(key: str, default: int) -> int:
            return int(tmo[key]) if key in tmo else default

        return StockbitConfig(
            iev_movers_main_url=_url("iev_movers_main", defaults.iev_movers_main_url),
            iev_movers_special_url=_url("iev_movers_special", defaults.iev_movers_special_url),
            orderbook_url=_url("orderbook", defaults.orderbook_url),
            marketdetectors_url=_url("broker_marketdetectors", defaults.marketdetectors_url),
            broker_activity_url=_url("broker_activity", defaults.broker_activity_url),
            broker_historical_url=_url("broker_historical", defaults.broker_historical_url),
            historical_summary_url=_url("historical_summary", defaults.historical_summary_url),
            bandar_detector_url=_url("bandar_detector", defaults.bandar_detector_url),
            corp_action_url=_url("corp_action", defaults.corp_action_url),
            running_trade_url=_url("running_trade", defaults.running_trade_url),
            running_trade_chart_url=_url("running_trade_chart", defaults.running_trade_chart_url),
            intraday_broker_chart_url=_url("intraday_broker_chart", defaults.intraday_broker_chart_url),
            company_profile_url=_url("company_profile", defaults.company_profile_url),
            seasonality_url=_url("seasonality", defaults.seasonality_url),
            analyst_url=_url("analyst_ratings", defaults.analyst_url),
            analyst_consensus_url=_url("analyst_consensus", defaults.analyst_consensus_url),
            emitten_info_url=_url("emitten_info", defaults.emitten_info_url),
            keystats_url=_url("keystats", defaults.keystats_url),
            shareholding_url=_url("shareholding", defaults.shareholding_url),
            insider_url=_url("insider", defaults.insider_url),
            market_time_url=_url("market_time", defaults.market_time_url),
            universe_sector_88_url=_url("universe_sector_88", defaults.universe_sector_88_url),
            universe_sector_70_url=_url("universe_sector_70", defaults.universe_sector_70_url),
            universe_company_url=_url("universe_company", defaults.universe_company_url),
            universe_screener_url=_url("universe_screener", defaults.universe_screener_url),
            nav_timeout_ms=_ms("nav_ms", defaults.nav_timeout_ms),
            element_timeout_ms=_ms("element_ms", defaults.element_timeout_ms),
            spa_settle_ms=_ms("spa_settle_ms", defaults.spa_settle_ms),
            institutional_proxy_codes=_codes("institutional_proxy", defaults.institutional_proxy_codes),
            tracked_broker_codes=_codes("tracked", defaults.tracked_broker_codes),
        )
    except Exception:
        return defaults


STOCKBIT_CFG: StockbitConfig = load_stockbit_config()
