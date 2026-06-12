"""
SQLite implementation of the sentiment repository.

Persists sentiment logs and audits to the local SQLite database.

Layer: Infrastructure (Persistence)
"""

import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

from src.domain.ports.sentiment_repository import SentimentAudit, SentimentLog, SentimentRepository
from src.domain.value_objects.sentiment import CatalystType, Sentiment


class SQLiteSentimentRepository(SentimentRepository):
    """SQLite implementation of the SentimentRepository port."""

    def __init__(self, db_path: str | Path = "data.db"):
        """Initialize repository and ensure tables exist.

        Args:
            db_path: Path to the SQLite database file
        """
        self._db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Create sentiment tables if they don't exist."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sentiment_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    sentiment TEXT NOT NULL,
                    catalyst TEXT NOT NULL,
                    score REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sentiment_audits (
                    log_id INTEGER NOT NULL,
                    days_after INTEGER NOT NULL,
                    price_delta_pct REAL NOT NULL,
                    audited_at TEXT NOT NULL,
                    PRIMARY KEY (log_id, days_after),
                    FOREIGN KEY (log_id) REFERENCES sentiment_logs (id)
                )
            """)
            conn.commit()

    def save_log(self, log: SentimentLog) -> int:
        """Save a new sentiment log."""
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO sentiment_logs (date, ticker, sentiment, catalyst, score) VALUES (?, ?, ?, ?, ?)",
                (log.date.isoformat(), log.ticker.upper(), log.sentiment.value, log.catalyst.value, log.score)
            )
            conn.commit()
            return cursor.lastrowid

    def get_unaudited_logs(self, days_ago: int) -> list[SentimentLog]:
        """Find logs that haven't been audited for a specific timeframe."""
        with sqlite3.connect(self._db_path) as conn:
            # Join with audits to find logs of certain age that lack an audit for 'days_ago'
            cursor = conn.execute(
                """
                SELECT l.id, l.date, l.ticker, l.sentiment, l.catalyst, l.score
                FROM sentiment_logs l
                LEFT JOIN sentiment_audits a ON l.id = a.log_id AND a.days_after = ?
                WHERE a.log_id IS NULL
                AND l.date <= date('now', '-' || ? || ' days')
                """,
                (days_ago, days_ago)
            )
            rows = cursor.fetchall()

        return [
            SentimentLog(
                id=row[0],
                date=date.fromisoformat(row[1]),
                ticker=row[2],
                sentiment=Sentiment(row[3]),
                catalyst=CatalystType(row[4]),
                score=row[5]
            )
            for row in rows
        ]

    def save_audit(self, audit: SentimentAudit) -> None:
        """Save an audit result."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sentiment_audits (log_id, days_after, price_delta_pct, audited_at) VALUES (?, ?, ?, ?)",
                (audit.log_id, audit.days_after, float(audit.price_delta_pct), audit.audited_at.isoformat())
            )
            conn.commit()

    def get_stats(self) -> dict:
        """Get summary statistics for sentiment accuracy."""
        stats = {
            "total_logs": 0,
            "audited_logs": 0,
            "by_sentiment": {},
            "by_catalyst": {}
        }

        with sqlite3.connect(self._db_path) as conn:
            # Total logs
            cursor = conn.execute("SELECT COUNT(*) FROM sentiment_logs")
            stats["total_logs"] = cursor.fetchone()[0]

            # Overall Accuracy (where price move direction matches sentiment)
            # POSITIVE sentiment + price_delta > 0 = WIN
            # NEGATIVE sentiment + price_delta < 0 = WIN
            cursor = conn.execute("""
                SELECT l.sentiment, l.catalyst, a.price_delta_pct
                FROM sentiment_logs l
                JOIN sentiment_audits a ON l.id = a.log_id
                WHERE a.days_after = 5
            """)
            rows = cursor.fetchall()
            stats["audited_logs"] = len(rows)

            for sentiment_val, catalyst_val, delta in rows:
                is_win = False
                if sentiment_val == Sentiment.POSITIVE.value and delta > 0:
                    is_win = True
                elif sentiment_val == Sentiment.NEGATIVE.value and delta < 0:
                    is_win = True

                # By sentiment
                if sentiment_val not in stats["by_sentiment"]:
                    stats["by_sentiment"][sentiment_val] = {"wins": 0, "total": 0}
                stats["by_sentiment"][sentiment_val]["total"] += 1
                if is_win:
                    stats["by_sentiment"][sentiment_val]["wins"] += 1

                # By catalyst
                if catalyst_val not in stats["by_catalyst"]:
                    stats["by_catalyst"][catalyst_val] = {"wins": 0, "total": 0}
                stats["by_catalyst"][catalyst_val]["total"] += 1
                if is_win:
                    stats["by_catalyst"][catalyst_val]["wins"] += 1

        return stats
