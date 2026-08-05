"""ADR-068 behavioural probe harness gate.

Frozen synthetic probe set under tests/fixtures/ with a SHA-256 sidecar.
Proves: the fixture is unmodified, the probe-set contract (ids/counts/
projection version) matches what ``behavioral_probe_set`` and
``behavioral_probe_runner`` currently declare, the frozen input and
behavioural output digests are reproducible bit-for-bit within a process,
across processes, and independent of hash randomisation, that a probe run
performs no clock/network/database/filesystem IO, that every core probe
supplies its own ``as_of_date`` (so the ``date.today()`` fallback is
structurally unreachable), that the frozen probe ports fail closed on any
write, that the core probe set actually exercises the accum decision
surface named in ADR-068 Section 2, that the extended probe set stays
disjoint from core and never enters identity, that every declared probe
input — enrichment stubs and flat ``BehavioralProbe`` fields alike — is
folded into the input digest, and that deliberately mutating a frozen
threshold moves the digest.

The digests here are read from the fixture, never hardcoded, so a
deliberate core-set change is a one-file fixture regeneration reviewed
alongside the probe diff. The literal digests live in
``test_behavioral_probe_coverage_and_mutation`` so a moved identity is
visible in review.
"""

from __future__ import annotations

import builtins
import dataclasses
import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from typing import NoReturn, get_args, get_type_hints

import pytest

import src.application.services.behavioral_probe_runner as runner_module
from src.application.services.behavioral_probe_runner import (
    PROBE_PROJECTION_CONTRACT,
    FrozenProbeBrokerRepository,
    FrozenProbeMarketRepository,
    ProbeIOForbiddenError,
    ProbeRulesLoader,
    build_probe_request,
    compute_behavioral_probe_digest,
    compute_probe_input_digest,
    run_probe_set,
)
from src.application.services.behavioral_probe_set import (
    CORE_PROBE_SET_ID,
    EXTENDED_PROBE_SET_ID,
    BehavioralProbe,
    ProbeEnrichmentStub,
    ProbeForwardEstimates,
    ProbeTicker,
    core_probe_set,
    extended_probe_set,
    probe_input_fields,
)
from src.application.services.engine_bootstrap.risk_config_resolvers import (
    resolve_risk_gates,
)
from src.application.services.signal_engine_config import (
    SignalClassificationConfig,
    SignalEngineConfig,
)

_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE = _ROOT / "tests" / "fixtures" / "behavioral_probe_core.v1.json"
_SHA = _ROOT / "tests" / "fixtures" / "behavioral_probe_core.v1.sha256"


def _load_fixture() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _forbidden(*args: object, **kwargs: object) -> NoReturn:
    raise AssertionError("probe run attempted forbidden IO")


def test_fixture_sha256_matches_sidecar() -> None:
    digest = hashlib.sha256(_FIXTURE.read_bytes()).hexdigest()
    recorded = _SHA.read_text(encoding="utf-8").strip().split()[0]
    assert digest == recorded


def test_fixture_records_the_current_probe_set_contract() -> None:
    fixture = _load_fixture()
    assert fixture["core_probe_set_id"] == CORE_PROBE_SET_ID
    assert fixture["extended_probe_set_id"] == EXTENDED_PROBE_SET_ID
    assert fixture["projection_contract"] == PROBE_PROJECTION_CONTRACT
    assert fixture["core_probe_count"] == len(core_probe_set())
    assert fixture["extended_probe_count"] == len(extended_probe_set())
    assert fixture["core_probe_ids"] == [p.probe_id for p in core_probe_set()]
    assert fixture["extended_probe_ids"] == [p.probe_id for p in extended_probe_set()]


def test_core_probe_ids_are_unique() -> None:
    core_ids = [p.probe_id for p in core_probe_set()]
    assert len(core_ids) == len(set(core_ids))
    combined_ids = [p.probe_id for p in core_probe_set() + extended_probe_set()]
    assert len(combined_ids) == len(set(combined_ids))


def test_probe_input_digest_matches_frozen_fixture() -> None:
    fixture = _load_fixture()
    assert compute_probe_input_digest() == fixture["probe_input_digest"], (
        "probe input digest drifted from the frozen fixture — this means the "
        "frozen probe INPUTS changed (a probe-set authoring change), not that "
        "engine behaviour changed"
    )


def test_behavioral_probe_digest_matches_frozen_fixture() -> None:
    fixture = _load_fixture()
    assert compute_behavioral_probe_digest() == fixture["behavioral_probe_digest"], (
        "behavioural probe digest drifted while the input digest is unchanged — "
        "this means the accum decision path changed behaviour"
    )


def test_repeat_run_in_one_process_is_bit_identical() -> None:
    first = run_probe_set()
    second = run_probe_set()
    assert first == second

    digest_one = compute_behavioral_probe_digest()
    digest_two = compute_behavioral_probe_digest()
    assert digest_one == digest_two


def test_cross_process_digest_is_identical() -> None:
    fixture = _load_fixture()
    script = (
        "from src.application.services.behavioral_probe_runner import "
        "compute_behavioral_probe_digest\n"
        "print(compute_behavioral_probe_digest())\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_ROOT,
        env={**os.environ, "PYTHONHASHSEED": "12345"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == fixture["behavioral_probe_digest"], result.stderr


def test_probe_run_performs_no_clock_network_database_or_filesystem_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Warm every lazy import first — module import is not probe IO.
    warm = compute_behavioral_probe_digest()

    # Patching time.time blocks datetime.date.today() in CPython, which is the
    # only clock fallback in AccumulationScreenUseCase.execute.
    monkeypatch.setattr(time, "time", _forbidden)
    monkeypatch.setattr(socket, "socket", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)
    monkeypatch.setattr(sqlite3, "connect", _forbidden)
    monkeypatch.setattr(builtins, "open", _forbidden)
    monkeypatch.setattr(Path, "open", _forbidden)
    monkeypatch.setattr(Path, "read_text", _forbidden)
    monkeypatch.setattr(Path, "read_bytes", _forbidden)
    monkeypatch.setattr(os, "open", _forbidden)

    patched = compute_behavioral_probe_digest()
    assert patched == warm

    # Honest limitation: datetime.datetime.now() is not interceptable this
    # way. It is instead covered by the repeat-run and cross-process
    # determinism tests above — a wall-clock-dependent output could not stay
    # stable across those.


def test_every_core_probe_supplies_its_own_as_of_date() -> None:
    for probe in core_probe_set():
        request = build_probe_request(probe)
        assert request.as_of_date is not None
        assert request.as_of_date == probe.as_of_date


def test_frozen_probe_ports_reject_writes() -> None:
    market_repository = FrozenProbeMarketRepository(())
    with pytest.raises(ProbeIOForbiddenError):
        market_repository.save_candles([])

    broker_repository = FrozenProbeBrokerRepository((), ())
    with pytest.raises(ProbeIOForbiddenError):
        broker_repository.save_broker_summary(None)  # type: ignore[arg-type]
    with pytest.raises(ProbeIOForbiddenError):
        broker_repository.save_broker_summaries([])
    with pytest.raises(ProbeIOForbiddenError):
        broker_repository.save_broker_daily_flows([])

    with pytest.raises(ProbeIOForbiddenError):
        ProbeRulesLoader().load()
    with pytest.raises(ProbeIOForbiddenError):
        ProbeRulesLoader().load_from_string("")


def test_core_probe_set_covers_the_accum_decision_surface() -> None:
    projections = run_probe_set()

    actions: set[str | None] = set()
    risk_gate_names: set[str | None] = set()
    entry_qualities: set[str | None] = set()
    signal_strengths: set[str | None] = set()
    setup_phases: set[str | None] = set()
    bci_labels: set[str] = set()
    trends: set[str] = set()
    screen_results: set[str] = set()
    authority_coverage: set[float | None] = set()
    any_not_evaluated = False
    any_skipped = False

    for projection in projections.values():
        if projection["not_evaluated"]:
            any_not_evaluated = True
        if projection["tickers_skipped"] > 0:
            any_skipped = True
        screen_results.update(projection["screen_results"].values())
        for candidate in projection["candidates"].values():
            actions.add(candidate["action"])
            risk_gate_names.add(candidate["risk_gate_triggered"])
            entry_qualities.add(candidate["entry_quality"])
            signal_strengths.add(candidate["signal_strength"])
            setup_phases.add(candidate["setup_phase"])
            bci_labels.add(candidate["bci_label"])
            trends.add(candidate["trend"])
            authority_coverage.add(candidate["signal_authority_coverage"])

    expected_actions = {
        "ENTER",
        "WATCH",
        "AVOID",
        "BLOCKED_EXECUTION",
        "BLOCKED_STRUCTURAL",
    }
    assert expected_actions <= actions, f"missing actions: {expected_actions - actions}"

    expected_gates = {"FundamentalGate", "LiquidityGate", "FreeFloatGate", "BandarGate", None}
    assert expected_gates <= risk_gate_names, (
        f"missing risk gate names: {expected_gates - risk_gate_names}"
    )

    expected_entry_qualities = {"ENTER", "WATCH", "AVOID"}
    assert expected_entry_qualities <= entry_qualities, (
        f"missing entry qualities: {expected_entry_qualities - entry_qualities}"
    )

    expected_signal_strengths = {"STRONG", "MODERATE", "WEAK"}
    assert expected_signal_strengths <= signal_strengths, (
        f"missing signal strengths: {expected_signal_strengths - signal_strengths}"
    )

    expected_setup_phases = {
        "ACCUMULATION",
        "COMPRESSION",
        "DISTRIBUTION",
        "EXHAUSTION",
        "NONE",
    }
    assert expected_setup_phases <= setup_phases, (
        f"missing setup phases: {expected_setup_phases - setup_phases}"
    )

    expected_bci_labels = {"CLUSTER", "STABLE", "RETAIL-LED"}
    assert expected_bci_labels <= bci_labels, (
        f"missing BCI labels: {expected_bci_labels - bci_labels}"
    )

    expected_trends = {"UP", "SIDE", "DOWN"}
    assert expected_trends <= trends, f"missing trends: {expected_trends - trends}"

    expected_screen_results = {"pass", "rejected_flow", "rejected_signal"}
    assert expected_screen_results <= screen_results, (
        f"missing screen results: {expected_screen_results - screen_results}"
    )

    assert 0.0 in authority_coverage
    assert 1.0 in authority_coverage

    assert any_not_evaluated or any_skipped, (
        "expected at least one probe to exercise the evaluator skip path via "
        "a non-empty not_evaluated list or tickers_skipped > 0"
    )


def test_extended_probes_do_not_change_core_identity() -> None:
    extended = extended_probe_set()
    assert extended, "an empty extended set measures nothing"
    core_ids = {probe.probe_id for probe in core_probe_set()}
    assert not (core_ids & {probe.probe_id for probe in extended})

    # The extended set runs, produces its own projections, and none of that
    # reaches the identity digest, which is computed over the core set alone.
    extended_projections = run_probe_set(extended)
    assert set(extended_projections) == {probe.probe_id for probe in extended}

    extra = dataclasses.replace(core_probe_set()[0], probe_id="extended_smoke")
    augmented = core_probe_set() + (extra,)
    assert compute_behavioral_probe_digest(augmented) != compute_behavioral_probe_digest()

    fixture = _load_fixture()
    assert compute_behavioral_probe_digest() == fixture["behavioral_probe_digest"]

    with pytest.raises(ValueError):
        run_probe_set(core_probe_set() + (core_probe_set()[0],))


def test_digest_moves_when_a_frozen_threshold_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = _load_fixture()
    frozen_digest = fixture["behavioral_probe_digest"]

    with monkeypatch.context() as patch_signal:
        patch_signal.setattr(
            runner_module,
            "SignalEngineConfig",
            lambda: dataclasses.replace(
                SignalEngineConfig(),
                classification=SignalClassificationConfig(strong_min_score=50),
            ),
        )
        assert compute_behavioral_probe_digest() != frozen_digest

    with monkeypatch.context() as patch_risk:
        patch_risk.setattr(
            runner_module,
            "resolve_risk_gates",
            lambda cfg: resolve_risk_gates(
                {"risk_engine": {"gates": {"fundamental": {"piotroski_min": 9}}}}
            ),
        )
        assert compute_behavioral_probe_digest() != frozen_digest

    assert compute_behavioral_probe_digest() == frozen_digest


_PROBE_MODULES = (
    "src.application.services.behavioral_probe_set",
    "src.application.services.behavioral_probe_runner",
)


def test_probe_digest_is_not_wired_into_cohort_identity_yet() -> None:
    """ADR-068 Section 7 trust ordering: the digest must stay non-authoritative.

    Slice 1 introduces the measurement only. Making it identity-material before
    the slice-2 coverage/mutation gate proves the probe set detects deliberate
    scoring changes would be strictly worse than today's proxies. This guard is
    expected to be updated deliberately by slices 3 and 4 — never silently.
    """
    importers: list[str] = []
    for path in sorted((_ROOT / "src").rglob("*.py")):
        relative = path.relative_to(_ROOT / "src").with_suffix("")
        module = "src." + relative.as_posix().replace("/", ".")
        if module in _PROBE_MODULES:
            continue
        source = path.read_text(encoding="utf-8")
        if any(probe_module in source for probe_module in _PROBE_MODULES):
            importers.append(module)

    assert importers == [], (
        "the behavioural probe harness must not be consumed by production code "
        f"in slice 1, but these modules reference it: {importers}"
    )

    identity_source = (
        _ROOT / "src" / "application" / "services" / "lean_observation_identity.py"
    ).read_text(encoding="utf-8")
    assert "behavioral_probe" not in identity_source
    assert "probe_digest" not in identity_source


def _valuation_probe() -> BehavioralProbe:
    return next(p for p in core_probe_set() if p.probe_id == "signal_flag_valuation_stretched")


def _mutated_probe_set(index: int, **changes: object) -> tuple[BehavioralProbe, ...]:
    """One-probe set with a single ProbeTicker field replaced."""
    probe = _valuation_probe()
    tickers = list(probe.tickers)
    tickers[index] = dataclasses.replace(tickers[index], **changes)
    return (dataclasses.replace(probe, tickers=tuple(tickers)),)


@pytest.mark.parametrize(
    ("field_name", "changes"),
    [
        pytest.param("fundamentals", {"piotroski_f_score": 3}, id="fundamentals"),
        pytest.param("shareholding", {"institution_pct": 57.0}, id="shareholding"),
        pytest.param("bandar", {"five_day_accdist": "Big Dist"}, id="bandar"),
        pytest.param("forward_estimates", {"forward_eps_1y": 21.0}, id="forward_estimates"),
    ],
)
def test_input_digest_covers_every_enrichment_stub_field(
    field_name: str, changes: dict[str, object]
) -> None:
    """Every enrichment stub field must move the input digest on its own.

    Before ADR-068's enrichment-stub fold-in, editing fundamentals,
    shareholding, bandar, or forward_estimates left
    ``compute_probe_input_digest`` untouched — an enrichment-only probe edit
    was indistinguishable from an engine change.
    """
    baseline = compute_probe_input_digest((_valuation_probe(),))
    original_stub = getattr(_valuation_probe().tickers[1], field_name)
    mutated_stub = dataclasses.replace(original_stub, **changes)
    mutated = _mutated_probe_set(1, **{field_name: mutated_stub})
    assert compute_probe_input_digest(mutated) != baseline


def test_declaring_a_previously_absent_stub_moves_the_input_digest() -> None:
    """Presence/absence of a stub is itself input.

    PRBA (index 0) carries no ``forward_estimates`` stub. Wiring one for the
    first time must move the input digest exactly as changing a value on an
    already-declared stub does — a field appearing is as much a probe-input
    change as a field's value changing.
    """
    baseline = compute_probe_input_digest((_valuation_probe(),))
    mutated = _mutated_probe_set(0, forward_estimates=ProbeForwardEstimates(forward_eps_1y=25.0))
    assert compute_probe_input_digest(mutated) != baseline


def test_enrichment_only_change_that_moves_output_also_moves_the_input_digest() -> None:
    """ADR-068 Section 2 attribution contract.

    Both digests moving reads as "the probe's own test data changed"; before
    the fix, an enrichment edit that also changed the OUTPUT moved only the
    behavioural digest, which read as "the engine changed" — a false
    attribution. forward_eps_1y=100.0 pushes PRBN's derived forward P/E back
    under the frozen valuation_stretched threshold, so the flag genuinely
    un-fires and the output changes too.
    """
    baseline = (_valuation_probe(),)
    original_forward = _valuation_probe().tickers[1].forward_estimates
    assert original_forward is not None
    mutated = _mutated_probe_set(
        1, forward_estimates=dataclasses.replace(original_forward, forward_eps_1y=100.0)
    )
    assert compute_probe_input_digest(mutated) != compute_probe_input_digest(baseline)
    assert compute_behavioral_probe_digest(mutated) != compute_behavioral_probe_digest(baseline)


def test_input_digest_still_moves_for_already_covered_inputs() -> None:
    """Sanity: widening the hash to cover stubs must not regress prior coverage."""
    baseline = compute_probe_input_digest((_valuation_probe(),))
    original_prbn = _valuation_probe().tickers[1]

    candle_mutated = _mutated_probe_set(1, base_price=original_prbn.base_price + 1)
    assert compute_probe_input_digest(candle_mutated) != baseline

    broker_mutated = _mutated_probe_set(1, foreign_buy_lot=original_prbn.foreign_buy_lot + 1)
    assert compute_probe_input_digest(broker_mutated) != baseline

    knob_mutated = (dataclasses.replace(_valuation_probe(), window_days=5),)
    assert compute_probe_input_digest(knob_mutated) != baseline


# One materially different value per BehavioralProbe field, used to prove each
# field on its own moves the input digest. Asserted below to be exhaustive over
# ``dataclasses.fields(BehavioralProbe)``, so a newly declared field fails this
# suite until it is proven covered rather than silently escaping the hash.
_PROBE_FIELD_MUTATIONS: dict[str, object] = {
    "probe_id": "mutated_probe_id",
    "surface": "mutated surface description",
    "tickers": None,  # filled in per-probe below: a strict subset of the real tuple
    "as_of_date": date(2026, 6, 18),
    "window_days": 5,
    "min_net_buy_days": 3,
    "min_accum_score": 1.5,
    "min_accum_score_enabled": False,
    "min_signal_score": 2.5,
    "min_signal_score_enabled": True,
    "min_market_cap_idr": 1_000,
    "min_piotroski": 2,
    "resistance_gate_enabled": False,
    "resistance_headroom_min_pct": 6.5,
    "regime": "RISK_ON",
    "regime_conviction": 0.55,
    "regime_signal_multiplier": 0.8,
    "regime_gate_tightening": True,
    "enrichment_providers_enabled": False,
    "source_availability_enabled": False,
    "swing_setup_families_enabled": True,
    "rsi_period": 9,
    "sma_period": 30,
    "extra_notes": ("mutated note",),
}


def test_probe_field_mutation_map_covers_every_behavioral_probe_field() -> None:
    """Guard the guard: the map below must stay exhaustive.

    Without this, adding a field to ``BehavioralProbe`` would leave the
    per-field digest test silently blind to it — the exact shape of the bug the
    structural sweep exists to prevent.
    """
    declared = {probe_field.name for probe_field in dataclasses.fields(BehavioralProbe)}
    assert set(_PROBE_FIELD_MUTATIONS) == declared, (
        "add an entry to _PROBE_FIELD_MUTATIONS for every new BehavioralProbe "
        f"field; missing: {declared - set(_PROBE_FIELD_MUTATIONS)}, "
        f"stale: {set(_PROBE_FIELD_MUTATIONS) - declared}"
    )


@pytest.mark.parametrize("field_name", sorted(_PROBE_FIELD_MUTATIONS))
def test_input_digest_moves_for_every_behavioral_probe_field(field_name: str) -> None:
    """Every declared probe field must move the input digest on its own.

    Slice 1 hashed candles, broker rows and a hand-listed subset of the request
    knobs; the enrichment-stub fix widened it structurally over ``ProbeTicker``
    but left the flat probe fields itemised, so ``rsi_period``, ``sma_period``,
    the three regime dimensions, ``source_availability_enabled``,
    ``swing_setup_families_enabled`` and ``extra_notes`` all sat outside the
    hash. Each can change what the engine is asked, so editing one moved the
    behavioural digest alone — reading as "the engine changed" (ADR-068 §2).
    """
    probe = _valuation_probe()
    value = _PROBE_FIELD_MUTATIONS[field_name]
    if field_name == "tickers":
        assert len(probe.tickers) > 1
        value = (probe.tickers[0],)
    assert value != getattr(probe, field_name), (
        f"the mutation for {field_name} equals its current value, so this test would pass vacuously"
    )

    baseline = compute_probe_input_digest((probe,))
    mutated = (dataclasses.replace(probe, **{field_name: value}),)
    assert compute_probe_input_digest(mutated) != baseline, (
        f"BehavioralProbe.{field_name} is not folded into the input digest"
    )


def test_probe_input_field_sweep_excludes_only_structurally_hashed_fields() -> None:
    """Pin the two deliberate exclusions so a third cannot be added quietly.

    ``probe_id`` keys the digest payload and ``tickers`` is expanded into
    candles/broker rows/enrichment stubs. Anything else dropped from the sweep
    would leave a real input outside the hash.
    """
    swept = {name for name, _ in probe_input_fields(_valuation_probe())}
    declared = {probe_field.name for probe_field in dataclasses.fields(BehavioralProbe)}
    assert declared - swept == {"probe_id", "tickers"}
    assert swept, "an empty sweep would make the per-field test above meaningless"


# tail only shapes candles, which are already hashed via build_probe_candles —
# it is the one deliberate exception to "every dataclass field is a stub".
_NON_ENRICHMENT_DATACLASS_FIELDS = frozenset({"tail"})


def test_every_dataclass_field_on_probe_ticker_is_a_tagged_enrichment_stub() -> None:
    """Structural guard so this bug class cannot recur.

    Any future dataclass-typed field added to ``ProbeTicker`` that is not a
    ``ProbeEnrichmentStub`` subclass would silently fall outside
    ``compute_probe_input_digest``, reproducing the exact gap the tests above
    close.
    """
    type_hints = get_type_hints(ProbeTicker)
    inspected_fields: set[str] = set()
    for probe_field in dataclasses.fields(ProbeTicker):
        annotation = type_hints[probe_field.name]
        candidates = get_args(annotation) or (annotation,)
        for candidate in candidates:
            if not (isinstance(candidate, type) and dataclasses.is_dataclass(candidate)):
                continue
            inspected_fields.add(probe_field.name)
            if probe_field.name in _NON_ENRICHMENT_DATACLASS_FIELDS:
                continue
            assert issubclass(candidate, ProbeEnrichmentStub), (
                f"ProbeTicker.{probe_field.name} is a dataclass field "
                f"({candidate.__name__}) that is not a ProbeEnrichmentStub subclass. "
                "Subclass ProbeEnrichmentStub so probe_enrichment_stubs — and "
                "therefore the input digest — picks up the new field "
                "automatically."
            )

    known_stub_fields = {"fundamentals", "shareholding", "bandar", "forward_estimates"}
    assert known_stub_fields <= inspected_fields, (
        f"expected to inspect at least {known_stub_fields}, got {inspected_fields} — "
        "this test would otherwise pass vacuously"
    )
