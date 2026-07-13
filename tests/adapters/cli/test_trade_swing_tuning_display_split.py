"""Tests for the swing tuning display module split (finding #12).

Layer: Adapter
"""

from __future__ import annotations

import ast
from pathlib import Path

from src.adapters.cli import trade_swing_tuning_display as facade
from src.adapters.cli.trade_swing_tuning_display_formatters import (
    format_delta,
    format_int,
    format_pct,
    format_value,
    period,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _imports_from(module_path: Path, target: str) -> bool:
    tree = ast.parse(module_path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == target:
            return True
    return False


def test_facade_exports_all_eight_public_display_functions():
    expected = [
        "display_swing_tuning_review_report",
        "display_swing_tuning_loop_status",
        "display_swing_tuning_review_comparison",
        "display_swing_tuning_post_apply_measurement",
        "display_swing_tuning_patch_validation",
        "display_swing_tuning_patch_dry_run",
        "display_swing_tuning_patch_apply",
        "display_swing_tuning_patch_verify",
    ]
    assert facade.__all__ == expected
    for name in expected:
        assert callable(getattr(facade, name))


def test_status_commands_no_longer_import_from_facade():
    module_path = REPO_ROOT / "src" / "adapters" / "cli" / "trade_tuning_status_commands.py"
    assert not _imports_from(module_path, "src.adapters.cli.trade_swing_tuning_display")


def test_patch_commands_no_longer_import_from_facade():
    module_path = REPO_ROOT / "src" / "adapters" / "cli" / "trade_tuning_patch_commands.py"
    assert not _imports_from(module_path, "src.adapters.cli.trade_swing_tuning_display")


def test_format_int_none_is_na():
    assert format_int(None) == "N/A"


def test_format_pct_unsigned_positive():
    assert format_pct(1.23) == "[green]1.2%[/]"


def test_format_pct_signed_negative():
    assert format_pct(-1.23, signed=True) == "[red]-1.23%[/]"


def test_format_value_float():
    assert format_value(1.234) == "1.23"


def test_format_delta_positive_int():
    assert format_delta(2) == "[green]+2[/]"


def test_period_with_dates():
    assert period("2026-01-01", "2026-01-31") == "2026-01-01 to 2026-01-31"
