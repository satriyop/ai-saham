"""Canonical persisted-artifact schema version constants.

Layer: Domain
Depends on: stdlib only

These are the single source of truth for candidate-observation and
forward-label schema identity. Do not hardcode another canonical 2 or 3
anywhere else — import these constants instead.
"""

from __future__ import annotations

CANDIDATE_OBSERVATION_SCHEMA_VERSION = 3
SIGNAL_FORWARD_LABEL_SCHEMA_VERSION = 2
