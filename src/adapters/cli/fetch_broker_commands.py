"""
Router facade for broker fetch CLI commands.

The actual command implementations live in per-command modules:
- fetch_broker_summary_commands (broker_fetch)
- fetch_broker_import_commands (broker_import)
- fetch_broker_history_commands (broker_history)
- fetch_broker_foreign_top_commands (broker_top_foreign)

This module exists only for backward-compatible imports.

Layer: Adapter
"""

from __future__ import annotations

from src.adapters.cli.fetch_broker_foreign_top_commands import broker_top_foreign
from src.adapters.cli.fetch_broker_history_commands import broker_history
from src.adapters.cli.fetch_broker_import_commands import broker_import
from src.adapters.cli.fetch_broker_summary_commands import broker_fetch

__all__ = ["broker_fetch", "broker_import", "broker_history", "broker_top_foreign"]
