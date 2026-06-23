"""
StockbitCorporateActionRepository — live corporate action data from Stockbit Exodus API.

Calls /corpaction/{ticker} to retrieve upcoming dividend, rights issue, RUPS,
split, bonus, and other corporate action events.

Caching: SQLite daily cache (table: corp_action_cache) to avoid repeated API
calls across multiple screener tickers in the same run. Cache TTL = calendar day.

Token: Reuses the RS256 Bearer token from StockbitPlaywrightBrokerProvider._get_token()
— no separate browser session is opened.

Layer: Infrastructure
Depends on: playwright_stockbit (for token), sqlite3, CorporateActionEvent
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.application.ports.corporate_action_repository import CorporateActionRepository
from src.domain.value_objects.corporate_action_event import CorporateActionEvent

if TYPE_CHECKING:
    from src.infrastructure.browser.playwright_stockbit_provider import StockbitPlaywrightBrokerProvider

logger = logging.getLogger(__name__)

from src.infrastructure.config.stockbit_config import STOCKBIT_CFG

_CORPACTION_URL = STOCKBIT_CFG.corp_action_url

# Map raw Stockbit action type strings → CorporateActionEvent.TYPE_* constants
_TYPE_MAP: dict[str, str] = {
    "dividend":     CorporateActionEvent.TYPE_DIVIDEND,
    "dividen":      CorporateActionEvent.TYPE_DIVIDEND,
    "cash dividend":CorporateActionEvent.TYPE_DIVIDEND,
    "rightissue":   CorporateActionEvent.TYPE_RIGHTS_ISSUE,
    "right issue":  CorporateActionEvent.TYPE_RIGHTS_ISSUE,
    "rights issue": CorporateActionEvent.TYPE_RIGHTS_ISSUE,
    "hmetd":        CorporateActionEvent.TYPE_RIGHTS_ISSUE,   # Hak Memesan Efek Terlebih Dahulu
    "rups":         CorporateActionEvent.TYPE_RUPS,
    "rupslb":       CorporateActionEvent.TYPE_RUPS,
    "stocksplit":   CorporateActionEvent.TYPE_SPLIT,
    "stock split":  CorporateActionEvent.TYPE_SPLIT,
    "split":        CorporateActionEvent.TYPE_SPLIT,
    "bonus":        CorporateActionEvent.TYPE_BONUS,
    "bonus share":  CorporateActionEvent.TYPE_BONUS,
    "warrant":      CorporateActionEvent.TYPE_WARRANT,
    "ipo":          CorporateActionEvent.TYPE_IPO,
    "tenderoffer":  CorporateActionEvent.TYPE_TENDER_OFFER,
    "tender offer": CorporateActionEvent.TYPE_TENDER_OFFER,
}


def _normalise_type(raw: str) -> str:
    key = raw.strip().lower()
    return _TYPE_MAP.get(key, CorporateActionEvent.TYPE_OTHER)


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    raw = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y%m%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_events(ticker: str, body: dict) -> list[CorporateActionEvent]:
    """Parse the /corpaction/{ticker} response into CorporateActionEvent objects.

    Actual Stockbit Exodus response shape (confirmed 2026-06):
      data[] — direct list of action objects, each:
        action_type: "dividend" | "rups" | "rightissue" | "split" | ...
        action_info:
          dividend:
            dividend_exdate, dividend_cumdate, dividend_recdate,
            dividend_paydate, dividend_created, dividend_value,
            corp_action_active (bool)
          rups:
            rups_date, rups_time, rups_venue, corp_action_active
    """
    data = body.get("data") if isinstance(body, dict) else None
    if data is None:
        return []

    items: list = data if isinstance(data, list) else []

    events: list[CorporateActionEvent] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        raw_type = str(item.get("action_type") or "").strip()
        event_type = _normalise_type(raw_type)

        # Nested payload under action_info[action_type]
        info = item.get("action_info", {})
        payload = info.get(raw_type.lower(), {}) if isinstance(info, dict) else {}

        ex_date: date | None = None
        cum_date: date | None = None
        record_date: date | None = None
        payment_date: date | None = None
        announcement_date: date | None = None
        detail = raw_type

        if event_type == CorporateActionEvent.TYPE_DIVIDEND:
            ex_date = _parse_date(payload.get("dividend_exdate"))
            cum_date = _parse_date(payload.get("dividend_cumdate"))
            record_date = _parse_date(payload.get("dividend_recdate"))
            payment_date = _parse_date(payload.get("dividend_paydate"))
            announcement_date = _parse_date(payload.get("dividend_created"))
            val = payload.get("dividend_value") or payload.get("dividend_value_formatted")
            if val:
                detail = f"Rp {val}/share"

        elif event_type == CorporateActionEvent.TYPE_RUPS:
            # RUPS date is the meeting date — store as ex_date for window-filter compat
            ex_date = _parse_date(payload.get("rups_date"))
            announcement_date = _parse_date(payload.get("rups_created"))
            venue = payload.get("rups_venue") or ""
            rups_time = payload.get("rups_time") or ""
            detail = f"RUPS {rups_time} {venue}".strip()

        elif event_type == CorporateActionEvent.TYPE_RIGHTS_ISSUE:
            ex_date = _parse_date(
                payload.get("rightissue_exdate") or payload.get("ex_date")
            )
            cum_date = _parse_date(
                payload.get("rightissue_cumdate") or payload.get("cum_date")
            )
            record_date = _parse_date(payload.get("rightissue_recdate"))
            payment_date = _parse_date(payload.get("rightissue_paydate"))
            price = payload.get("rightissue_price") or payload.get("subscription_price")
            if price:
                detail = f"Rights subs price Rp {price}"

        elif event_type == CorporateActionEvent.TYPE_SPLIT:
            ex_date = _parse_date(payload.get("split_exdate") or payload.get("ex_date"))
            ratio = payload.get("split_ratio") or payload.get("ratio")
            if ratio:
                detail = f"Split ratio {ratio}"

        else:
            # Generic fallback — try common field names
            ex_date = _parse_date(payload.get("ex_date") or payload.get("exdate"))
            cum_date = _parse_date(payload.get("cum_date") or payload.get("cumdate"))

        events.append(CorporateActionEvent(
            ticker=ticker.upper(),
            event_type=event_type,
            ex_date=ex_date,
            cum_date=cum_date,
            record_date=record_date,
            payment_date=payment_date,
            announcement_date=announcement_date,
            detail=detail,
            status="active" if payload.get("corp_action_active") else "inactive",
        ))

    return events


class StockbitCorporateActionRepository(CorporateActionRepository):
    """
    Fetches upcoming corporate actions from Stockbit and caches results
    in SQLite (table: corp_action_cache, TTL = 1 calendar day).

    Args:
        broker_provider: An authenticated StockbitPlaywrightBrokerProvider instance.
            Used to obtain the RS256 Bearer token without launching a new browser.
        db_path:  Path to the SQLite database (same data.db used by broker repos).
    """

    def __init__(
        self,
        broker_provider: "StockbitPlaywrightBrokerProvider",
        db_path: str | Path = Path("data.db"),
    ) -> None:
        self._provider = broker_provider
        self._db_path = Path(db_path).expanduser()
        self._ensure_schema()

    # ── Schema ───────────────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS corp_action_cache (
                        ticker            TEXT NOT NULL,
                        event_type        TEXT NOT NULL,
                        ex_date           TEXT,
                        cum_date          TEXT,
                        record_date       TEXT,
                        payment_date      TEXT,
                        announcement_date TEXT,
                        detail            TEXT,
                        status            TEXT,
                        fetched_date      TEXT NOT NULL,
                        PRIMARY KEY (ticker, event_type, ex_date, cum_date)
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_corp_action_ticker_fetched
                    ON corp_action_cache(ticker, fetched_date)
                """)
        except Exception as e:
            logger.warning("corp_action_cache schema error: %s", e)

    # ── Cache ─────────────────────────────────────────────────────────────────

    def _is_cache_fresh(self, ticker: str) -> bool:
        today_str = date.today().isoformat()
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT 1 FROM corp_action_cache WHERE ticker=? AND fetched_date=? LIMIT 1",
                    (ticker.upper(), today_str),
                ).fetchone()
            return row is not None
        except Exception:
            return False

    def _read_cache(self, ticker: str, from_date: date, to_date: date) -> list[CorporateActionEvent]:
        try:
            with self._get_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT event_type, ex_date, cum_date, record_date, payment_date,
                           announcement_date, detail, status
                    FROM corp_action_cache
                    WHERE ticker = ?
                    """,
                    (ticker.upper(),),
                ).fetchall()
        except Exception as e:
            logger.debug("corp_action_cache read error for %s: %s", ticker, e)
            return []

        events: list[CorporateActionEvent] = []
        for row in rows:
            ex = _parse_date(row["ex_date"])
            cum = _parse_date(row["cum_date"])
            rec = _parse_date(row["record_date"])
            earliest = ex or cum or rec or _parse_date(row["announcement_date"])
            if earliest is None or not (from_date <= earliest <= to_date):
                continue
            events.append(CorporateActionEvent(
                ticker=ticker.upper(),
                event_type=row["event_type"],
                ex_date=ex,
                cum_date=cum,
                record_date=rec,
                payment_date=_parse_date(row["payment_date"]),
                announcement_date=_parse_date(row["announcement_date"]),
                detail=row["detail"] or "",
                status=row["status"] or "",
            ))
        return events

    def _write_cache(self, ticker: str, events: list[CorporateActionEvent]) -> None:
        today_str = date.today().isoformat()
        try:
            with self._get_conn() as conn:
                # Clear stale entries for this ticker (different day)
                conn.execute(
                    "DELETE FROM corp_action_cache WHERE ticker=? AND fetched_date!=?",
                    (ticker.upper(), today_str),
                )
                for e in events:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO corp_action_cache
                            (ticker, event_type, ex_date, cum_date, record_date,
                             payment_date, announcement_date, detail, status, fetched_date)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            e.ticker,
                            e.event_type,
                            e.ex_date.isoformat() if e.ex_date else None,
                            e.cum_date.isoformat() if e.cum_date else None,
                            e.record_date.isoformat() if e.record_date else None,
                            e.payment_date.isoformat() if e.payment_date else None,
                            e.announcement_date.isoformat() if e.announcement_date else None,
                            e.detail,
                            e.status,
                            today_str,
                        ),
                    )
                # If no events, insert a sentinel row so we know we fetched (empty result)
                if not events:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO corp_action_cache
                            (ticker, event_type, ex_date, cum_date, fetched_date)
                        VALUES (?, '__NONE__', NULL, NULL, ?)
                        """,
                        (ticker.upper(), today_str),
                    )
        except Exception as e:
            logger.debug("corp_action_cache write error for %s: %s", ticker, e)

    # ── Fetch ─────────────────────────────────────────────────────────────────

    def _fetch_from_api(self, ticker: str) -> list[CorporateActionEvent]:
        """Call Exodus /corpaction/{ticker} and parse the response."""
        if self._provider is None:
            return []
        try:
            from src.infrastructure.browser.playwright_stockbit_provider import _exodus_get
            token = self._provider._get_token()
            url = _CORPACTION_URL.format(ticker=ticker.upper())
            body = _exodus_get(url, token)
            if not body:
                logger.debug("Empty corp action response for %s", ticker)
                return []
            events = _parse_events(ticker, body)
            logger.debug("Stockbit corp action: %s → %d events", ticker, len(events))
            return events
        except Exception as e:
            logger.warning("Corp action fetch failed for %s: %s", ticker, e)
            return []

    # ── Port implementation ───────────────────────────────────────────────────

    def get_upcoming_events(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
    ) -> list[CorporateActionEvent]:
        """Return upcoming corporate action events in [from_date, to_date].

        Checks SQLite cache first (TTL = today). On cache miss, calls the
        Stockbit API and writes results to cache before returning.
        """
        ticker = ticker.upper()

        if self._is_cache_fresh(ticker):
            return self._read_cache(ticker, from_date, to_date)

        events = self._fetch_from_api(ticker)
        self._write_cache(ticker, events)

        return [
            e for e in events
            if _event_in_window(e, from_date, to_date)
        ]


def _event_in_window(event: CorporateActionEvent, from_date: date, to_date: date) -> bool:
    """True if the event's earliest relevant date falls within [from_date, to_date]."""
    d = event.earliest_relevant_date
    return d is not None and from_date <= d <= to_date
