"""ADR-068 slice-1 behavioural probe harness gate.

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
empty and additive-only, and that deliberately mutating a frozen
threshold moves the digest.
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
from pathlib import Path
from typing import NoReturn

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
    core_probe_set,
    extended_probe_set,
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
    assert extended, "slice 2 populates the extended set; an empty set measures nothing"
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
