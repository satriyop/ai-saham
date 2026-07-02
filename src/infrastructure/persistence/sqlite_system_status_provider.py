"""
SQLite implementation of SystemStatusProvider.

Handles data provider probing and DB freshness queries in Infrastructure.

Layer: Infrastructure
"""

import os
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path
from typing import List

from src.domain.value_objects.benchmark_symbol import YAHOO_BENCHMARK_TICKER
from src.domain.ports.system_status_provider import (
    ProviderStatusDto,
    SystemStatusProvider,
    TableFreshnessDto,
)


class SQLiteSystemStatusProvider(SystemStatusProvider):
    """Infrastructure-level checker for database status and data providers."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def check_provider_health(self) -> List[ProviderStatusDto]:
        """Probe data provider endpoints (IDX, Yahoo, Stockbit, AI keys) and return status list."""
        results = []

        # 1. IDX market status
        results.append(self._check_market_status())

        # 2. IDX API
        results.append(self._check_idx_api())

        # 3. Yahoo Finance
        results.append(self._check_yahoo())

        # 4. Stockbit session
        results.append(self._check_stockbit_session())

        # 5. AI API config
        results.append(self._check_ai_api())

        return results

    def get_data_freshness(self) -> List[TableFreshnessDto]:
        """Query database tables and return freshness metrics."""
        if not self.db_path.exists():
            return []

        queries = [
            (
                "broker_summaries",
                "SELECT source, MAX(date), COUNT(*) FROM broker_summaries GROUP BY source",
            ),
            (
                "foreign_flow_points",
                "SELECT source, MAX(date), COUNT(*) FROM foreign_flow_points GROUP BY source",
            ),
            (
                "broker_daily_flow",
                "SELECT source, MAX(date), COUNT(*) FROM broker_daily_flow GROUP BY source",
            ),
            ("candles", "SELECT '—', MAX(date), COUNT(*) FROM candles"),
        ]

        rows: List[TableFreshnessDto] = []
        try:
            conn = sqlite3.connect(str(self.db_path))
            for table, sql in queries:
                try:
                    for row in conn.execute(sql).fetchall():
                        rows.append(
                            TableFreshnessDto(
                                table=table,
                                source=row[0],
                                latest=row[1],
                                count=row[2],
                            )
                        )
                except sqlite3.OperationalError:
                    pass
            conn.close()
        except sqlite3.OperationalError:
            pass

        return rows

    def _check_market_status(self) -> ProviderStatusDto:
        start = time.time()
        try:
            from src.infrastructure.browser.stockbit_market_time import (
                fetch_and_cache_market_status,
                get_display_market_status,
            )
            live = fetch_and_cache_market_status()
            elapsed = round(time.time() - start, 1)
            if live:
                return ProviderStatusDto(
                    name="IDX market",
                    ok=True,
                    label=f"{live.session_name} [stockbit ✓]",
                    ms=elapsed,
                )
            fallback = get_display_market_status()
            return ProviderStatusDto(
                name="IDX market",
                ok=True,
                label=f"{fallback.session_name} [{fallback.source}]",
                ms=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 1)
            return ProviderStatusDto(
                name="IDX market",
                ok=False,
                label=str(e)[:55],
                ms=elapsed,
            )

    def _check_idx_api(self) -> ProviderStatusDto:
        import httpx

        from src.infrastructure.data_providers.idx import (
            IDX_API_BASE,
            IDX_HEADERS,
            STOCK_SUMMARY_ENDPOINT,
        )

        target = date.today() - timedelta(days=1)
        url = f"{IDX_API_BASE}{STOCK_SUMMARY_ENDPOINT}"
        params = {"start": 0, "length": 1, "date": target.strftime("%Y%m%d")}

        start = time.time()
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    url,
                    params=params,
                    headers=IDX_HEADERS,
                    follow_redirects=True,
                )
            elapsed = round(time.time() - start, 1)

            if resp.status_code == 200:
                data = resp.json().get("data", [])
                return ProviderStatusDto(
                    name="IDX API",
                    ok=True,
                    label=f"200 ({len(data)} stocks)",
                    ms=elapsed,
                )
            if resp.status_code == 403:
                return ProviderStatusDto(
                    name="IDX API",
                    ok=True,
                    label="403 (no data — possible non-trading day)",
                    ms=elapsed,
                )
            return ProviderStatusDto(
                name="IDX API",
                ok=False,
                label=f"HTTP {resp.status_code}",
                ms=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 1)
            return ProviderStatusDto(
                name="IDX API",
                ok=False,
                label=str(e)[:55],
                ms=elapsed,
            )

    def _check_yahoo(self) -> ProviderStatusDto:
        import yfinance as yf

        start = time.time()
        try:
            hist = yf.download(
                YAHOO_BENCHMARK_TICKER,
                period="5d",
                progress=False,
                auto_adjust=True,
            )
            elapsed = round(time.time() - start, 1)

            if hist is not None and not hist.empty:
                return ProviderStatusDto(
                    name="Yahoo Finance",
                    ok=True,
                    label=f"{len(hist)} days ({YAHOO_BENCHMARK_TICKER})",
                    ms=elapsed,
                )
            return ProviderStatusDto(
                name="Yahoo Finance",
                ok=True,
                label="empty response",
                ms=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 1)
            return ProviderStatusDto(
                name="Yahoo Finance",
                ok=False,
                label=str(e)[:55],
                ms=elapsed,
            )

    def _check_stockbit_session(self) -> ProviderStatusDto:
        start = time.time()
        try:
            from src.infrastructure.browser.playwright_stockbit_provider import get_session_status

            info = get_session_status()
            elapsed = round(time.time() - start, 1)

            if not info.get("exists"):
                return ProviderStatusDto(
                    name="Stockbit session",
                    ok=False,
                    label="no session found",
                    ms=elapsed,
                )

            likely = info.get("likely_valid", False)
            age = info.get("age_hours")
            age_str = f" ({age}h old)" if age is not None else ""
            if likely:
                return ProviderStatusDto(
                    name="Stockbit session",
                    ok=True,
                    label=f"valid{age_str}",
                    ms=elapsed,
                )
            return ProviderStatusDto(
                name="Stockbit session",
                ok=False,
                label=f"expired{age_str}",
                ms=elapsed,
            )
        except ImportError:
            return ProviderStatusDto(
                name="Stockbit session",
                ok=False,
                label="playwright not installed",
                ms=0,
            )
        except Exception as e:
            return ProviderStatusDto(
                name="Stockbit session",
                ok=False,
                label=str(e)[:55],
                ms=0,
            )

    def _check_ai_api(self) -> ProviderStatusDto:
        configured = []
        if os.environ.get("DEEPSEEK_API_KEY"):
            configured.append("DeepSeek")
        if os.environ.get("ANTHROPIC_API_KEY"):
            configured.append("Claude")
        if os.environ.get("OPENAI_API_KEY"):
            configured.append("OpenAI")
        if os.environ.get("GEMINI_API_KEY"):
            configured.append("Gemini")

        if not configured:
            return ProviderStatusDto(
                name="AI classifier",
                ok=False,
                label="no API key (set DEEPSEEK_API_KEY or ANTHROPIC_API_KEY)",
                ms=0,
            )
        return ProviderStatusDto(
            name="AI classifier",
            ok=True,
            label=f"{', '.join(configured)} key(s) set",
            ms=0,
        )
