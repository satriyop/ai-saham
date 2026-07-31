"""Architecture guard: one application-layer effective-session contract.

DQ-002 criterion 1: current screen, swing, canonical capture, and
accumulation-evaluation workflows must all reach the same
``EffectiveMarketSessionResolver`` for their effective-session contract.
No parallel ``date.today()`` / ``datetime.now()`` / weekday-arithmetic
path may derive ``analysis_as_of`` or ``latest_completed_session``
outside the resolver.

``date.today()`` and ``datetime.now()`` may legitimately appear when
constructing the ``run_at`` timestamp that is then passed *into* the
resolver. What is forbidden is constructing a session directly from
those calls without going through the resolver.

Layer: Test (architecture guard, no runtime behavior).
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Adapter factories that must construct EffectiveMarketSessionResolver
# and inject it into the use cases they build. They do not call .resolve()
# themselves — the resolver is handed off to the use case.
ADAPTER_FACTORY_FILES = (
    "src/adapters/composition/screen_accum_workflow_factory.py",
    "src/adapters/composition/plan_swing_workflow_factory.py",
    "src/adapters/cli/research_accum_backfill_commands.py",
    "src/infrastructure/composition/fetch_market/fetch_market_workflow_factory.py",
)

# Application use cases that must invoke the resolver via .resolve() to
# obtain the effective IDX session. They may construct the resolver
# themselves or receive it as an injected dependency.
USE_CASE_FILES = (
    "src/application/use_case/accumulation_audit_use_case.py",
    "src/application/use_case/plan_swing_workflow_use_case.py",
    "src/application/use_case/swing_backtest_use_case.py",
    "src/application/use_case/log_swing_candidate_use_case.py",
    "src/application/use_case/backfill_signal_observations_use_case.py",
    "src/application/use_case/daily_briefing_use_case.py",
    "src/application/use_case/fetch_market_command_workflow_use_case.py",
    "src/application/use_case/build_live_signal_evidence_execution_context_use_case.py",
)

# last_weekday() is the resolver-internal fallback when no cached IHSG
# data bounds the decision date. Workflow files must not call it
# directly to derive a session — that bypasses the single authority.
FORBIDDEN_DIRECT_CALLS = ("last_weekday(",)


def _read(path_str: str) -> str:
    return (REPO_ROOT / path_str).read_text()


@pytest.mark.parametrize("path", ADAPTER_FACTORY_FILES)
def test_adapter_factory_constructs_effective_market_session_resolver(path: str) -> None:
    """Each screen / swing / canonical-capture / fetch adapter factory
    must reference and construct EffectiveMarketSessionResolver, proving
    one application-layer authority supplies the effective IDX session."""
    source = _read(path)
    assert "EffectiveMarketSessionResolver" in source, (
        f"{path} does not reference EffectiveMarketSessionResolver; "
        "the workflow must reach the same application-layer authority"
    )
    assert "EffectiveMarketSessionResolver(" in source, (
        f"{path} references the resolver but never constructs it; "
        "the factory must build the canonical authority"
    )


@pytest.mark.parametrize("path", USE_CASE_FILES)
def test_use_case_references_effective_market_session_resolver(path: str) -> None:
    """Each screen / swing / canonical-capture / accumulation-evaluation
    use case must reference EffectiveMarketSessionResolver — by
    constructing it, receiving it as an injected dependency, or by type-
    annotating a parameter that holds it. The reference proves the use
    case obtains the effective IDX session from the single authority
    rather than from local date arithmetic."""
    source = _read(path)
    assert "EffectiveMarketSessionResolver" in source, (
        f"{path} does not reference EffectiveMarketSessionResolver; "
        "the use case must obtain the session from the canonical authority"
    )


@pytest.mark.parametrize("path", ADAPTER_FACTORY_FILES + USE_CASE_FILES)
def test_workflow_does_not_bypass_resolver_with_internal_fallback(path: str) -> None:
    """No screen / swing / canonical-capture / accumulation-evaluation
    file may call ``last_weekday()`` directly — that is a resolver-
    internal fallback when IHSG cached data is unavailable. Deriving a
    session from it in a workflow bypasses the single authority."""
    source = _read(path)
    for forbidden in FORBIDDEN_DIRECT_CALLS:
        assert forbidden not in source, (
            f"{path} contains forbidden direct call {forbidden!r}; "
            "the effective session must come from EffectiveMarketSessionResolver"
        )
