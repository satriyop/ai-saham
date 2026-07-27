"""
Parser functions for Stockbit /keystats/ratio/v1/{ticker}?year_limit=10 payloads.

Extracts fundamental ratios from the flat fin_name_results list and historical
quarterly rows from financial_year_parent. Pure parsing — no SQLite, no cache,
no network calls.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.domain.value_objects.company_fundamentals import CompanyFundamentals

logger = logging.getLogger(__name__)

_QUARTER_END: dict[str, tuple[int, int]] = {
    "Q1": (3, 31),
    "Q2": (6, 30),
    "Q3": (9, 30),
    "Q4": (12, 31),
}


def _parse_financial_value(s: str | None) -> float | None:
    """Parse Stockbit formatted value like '14,684 B' or '29,654 B' -> 14684.0.

    Units (B/T/M/K) are stripped -- the caller uses the ratio, not the absolute
    value, so units only need to be consistent within a single response.
    """
    if not s or s.strip() in ("-", "N/A", ""):
        return None
    try:
        cleaned = s.strip().replace(",", "")
        for suffix in (" B", " T", " M", " K", "B", "T", "M", "K"):
            if cleaned.endswith(suffix):
                cleaned = cleaned[: -len(suffix)].strip()
                break
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _strip(raw: str | None) -> str:
    return (raw or "").strip().rstrip("%").replace(",", "")


def _parse_float(raw: str | None) -> float | None:
    try:
        v = _strip(raw)
        if not v or v in ("-", "N/A", ""):
            return None
        return float(v)
    except (ValueError, TypeError):
        return None


def _parse_int(raw: str | None) -> int | None:
    f = _parse_float(raw)
    return int(round(f)) if f is not None else None


def _build_metrics(body: dict) -> dict[str, str]:
    """Flatten the nested fin_name_results list into a name -> value dict."""
    metrics: dict[str, str] = {}
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return metrics
    for section in data.get("closure_fin_items_results") or []:
        for item in section.get("fin_name_results") or []:
            fitem = item.get("fitem") or {}
            name = fitem.get("name")
            value = fitem.get("value")
            if name and value is not None:
                metrics[name] = str(value)
    return metrics


def _parse_market_cap(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        cleaned = raw.replace(",", "").strip()
        multiplier = 1
        if cleaned.endswith("T"):
            multiplier = 1_000_000_000_000
            cleaned = cleaned[:-1].strip()
        elif cleaned.endswith("B"):
            multiplier = 1_000_000_000
            cleaned = cleaned[:-1].strip()
        elif cleaned.endswith("M"):
            multiplier = 1_000_000
            cleaned = cleaned[:-1].strip()
        val = float(cleaned)
        return int(round(val * multiplier))
    except (ValueError, TypeError):
        return None


def _parse_fundamentals(ticker: str, body: dict) -> CompanyFundamentals | None:
    metrics = _build_metrics(body)
    if not metrics:
        return None

    pe = _parse_float(metrics.get("Current PE Ratio (TTM)"))
    roe = _parse_float(metrics.get("Return on Equity (TTM)"))
    npm = _parse_float(metrics.get("Net Profit Margin (Quarter)"))
    rev_yoy = _parse_float(metrics.get("Revenue (Quarter YoY Growth)"))
    f_score = _parse_int(metrics.get("Piotroski F-Score"))
    div_yld = _parse_float(metrics.get("Dividend Yield"))
    hi52 = _parse_float(metrics.get("52 Week High"))
    lo52 = _parse_float(metrics.get("52 Week Low"))
    near52 = _parse_float(metrics.get("Rank (Near 52 Weeks High)"))

    if all(v is None for v in [pe, roe, npm, rev_yoy, f_score]):
        return None

    data_raw = body.get("data") if isinstance(body, dict) else {}
    stats = (data_raw or {}).get("stats") or {}

    market_cap_idr: int | None = None
    if isinstance(stats, dict) and "market_cap" in stats:
        market_cap_idr = _parse_market_cap(stats["market_cap"])
    if market_cap_idr is None:
        info = (data_raw or {}).get("info") or {}
        if isinstance(info, dict):
            mc_raw = (info.get("market_cap") or {}).get("raw")
            if mc_raw is not None:
                if isinstance(mc_raw, (int, float)):
                    market_cap_idr = int(mc_raw)
                elif isinstance(mc_raw, str):
                    market_cap_idr = _parse_market_cap(mc_raw)

    pbv = _parse_float(metrics.get("Current Price to Book Value"))
    if pbv is None:
        info = (data_raw or {}).get("info") or {}
        if isinstance(info, dict):
            pbv_raw = (info.get("pbv") or {}).get("raw")
            try:
                pbv = float(pbv_raw) if pbv_raw is not None else None
            except (TypeError, ValueError):
                pass

    return CompanyFundamentals(
        ticker=ticker.upper(),
        pe_ratio_ttm=pe,
        roe_ttm=roe,
        net_profit_margin=npm,
        revenue_yoy_growth=rev_yoy,
        piotroski_f_score=f_score,
        dividend_yield=div_yld,
        week52_high=hi52,
        week52_low=lo52,
        near_52w_high_rank=near52,
        market_cap_idr=market_cap_idr,
        pbv=pbv,
        fetched_at=datetime.now(),
    )


def _parse_historical_rows(ticker: str, body: dict) -> list[CompanyFundamentals]:
    """Extract quarterly Net Income + Revenue history from financial_year_parent.

    Returns one CompanyFundamentals per (year, quarter) where both values are
    available. Only net_profit_margin and revenue_yoy_growth are populated;
    all other fields (market_cap_idr, piotroski_f_score, roe_ttm, etc.) are None.

    fetched_at is set to the quarter end date (Q1->Mar31, Q2->Jun30, Q3->Sep30,
    Q4->Dec31). _write_historical_rows adds a 60-day publication lag before
    storing, so the resulting PIT fetched_date = quarter_end + 60 days.
    """
    try:
        data = body.get("data") if isinstance(body, dict) else None
        fyp = (data or {}).get("financial_year_parent") or {}
        groups = fyp.get("financial_year_groups") or []
        if not groups:
            return []

        quarterly: dict[tuple[str, str], dict[str, float]] = {}
        for group in groups:
            fitem_name = group.get("fitem_name", "")
            if fitem_name not in ("Net Income", "Revenue"):
                continue
            col = "net_income" if fitem_name == "Net Income" else "revenue"
            for year_entry in group.get("financial_year_values") or []:
                year = str(year_entry.get("year") or "").strip()
                if not year:
                    continue
                for pv in year_entry.get("period_values") or []:
                    period = str(pv.get("period") or "").strip()
                    if period not in _QUARTER_END:
                        continue
                    val = _parse_financial_value(pv.get("quarter_value"))
                    if val is None:
                        continue
                    key = (year, period)
                    if key not in quarterly:
                        quarterly[key] = {}
                    quarterly[key][col] = val

        rows: list[CompanyFundamentals] = []
        for (year, period), vals in quarterly.items():
            net_income = vals.get("net_income")
            revenue = vals.get("revenue")
            if net_income is None or revenue is None or revenue == 0:
                continue

            npm: float | None = (net_income / revenue) * 100

            prior_year = str(int(year) - 1)
            prior = quarterly.get((prior_year, period), {})
            prior_rev = prior.get("revenue")
            rev_yoy: float | None = None
            if prior_rev and prior_rev != 0:
                rev_yoy = ((revenue - prior_rev) / abs(prior_rev)) * 100

            month, day = _QUARTER_END[period]
            try:
                fetched_at = datetime(int(year), month, day)
            except ValueError:
                continue

            rows.append(
                CompanyFundamentals(
                    ticker=ticker.upper(),
                    pe_ratio_ttm=None,
                    roe_ttm=None,
                    net_profit_margin=round(npm, 4),
                    revenue_yoy_growth=round(rev_yoy, 4) if rev_yoy is not None else None,
                    piotroski_f_score=None,
                    dividend_yield=None,
                    week52_high=None,
                    week52_low=None,
                    near_52w_high_rank=None,
                    market_cap_idr=None,
                    pbv=None,
                    fetched_at=fetched_at,
                )
            )
        return rows
    except Exception as exc:
        logger.debug("_parse_historical_rows failed for %s: %s", ticker, exc)
        return []
