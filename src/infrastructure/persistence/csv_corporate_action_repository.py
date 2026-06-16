"""
CsvCorporateActionRepository — reads ex-date data from a user-maintained CSV file.

CSV format: ticker,ex_date
  - ticker: uppercase IDX code (e.g. BBCA)
  - ex_date: ISO date string (YYYY-MM-DD)

If the file does not exist, all queries return empty lists (graceful degradation).
User populates this from IDX announcements at idx.co.id or stockbit.com.

Layer: Infrastructure
"""

import csv
import logging
from datetime import date
from pathlib import Path

from src.application.ports.corporate_action_repository import CorporateActionRepository

logger = logging.getLogger(__name__)


class CsvCorporateActionRepository(CorporateActionRepository):
    """Read ex-dividend dates from a local CSV file."""

    def __init__(self, csv_path: Path) -> None:
        self._path = csv_path
        self._cache: dict[str, list[date]] | None = None

    def _load(self) -> dict[str, list[date]]:
        if self._cache is not None:
            return self._cache
        result: dict[str, list[date]] = {}
        if not self._path.exists():
            self._cache = result
            return result
        try:
            with open(self._path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ticker = str(row.get("ticker", "")).strip().upper()
                    raw_date = str(row.get("ex_date", "")).strip()
                    if not ticker or not raw_date:
                        continue
                    try:
                        ex_date = date.fromisoformat(raw_date)
                        result.setdefault(ticker, []).append(ex_date)
                    except ValueError:
                        logger.debug("Skipping invalid ex_date row: %s", row)
        except Exception as e:
            logger.warning("Could not load corporate actions CSV %s: %s", self._path, e)
        self._cache = result
        return result

    def get_upcoming_ex_dates(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
    ) -> list[date]:
        data = self._load()
        dates = data.get(ticker.upper(), [])
        return [d for d in dates if from_date <= d <= to_date]
