"""
GetTickerDashboardUseCase — assemble a cache-only ticker dashboard snapshot.

Owns windows, source preference, corp-action merge, freshness classification,
brief/full panel selection, related deep-dive actions, and per-panel isolation.
Does not render UI or touch the network.

Layer: Application
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any, TypeVar

from src.application.dto.ticker_dashboard import (
    GetTickerDashboardRequest,
    PanelLoadError,
    TickerDashboard,
    ViewRelatedAction,
)
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
    CacheStatus,
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

T = TypeVar("T")


def _related_actions_for(ticker: str) -> tuple[ViewRelatedAction, ...]:
    t = ticker.upper()
    return (
        ViewRelatedAction(
            verb="flow",
            label="Foreign flow table",
            command=f"saham view ticker flow {t}",
        ),
        ViewRelatedAction(
            verb="top-brokers",
            label="Top broker desks",
            command=f"saham view ticker top-brokers {t}",
        ),
        ViewRelatedAction(
            verb="foreign-history",
            label="Foreign flow history",
            command=f"saham view ticker foreign-history {t}",
        ),
        ViewRelatedAction(
            verb="distribution",
            label="Broker distribution",
            command=f"saham view ticker distribution {t}",
        ),
    )


class GetTickerDashboardUseCase:
    """Build a read-only local-cache dashboard for one ticker."""

    def __init__(self, source: TickerDashboardSource) -> None:
        self._source = source

    def execute(self, request: GetTickerDashboardRequest) -> TickerDashboard:
        ticker = request.ticker.upper()
        today = request.today or date.today()
        brief = bool(request.brief)
        errors: list[PanelLoadError] = []

        def safe(key: str, default: T, fn: Callable[[], T]) -> T:
            try:
                return fn()
            except Exception as exc:  # isolate panel failures for CLI/TUI resilience
                errors.append(PanelLoadError(key=key, message=str(exc) or exc.__class__.__name__))
                return default

        corp_from = today - timedelta(days=CORP_ACTION_LOOKBACK_DAYS)
        corp_to = today + timedelta(days=CORP_ACTION_LOOKAHEAD_DAYS)
        insider_from = today - timedelta(days=INSIDER_LOOKBACK_DAYS)
        candle_from = today - timedelta(days=CANDLE_LOOKBACK_DAYS)

        notation = safe("identity", None, lambda: self._source.get_notation(ticker))
        fund = safe("fundamentals", None, lambda: self._source.get_fundamentals(ticker))
        analyst = safe("analyst", None, lambda: self._source.get_analyst(ticker))
        ownership = safe("ownership", None, lambda: self._source.get_ownership(ticker))
        bandar = safe(
            "bandar",
            None,
            lambda: self._source.get_bandar(ticker, today)
            or self._source.get_bandar(ticker, today - timedelta(days=1)),
        )
        fwd = safe("forward_estimates", None, lambda: self._source.get_forward_estimates(ticker))
        profile = safe("profile", None, lambda: self._source.get_profile(ticker))
        candles = safe(
            "price",
            [],
            lambda: self._source.get_candles(ticker, candle_from, today),
        )

        ticker_corp_actions = safe(
            "corp",
            [],
            lambda: self._source.get_ticker_corp_actions(ticker, corp_from, corp_to),
        )
        calendar_raw = safe(
            "corp",
            [],
            lambda: self._source.get_calendar_corp_actions(ticker, corp_from, corp_to),
        )
        calendar_corp_actions = [calendar_event_to_display(event) for event in calendar_raw]
        corp_actions = merge_corp_action_events(ticker_corp_actions, calendar_corp_actions)

        insider_txns = safe(
            "insider",
            [],
            lambda: self._source.get_insider_transactions(
                ticker, insider_from, today, "ALL"
            ),
        )
        insider_last_known = None
        if not insider_txns and not any(e.key == "insider" for e in errors):
            older = safe(
                "insider",
                [],
                lambda: self._source.get_insider_transactions(
                    ticker,
                    today - timedelta(days=INSIDER_HISTORY_LOOKBACK_DAYS),
                    insider_from - timedelta(days=1),
                    "ALL",
                ),
            )
            if older:
                insider_last_known = older[0].transaction_date

        seasonality = safe(
            "seasonality",
            None,
            lambda: self._source.get_seasonality(ticker, today.year, today.month),
        )

        flow_by_source = safe(
            "flow",
            {},
            lambda: {
                source: self._source.get_foreign_flow_points(ticker, source)
                for source in FOREIGN_FLOW_SOURCE_PREFERENCE
            },
        )
        foreign_flow_points, foreign_flow_source = select_foreign_flow_points(flow_by_source)

        earnings = safe(
            "earnings",
            [],
            lambda: self._source.get_earnings_history(ticker, EARNINGS_QUARTERS),
        )
        iev_rows = safe(
            "iev",
            [],
            lambda: self._source.get_iev_history(ticker, IEV_HISTORY_LIMIT),
        )
        sentiment_logs = safe(
            "sentiment",
            [],
            lambda: self._source.get_sentiment_logs(ticker, SENTIMENT_LOG_LIMIT),
        )

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

        error_keys = {e.key for e in errors}

        def with_error(key: str, status: CacheStatus) -> CacheStatus:
            return CacheStatus.ERROR if key in error_keys else status

        insider_status = with_error(
            "insider",
            classify_sequence(
                insider_txns,
                ever_fetched=insider_last_known is not None,
                last_known=insider_last_known,
            ),
        )
        corp_status = with_error(
            "corp",
            classify_sequence(
                corp_actions,
                ever_fetched=bool(ticker_corp_actions) or bool(calendar_corp_actions),
            ),
        )
        if (
            corp_status is not CacheStatus.ERROR
            and not corp_actions
            and safe("corp", False, lambda: self._source.is_ticker_corp_cache_fresh(ticker))
        ):
            corp_status = classify_sequence([], ever_fetched=True)

        freshness = (
            build_freshness_item(
                "price",
                "Price",
                with_error(
                    "price",
                    classify_sequence(
                        candles, as_of=price_as_of, today=today, ttl_days=DEFAULT_TTL_DAYS["price"]
                    ),
                ),
                as_of=price_as_of,
                today=today,
            ),
            build_freshness_item(
                "flow",
                "Flow",
                with_error(
                    "flow",
                    classify_sequence(
                        foreign_flow_points,
                        as_of=flow_as_of,
                        today=today,
                        ttl_days=DEFAULT_TTL_DAYS["flow"],
                    ),
                ),
                as_of=flow_as_of,
                today=today,
            ),
            build_freshness_item(
                "bandar",
                "Bandar",
                with_error(
                    "bandar",
                    classify_optional(
                        bandar, as_of=bandar_as_of, today=today, ttl_days=DEFAULT_TTL_DAYS["bandar"]
                    ),
                ),
                as_of=bandar_as_of,
                today=today,
            ),
            build_freshness_item(
                "earnings",
                "Earnings",
                with_error(
                    "earnings",
                    classify_sequence(
                        earnings,
                        as_of=earnings_as_of,
                        today=today,
                        ttl_days=DEFAULT_TTL_DAYS["earnings"],
                    ),
                ),
                as_of=earnings_as_of,
                today=today,
            ),
            build_freshness_item(
                "analyst",
                "Analyst",
                with_error(
                    "analyst",
                    classify_optional(
                        analyst,
                        as_of=analyst_as_of,
                        today=today,
                        ttl_days=DEFAULT_TTL_DAYS["analyst"],
                    ),
                ),
                as_of=analyst_as_of,
                today=today,
            ),
            build_freshness_item(
                "fundamentals",
                "Fundamentals",
                with_error(
                    "fundamentals",
                    classify_optional(
                        fund,
                        as_of=fund_as_of,
                        today=today,
                        ttl_days=DEFAULT_TTL_DAYS["fundamentals"],
                    ),
                ),
                as_of=fund_as_of,
                today=today,
            ),
            build_freshness_item(
                "ownership",
                "Ownership",
                with_error(
                    "ownership",
                    classify_optional(
                        ownership,
                        as_of=ownership_as_of,
                        today=today,
                        ttl_days=DEFAULT_TTL_DAYS["ownership"],
                    ),
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
                with_error(
                    "iev",
                    classify_sequence(
                        iev_rows, as_of=iev_as_of, today=today, ttl_days=DEFAULT_TTL_DAYS["iev"]
                    ),
                ),
                as_of=iev_as_of,
                today=today,
            ),
        )

        as_of = price_as_of or flow_as_of or today
        # Dedupe panel errors by key (keep first message).
        deduped_errors: list[PanelLoadError] = []
        seen_err: set[str] = set()
        for err in errors:
            if err.key in seen_err:
                continue
            seen_err.add(err.key)
            deduped_errors.append(err)

        return TickerDashboard(
            ticker=ticker,
            mode="brief" if brief else "full",
            as_of=as_of,
            today=today,
            fetch_hint=default_fetch_hint(ticker),
            panel_keys=panel_keys_for_mode(brief=brief),
            freshness=freshness,
            related_actions=_related_actions_for(ticker),
            panel_errors=tuple(deduped_errors),
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
