"""Screen accum exposes named setup MATCH/PARTIAL/NO_MATCH (diagnostic)."""

from __future__ import annotations

from types import SimpleNamespace

from src.adapters.shared.decision_display import (
    format_primary_setup_family,
    named_setup_match_glyphs,
)
from src.application.services.primary_setup_family_resolver import PrimarySetupFamilyResult
from src.domain.value_objects.setup_evaluation import SetupEvaluation, SetupMatch


def _eval(name: str, match: SetupMatch, family: str) -> SetupEvaluation:
    return SetupEvaluation(
        name=name,
        match=match,
        gates=(),
        failed_reasons=(),
        family=family,
        entry_authority=True,
        can_enter_from_phases=(),
    )


def test_named_setup_match_glyphs_board_order() -> None:
    candidate = SimpleNamespace(
        named_setup_evaluations={
            "foreign-bounce": _eval("foreign-bounce", SetupMatch.PARTIAL, "accumulation"),
            "coiled-spring": _eval("coiled-spring", SetupMatch.NO_MATCH, "breakout"),
            "smart-money-confirmed": _eval(
                "smart-money-confirmed", SetupMatch.NO_MATCH, "confirmation"
            ),
            "pullback-continuation": _eval("pullback-continuation", SetupMatch.MATCH, "pullback"),
        }
    )
    glyphs = named_setup_match_glyphs(candidate)
    assert list(glyphs.keys()) == ["FB", "CS", "SM", "PB"]
    assert glyphs == {"FB": "~", "CS": "·", "SM": "·", "PB": "M"}


def test_named_setup_match_glyphs_missing_evals_are_dash() -> None:
    assert named_setup_match_glyphs(SimpleNamespace(named_setup_evaluations=None)) == {
        "FB": "-",
        "CS": "-",
        "SM": "-",
        "PB": "-",
    }


def test_format_primary_setup_family_from_result() -> None:
    candidate = SimpleNamespace(
        signal_assessment=None,
        setup_family=None,
        setup_family_result=PrimarySetupFamilyResult(
            matched_setup_families=("pullback",),
            primary_setup_family="pullback",
            setup_family_source="detected_screen_evidence",
        ),
    )
    assert format_primary_setup_family(candidate) == "pullback"


def test_primary_setup_family_result_to_dict() -> None:
    result = PrimarySetupFamilyResult(
        matched_setup_families=("pullback", "breakout"),
        primary_setup_family="pullback",
        setup_family_source="detected_screen_evidence",
        rationale=("setup 'pullback-continuation' matched",),
    )
    assert result.to_dict() == {
        "primary_setup_family": "pullback",
        "matched_setup_families": ["pullback", "breakout"],
        "setup_family_source": "detected_screen_evidence",
        "rationale": ["setup 'pullback-continuation' matched"],
    }
