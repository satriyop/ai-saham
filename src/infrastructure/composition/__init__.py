"""
Infrastructure composition roots.

Concrete wiring for engine/session factories that need SQLite repositories,
Stockbit providers, config loaders, plugin discovery, or app config lives
here. Application layer must not import these modules; adapters call them
directly to obtain fully-wired instances to pass into application use cases.

Layer: Infrastructure (composition root)
"""

from __future__ import annotations
