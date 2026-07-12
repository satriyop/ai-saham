"""Manage universe use cases.

Layer: Application
"""

from dataclasses import replace
from datetime import date
from typing import Callable

from src.application.dto.universe_management import (
    UniverseCreateResult,
    UniverseDiscoverItem,
    UniverseInspectResult,
    UniverseInspectRow,
    UniverseUpdateItem,
    UniverseUpdateResult,
)
from src.application.ports.universe_catalog_provider import UniverseCatalogProvider
from src.application.services.universe_config_store import UniverseConfigStore
from src.application.services.universe_payload_parser import (
    extract_company_rows,
    extract_company_tickers,
    extract_sector_rows,
    extract_subsector_rows,
)


class UpdateUniverseUseCase:
    """Update universe ticker lists from Stockbit."""

    def __init__(
        self,
        provider: UniverseCatalogProvider,
        config_store: UniverseConfigStore,
        sleep: Callable[[float], None] | None = None,
        universe_type: Callable[[str], str] | None = None,
    ) -> None:
        self._provider = provider
        self._config_store = config_store
        self._sleep = sleep or (lambda x: None)
        self._universe_type = universe_type or (lambda _: "unknown")

    def execute(
        self,
        *,
        universe_name: str | None,
        discover: bool,
        today: date,
    ) -> UniverseUpdateResult | tuple[UniverseDiscoverItem, ...]:
        existing = self._config_store.load_raw()
        available = self._provider.list_available()

        if discover:
            return self._discover(available)

        targets = self._resolve_targets(universe_name, available, existing)
        if not targets:
            return UniverseUpdateResult(
                updated=(), failed=(), config_path=self._config_store.config_path
            )

        today_str = today.isoformat()
        updated_items: list[UniverseUpdateItem] = []
        failed: list[str] = []

        for key in targets:
            is_custom = (
                key in existing
                and isinstance(existing[key], dict)
                and "sector_id" in existing[key]
            )
            utype = "custom" if is_custom else self._universe_type(key)

            tickers = self._fetch_tickers(key, is_custom,
                                          existing.get(key) if is_custom else None)

            if tickers:
                prev_count = len((existing.get(key) or {}).get("tickers") or [])
                updated_items.append(
                    UniverseUpdateItem(
                        key=key,
                        universe_type=utype,
                        tickers=tuple(tickers),
                        previous_count=prev_count,
                        delta=len(tickers) - prev_count,
                    )
                )
            else:
                failed.append(key)

        if not updated_items:
            return UniverseUpdateResult(
                updated=(), failed=tuple(failed), config_path=self._config_store.config_path
            )

        for item in updated_items:
            if item.key in existing and isinstance(existing[item.key], dict):
                existing[item.key]["updated"] = today_str
                existing[item.key]["tickers"] = list(item.tickers)
            else:
                existing[item.key] = {"updated": today_str, "tickers": list(item.tickers)}

        self._config_store.save_raw(existing, updated=today_str)

        return UniverseUpdateResult(
            updated=tuple(updated_items),
            failed=tuple(failed),
            config_path=self._config_store.config_path,
        )

    def _discover(
        self, available: dict[str, tuple[int | str, int]]
    ) -> tuple[UniverseDiscoverItem, ...]:
        return tuple(
            UniverseDiscoverItem(
                key=key,
                universe_type=self._universe_type(key),
                subsector_id=sub_id,
                sector_id=sector,
            )
            for key, (sub_id, sector) in sorted(available.items())
        )

    def _resolve_targets(
        self,
        universe_name: str | None,
        available: dict[str, tuple[int | str, int]],
        existing: dict,
    ) -> list[str]:
        if universe_name:
            targets = [u.strip().lower() for u in universe_name.split(",")]
            unknown = [
                t
                for t in targets
                if t not in available
                and not (t in existing
                         and isinstance(existing[t], dict)
                         and "sector_id" in existing[t])
            ]
            if unknown:
                raise ValueError(
                    f"Unknown universe(s): {', '.join(unknown)}. "
                    f"Available: {', '.join(sorted(available.keys()))}"
                )
            return targets

        targets = [k for k in available if k != "ihsg"]
        for k, v in existing.items():
            if isinstance(v, dict) and "sector_id" in v and k not in targets:
                targets.append(k)
        return targets

    def _fetch_tickers(
        self, key: str, is_custom: bool, custom_cfg: dict | None
    ) -> list[str]:
        if is_custom and custom_cfg:
            return self._fetch_custom_tickers(custom_cfg)
        return self._provider.fetch(key)

    def _fetch_custom_tickers(self, cfg: dict) -> list[str]:
        sector_id = cfg["sector_id"]
        subsector_id = cfg.get("subsector_id")
        tickers: list[str] = []

        if subsector_id is not None:
            url = (
                "https://exodus.stockbit.com/emitten/v3/sector/"
                f"{sector_id}/subsector/{subsector_id}/company"
            )
            body = self._provider.get(url)
            if body is not None:
                tickers = extract_company_tickers(body)
        else:
            url = f"https://exodus.stockbit.com/emitten/sectors/{sector_id}/subsectors"
            body = self._provider.get(url)
            if body is not None:
                subsectors = extract_subsector_rows(body)
                for i, sub in enumerate(subsectors):
                    sub_id = sub.id
                    if sub_id == "?":
                        continue
                    if i > 0:
                        self._sleep(0.2)
                    comp_url = (
                        "https://exodus.stockbit.com/emitten/v3/sector/"
                        f"{sector_id}/subsector/{sub_id}/company"
                    )
                    comp_body = self._provider.get(comp_url)
                    if comp_body is None:
                        return []
                    tickers.extend(extract_company_tickers(comp_body))

        return sorted(set(tickers))


class CreateUniverseUseCase:
    """Create a custom universe from a sector/subsector."""

    def __init__(
        self,
        provider: UniverseCatalogProvider,
        config_store: UniverseConfigStore,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._provider = provider
        self._config_store = config_store
        self._sleep = sleep or (lambda x: None)

    def execute(
        self,
        *,
        name: str,
        sector_id: int,
        subsector_id: int | None,
        today: date,
    ) -> UniverseCreateResult:
        universe_key = name.strip().lower()
        today_str = today.isoformat()

        tickers = self._fetch_tickers(sector_id, subsector_id)
        tickers = sorted(set(tickers))

        if not tickers:
            raise ValueError("No valid company tickers extracted.")

        existing = self._config_store.load_raw()
        existing[universe_key] = {
            "updated": today_str,
            "tickers": tickers,
            "sector_id": sector_id,
        }
        if subsector_id is not None:
            existing[universe_key]["subsector_id"] = subsector_id

        self._config_store.save_raw(existing, updated=today_str)

        return UniverseCreateResult(
            universe_name=universe_key,
            tickers=tuple(tickers),
            sector_id=sector_id,
            subsector_id=subsector_id,
            config_path=self._config_store.config_path,
        )

    def _fetch_tickers(self, sector_id: int, subsector_id: int | None) -> list[str]:
        tickers: list[str] = []

        if subsector_id is not None:
            url = (
                "https://exodus.stockbit.com/emitten/v3/sector/"
                f"{sector_id}/subsector/{subsector_id}/company"
            )
            body = self._provider.get(url)
            if body is None:
                raise ValueError(
                    "Error: Failed to fetch data for sector "
                    f"{sector_id} subsector {subsector_id}."
                )
            items = extract_company_tickers(body)
            if not items:
                raise ValueError(
                    f"No companies found in sector {sector_id} "
                    f"subsector {subsector_id}."
                )
            tickers.extend(items)
        else:
            url = f"https://exodus.stockbit.com/emitten/sectors/{sector_id}/subsectors"
            body = self._provider.get(url)
            if body is None:
                raise ValueError(f"Failed to fetch subsectors for sector {sector_id}.")
            subsectors = extract_subsector_rows(body)
            if not subsectors:
                raise ValueError(f"No subsectors found for sector {sector_id}.")

            for i, sub in enumerate(subsectors):
                sub_id = sub.id
                if sub_id == "?":
                    continue
                if i > 0:
                    self._sleep(0.2)
                comp_url = (
                    "https://exodus.stockbit.com/emitten/v3/sector/"
                    f"{sector_id}/subsector/{sub_id}/company"
                )
                comp_body = self._provider.get(comp_url)
                if comp_body is None:
                    raise ValueError(
                        "Error: Failed to fetch data for sector "
                        f"{sector_id} subsector {sub_id}. "
                        "Aborting transaction to keep config safe."
                    )
                tickers.extend(extract_company_tickers(comp_body))

        return tickers


class InspectUniverseUseCase:
    """Inspect Stockbit sectors, subsectors, and companies."""

    def __init__(self, provider: UniverseCatalogProvider) -> None:
        self._provider = provider

    def execute(
        self,
        *,
        sector_id: int | None,
        subsector_id: int | None,
        with_count: bool,
    ) -> UniverseInspectResult:
        if subsector_id is not None and sector_id is None:
            raise ValueError(
                "--sector (-s) ID is required when specifying --subsector (-b) ID."
            )

        if sector_id is None:
            return self._inspect_sectors()
        elif subsector_id is None:
            return self._inspect_subsectors(sector_id, with_count)
        else:
            return self._inspect_companies(sector_id, subsector_id)

    def _inspect_sectors(self) -> UniverseInspectResult:
        body = self._provider.get("https://exodus.stockbit.com/emitten/sectors")
        if body is None:
            raise ValueError("No sectors returned. Check session or response shape.")
        rows = extract_sector_rows(body)
        return UniverseInspectResult(
            title="STOCKBIT SECTORS",
            rows=tuple(rows),
            tip_lines=(
                "Tip: drill into a sector with --sector <ID> (e.g., -s 70)",
                "     Known useful IDs: 88=Broad Indices  70=Sectoral Indices",
            ),
        )

    def _inspect_subsectors(self, sector_id: int, with_count: bool) -> UniverseInspectResult:
        url = f"https://exodus.stockbit.com/emitten/sectors/{sector_id}/subsectors"
        body = self._provider.get(url)
        if body is None:
            raise ValueError(f"No subsectors found for sector {sector_id}.")
        rows = extract_subsector_rows(body)

        if with_count:
            enriched: list[UniverseInspectRow] = []
            for row in rows:
                if row.count == "?":
                    comp_url = (
                        "https://exodus.stockbit.com/emitten/v3/sector/"
                        f"{sector_id}/subsector/{row.id}/company"
                    )
                    comp_body = self._provider.get(comp_url)
                    items = extract_company_rows(comp_body) if comp_body else []
                    enriched.append(replace(row, count=str(len(items))))
                else:
                    enriched.append(row)
            rows = tuple(enriched)

        tip = (
            "Tip: drill into a subsector with: "
            f"--sector {sector_id} --subsector <SUB-ID>"
        )
        return UniverseInspectResult(
            title=f"SUBSECTORS OF SECTOR {sector_id}",
            rows=tuple(rows),
            tip_lines=(tip,),
        )

    def _inspect_companies(self, sector_id: int, subsector_id: int) -> UniverseInspectResult:
        url = (
            "https://exodus.stockbit.com/emitten/v3/sector/"
            f"{sector_id}/subsector/{subsector_id}/company"
        )
        body = self._provider.get(url)
        if body is None:
            raise ValueError(
                f"No companies found in sector {sector_id} subsector {subsector_id}."
            )
        rows = extract_company_rows(body)
        return UniverseInspectResult(
            title=f"COMPANIES IN SUBSECTOR {subsector_id} (Sector {sector_id})",
            rows=tuple(rows),
            total=len(rows),
        )
