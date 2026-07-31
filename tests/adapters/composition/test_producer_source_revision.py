"""Producer source_revision must be non-empty stable provenance."""

from __future__ import annotations

from src import __version__
from src.adapters.composition.producer_source_revision import (
    resolve_producer_source_revision,
)


def test_producer_source_revision_is_non_empty_and_versioned() -> None:
    resolve_producer_source_revision.cache_clear()
    revision = resolve_producer_source_revision()
    assert revision
    assert revision.startswith(f"ai-saham@{__version__}")
    assert " " not in revision
