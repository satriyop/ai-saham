"""ADR-068 slice-2 gate: is the behavioural probe set worth trusting?

Slice 1 produced a measurement. This module decides whether that measurement is
*trustworthy enough* to become cohort identity, using the two enforced measures
ADR-068 §5 requires:

1. **Branch coverage** of the accum decision path under the probe run, with a
   numeric floor. New uncovered branches fail the build.
2. **Mutation testing** — deliberately perturb scoring constants, gate
   thresholds, and comparison/verdict directions, and assert the behavioural
   digest moves. A surviving mutant is a *named, fixable hole*, recorded here
   with its rationale, never silenced by deleting or weakening a test.

Coverage is a floor over a finite frozen input set. It is **not** a proof of
behavioural equivalence (ADR-068 "Do Not Interpret This As").

Measured result recorded on 2026-08-05, CPython 3.12.10, coverage 7.14.1
--------------------------------------------------------------------------

Probe sets used for coverage: core (15 probes) + extended (4 probes).

    Aggregate branch coverage over the accum decision path: 59.44% (428/720)
    Aggregate statement coverage over the same scope:       81.89% (1718/2098)

Core-set-only branch coverage was 55.69% (401/720) before slice 2; the four
extended probes added in this slice raised it to 59.44% by attaching a swing
setup catalog, which is what makes setup-family resolution, setup readiness,
and the setup-family branches of DecisionPolicy reachable at all.

Mutants: **45 planted / 31 caught by the core (identity) digest / 14 surviving.**

    GATE_THRESHOLD   14   risk gate thresholds, enablement, confidence
    SIGNAL_CONSTANT  14   SignalEngineConfig scoring/classification/policy
    ACCUM_WEIGHT      8   AccumScorePolicy weights, caps, saturation points
    PHASE_THRESHOLD   5   setup-phase detection thresholds
    COMPARISON_FLIP   4   inverted gate verdicts (comparison direction)

Every survivor is named in ``_SURVIVING_MUTANTS`` below with a rationale, and
each survivor is asserted to *still survive*, so closing a hole fails this
suite and forces the record to be updated deliberately.

**Read the survivor list before making the probe digest authoritative.** All 14
survivors are holes in the *frozen core probe inputs*, not defects in
production code: the constant is simply never compared because no core probe
supplies data that reaches it. Every one of them is closable only by adding or
changing a **core** probe, which ADR-068 §3 defines as a deliberate cohort
boundary — out of scope for this slice and a decision that belongs to a human
before slice 3 begins.

Why the floor lives here and not in CI config
---------------------------------------------

The floor is enforced by ``test_branch_coverage_floor_over_the_accum_decision_path``
below, which spawns a clean subprocess, runs coverage in branch mode over an
explicit module scope, and asserts the frozen per-module and aggregate numbers.
CI already runs ``pytest tests/``, so this is caught by the existing ``test``
job with no workflow change and no ``--cov`` flags that would slow or perturb
coverage accounting for the ~5.7k unrelated tests.

The subprocess is deliberate: it starts coverage *before* importing the runner
so import-time statements are counted honestly, and it cannot collide with an
outer ``pytest --cov`` tracer.

Floors were measured on CPython 3.12. If a different interpreter reports a
different arc count for a module, investigate the arc difference — do **not**
lower a floor to make the suite green (ADR-068 "Do Not Interpret This As").
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import src.application.services.behavioral_probe_runner as runner_module
import src.application.services.setup_phase_detector as setup_phase_detector_module
import src.application.use_case.score_accum_use_case as score_accum_module
from src.application.services.behavioral_probe_runner import (
    compute_behavioral_probe_digest,
)
from src.application.services.behavioral_probe_set import (
    core_probe_set,
    extended_probe_set,
)
from src.application.services.engine_bootstrap.risk_config_resolvers import (
    resolve_risk_gates,
)
from src.application.services.setup_phase_config import SetupPhaseConfig
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.score_accum_use_case import AccumScorePolicy
from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.free_float_gate import FreeFloatGate
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.rules.liquidity_gate import LiquidityGate

_ROOT = Path(__file__).resolve().parents[3]

# The frozen core digests, asserted here as literals so the slice-2 diff itself
# proves the extended probes did not move identity (ADR-068 §3).
_FROZEN_CORE_BEHAVIORAL_DIGEST = "04ce202b41b30d8f1e7e9bcd36a853664c907668fbff8f8f1bb68aee3fd5398b"
_FROZEN_CORE_INPUT_DIGEST = "5be656d19d36c9369a6f08cd8d453288b74c6c36ddaee694f125fca0be6aa8f9"


# ── Coverage scope and floors ───────────────────────────────────────────────
#
# "The accum decision path" is bounded by what the probe runner actually drives:
# AccumulationScreenUseCase.execute and the decision-owning components beneath
# it. Diagnostic-only builders (sector context, sector macro, company quality,
# seasonality, analyst) are deliberately out of scope — under ADR-057 they carry
# no Action authority, so their branches cannot fork a cohort.
#
# Values are (branches_taken, branches_total) measured under the core+extended
# probe run. Both halves are enforced:
#   - taken must not fall      -> no coverage regression
#   - uncovered must not rise  -> new uncovered branches fail the build
_BRANCH_COVERAGE_FLOOR: dict[str, tuple[int, int]] = {
    "src/application/services/accumulation_candidate_enricher.py": (14, 32),
    "src/application/services/accumulation_candidate_evaluator.py": (23, 28),
    "src/application/services/accumulation_candidate_signal_assessor.py": (8, 12),
    "src/application/services/accumulation_candidate_structural_filter.py": (8, 10),
    "src/application/services/accumulation_risk_funnel.py": (0, 0),
    "src/application/services/accumulation_technical_features.py": (26, 34),
    "src/application/services/alpha_trigger_aggregator.py": (23, 40),
    "src/application/services/decision_policy.py": (32, 46),
    "src/application/services/flow_confirmation_evidence_builder.py": (33, 50),
    "src/application/services/primary_setup_family_resolver.py": (26, 48),
    "src/application/services/screen_assessment_pipeline.py": (18, 42),
    "src/application/services/setup_phase_detector.py": (25, 38),
    "src/application/services/setup_phase_readiness_evaluator.py": (7, 26),
    "src/application/services/setup_phase_volume_trigger.py": (13, 26),
    "src/application/services/signal_engine.py": (3, 30),
    "src/application/services/signal_evidence_group_scorer.py": (47, 66),
    "src/application/services/signal_legacy_regime_conditioning.py": (11, 16),
    "src/application/use_case/accumulation_screen_use_case.py": (15, 30),
    "src/application/use_case/assess_risk_gate_evaluator.py": (23, 30),
    "src/application/use_case/assess_risk_use_case.py": (1, 4),
    "src/application/use_case/assess_trade_setup_use_case.py": (12, 16),
    "src/application/use_case/score_accum_use_case.py": (19, 34),
    "src/domain/rules/bandar_gate.py": (4, 4),
    "src/domain/rules/free_float_gate.py": (4, 4),
    "src/domain/rules/fundamental_gate.py": (5, 6),
    "src/domain/rules/liquidity_gate.py": (8, 12),
    "src/domain/value_objects/accum_score_breakdown.py": (20, 36),
}

# Headline aggregate floor, in whole percent. Measured 59.44%.
_AGGREGATE_BRANCH_COVERAGE_FLOOR_PCT = 59

_COVERAGE_SUBPROCESS = """
import json
import os
import sys

import coverage

scope = json.loads(sys.argv[1])
cov = coverage.Coverage(branch=True, include=scope, data_file=None)
cov.start()
from src.application.services.behavioral_probe_runner import run_probe_set
from src.application.services.behavioral_probe_set import (
    core_probe_set,
    extended_probe_set,
)

run_probe_set(core_probe_set() + extended_probe_set())
cov.stop()

report = {}
for measured in cov.get_data().measured_files():
    analysis = cov._analyze(measured)
    stats = analysis.branch_stats()
    report[os.path.relpath(measured, os.getcwd())] = {
        "branches_total": sum(v[0] for v in stats.values()),
        "branches_taken": sum(v[1] for v in stats.values()),
        "statements_total": len(analysis.statements),
        "statements_missed": len(analysis.missing),
    }
print("<<<COVERAGE_JSON>>>" + json.dumps(report, sort_keys=True))
"""


def _measure_probe_branch_coverage() -> dict[str, dict[str, int]]:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _COVERAGE_SUBPROCESS,
            json.dumps(sorted(_BRANCH_COVERAGE_FLOOR)),
        ],
        cwd=_ROOT,
        env={**os.environ, "PYTHONHASHSEED": "12345"},
        capture_output=True,
        text=True,
        check=True,
    )
    marker = "<<<COVERAGE_JSON>>>"
    assert marker in result.stdout, result.stderr
    return json.loads(result.stdout.split(marker, 1)[1])


def test_branch_coverage_floor_over_the_accum_decision_path() -> None:
    """ADR-068 §5: enforced branch-coverage floor, not a hoped-for number."""
    report = _measure_probe_branch_coverage()

    missing = sorted(set(_BRANCH_COVERAGE_FLOOR) - set(report))
    assert missing == [], (
        "these accum decision-path modules were never executed by the probe run, "
        f"so their branches are unmeasured: {missing}"
    )

    regressions: list[str] = []
    for module, (floor_taken, floor_total) in sorted(_BRANCH_COVERAGE_FLOOR.items()):
        taken = report[module]["branches_taken"]
        total = report[module]["branches_total"]
        if taken < floor_taken:
            regressions.append(
                f"{module}: covered branches fell {floor_taken} -> {taken} "
                f"(of {total}); the probe set now measures less than it did"
            )
        if (total - taken) > (floor_total - floor_taken):
            regressions.append(
                f"{module}: uncovered branches rose "
                f"{floor_total - floor_taken} -> {total - taken}; a new branch "
                "in the accum decision path is unreachable by every probe, which "
                "is exactly the under-forking ADR-068 exists to prevent"
            )
    assert regressions == [], "\n".join(regressions)


def test_aggregate_branch_coverage_meets_the_recorded_floor() -> None:
    report = _measure_probe_branch_coverage()
    total = sum(row["branches_total"] for row in report.values())
    taken = sum(row["branches_taken"] for row in report.values())
    assert total > 0
    pct = 100.0 * taken / total
    assert pct >= _AGGREGATE_BRANCH_COVERAGE_FLOOR_PCT, (
        f"aggregate branch coverage over the accum decision path is {pct:.2f}% "
        f"({taken}/{total}), below the recorded floor of "
        f"{_AGGREGATE_BRANCH_COVERAGE_FLOOR_PCT}%. Raise coverage with an "
        "extended probe; do not lower the floor."
    )


def test_coverage_scope_is_not_quietly_shrunk() -> None:
    """A floor is only meaningful while the scope it covers stays honest."""
    assert len(_BRANCH_COVERAGE_FLOOR) == 27
    for module in _BRANCH_COVERAGE_FLOOR:
        assert (_ROOT / module).is_file(), f"scope module no longer exists: {module}"


# ── Mutation suite ──────────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class Mutant:
    """One deliberately planted behavioural change.

    ``apply`` mutates a production constant/comparison **transiently**, inside
    the test process only, via monkeypatch at a named injection seam. Nothing
    in ``src/`` changes permanently — this slice is NON_SEMANTIC.
    """

    name: str
    category: str
    apply: Callable[[pytest.MonkeyPatch], None]


def _risk_gate_mutant(name: str, gates_cfg: dict[str, Any]) -> Mutant:
    """Mutate a resolved risk gate through the production gate resolver."""

    def apply(monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            runner_module,
            "resolve_risk_gates",
            lambda _cfg: resolve_risk_gates({"risk_engine": {"gates": gates_cfg}}),
        )

    return Mutant(name=name, category="GATE_THRESHOLD", apply=apply)


def _signal_config_mutant(name: str, mutate: Callable[[SignalEngineConfig], Any]) -> Mutant:
    def apply(monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            runner_module, "SignalEngineConfig", lambda: mutate(SignalEngineConfig())
        )

    return Mutant(name=name, category="SIGNAL_CONSTANT", apply=apply)


def _accum_policy_mutant(name: str, mutate: Callable[[AccumScorePolicy], Any]) -> Mutant:
    def apply(monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            score_accum_module, "AccumScorePolicy", lambda: mutate(AccumScorePolicy())
        )

    return Mutant(name=name, category="ACCUM_WEIGHT", apply=apply)


def _setup_phase_mutant(name: str, mutate: Callable[[SetupPhaseConfig], Any]) -> Mutant:
    def apply(monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            setup_phase_detector_module,
            "SetupPhaseConfig",
            lambda: mutate(SetupPhaseConfig()),
        )

    return Mutant(name=name, category="PHASE_THRESHOLD", apply=apply)


def _gate_verdict_inversion(name: str, gate_class: type) -> Mutant:
    """Flip a gate's comparison direction by inverting its verdict.

    ``triggered = not triggered`` is exactly what flipping the gate's threshold
    comparison operator produces, without rewriting the gate's arithmetic.
    """

    def apply(monkeypatch: pytest.MonkeyPatch) -> None:
        original = gate_class.evaluate

        def inverted(self: Any, context: Any) -> Any:
            result = original(self, context)
            return dataclasses.replace(result, triggered=not result.triggered)

        monkeypatch.setattr(gate_class, "evaluate", inverted)

    return Mutant(name=name, category="COMPARISON_FLIP", apply=apply)


def _replace(obj: Any, **changes: Any) -> Any:
    return dataclasses.replace(obj, **changes)


_MUTANTS: tuple[Mutant, ...] = (
    # ── Risk gates: thresholds, enablement, missing-data direction ──────────
    _risk_gate_mutant("gate.fundamental.piotroski_min:3->9", {"fundamental": {"piotroski_min": 9}}),
    _risk_gate_mutant("gate.fundamental.piotroski_min:3->0", {"fundamental": {"piotroski_min": 0}}),
    _risk_gate_mutant("gate.fundamental.enabled:true->false", {"fundamental": {"enabled": False}}),
    _risk_gate_mutant(
        "gate.fundamental.triggered_confidence:100->40",
        {"fundamental": {"triggered_confidence": 40}},
    ),
    _risk_gate_mutant(
        "gate.liquidity.market_cap_floor_idr:1T->100T",
        {"liquidity": {"market_cap_floor_idr": 100_000_000_000_000}},
    ),
    _risk_gate_mutant(
        "gate.liquidity.median_tx_floor_idr:5B->500T",
        {"liquidity": {"median_tx_floor_idr": 500_000_000_000_000}},
    ),
    _risk_gate_mutant("gate.liquidity.lookback_days:20->3", {"liquidity": {"lookback_days": 3}}),
    _risk_gate_mutant(
        "gate.liquidity.missing_data_action:skip->trigger",
        {"liquidity": {"missing_data_action": "trigger"}},
    ),
    _risk_gate_mutant("gate.liquidity.enabled:true->false", {"liquidity": {"enabled": False}}),
    _risk_gate_mutant(
        "gate.free_float.min_free_float_pct:15->100.5",
        {"free_float": {"min_free_float_pct": 100.5}},
    ),
    _risk_gate_mutant("gate.free_float.enabled:true->false", {"free_float": {"enabled": False}}),
    _risk_gate_mutant(
        "gate.bandar.distribution_labels:dist->accum",
        {"bandar": {"distribution_labels": ["Small Accum", "Big Accum"]}},
    ),
    _risk_gate_mutant("gate.bandar.enabled:true->false", {"bandar": {"enabled": False}}),
    _risk_gate_mutant(
        "gate.bandar.triggered_confidence:80->10", {"bandar": {"triggered_confidence": 10}}
    ),
    # ── Gate comparison-direction flips ─────────────────────────────────────
    _gate_verdict_inversion("comparison.FundamentalGate.verdict_inverted", FundamentalGate),
    _gate_verdict_inversion("comparison.LiquidityGate.verdict_inverted", LiquidityGate),
    _gate_verdict_inversion("comparison.FreeFloatGate.verdict_inverted", FreeFloatGate),
    _gate_verdict_inversion("comparison.BandarGate.verdict_inverted", BandarGate),
    # ── Signal engine scoring constants ─────────────────────────────────────
    _signal_config_mutant(
        "signal.classification.strong_min_score:70->50",
        lambda c: _replace(c, classification=_replace(c.classification, strong_min_score=50)),
    ),
    _signal_config_mutant(
        "signal.classification.moderate_min_score:45->80",
        lambda c: _replace(c, classification=_replace(c.classification, moderate_min_score=80)),
    ),
    _signal_config_mutant(
        "signal.evidence_groups.flow_confirmation.weight:x3",
        lambda c: _replace(
            c,
            evidence_groups=_replace(
                c.evidence_groups,
                flow_confirmation=_replace(
                    c.evidence_groups.flow_confirmation,
                    weight=c.evidence_groups.flow_confirmation.weight * 3.0,
                ),
            ),
        ),
    ),
    _signal_config_mutant(
        "signal.evidence_groups.setup_quality.weight:->0",
        lambda c: _replace(
            c,
            evidence_groups=_replace(
                c.evidence_groups,
                setup_quality=_replace(c.evidence_groups.setup_quality, weight=0.0),
            ),
        ),
    ),
    _signal_config_mutant(
        "signal.decision_policy.regime_confidence_min_enter:0.35->0.99",
        lambda c: _replace(
            c, decision_policy=_replace(c.decision_policy, regime_confidence_min_enter=0.99)
        ),
    ),
    _signal_config_mutant(
        "signal.decision_policy.NEUTRAL.watch_threshold:45->95",
        lambda c: _replace(
            c,
            decision_policy=_replace(
                c.decision_policy,
                regime_policy={
                    **c.decision_policy.regime_policy,
                    "NEUTRAL": _replace(
                        c.decision_policy.regime_policy["NEUTRAL"], watch_threshold=95
                    ),
                },
            ),
        ),
    ),
    _signal_config_mutant(
        "signal.decision_policy.RISK_ON.enter_allowed:true->false",
        lambda c: _replace(
            c,
            decision_policy=_replace(
                c.decision_policy,
                regime_policy={
                    **c.decision_policy.regime_policy,
                    "RISK_ON": _replace(
                        c.decision_policy.regime_policy["RISK_ON"], enter_allowed=False
                    ),
                },
            ),
        ),
    ),
    _signal_config_mutant(
        "signal.regime_conditioning.neutral.weak_flow_threshold:50->99",
        lambda c: _replace(
            c,
            regime_conditioning=_replace(
                c.regime_conditioning,
                neutral=_replace(c.regime_conditioning.neutral, weak_flow_threshold=99.0),
            ),
        ),
    ),
    _signal_config_mutant(
        "signal.regime_conditioning.volatile.flow_discount:0.80->0.10",
        lambda c: _replace(
            c,
            regime_conditioning=_replace(
                c.regime_conditioning,
                volatile=_replace(c.regime_conditioning.volatile, flow_discount=0.10),
            ),
        ),
    ),
    _signal_config_mutant(
        "signal.regime_conditioning.risk_off.weak_setup_discount:0.50->0.05",
        lambda c: _replace(
            c,
            regime_conditioning=_replace(
                c.regime_conditioning,
                risk_off=_replace(c.regime_conditioning.risk_off, weak_setup_discount=0.05),
            ),
        ),
    ),
    _signal_config_mutant(
        "signal.alpha_trigger.low_weight_cap:0.10->0.90",
        lambda c: _replace(c, alpha_trigger=_replace(c.alpha_trigger, low_weight_cap=0.90)),
    ),
    _signal_config_mutant(
        "signal.alpha_trigger.enabled:true->false",
        lambda c: _replace(c, alpha_trigger=_replace(c.alpha_trigger, enabled=False)),
    ),
    _signal_config_mutant(
        "signal.flags.valuation_stretched.score_penalty:10->60",
        lambda c: _replace(
            c,
            flags=_replace(
                c.flags,
                valuation_stretched=_replace(c.flags.valuation_stretched, score_penalty=60),
            ),
        ),
    ),
    _signal_config_mutant(
        "signal.input_mapping.accum_score.max_score:100->50",
        lambda c: _replace(
            c,
            input_mapping=_replace(
                c.input_mapping,
                accum_score=_replace(c.input_mapping.accum_score, max_score=50.0),
            ),
        ),
    ),
    # ── Accum score policy weights and saturation constants ─────────────────
    _accum_policy_mutant("accum.max_score:100->60", lambda p: _replace(p, max_score=60.0)),
    _accum_policy_mutant(
        "accum.consistency.weight:33.3->5",
        lambda p: _replace(p, consistency=_replace(p.consistency, weight=5.0)),
    ),
    # Weight 0 is rejected by the AccumScoreBreakdown domain invariant
    # (AVAILABLE components require max_points > 0), so weight mutations shrink
    # rather than zero the component.
    _accum_policy_mutant(
        "accum.streak.weight:25->3",
        lambda p: _replace(p, streak=_replace(p.streak, weight=3.0)),
    ),
    _accum_policy_mutant(
        "accum.vwap_discount.weight:16.7->2",
        lambda p: _replace(p, vwap_discount=_replace(p.vwap_discount, weight=2.0)),
    ),
    _accum_policy_mutant(
        "accum.vwap_discount.saturate_at:10->1",
        lambda p: _replace(p, vwap_discount=_replace(p.vwap_discount, saturate_at=1.0)),
    ),
    _accum_policy_mutant(
        "accum.rsi_headroom.weight:8.3->40",
        lambda p: _replace(p, rsi_headroom=_replace(p.rsi_headroom, weight=40.0)),
    ),
    _accum_policy_mutant(
        "accum.foreign_flow_ratio.saturate_at:20->2",
        lambda p: _replace(p, foreign_flow_ratio=_replace(p.foreign_flow_ratio, saturate_at=2.0)),
    ),
    _accum_policy_mutant(
        "accum.bb_squeeze.enabled:false->true",
        lambda p: _replace(p, bb_squeeze=_replace(p.bb_squeeze, enabled=True)),
    ),
    # ── Setup-phase detection thresholds ────────────────────────────────────
    _setup_phase_mutant(
        "phase.thresholds.compression_max_bb_width_pctile:0.20->0.90",
        lambda c: _replace(
            c, thresholds=_replace(c.thresholds, compression_max_bb_width_pctile=0.90)
        ),
    ),
    _setup_phase_mutant(
        "phase.thresholds.exhaustion_rsi_min:72->30",
        lambda c: _replace(c, thresholds=_replace(c.thresholds, exhaustion_rsi_min=30.0)),
    ),
    _setup_phase_mutant(
        "phase.thresholds.exhaustion_min_price_extension_pct:8->0.1",
        lambda c: _replace(
            c, thresholds=_replace(c.thresholds, exhaustion_min_price_extension_pct=0.1)
        ),
    ),
    _setup_phase_mutant(
        "phase.thresholds.distribution_min_bandar_score:-4->9",
        lambda c: _replace(c, thresholds=_replace(c.thresholds, distribution_min_bandar_score=9)),
    ),
    _setup_phase_mutant(
        "phase.volume_trigger.min_valid_20d_sessions:18->200",
        lambda c: _replace(
            c, volume_trigger=_replace(c.volume_trigger, min_valid_20d_sessions=200)
        ),
    ),
)


# Mutants proven (by this suite) not to move the **core** identity digest.
# ADR-068 §5: a surviving mutant is a named, fixable hole, not something to
# wave through. Each entry states why it survives and what would close it.
#
# Every survivor below is a *hole in the frozen core probe inputs*, not a
# defect in production code and not a licence to change one. Closing any of
# them requires a new or changed **core** probe, which is a deliberate cohort
# boundary under ADR-068 §3 and therefore out of scope for slice 2. Adding an
# extended probe would make the constant measurable but would still not fork
# identity, so it does not close the hole.
_SURVIVING_MUTANTS: dict[str, str] = {
    "gate.liquidity.lookback_days:20->3": (
        "Every probe ticker uses a constant per-session volume, so the median "
        "20-day transaction value is identical for any lookback window. Closing "
        "this needs a core probe with a varying volume series."
    ),
    "gate.liquidity.missing_data_action:skip->trigger": (
        "No core probe reaches LiquidityGate's missing-market-cap branch: the "
        "enrichment-free probe still supplies candles, so the gate resolves on "
        "median transaction value before the missing-data action applies. "
        "Closing this needs a core probe with candles but no market cap."
    ),
    "signal.evidence_groups.setup_quality.weight:->0": (
        "The setup_quality evidence group carries no evidence on the "
        "screen-accum surface, so its weight cannot change a score. This is the "
        "same emptiness ADR-067 retires; expect this mutant to be deleted with "
        "the group rather than closed by a probe."
    ),
    "signal.decision_policy.regime_confidence_min_enter:0.35->0.99": (
        "The ENTER-confidence cap reads MarketContext regime *stability*, which "
        "no core probe supplies (probes set regime and conviction only). "
        "Closing this needs a core probe carrying a stability value."
    ),
    "signal.regime_conditioning.volatile.flow_discount:0.80->0.10": (
        "The VOLATILE flow discount only applies to flow evidence classified "
        "weak by weak_flow_threshold; no core probe lands a candidate in that "
        "band under VOLATILE. Closing this needs a core probe tuned into it."
    ),
    "signal.regime_conditioning.risk_off.weak_setup_discount:0.50->0.05": (
        "The RISK_OFF setup discount applies only to PARTIAL/NO_MATCH setup "
        "evidence, and no core probe attaches a setup family at all — see the "
        "setup-family hole below. Closing this needs a core probe with a "
        "resolved, partially-matched setup family."
    ),
    "signal.alpha_trigger.low_weight_cap:0.10->0.90": (
        "Alpha-trigger aggregation runs on the screen-accum path but its output "
        "is not part of the projected Accum/Signal/Risk/Action decision surface "
        "(ADR-068 §2). Before treating this as a hole, confirm whether alpha "
        "trigger has any Action authority on this surface; if it has none, this "
        "is an equivalent mutant rather than an identity gap."
    ),
    "signal.alpha_trigger.enabled:true->false": (
        "Same as low_weight_cap: disabling alpha triggers changes no projected "
        "decision field. Needs the same authority confirmation."
    ),
    "signal.flags.valuation_stretched.score_penalty:10->60": (
        "Signal flags require forward-estimate/analyst/insider evidence that no "
        "core probe supplies, so no flag ever fires and no penalty applies. "
        "Closing this needs a core probe carrying that evidence."
    ),
    "signal.input_mapping.accum_score.max_score:100->50": (
        "The accum-score input mapping is not consumed by the screen-accum "
        "signal path; the assessor passes the already-scored breakdown. Confirm "
        "whether this config is live on any surface before treating it as a gap."
    ),
    "accum.vwap_discount.saturate_at:10->1": (
        "Every core probe's VWAP discount already sits at or beyond the "
        "saturation point, so lowering the saturation ceiling cannot change the "
        "awarded points. Closing this needs a core probe in the linear band. "
        "(The paired vwap_discount.weight mutant IS caught, so the component "
        "itself is measured.)"
    ),
    "phase.thresholds.compression_max_bb_width_pctile:0.20->0.90": (
        "Bollinger band-width percentile is unavailable for every core probe "
        "(bb_squeeze is disabled in the default AccumScorePolicy), so the "
        "compression threshold is never compared. Closing this needs a core "
        "probe supplying a band-width percentile."
    ),
    "phase.thresholds.exhaustion_rsi_min:72->30": (
        "No core probe's RSI reaches the exhaustion band; the EXHAUSTION phase "
        "is instead reached through price extension, whose threshold mutant IS "
        "caught. Closing this needs a core probe with an overbought RSI."
    ),
    "phase.volume_trigger.min_valid_20d_sessions:18->200": (
        "Volume-trigger validity requires trusted benchmark volume provenance "
        "that the frozen in-memory candles do not carry, so the session-count "
        "requirement is never evaluated. Closing this needs a core probe with "
        "provenance-bearing volume."
    ),
}


def _mutant_ids() -> list[str]:
    return [mutant.name for mutant in _MUTANTS]


@pytest.fixture(scope="module")
def baseline_core_digest() -> str:
    digest = compute_behavioral_probe_digest()
    assert digest == _FROZEN_CORE_BEHAVIORAL_DIGEST
    return digest


def test_mutant_names_are_unique() -> None:
    names = _mutant_ids()
    assert len(names) == len(set(names))
    assert set(_SURVIVING_MUTANTS) <= set(names), (
        "a recorded survivor no longer exists as a planted mutant; remove the "
        "record deliberately rather than leaving a stale rationale"
    )


@pytest.mark.parametrize("mutant", _MUTANTS, ids=_mutant_ids())
def test_planted_mutant_moves_the_behavioural_digest(
    mutant: Mutant, baseline_core_digest: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every planted mutant must fork the cohort, or be a recorded survivor."""
    with monkeypatch.context() as patch:
        mutant.apply(patch)
        mutated = compute_behavioral_probe_digest()

    if mutant.name in _SURVIVING_MUTANTS:
        assert mutated == baseline_core_digest, (
            f"{mutant.name} is recorded as a surviving mutant but now moves the "
            "core digest. The hole is closed — delete its entry from "
            "_SURVIVING_MUTANTS instead of leaving a false record."
        )
        return

    assert mutated != baseline_core_digest, (
        f"{mutant.name} did not move the behavioural probe digest. The core "
        "probe set cannot see this scoring/gate change, so two behaviourally "
        "different engines would share one cohort. Either add an extended "
        "probe and promote it to core (a deliberate cohort boundary), or "
        "record it in _SURVIVING_MUTANTS with a rationale. Do not delete "
        "this mutant."
    )


def test_mutations_are_transient_and_leave_production_behaviour_unchanged() -> None:
    """NON_SEMANTIC guarantee: nothing in src/ is permanently mutated."""
    assert compute_behavioral_probe_digest() == _FROZEN_CORE_BEHAVIORAL_DIGEST


def test_adding_extended_probes_left_the_frozen_core_digests_unchanged() -> None:
    """ADR-068 §3: an extended probe must never move identity."""
    from src.application.services.behavioral_probe_runner import compute_probe_input_digest

    assert extended_probe_set(), "slice 2 must actually add extended probes"
    assert compute_behavioral_probe_digest() == _FROZEN_CORE_BEHAVIORAL_DIGEST
    assert compute_probe_input_digest() == _FROZEN_CORE_INPUT_DIGEST

    combined = compute_behavioral_probe_digest(core_probe_set() + extended_probe_set())
    assert combined != _FROZEN_CORE_BEHAVIORAL_DIGEST, (
        "the extended probes must actually measure something the core set does not"
    )
