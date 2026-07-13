"""Compatibility facade for swing tuning display modules.

Layer: Adapter
"""

from __future__ import annotations

from src.adapters.cli.trade_swing_tuning_loop_status_display import (
    display_swing_tuning_loop_status,
)
from src.adapters.cli.trade_swing_tuning_measurement_display import (
    display_swing_tuning_post_apply_measurement,
)
from src.adapters.cli.trade_swing_tuning_patch_display import (
    display_swing_tuning_patch_apply,
    display_swing_tuning_patch_dry_run,
    display_swing_tuning_patch_validation,
    display_swing_tuning_patch_verify,
)
from src.adapters.cli.trade_swing_tuning_review_display import (
    display_swing_tuning_review_comparison,
    display_swing_tuning_review_report,
)

__all__ = [
    "display_swing_tuning_review_report",
    "display_swing_tuning_loop_status",
    "display_swing_tuning_review_comparison",
    "display_swing_tuning_post_apply_measurement",
    "display_swing_tuning_patch_validation",
    "display_swing_tuning_patch_dry_run",
    "display_swing_tuning_patch_apply",
    "display_swing_tuning_patch_verify",
]
