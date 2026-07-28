"""
Adapter wiring for the market-wide macro calendar sync, called once per
`saham fetch market` invocation. Mirrors fetch_market_calendar_refresh.py
(corporate actions) but targets Stockbit economic → macro_calendar_*.

Layer: Infrastructure composition
"""

from datetime import date
from pathlib import Path

from src.application.use_case.sync_macro_calendar_use_case import (
    SyncMacroCalendarRequest,
    SyncMacroCalendarUseCase,
)


def refresh_market_macro_calendar(db_path: Path, api_client, refresh: bool) -> str:
    """Sync the macroeconomic calendar once. Returns a status string for the
    `Macro calendar: ...` summary line. Never raises — catches all exceptions
    and returns an 'ERR:' status so failure never aborts the market fetch.
    """
    try:
        from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
        from src.infrastructure.browser.stockbit_macro_calendar import (
            StockbitMacroCalendarProvider,
        )
        from src.infrastructure.persistence.sqlite_macro_calendar_repository import (
            SQLiteMacroCalendarRepository,
        )

        provider = StockbitMacroCalendarProvider(
            api_client=api_client, stockbit_config=load_stockbit_provider_config()
        )
        repository = SQLiteMacroCalendarRepository(db_path)
        use_case = SyncMacroCalendarUseCase(provider=provider, repository=repository)
        response = use_case.execute(
            SyncMacroCalendarRequest(
                sync_date=date.today(),
                force_remote_fetch=refresh,
            )
        )
    except Exception as e:
        return f"ERR:{str(e)[:30]}"

    if response.from_cache:
        return "cached"
    if response.status == "failed":
        combined = " ".join(response.errors).lower()
        return (
            "ERR:auth"
            if "auth" in combined
            else (f"ERR:{(response.errors[0] if response.errors else 'unknown')[:30]}")
        )
    parts = " ".join(f"{k}={v}" for k, v in sorted(response.category_counts.items()))
    prefix = "stockbit" if response.status == "success" else "PARTIAL stockbit"
    return f"{prefix} {parts}".strip()
