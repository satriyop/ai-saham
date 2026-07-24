"""
GetTickerDashboardUseCase — assemble a cache-only ticker dashboard snapshot.

Owns windows, source preference, corp-action merge, freshness classification,
and brief/full panel selection. Does not render UI or touch the network.

Layer: Application
"""

from __future__ import annotations

from datetime import date, timedelta

from src.application.dto.ticker_dashboard import GetTickerDashboardRequest, TickerDashboard
from src.application.ports.ticker_dashboard_source import TickerDashboardSource
from src.application.services.ticker_dashboard_corp_actions import (
    calendar_event_to_display,
    merge_corp_action_events,
)
from src.application.services.ticker_dashboard_flow import (
    FOREIGN_FLOW_SOURCE_PREFERENCE,
    select_foreign_flow_points,
)
from src.application.services.ticker_dashboard_layout import panel_keys_for_mode
from src.application.services.ticker_dashboard_price_structure import compute_price_structure
from src.application.services.ticker_dashboard_status import (
    DEFAULT_TTL_DAYS,
    build_freshness_item,
    classify_optional,
    classify_sequence,
    default_fetch_hint,
)

# Policy constants (owned by application, not the adapter).
CORP_ACTION_LOOKBACK_DAYS = 365
CORP_ACTION_LOOKAHEAD_DAYS = 180
INSIDER_LOOKBACK_DAYS = 365
INSIDER_HISTORY_LOOKBACK_DAYS = 3650
CANDLE_LOOKBACK_DAYS = 400
EARNINGS_QUARTERS = 4
IEV_HISTORY_LIMIT = 5
SENTIMENT_LOG_LIMIT = 8


class GetTickerDashboardUseCase:
    """Build a read-only local-cache dashboard for one ticker."""

    def __init__(self, source: TickerDashboardSource) -> None:
        self._source = source

    def execute(self, request: GetTickerDashboardRequest) -> TickerDashboard:
        ticker = request.ticker.upper()
        today = request.today or date.today()
        brief = bool(request.brief)

        corp_from = today - timedelta(days=CORP_ACTION_LOOKBACK_DAYS)
        corp_to = today + timedelta(days=CORP_ACTION_LOOKAHEAD_DAYS)
        insider_from = today - timedelta(days=INSIDER_LOOKBACK_DAYS)
        candle_from = today - timedelta(days=CANDLE_LOOKBACK_DAYS)

        notation = self._source.get_notation(ticker)
        fund = self._source.get_fundamentals(ticker)
        analyst = self._source.get_analyst(ticker)
        ownership = self._source.get_ownership(ticker)
        bandar = self._source.get_bandar(ticker, today) or self._source.get_bandar(
            ticker, today - timedelta(days=1)
        )
        fwd = self._source.get_forward_estimates(ticker)
        profile = self._source.get_profile(ticker)
        candles = self._source.get_candles(ticker, candle_from, today)

        ticker_corp_actions = self._source.get_ticker_corp_actions(ticker, corp_from, corp_to)
        calendar_corp_actions = [
            calendar_event_to_display(event)
            for event in self._source.get_calendar_corp_actions(ticker, corp_from, corp_to)
        ]
        corp_actions = merge_corp_action_events(ticker_corp_actions, calendar_corp_actions)

        insider_txns = self._source.get_insider_transactions(
            ticker, insider_from, today, "ALL"
        )
        insider_last_known = None
        if not insider_txns:
            older = self._source.get_insider_transactions(
                ticker,
                today - timedelta(days=INSIDER_HISTORY_LOOKBACK_DAYS),
                insider_from - timedelta(days=1),
                "ALL",
            )
            if older:
                insider_last_known = older[0].transaction_date

        seasonality = self._source.get_seasonality(ticker, today.year, today.month)

        flow_by_source = {
            source: self._source.get_foreign_flow_points(ticker, source)
            for source in FOREIGN_FLOW_SOURCE_PREFERENCE
        }
        foreign_flow_points, foreign_flow_source = select_foreign_flow_points(flow_by_source)

        earnings = self._source.get_earnings_history(ticker, EARNINGS_QUARTERS)
        iev_rows = self._source.get_iev_history(ticker, IEV_HISTORY_LIMIT)
        sentiment_logs = self._source.get_sentiment_logs(ticker, SENTIMENT_LOG_LIMIT)

        latest_close = candles[-1].close if candles else None
        price_structure = compute_price_structure(
            candles,
            week52_high=getattr(fund, "week52_high", None) if fund is not None else None,
            week52_low=getattr(fund, "week52_low", None) if fund is not None else None,
        )

        price_as_of = candles[-1].date if candles else None
        flow_as_of = foreign_flow_points[-1].date if foreign_flow_points else None
        bandar_as_of = getattr(bandar, "session_date", None) if bandar is not None else None
        fund_as_of = getattr(fund, "fetched_at", None) if fund is not None else None
        analyst_as_of = getattr(analyst, "fetched_at", None) if analyst is not None else None
        earnings_as_of = earnings[0].fetched_at if earnings else None
        ownership_as_of = getattr(ownership, "fetched_at", None) if ownership is not None else None
        iev_as_of = iev_rows[0].date if iev_rows else None

        # Event-history panels are OK/EMPTY/MISSING only.
        insider_status = classify_sequence(
            insider_txns,
            ever_fetched=insider_last_known is not None,
            last_known=insider_last_known,
        )
        corp_status = classify_sequence(
            corp_actions,
            ever_fetched=bool(ticker_corp_actions) or bool(calendar_corp_actions),
        )
        if not corp_actions and self._source.is_ticker_corp_cache_fresh(ticker):
            corp_status = classify_sequence([], ever_fetched=True)

        freshness = (
            build_freshness_item(
                "price",
                "Price",
                classify_sequence(
                    candles, as_of=price_as_of, today=today, ttl_days=DEFAULT_TTL_DAYS["price"]
                ),
                as_of=price_as_of,
                today=today,
            ),
            build_freshness_item(
                "flow",
                "Flow",
                classify_sequence(
                    foreign_flow_points,
                    as_of=flow_as_of,
                    today=today,
                    ttl_days=DEFAULT_TTL_DAYS["flow"],
                ),
                as_of=flow_as_of,
                today=today,
            ),
            build_freshness_item(
                "bandar",
                "Bandar",
                classify_optional(
                    bandar, as_of=bandar_as_of, today=today, ttl_days=DEFAULT_TTL_DAYS["bandar"]
                ),
                as_of=bandar_as_of,
                today=today,
            ),
            build_freshness_item(
                "earnings",
                "Earnings",
                classify_sequence(
                    earnings,
                    as_of=earnings_as_of,
                    today=today,
                    ttl_days=DEFAULT_TTL_DAYS["earnings"],
                ),
                as_of=earnings_as_of,
                today=today,
            ),
            build_freshness_item(
                "analyst",
                "Analyst",
                classify_optional(
                    analyst,
                    as_of=analyst_as_of,
                    today=today,
                    ttl_days=DEFAULT_TTL_DAYS["analyst"],
                ),
                as_of=analyst_as_of,
                today=today,
            ),
            build_freshness_item(
                "fundamentals",
                "Fundamentals",
                classify_optional(
                    fund,
                    as_of=fund_as_of,
                    today=today,
                    ttl_days=DEFAULT_TTL_DAYS["fundamentals"],
                ),
                as_of=fund_as_of,
                today=today,
            ),
            build_freshness_item(
                "ownership",
                "Ownership",
                classify_optional(
                    ownership,
                    as_of=ownership_as_of,
                    today=today,
                    ttl_days=DEFAULT_TTL_DAYS["ownership"],
                ),
                as_of=ownership_as_of,
                today=today,
            ),
            build_freshness_item(
                "insider",
                "Insider",
                insider_status,
                as_of=insider_txns[0].transaction_date if insider_txns else insider_last_known,
                today=today,
            ),
            build_freshness_item(
                "corp",
                "Corp",
                corp_status,
                today=today,
            ),
            build_freshness_item(
                "iev",
                "IEV",
                classify_sequence(
                    iev_rows, as_of=iev_as_of, today=today, ttl_days=DEFAULT_TTL_DAYS["iev"]
                ),
                as_of=iev_as_of,
                today=today,
            ),
        )

        as_of = price_as_of or flow_as_of or today
        return TickerDashboard(
            ticker=ticker,
            mode="brief" if brief else "full",
            as_of=as_of,
            today=today,
            fetch_hint=default_fetch_hint(ticker),
            panel_keys=panel_keys_for_mode(brief=brief),
            freshness=freshness,
            notation=notation,
            fundamentals=fund,
            forward_estimates=fwd,
            latest_close=latest_close,
            price_structure=price_structure,
            analyst=analyst,
            earnings=tuple(earnings),
            ownership=ownership,
            bandar=bandar,
            foreign_flow_points=tuple(foreign_flow_points),
            foreign_flow_source=foreign_flow_source,
            corp_actions=tuple(corp_actions),
            corp_status=corp_status,
            insider_txns=tuple(insider_txns),
            insider_status=insider_status,
            insider_last_known=insider_last_known,
            seasonality=seasonality,
            iev_rows=tuple(iev_rows),
            sentiment_logs=tuple(sentiment_logs),
            profile=profile,
            candles=tuple(candles),
        )
