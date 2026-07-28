"""Sector macro is judgment-desk only (ADR-054) — not plan swing structure."""

from src.adapters.cli import plan_swing_evidence_display as evidence_mod


def test_plan_swing_evidence_does_not_import_sector_macro_printer():
    """Regression: plan must not re-wire sector macro panel after ADR-054."""
    assert not hasattr(evidence_mod, "print_sector_macro_context_panel")
    src = open(evidence_mod.__file__, encoding="utf-8").read()
    assert "print_sector_macro_context_panel" not in src
