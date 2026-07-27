"""
Yahoo Finance implementation of FinancialsProvider.

Reads yfinance quarterly/annual income statements and maps a stable subset
of line items into CompanyFinancialPeriod rows. Source field is always
``yahoo``.

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
)

logger = logging.getLogger(__name__)

_SOURCE = "yahoo"
_DEFAULT_MARKET_SUFFIX = ".JK"

# Prefer exact yfinance row labels; first match wins.
_ROW_ALIASES: dict[str, tuple[str, ...]] = {
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
}


class YahooFinancialsProvider(FinancialsProvider):
    """Fetch multi-period income statements via yfinance."""

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
    ) -> list[CompanyFinancialPeriod]:
        symbol = ticker.upper().strip()
        yahoo_sym = self._to_yahoo_ticker(symbol)
        fetched_at = datetime.now(tz=timezone.utc)
        stock = yf.Ticker(yahoo_sym)
        currency = self._currency_from_info(stock)

        periods: list[CompanyFinancialPeriod] = []
        if include_quarterly:
            periods.extend(
                self._map_frame(
                    stock.quarterly_income_stmt,
                    ticker=symbol,
                    period_type="quarter",
                    currency=currency,
                    fetched_at=fetched_at,
                )
            )
        if include_annual:
            periods.extend(
                self._map_frame(
                    stock.income_stmt,
                    ticker=symbol,
                    period_type="annual",
                    currency=currency,
                    fetched_at=fetched_at,
                )
            )
        periods.sort(key=lambda p: (p.period_type, p.period_end), reverse=True)
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
        for col in frame.columns:
            period_end = self._to_date(col)
            if period_end is None:
                continue
            series = frame[col]
            out.append(
                CompanyFinancialPeriod(
                    ticker=ticker,
                    period_end=period_end,
                    period_type=period_type,
                    source=_SOURCE,
                    currency=currency,
                    total_revenue=self._int_field(series, "total_revenue"),
                    net_income=self._int_field(series, "net_income"),
                    net_income_incl_nci=self._int_field(series, "net_income_incl_nci"),
                    interest_income=self._int_field(series, "interest_income"),
                    operating_income=self._int_field(series, "operating_income"),
                    eps_basic=self._float_field(series, "eps_basic"),
                    eps_diluted=self._float_field(series, "eps_diluted"),
                    fetched_at=fetched_at,
                )
            )
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

    def _int_field(self, series: Any, field: str) -> int | None:
        raw = self._lookup(series, field)
        return self._as_int(raw)

    def _float_field(self, series: Any, field: str) -> float | None:
        raw = self._lookup(series, field)
        return self._as_float(raw)

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
            # pandas / numpy NA
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
