"""Pure, allow-listed projection for view-ticker dashboard stage (ADR-066)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from src.application.dto.accumulation_agent import AgentViewTickerContext
from src.application.dto.ticker_dashboard import TickerDashboard
from src.application.services.agent_accumulation_context import (
    AgentContextInvariantError,
    AgentContextUnavailableError,
)
from src.application.services.agent_ticker_dashboard_tool import (
    project_ticker_dashboard_for_agent,
)

SCHEMA_ID = "tui_agent.view_ticker.v1"


def build_agent_view_ticker_context(dashboard: TickerDashboard) -> AgentViewTickerContext:
    """Project cache-only ticker dashboard facts for Research Cockpit open."""
    if not isinstance(dashboard, TickerDashboard):
        raise TypeError(
            f"view_ticker raw input must be TickerDashboard, got {type(dashboard).__name__}"
        )
    ticker = str(dashboard.ticker or "").strip().upper()
    if len(ticker) != 4 or not ticker.isalpha():
        raise AgentContextUnavailableError(
            f"View ticker context unavailable: invalid ticker {dashboard.ticker!r}"
        )

    data, warnings, usable = project_ticker_dashboard_for_agent(dashboard)
    if not usable:
        raise AgentContextUnavailableError(
            f"View ticker context unavailable: no cached dashboard data for {ticker}"
        )
    projected_ticker = str(data.ticker or "").strip().upper()
    if projected_ticker != ticker:
        raise AgentContextInvariantError(
            f"View ticker identity mismatch: dashboard={ticker} projected={projected_ticker}"
        )

    context = AgentViewTickerContext(
        schema_id=SCHEMA_ID,
        context_reference="",
        ticker=ticker,
        as_of=data.as_of,
        today=data.today,
        mode=data.mode,
        freshness=data.freshness,
        identity=data.identity,
        price=data.price,
        fundamentals=data.fundamentals,
        forward_estimates=data.forward_estimates,
        analyst=data.analyst,
        earnings=data.earnings,
        ownership=data.ownership,
        bandar=data.bandar,
        foreign_flow=data.foreign_flow,
        corporate_action_count=data.corporate_action_count,
        corporate_action_status=data.corporate_action_status,
        insider_transaction_count=data.insider_transaction_count,
        insider_status=data.insider_status,
        insider_last_known=data.insider_last_known,
        iev_row_count=data.iev_row_count,
        sentiment_log_count=data.sentiment_log_count,
        profile_available=data.profile_available,
        seasonality_available=data.seasonality_available,
        sector_macro_diagnostic_available=data.sector_macro_diagnostic_available,
        missing_branches=data.missing_branches,
        stale_branches=data.stale_branches,
        error_branches=data.error_branches,
        warnings=warnings,
    )
    canonical = json.dumps(
        context.canonical_payload(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return replace(
        context,
        context_reference="sha256:" + hashlib.sha256(canonical).hexdigest(),
    )
