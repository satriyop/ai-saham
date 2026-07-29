"""One-time backfill of setup phase ledger from learning observations.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from src.domain.ports.setup_phase_history_repository import (
    SOURCE_WORKFLOW_SCREEN_ACCUM,
    SetupPhaseHistoryRepository,
    SetupPhaseRecordResult,
)
from src.domain.value_objects.learning_artifacts import AssessmentPurpose
from src.domain.value_objects.setup_phase import SetupPhaseState

CANONICAL_WINDOW_KEY = "7"


@dataclass(frozen=True)
class SetupPhaseLedgerBackfillReport:
    observations_seen: int
    rows_written: int
    rows_updated: int
    rows_identical: int
    rows_skipped: int

    def to_dict(self) -> dict[str, int]:
        return {
            "observations_seen": self.observations_seen,
            "rows_written": self.rows_written,
            "rows_updated": self.rows_updated,
            "rows_identical": self.rows_identical,
            "rows_skipped": self.rows_skipped,
        }


def backfill_setup_phase_ledger_from_observations(
    *,
    observation_repository: Any,
    ledger_repository: SetupPhaseHistoryRepository,
    purpose: AssessmentPurpose = AssessmentPurpose.ACCUMULATION_DISCOVERY,
) -> SetupPhaseLedgerBackfillReport:
    """Copy as-of phase facts from corpus observations into the production ledger.

    Prefers ``features_by_window[7]`` (canonical ADR-056 window). Last write
    wins per natural key when multiple observations map to the same session.
    """
    observations = list(observation_repository.list_observations(purpose))
    # Process oldest first so last-wins ends on the latest observation.
    observations.sort(key=lambda o: (o.cutoff_at, o.observation_id))

    written = updated = identical = skipped = 0
    for observation in observations:
        extracted = _extract_phase_fact(observation)
        if extracted is None:
            skipped += 1
            continue
        ticker, as_of, phase, family, workflow, observation_id = extracted
        result = ledger_repository.record_phase(
            ticker=ticker,
            as_of_date=as_of,
            phase=phase,
            setup_family=family,
            source_workflow=workflow,
            observation_id=observation_id,
        )
        if result is SetupPhaseRecordResult.INSERTED:
            written += 1
        elif result is SetupPhaseRecordResult.UPDATED:
            updated += 1
        elif result is SetupPhaseRecordResult.SKIPPED_IDENTICAL:
            identical += 1
        else:
            skipped += 1

    return SetupPhaseLedgerBackfillReport(
        observations_seen=len(observations),
        rows_written=written,
        rows_updated=updated,
        rows_identical=identical,
        rows_skipped=skipped,
    )


def _extract_phase_fact(
    observation: Any,
) -> tuple[str, date, SetupPhaseState, str | None, str, str] | None:
    payload = getattr(observation, "decision_payload", None)
    if not isinstance(payload, dict):
        return None

    window_pack = _canonical_window_pack(payload)
    if window_pack is None:
        return None

    fingerprint = window_pack.get("sub_signal_fingerprint") or {}
    if not isinstance(fingerprint, dict):
        return None

    phase = _parse_phase(fingerprint.get("setup_phase_current"))
    if phase is None or phase is SetupPhaseState.NONE:
        return None

    ticker = str(window_pack.get("ticker") or payload.get("ticker") or "").strip().upper()
    if not ticker:
        return None

    as_of = _as_of_date(window_pack, observation)
    if as_of is None:
        return None

    family = fingerprint.get("primary_setup_family") or fingerprint.get("setup_family")
    if family is not None:
        family = str(family).strip() or None

    workflow = str(
        window_pack.get("workflow") or payload.get("workflow") or SOURCE_WORKFLOW_SCREEN_ACCUM
    )
    # Normalize capture workflow to screen_accum production key when it is
    # the assess path under another name.
    if workflow in {"research_accum_capture", "screen_accum"}:
        workflow = SOURCE_WORKFLOW_SCREEN_ACCUM

    observation_id = str(getattr(observation, "observation_id", "") or "")
    return ticker, as_of, phase, family, workflow, observation_id


def _canonical_window_pack(payload: dict) -> dict | None:
    # ADR-056 multi-window shape
    features = payload.get("features_by_window")
    if isinstance(features, dict):
        for key in (CANONICAL_WINDOW_KEY, 7, "7"):
            pack = features.get(key)
            if isinstance(pack, dict):
                return pack
        # Fallback: any window with a phase fingerprint
        for pack in features.values():
            if not isinstance(pack, dict):
                continue
            fp = pack.get("sub_signal_fingerprint") or {}
            if isinstance(fp, dict) and fp.get("setup_phase_current"):
                return pack

    # Legacy flat observation payload
    if payload.get("sub_signal_fingerprint") is not None or payload.get("ticker"):
        return payload
    return None


def _as_of_date(window_pack: dict, observation: Any) -> date | None:
    for key in ("snapshot_date", "data_as_of_date", "session_date"):
        raw = window_pack.get(key)
        parsed = _parse_date(raw)
        if parsed is not None:
            return parsed
    cutoff = getattr(observation, "cutoff_at", None)
    if cutoff is not None:
        try:
            if hasattr(cutoff, "date"):
                return cutoff.date()
            return date.fromisoformat(str(cutoff)[:10])
        except (TypeError, ValueError):
            return None
    return None


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parse_phase(value: object) -> SetupPhaseState | None:
    if value is None:
        return None
    try:
        return SetupPhaseState(str(value))
    except ValueError:
        return None
