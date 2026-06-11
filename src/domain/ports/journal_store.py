"""
JournalStore port — abstract persistence interface for paper trade journal.

Layer: Domain
"""

from abc import ABC, abstractmethod

from src.domain.value_objects.journal_entry import JournalEntry


class JournalStore(ABC):
    @abstractmethod
    def append(self, entries: list[JournalEntry]) -> int:
        """Append entries to the store. Idempotent: (screened_at, ticker) is the key.

        Returns:
            Number of rows actually written (0 if all were duplicates).
        """

    @abstractmethod
    def read_all(self) -> list[JournalEntry]:
        """Return all stored entries sorted by screened_at ascending."""
