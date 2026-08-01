"""P2 guard: production must not claim group/sector-breadth authority yet.

Configured breadth exists as an isolated applier, but composition roots do not
inject idx_groups. No production_policy_snapshot.v3 / lean-v3 / migration 4.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import src.adapters.composition.screen_accum_workflow_factory as workflow_factory
import src.application.services.accumulation_screen_factory as screen_factory
from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS,
    LearningContractId,
)

ROOT = Path(__file__).resolve().parents[3]


def test_active_closed_set_is_exactly_seven_v2_ids() -> None:
    assert len(ACCUMULATION_PRODUCTION_POLICY_IDS) == 7
    assert "screener.accum.sector_breadth" not in ACCUMULATION_PRODUCTION_POLICY_IDS
    assert LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2.value == (
        "production_policy_snapshot.v2"
    )
    # No v3 contract member authorized.
    assert not hasattr(LearningContractId, "PRODUCTION_POLICY_SNAPSHOT_V3")
    values = {m.value for m in LearningContractId}
    assert "production_policy_snapshot.v3" not in values
    assert "lean_accumulation_compatibility.v3" not in values


def test_create_accumulation_screen_use_case_defaults_idx_groups_none() -> None:
    sig = inspect.signature(screen_factory.create_accumulation_screen_use_case)
    assert "idx_groups" in sig.parameters
    assert sig.parameters["idx_groups"].default is None


def test_workflow_factory_does_not_pass_idx_groups() -> None:
    source = inspect.getsource(workflow_factory.create_accumulation_screen_workflow)
    assert "idx_groups" not in source
    bundle_source = inspect.getsource(workflow_factory.create_accumulation_screen_workflow_bundle)
    assert "idx_groups" not in bundle_source


def test_accum_screen_production_composition_does_not_inject_idx_groups() -> None:
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
    ]
    offenders: list[str] = []
    for path in production_paths:
        text = path.read_text(encoding="utf-8")
        # Parameter default None is allowed on the factory signature; a non-None
        # wiring call site is not.
        if "idx_groups=" in text and "idx_groups=None" not in text and "idx_groups: " not in text:
            offenders.append(str(path.relative_to(ROOT)))
        if "create_group_mapping_service" in text or "load_group_mapping" in text:
            offenders.append(str(path.relative_to(ROOT)))
        if "idx_groups.yaml" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"production wiring injects group mapping: {offenders}"


def test_no_v3_snapshot_or_migration_4_artifacts() -> None:
    """Speculative v3/migration artifacts must not appear from this task."""
    forbidden_snippets = (
        "production_policy_snapshot.v3",
        "lean_accumulation_compatibility.v3",
        "PRODUCTION_POLICY_SNAPSHOT_V3",
        "screener.accum.sector_breadth",
    )
    # Learning schema migration version 4 would appear as a dedicated migration
    # step; search migration/install code for v3 contract introduction.
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
    """ADR-059: score_weights payload must keep sector_breadth explicitly excluded."""
    from src.application.services.accumulation_policy_snapshot_payloads import (
        build_accum_score_weights_payload,
    )
    from src.application.use_case.score_accum_use_case import AccumScorePolicy

    payload = build_accum_score_weights_payload(AccumScorePolicy())
    excluded = payload.get("explicitly_excluded") or []
    keys = {row.get("key") for row in excluded if isinstance(row, dict)}
    assert "sector_breadth" in keys
