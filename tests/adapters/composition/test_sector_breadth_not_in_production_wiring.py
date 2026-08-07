"""ADR-062: group-breadth score bonus is retired from production.

No idx_groups accumulation-scoring seam, no applier module, no sector_breadth
policy row.

The original version of this module also banned every ``production_policy_snapshot.v3``
token, as a scope guard against ADR-062 inventing a speculative snapshot version
while retiring sector breadth. That ban is lifted here: ADR-059 v3 is a real,
separately motivated closed-set growth (the eighth row is
``risk.accum.unevaluable_policy``, which threads the aggregate unevaluable-gate
posture into the ADR-068 cohort identity). What this module actually guards —
that no group/sector-breadth scoring seam or policy row comes back — is
unchanged and still asserted below, including that the eighth row is *not*
sector breadth.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import src.adapters.composition.screen_accum_workflow_factory as workflow_factory
import src.application.services.accumulation_screen_factory as screen_factory
import src.application.use_case.accumulation_screen_use_case as screen_uc
from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS,
    LearningContractId,
)
from src.domain.value_objects.signal_semantic_contract import ACCUMULATION_DISCOVERY

ROOT = Path(__file__).resolve().parents[3]


def test_active_closed_set_is_exactly_nine_v4_ids_without_sector_breadth() -> None:
    assert len(ACCUMULATION_PRODUCTION_POLICY_IDS) == 9
    assert "screener.accum.sector_breadth" not in ACCUMULATION_PRODUCTION_POLICY_IDS
    assert LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V4.value == (
        "production_policy_snapshot.v4"
    )
    values = {m.value for m in LearningContractId}
    # ADR-068 retired the lean compatibility contract family outright; no v3 of
    # it may reappear alongside the snapshot v3.
    assert "lean_accumulation_compatibility.v3" not in values


def test_screen_factory_has_no_idx_groups_parameter() -> None:
    for name in (
        "create_accumulation_screen_use_case",
        "create_accumulation_screen_use_case_bundle",
    ):
        sig = inspect.signature(getattr(screen_factory, name))
        assert "idx_groups" not in sig.parameters


def test_screen_use_case_has_no_idx_groups_or_breadth_applier() -> None:
    sig = inspect.signature(screen_uc.AccumulationScreenUseCase.__init__)
    assert "idx_groups" not in sig.parameters
    source = inspect.getsource(screen_uc.AccumulationScreenUseCase)
    assert "AccumulationSectorBreadthApplier" not in source
    assert "_sector_breadth_applier" not in source
    assert "_ticker_to_group" not in source


def test_workflow_factory_does_not_pass_idx_groups() -> None:
    source = inspect.getsource(workflow_factory.create_accumulation_screen_workflow)
    assert "idx_groups" not in source
    bundle_source = inspect.getsource(workflow_factory.create_accumulation_screen_workflow_bundle)
    assert "idx_groups" not in bundle_source


def test_accum_screen_production_composition_has_no_group_scoring_seam() -> None:
    """Screen-accum / corpus production roots must not wire group mapping.

    Other inspect tools may load conglomerate maps for display; that is not
    production Accum scoring authority and is out of this guard's scope.
    """
    production_paths = [
        ROOT / "src" / "adapters" / "composition" / "screen_accum_workflow_factory.py",
        ROOT / "src" / "adapters" / "composition" / "screen_deps.py",
        ROOT / "src" / "adapters" / "cli" / "research_accum_backfill_commands.py",
        ROOT / "src" / "adapters" / "cli" / "research_accum_capture_commands.py",
        ROOT / "src" / "application" / "services" / "accumulation_screen_factory.py",
        ROOT / "src" / "application" / "use_case" / "accumulation_screen_use_case.py",
    ]
    offenders: list[str] = []
    for path in production_paths:
        text = path.read_text(encoding="utf-8")
        if "idx_groups" in text:
            offenders.append(str(path.relative_to(ROOT)))
        if "create_group_mapping_service" in text or "load_group_mapping" in text:
            offenders.append(str(path.relative_to(ROOT)))
        if "idx_groups.yaml" in text:
            offenders.append(str(path.relative_to(ROOT)))
        if "AccumulationSectorBreadthApplier" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"production wiring injects group scoring seam: {offenders}"


def test_retired_applier_module_is_gone() -> None:
    applier = ROOT / "src" / "application" / "services" / "accumulation_sector_breadth.py"
    assert not applier.exists()


def test_material_config_paths_exclude_retired_sector_breadth() -> None:
    paths = ACCUMULATION_DISCOVERY.common_material_config_paths
    retired = [p for p in paths if "sector_breadth" in p]
    assert retired == []


def test_no_sector_breadth_or_lean_v3_tokens() -> None:
    """Retired breadth policy and lean-compatibility identities stay gone."""
    forbidden_snippets = (
        "lean_accumulation_compatibility.v3",
        "screener.accum.sector_breadth",
    )
    search_roots = [
        ROOT / "src" / "domain",
        ROOT / "src" / "application",
        ROOT / "src" / "infrastructure" / "persistence",
    ]
    hits: list[str] = []
    for root in search_roots:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for snip in forbidden_snippets:
                if snip in text:
                    hits.append(f"{path.relative_to(ROOT)}:{snip}")
    assert hits == [], f"forbidden breadth/v3 tokens present: {hits}"


def test_score_weights_payload_still_excludes_sector_breadth() -> None:
    """ADR-059/062: score_weights payload keeps sector_breadth explicitly excluded."""
    from src.application.services.accumulation_policy_snapshot_payloads import (
        build_accum_score_weights_payload,
    )
    from src.application.use_case.score_accum_use_case import AccumScorePolicy

    payload = build_accum_score_weights_payload(AccumScorePolicy())
    excluded = payload.get("explicitly_excluded") or []
    keys = {row.get("key") for row in excluded if isinstance(row, dict)}
    assert "sector_breadth" in keys
    reason = next(row["reason"] for row in excluded if row.get("key") == "sector_breadth")
    assert "ADR-062" in reason


def test_canonical_yaml_has_no_sector_breadth_block() -> None:
    text = (ROOT / "config" / "accumulation_screener.yaml").read_text(encoding="utf-8")
    assert "sector_breadth:" not in text
    assert "breadth_threshold:" not in text
    assert "min_tickers_for_breadth:" not in text


def test_retired_sector_breadth_yaml_is_hard_rejected(tmp_path: Path) -> None:
    """Silent ignore of the retired block is forbidden (ADR-062 clean break)."""
    from src.infrastructure.config.swing_policy_config_loader import load_swing_policy_config

    cfg = tmp_path / "accum.yaml"
    cfg.write_text(
        "accumulation_screener:\n"
        "  screener:\n"
        "    min_market_cap_idr: 0\n"
        "  sector_breadth:\n"
        "    enabled: true\n"
        "    breadth_threshold: 0.60\n"
        "    bonus_pts: 10\n"
        "    min_tickers_for_breadth: 3\n",
        encoding="utf-8",
    )
    # Split-style: loader reads single file when config_path is set.
    # Single-file composition puts sector_breadth at top-level after merge or
    # as nested under accumulation_screener depending on path shape.
    # load with single path uses read_single which returns whole file; sector_breadth
    # may be nested. Write flat shape that loader sees after single-file read.
    flat = tmp_path / "flat.yaml"
    flat.write_text(
        "screener:\n"
        "  min_market_cap_idr: 0\n"
        "sector_breadth:\n"
        "  enabled: true\n"
        "  breadth_threshold: 0.60\n"
        "  bonus_pts: 10\n"
        "  min_tickers_for_breadth: 3\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sector_breadth is retired"):
        load_swing_policy_config(config_path=flat)


def test_split_composer_rejects_sector_breadth_block(tmp_path: Path) -> None:
    from src.infrastructure.config.swing_policy_config_composer import (
        read_split_swing_policy_config,
    )

    accum = tmp_path / "accumulation_screener.yaml"
    setups = tmp_path / "swing_setups.yaml"
    targets = tmp_path / "swing_targets.yaml"
    risk = tmp_path / "swing_risk_policy.yaml"
    for p in (setups, targets, risk):
        p.write_text("{}\n", encoding="utf-8")
    accum.write_text(
        "accumulation_screener:\n"
        "  screener:\n"
        "    min_market_cap_idr: 0\n"
        "  sector_breadth:\n"
        "    enabled: true\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sector_breadth is retired"):
        read_split_swing_policy_config(accum, setups, targets, risk)
