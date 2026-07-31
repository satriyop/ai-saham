"""Re-export accum paper-log workflow factory from shared composition."""

from src.adapters.composition.trade_accum_workflow_factory import (
    create_log_accumulation_trade_workflow,
)

__all__ = ["create_log_accumulation_trade_workflow"]
