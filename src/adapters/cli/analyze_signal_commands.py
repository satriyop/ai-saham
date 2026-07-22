"""
Compatibility re-exports for signal CLI callables.

Public registration lives under:
  saham research signal …
  saham analyze signal inspect

Layer: Adapter
"""

from src.adapters.cli.analyze_signal_backfill_commands import signal_backfill_observations
from src.adapters.cli.analyze_signal_inspect_commands import signal_inspect
from src.adapters.cli.analyze_signal_label_commands import signal_labels
from src.adapters.cli.analyze_signal_readiness_commands import signal_readiness
from src.adapters.cli.analyze_signal_replay_commands import signal_replay

__all__ = [
    "signal_replay",
    "signal_labels",
    "signal_readiness",
    "signal_backfill_observations",
    "signal_inspect",
]
