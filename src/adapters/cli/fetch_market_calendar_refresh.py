"""
Adapter wiring for the market-wide corporate action calendar sync, called
once per `saham fetch market` invocation (not per ticker). Mirrors the
one-shot pattern used by fetch_market_context_inputs.py — this module owns
infrastructure construction so the use case never imports infrastructure.

Layer: Adapter
"""

from datetime import date
from pathlib import Path

from src.application.use_case.sync_corporate_action_calendar_use_case import (
    SyncCorporateActionCalendarRequest,
    SyncCorporateActionCalendarUseCase,
)
from src.domain.value_objects.corporate_action_calendar import CorporateActionType

DEFAULT_CALENDAR_EVENT_TYPES: tuple[CorporateActionType, ...] = (
    CorporateActionType.DIVIDEND,
    CorporateActionType.STOCK_SPLIT,
    CorporateActionType.REVERSE_SPLIT,
    CorporateActionType.RIGHTS_ISSUE,
    CorporateActionType.BONUS,
    CorporateActionType.TENDER_OFFER,
    CorporateActionType.RUPS,
    CorporateActionType.PUBEX,
    CorporateActionType.IPO,
)


def refresh_market_calendar(db_path: Path, api_client, refresh: bool) -> str:
    """Sync the market-wide corporate action calendar once. Returns a status string
    for the single `Calendar: ...` summary line. Never raises — catches all
    exceptions and returns an 'ERR:' status so calendar failure never aborts the
    candle/broker fetch loop."""
    try:
        from src.infrastructure.browser.stockbit_corporate_action_calendar import (
            StockbitCorporateActionCalendarProvider,
        )
        from src.infrastructure.persistence.sqlite_corporate_action_calendar_repository import (
            SQLiteCorporateActionCalendarRepository,
        )

        provider = StockbitCorporateActionCalendarProvider(api_client=api_client)
        repository = SQLiteCorporateActionCalendarRepository(db_path)
        use_case = SyncCorporateActionCalendarUseCase(provider=provider, repository=repository)
        response = use_case.execute(
            SyncCorporateActionCalendarRequest(
                event_types=DEFAULT_CALENDAR_EVENT_TYPES,
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
        return "ERR:auth" if "auth" in combined else (
            f"ERR:{(response.errors[0] if response.errors else 'unknown')[:30]}"
        )
    parts = " ".join(f"{k}={v}" for k, v in sorted(response.event_type_counts.items()))
    prefix = "stockbit" if response.status == "success" else "PARTIAL stockbit"
    return f"{prefix} {parts}".strip()
