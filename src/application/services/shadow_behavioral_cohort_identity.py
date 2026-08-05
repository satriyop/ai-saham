"""ADR-068 slice 3 — shadow (non-authoritative) behavioural cohort identity.

Layer: Application (pure policy; the probe run it drives performs no IO)

Slice 3 of ``tasks/backlog/01_implement_adr_068_behavioral_engine_identity.md``
computes the behavioural digest **alongside** the incumbent
``semantic_compatibility_id`` so operators can watch it on real capture runs
before it becomes authoritative in slice 4.

What this is, precisely
-----------------------

This resolves the **code axis** of ADR-068 §1 identity — the behavioural probe
digest — and carries the authoritative id beside it for side-by-side logging.
It deliberately does **not** synthesise a composite shadow ``compatibility_id``:

- ADR-068 §1 identity is a fold of three orthogonal parts (probe digest,
  ADR-059 snapshot payload digest, payload schema version). Two of those are
  not resolved here, so any composite produced now would be a *different*
  formula from the one slice 4 must ship, and a stale shadow value that looks
  like an id is worse than no id.
- The stability/sensitivity properties slice 3 exists to verify — identical
  across a no-op run, moved by a threshold change — live entirely on the probe
  digest. The other two axes cannot move on a code-constant change.

Trust ordering (ADR-068 §7, task §14)
-------------------------------------

Nothing reads the returned digests back to decide anything. The authoritative
``semantic_compatibility_id`` written to ``learning_observations`` is produced
by ``resolve_lean_semantic_compatibility_id`` exactly as before and is passed
through this module untouched. This is observation only.

Failure semantics
-----------------

A shadow diagnostic must never fail an authoritative corpus write. The nightly
capture chain (``scripts/cron_accum_challenge_corpus.sh``) is fail-closed by
design, and a broken probe harness is a real bug — but it is a bug in a value
nothing consumes, so blocking the corpus on it would trade a loud, harmless
defect for a silent gap in the corpus.

That decision is policy, so it lives here rather than in the adapter: any probe
failure becomes the typed unavailable result
``ShadowBehavioralCohortIdentity(behavioral_probe_digest=None, ...,
unavailable_reason="<ExcType>: <message>")``. The exception type and message are
preserved so the operator sees what broke. The broad ``except Exception`` is
deliberate and bounded: every value in this result is diagnostic, so there is no
authoritative computation for it to mask.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.services.behavioral_probe_runner import (
    PROBE_PROJECTION_CONTRACT,
    compute_behavioral_probe_digest,
    compute_probe_input_digest,
)
from src.application.services.behavioral_probe_set import CORE_PROBE_SET_ID
from src.domain.value_objects.signal_artifact_identity import SemanticCompatibilityId

# Framing label for the shadow diagnostic itself. Not an identity contract —
# it names which slice's shadow shape an operator is reading in a log.
SHADOW_BEHAVIORAL_IDENTITY_CONTRACT = "shadow_behavioral_cohort_identity.slice3"


@dataclass(frozen=True)
class ShadowBehavioralCohortIdentity:
    """Diagnostic pairing of the authoritative cohort id with the probe digests.

    ``authoritative_compatibility_id`` is the value actually persisted on the
    observation. It is echoed here only so a single log line can show both
    mechanisms side by side; this object never produces it.

    ``behavioral_probe_digest`` and ``probe_input_digest`` are ``None`` exactly
    when ``unavailable_reason`` is set, and set exactly when it is ``None``.
    """

    authoritative_compatibility_id: SemanticCompatibilityId
    probe_set_id: str
    projection_contract: str
    behavioral_probe_digest: str | None
    probe_input_digest: str | None
    unavailable_reason: str | None

    def __post_init__(self) -> None:
        available = self.behavioral_probe_digest is not None and self.probe_input_digest is not None
        if available == (self.unavailable_reason is not None):
            raise ValueError(
                "shadow identity must carry either both digests or an "
                "unavailable_reason, never both and never neither"
            )

    @property
    def is_available(self) -> bool:
        return self.unavailable_reason is None


def resolve_shadow_behavioral_cohort_identity(
    *,
    authoritative_compatibility_id: SemanticCompatibilityId,
) -> ShadowBehavioralCohortIdentity:
    """Run the frozen core probe set and pair its digests with the live cohort id.

    Deterministic and offline: the probe runner substitutes every port with
    frozen in-memory data and fails closed on any write (ADR-068 §4). Repeated
    calls with unchanged code return byte-identical digests; a change to any
    probe-reachable production constant moves ``behavioral_probe_digest``.
    """
    try:
        behavioral_digest = compute_behavioral_probe_digest()
        input_digest = compute_probe_input_digest()
    # Deliberately broad: every value produced here is diagnostic, so there is
    # no authoritative computation this can mask. See module docstring.
    except Exception as exc:
        return ShadowBehavioralCohortIdentity(
            authoritative_compatibility_id=authoritative_compatibility_id,
            probe_set_id=CORE_PROBE_SET_ID,
            projection_contract=PROBE_PROJECTION_CONTRACT,
            behavioral_probe_digest=None,
            probe_input_digest=None,
            unavailable_reason=f"{type(exc).__name__}: {exc}",
        )
    return ShadowBehavioralCohortIdentity(
        authoritative_compatibility_id=authoritative_compatibility_id,
        probe_set_id=CORE_PROBE_SET_ID,
        projection_contract=PROBE_PROJECTION_CONTRACT,
        behavioral_probe_digest=behavioral_digest,
        probe_input_digest=input_digest,
        unavailable_reason=None,
    )
