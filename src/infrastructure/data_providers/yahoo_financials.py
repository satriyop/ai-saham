"""
Yahoo Finance implementation of FinancialsProvider.

Maps yfinance income / balance / cashflow frames into sparse
CompanyFinancialPeriod rows. Source field is always ``yahoo``.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timezone
from typing import Any

import yfinance as yf

from src.domain.ports.financials_provider import FinancialsProvider
from src.domain.value_objects.company_financial_period import (
    CompanyFinancialPeriod,
    FinancialPeriodType,
    FinancialStatementKind,
    fields_for,
)

logger = logging.getLogger(__name__)

_SOURCE = "yahoo"
_DEFAULT_MARKET_SUFFIX = ".JK"

# Prefer exact yfinance row labels; first match wins.
_ROW_ALIASES: dict[str, tuple[str, ...]] = {
    # income
    "total_revenue": ("Total Revenue", "Operating Revenue"),
    "net_income": (
        "Net Income Common Stockholders",
        "Net Income",
        "Net Income From Continuing Operation Net Minority Interest",
    ),
    "net_income_incl_nci": (
        "Net Income Including Noncontrolling Interests",
        "Net Income Continuous Operations",
    ),
    "interest_income": ("Interest Income",),
    "operating_income": ("Operating Income", "Total Operating Income As Reported"),
    "eps_basic": ("Basic EPS",),
    "eps_diluted": ("Diluted EPS",),
    # balance
    "total_assets": ("Total Assets",),
    "total_liabilities": (
        "Total Liabilities Net Minority Interest",
        "Total Liabilities",
    ),
    "stockholders_equity": ("Stockholders Equity", "Common Stock Equity"),
    "cash_and_equivalents": (
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Federal Funds Sold",
    ),
    "total_debt": ("Total Debt",),
    # cashflow
    "operating_cash_flow": (
        "Operating Cash Flow",
        "Cash Flowsfromusedin Operating Activities Direct",
    ),
    "investing_cash_flow": ("Investing Cash Flow",),
    "financing_cash_flow": ("Financing Cash Flow",),
    "free_cash_flow": ("Free Cash Flow",),
    "capital_expenditure": ("Capital Expenditure",),
    "end_cash_position": ("End Cash Position",),
}

_FRAME_ATTRS: dict[tuple[FinancialStatementKind, FinancialPeriodType], str] = {
    ("income", "quarter"): "quarterly_income_stmt",
    ("income", "annual"): "income_stmt",
    ("balance", "quarter"): "quarterly_balance_sheet",
    ("balance", "annual"): "balance_sheet",
    ("cashflow", "quarter"): "quarterly_cashflow",
    ("cashflow", "annual"): "cashflow",
}

_MONEY_FIELDS = frozenset(
    {
        "total_revenue",
        "net_income",
        "net_income_incl_nci",
        "interest_income",
        "operating_income",
        "total_assets",
        "total_liabilities",
        "stockholders_equity",
        "cash_and_equivalents",
        "total_debt",
        "operating_cash_flow",
        "investing_cash_flow",
        "financing_cash_flow",
        "free_cash_flow",
        "capital_expenditure",
        "end_cash_position",
    }
)
_FLOAT_FIELDS = frozenset({"eps_basic", "eps_diluted"})


class YahooFinancialsProvider(FinancialsProvider):
    """Fetch multi-period statements via yfinance."""

    def __init__(self, market_suffix: str | None = None) -> None:
        if market_suffix is None:
            from src.infrastructure.config.app_config import load_app_config

            market_suffix = load_app_config().market.suffix
        self._market_suffix = market_suffix or _DEFAULT_MARKET_SUFFIX

    def fetch_statements(
        self,
        ticker: str,
        *,
        include_quarterly: bool = True,
        include_annual: bool = True,
        statement_kinds: frozenset[FinancialStatementKind],
    ) -> list[CompanyFinancialPeriod]:
        if not statement_kinds:
            return []

        symbol = ticker.upper().strip()
        yahoo_sym = self._to_yahoo_ticker(symbol)
        fetched_at = datetime.now(tz=timezone.utc)
        stock = yf.Ticker(yahoo_sym)
        currency = self._currency_from_info(stock)

        period_types: list[FinancialPeriodType] = []
        if include_quarterly:
            period_types.append("quarter")
        if include_annual:
            period_types.append("annual")

        periods: list[CompanyFinancialPeriod] = []
        for kind in sorted(statement_kinds):
            for period_type in period_types:
                attr = _FRAME_ATTRS[(kind, period_type)]
                try:
                    frame = getattr(stock, attr, None)
                except Exception as exc:
                    logger.debug("yfinance %s failed for %s: %s", attr, symbol, exc)
                    continue
                periods.extend(
                    self._map_frame(
                        frame,
                        ticker=symbol,
                        statement_kind=kind,
                        period_type=period_type,
                        currency=currency,
                        fetched_at=fetched_at,
                    )
                )

        periods.sort(
            key=lambda p: (p.statement_kind, p.period_type, p.period_end),
            reverse=True,
        )
        return periods

    def _to_yahoo_ticker(self, ticker: str) -> str:
        if ticker.startswith("^") or "." in ticker:
            return ticker
        if not ticker.endswith(self._market_suffix):
            return f"{ticker}{self._market_suffix}"
        return ticker

    @staticmethod
    def _currency_from_info(stock: Any) -> str | None:
        try:
            info = stock.info or {}
        except Exception:
            return None
        raw = info.get("financialCurrency") or info.get("currency")
        return str(raw) if raw else None

    def _map_frame(
        self,
        frame: Any,
        *,
        ticker: str,
        statement_kind: FinancialStatementKind,
        period_type: FinancialPeriodType,
        currency: str | None,
        fetched_at: datetime,
    ) -> list[CompanyFinancialPeriod]:
        if frame is None:
            return []
        try:
            if getattr(frame, "empty", True):
                return []
        except Exception:
            return []

        out: list[CompanyFinancialPeriod] = []
        metric_names = fields_for(statement_kind)
        for col in frame.columns:
            period_end = self._to_date(col)
            if period_end is None:
                continue
            series = frame[col]
            metrics: dict[str, Any] = {name: None for name in _MONEY_FIELDS | _FLOAT_FIELDS}
            for name in metric_names:
                raw = self._lookup(series, name)
                if name in _FLOAT_FIELDS:
                    metrics[name] = self._as_float(raw)
                else:
                    metrics[name] = self._as_int(raw)

            period = CompanyFinancialPeriod(
                ticker=ticker,
                period_end=period_end,
                period_type=period_type,
                statement_kind=statement_kind,
                source=_SOURCE,
                currency=currency,
                total_revenue=metrics["total_revenue"],
                net_income=metrics["net_income"],
                net_income_incl_nci=metrics["net_income_incl_nci"],
                interest_income=metrics["interest_income"],
                operating_income=metrics["operating_income"],
                eps_basic=metrics["eps_basic"],
                eps_diluted=metrics["eps_diluted"],
                total_assets=metrics["total_assets"],
                total_liabilities=metrics["total_liabilities"],
                stockholders_equity=metrics["stockholders_equity"],
                cash_and_equivalents=metrics["cash_and_equivalents"],
                total_debt=metrics["total_debt"],
                operating_cash_flow=metrics["operating_cash_flow"],
                investing_cash_flow=metrics["investing_cash_flow"],
                financing_cash_flow=metrics["financing_cash_flow"],
                free_cash_flow=metrics["free_cash_flow"],
                capital_expenditure=metrics["capital_expenditure"],
                end_cash_position=metrics["end_cash_position"],
                fetched_at=fetched_at,
            )
            if period.has_any_metric():
                out.append(period)
        return out

    @staticmethod
    def _to_date(value: Any) -> date | None:
        if value is None:
            return None
        if hasattr(value, "date") and callable(value.date):
            try:
                return value.date()
            except Exception:
                pass
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            logger.debug("Skipping unparseable financial period column: %r", value)
            return None

    @staticmethod
    def _lookup(series: Any, field: str) -> Any:
        for label in _ROW_ALIASES[field]:
            try:
                if label in series.index:
                    return series[label]
            except Exception:
                continue
        return None

    @staticmethod
    def _as_int(value: Any) -> int | None:
        number = YahooFinancialsProvider._as_float(value)
        if number is None:
            return None
        return int(round(number))

    @staticmethod
    def _as_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            if value != value:  # noqa: PLR0124 — NaN check
                return None
        except Exception:
            pass
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(number) or math.isinf(number):
            return None
        return number
