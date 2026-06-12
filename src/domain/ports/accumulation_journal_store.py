"""
AccumulationJournalStore port — abstract persistence for accumulation trade journal.

Layer: Domain
"""

from abc import ABC, abstractmethod

from src.domain.value_objects.accumulation_journal_entry import AccumulationJournalEntry


class AccumulationJournalStore(ABC):
    @abstractmethod
    def append(self, entries: list[AccumulationJournalEntry]) -> int:
        """Append entries. Idempotent: (logged_at, ticker, window_days) is the dedup key.

        Returns:
            Number of rows actually written (0 if all were duplicates).
        """

    @abstractmethod
    def read_all(self) -> list[AccumulationJournalEntry]:
        """Return all stored entries sorted by logged_at ascending."""
