"""Unit tests for pure accumulation producer readiness classification (P0)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from src.application.services.accumulation_producer_readiness import (
    LabelCohortValidation,
    LabelHorizonCounts,
    ObservationCohortValidation,
    ProducerReadinessStatus,
    classify_producer_status,
    extract_action_from_payload,
    extract_setup_readiness_status_from_payload,
    observation_session_date,
    verify_snapshot_binding,
)
from src.application.services.accumulation_producer_readiness import (
    count_labels_by_horizon as _count_labels_by_horizon_impl,
)
from src.application.services.accumulation_producer_readiness import (
    project_cohort_readiness as _project_cohort_readiness_impl,
)
from src.application.services.accumulation_production_policy_descriptors import (
    ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V2,
)
from src.domain.services.trading_calendar import (
    first_weekday_session_after,
    inclusive_weekday_sessions,
    nth_weekday_session_on_or_after,
)
from src.domain.services.trading_session_calendar import (
    IDX_TRADING_SESSIONS_CONTRACT,
    PATH_LABEL_METRICS_SCHEMA_VERSION,
    KnownTradingSessionCalendar,
    session_calendar_digest,
    session_calendar_revision,
)
from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS_V2,
    PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
    PRODUCTION_POLICY_ID_HARD_FILTERS,
    AccumPopulationBinding,
    AssessmentPurpose,
    LabelAvailability,
    LearningContractError,
    LearningContractId,
    LearningObservation,
    LearningOutcomeLabel,
    OutcomeBasis,
    ProductionPolicySnapshot,
    _artifact_payload,
    artifact_digest,
    recompute_path_label_fingerprint,
    stamp_universe_membership_id,
    validate_label_availability_outcome,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
    LEGACY_CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
COMPAT = "sha256:" + ("ab" * 32)
OBS_CONTRACT = LearningContractId.ACCUMULATION_OBSERVATION.value
PRODUCER_CONTRACT = "accumulation-discovery.v2"
MATERIAL = "sha256:" + ("11" * 32)
# Locked ACCUM population identity: capture membership digest (not free-form labels).
MEMBERSHIP_TICKERS = ["ASII", "BBCA", "BBRI", "BMRI", "TLKM"]
NAMED_ROSTER = ["ASII", "BBCA", "BBRI", "BMRI", "TLKM", "UNTR", "HMSP"]
LOCKED_UNIVERSE_ID = stamp_universe_membership_id(MEMBERSHIP_TICKERS)
PRODUCER_REV = "ai-saham@test+git:deadbeef"


def _weekday_sessions(start: date, end: date) -> tuple[date, ...]:
    """Mon–Fri dates in [start, end] for gap-free holiday-free test calendars."""
    out: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            out.append(current)
        current += timedelta(days=1)
    return tuple(out)


# Default authoritative calendar for fixtures (no holidays in coverage).
DEFAULT_SESSION_CALENDAR = KnownTradingSessionCalendar(
    sessions=_weekday_sessions(date(2026, 6, 1), date(2026, 9, 30)),
    coverage_start=date(2026, 6, 1),
    coverage_end=date(2026, 9, 30),
)


def project_cohort_readiness(**kwargs):
    """Test wrapper: inject default session calendar unless overridden."""
    kwargs.setdefault("session_calendar", DEFAULT_SESSION_CALENDAR)
    return _project_cohort_readiness_impl(**kwargs)


def count_labels_by_horizon(**kwargs):
    """Test wrapper: inject default session calendar unless overridden."""
    kwargs.setdefault("session_calendar", DEFAULT_SESSION_CALENDAR)
    return _count_labels_by_horizon_impl(**kwargs)


def _ok_labels() -> LabelCohortValidation:
    empty = LabelHorizonCounts(available=0, unavailable=0, insufficient_horizon=0, conflict=0)
    return LabelCohortValidation(
        counts_by_horizon={"H3": empty, "H10": empty, "H20": empty},
        invalid_label_count=0,
        invalid_reasons=(),
        has_integrity_corruption=False,
    )


def _binding_for_session(session_date: str) -> dict:
    return AccumPopulationBinding.create(
        membership_tickers=MEMBERSHIP_TICKERS,
        named_universe_tickers=NAMED_ROSTER,
        membership_session=session_date,
        pit_tradable_lookback_sessions=10,
        producer_source_revision=PRODUCER_REV,
    ).to_dict()


def _payload(
    *,
    session_date: str | None,
    ticker: str = "BBCA",
    action: str | None = "WATCH",
    readiness: str | None = None,
    artifact_type: str = "accumulation_session_observation",
    workflow: str = "research_accum_capture",
    horizon_primary: str = "accum_10d",
    schema_version: int | None = None,
    with_provenance: bool = True,
    with_population_binding: bool | None = None,
    captured_at: datetime | None = None,
    decision_at: str | None = None,
    population_binding: dict | None = None,
) -> dict:
    if schema_version is None:
        schema_version = CANDIDATE_OBSERVATION_SCHEMA_VERSION
    if with_population_binding is None:
        with_population_binding = schema_version == CANDIDATE_OBSERVATION_SCHEMA_VERSION
    trade_setup = {"action": action} if action is not None else None
    signal = {"setup_readiness": {"status": readiness}} if readiness is not None else {}
    shared: dict = {"current_price": 100.0}
    cap = captured_at or (
        datetime.fromisoformat(f"{session_date}T12:00:00+00:00") if session_date else NOW
    )
    if with_provenance and session_date is not None:
        shared["provenance"] = {
            "decision_at": decision_at
            if decision_at is not None
            else f"{session_date}T12:00:00+00:00",
            "latest_completed_session": session_date,
            "analysis_as_of": session_date,
            "market_session_name": "regular",
            "is_eod_pending": False,
            "resolution_source": "test",
            "resolution_notes": [],
        }
    body: dict = {
        "schema_version": schema_version,
        "artifact_type": artifact_type,
        "ticker": ticker.upper(),
        "canonical_window": 7,
        "workflow": workflow,
        "horizon_primary": horizon_primary,
        "captured_at": cap.isoformat(),
        "shared": shared,
        "features_by_window": {
            "7": {
                "trade_setup": trade_setup,
                "signal": signal,
                "candidate": {},
                "sub_signal_fingerprint": {
                    "setup_readiness_status": "READY",  # diagnostic only; must not count
                },
            },
            "30": {"trade_setup": trade_setup, "signal": {}, "candidate": {}},
            "90": {"trade_setup": trade_setup, "signal": {}, "candidate": {}},
        },
    }
    if session_date is not None:
        body["session_date"] = session_date
    if with_population_binding and session_date is not None:
        body["population_binding"] = population_binding or _binding_for_session(session_date)
    return body


def _observation(
    *,
    day: int,
    ticker: str = "BBCA",
    compatibility_id: str = COMPAT,
    action: str | None = "WATCH",
    readiness: str | None = None,
    purpose: AssessmentPurpose = AssessmentPurpose.ACCUMULATION_DISCOVERY,
    session_date: str | None = None,
    force_contract: LearningContractId | None = None,
    artifact_type: str = "accumulation_session_observation",
    schema_version: int | None = None,
    with_population_binding: bool | None = None,
    decision_at: str | None = None,
) -> LearningObservation:
    at = datetime(2026, 7, day, 12, 0, tzinfo=timezone.utc)
    ticker_u = ticker.upper()
    sd = session_date if session_date is not None else f"2026-07-{day:02d}"
    # LearningObservation.create binds contract by purpose; for adversarial
    # pre-open contract under accum purpose we replace after create.
    purpose_for_create = (
        purpose
        if force_contract is None
        else (
            AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION
            if force_contract is LearningContractId.PRE_OPEN_OBSERVATION
            else purpose
        )
    )
    if force_contract is LearningContractId.PRE_OPEN_OBSERVATION:
        obs = LearningObservation.create(
            purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
            policy_contract="pre_open.v1",
            horizon_contract="open_30m",
            compatibility_id=compatibility_id,
            cutoff_at=at,
            universe_id=LOCKED_UNIVERSE_ID,
            window_id=f"{ticker_u}:2026-07-{day:02d}",
            decision_payload={"ticker": ticker_u, "session_date": sd},
            captured_at=at,
        )
        # Adversarial: re-purpose without changing contract.
        return replace(obs, purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY)

    return LearningObservation.create(
        purpose=purpose_for_create,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id=compatibility_id,
        cutoff_at=at,
        universe_id=LOCKED_UNIVERSE_ID,
        window_id=f"{ticker_u}:{sd}",
        decision_payload=_payload(
            session_date=sd,
            ticker=ticker_u,
            action=action,
            readiness=readiness,
            artifact_type=artifact_type,
            schema_version=schema_version,
            with_population_binding=with_population_binding,
            captured_at=at,
            decision_at=decision_at,
        ),
        captured_at=at,
    )


def _legacy_observation(
    *,
    day: int,
    ticker: str = "BBCA",
    compatibility_id: str = COMPAT,
    action: str | None = "WATCH",
    readiness: str | None = None,
) -> LearningObservation:
    """Schema-9 historical row without population_binding (immutable corpus)."""
    return _observation(
        day=day,
        ticker=ticker,
        compatibility_id=compatibility_id,
        action=action,
        readiness=readiness,
        schema_version=LEGACY_CANDIDATE_OBSERVATION_SCHEMA_VERSION,
        with_population_binding=False,
    )


def _available_metrics(
    *,
    ticker: str = "BBCA",
    signal_date: str,
    horizon_days: int = 10,
    entry_price: float = 100.0,
    label_window_start: str | None = None,
    label_window_end: str | None = None,
    session_calendar: KnownTradingSessionCalendar | None = None,
) -> dict:
    """Build AVAILABLE path metrics with first-N sessions and calendar identity.

    Default windows use the default test session calendar (weekday-complete).
    """
    cal = session_calendar or DEFAULT_SESSION_CALENDAR
    signal = date.fromisoformat(signal_date)
    expected = cal.first_n_sessions_after(signal, horizon_days)
    if label_window_start is None or label_window_end is None:
        assert expected is not None, f"no first-{horizon_days} sessions after {signal_date}"
        start_s = expected[0].isoformat()
        end_s = expected[-1].isoformat()
        sessions = [s.isoformat() for s in expected]
    else:
        start_s = label_window_start
        end_s = label_window_end
        if (
            expected is not None
            and start_s == expected[0].isoformat()
            and end_s == expected[-1].isoformat()
        ):
            sessions = [s.isoformat() for s in expected]
        else:
            # Adversarial/custom endpoints: materialize inclusive weekday list when possible.
            start_d = date.fromisoformat(start_s)
            end_d = date.fromisoformat(end_s)
            sessions = [s.isoformat() for s in cal.sessions if start_d <= s <= end_d]
            if not sessions:
                sessions = [start_s, end_s]
    return {
        "ticker": ticker.upper(),
        "signal_date": signal_date,
        "label_window_start": start_s,
        "label_window_end": end_s,
        "label_window_sessions": sessions,
        "session_calendar_contract": IDX_TRADING_SESSIONS_CONTRACT,
        "session_calendar_revision": session_calendar_revision(cal),
        "session_calendar_digest": session_calendar_digest(cal),
        "path_label_metrics_schema_version": PATH_LABEL_METRICS_SCHEMA_VERSION,
        "entry_reference_price": entry_price,
        "close_return_pct": 3.5,
        "max_forward_return_pct": 5.0,
        "max_adverse_excursion_pct": -1.0,
        "days_to_peak": min(2, horizon_days),
        "days_to_trough": 1,
    }


def _label(
    observation: LearningObservation | str,
    *,
    contract: LearningContractId = LearningContractId.ACCUM_10D_LABEL,
    availability: LabelAvailability = LabelAvailability.AVAILABLE,
    outcome: str | None = "SUCCESS",
    outcome_basis: OutcomeBasis = OutcomeBasis.PRICE_PATH_ONLY,
    fingerprint: str | None = None,
    metrics: dict | None = None,
) -> LearningOutcomeLabel:
    if isinstance(observation, LearningObservation):
        observation_id = observation.observation_id
        if fingerprint is None:
            fingerprint = recompute_path_label_fingerprint(
                observation_id=observation.observation_id,
                observation_artifact_digest=observation.artifact_digest,
                label_contract=contract,
            )
        if metrics is None and availability is LabelAvailability.AVAILABLE:
            session = observation_session_date(observation)
            sd = session.isoformat() if session else "2026-07-01"
            ticker = str(observation.decision_payload.get("ticker", "BBCA"))
            horizon = {
                LearningContractId.ACCUM_3D_LABEL: 3,
                LearningContractId.ACCUM_10D_LABEL: 10,
                LearningContractId.ACCUM_20D_LABEL: 20,
            }.get(contract, 10)
            metrics = _available_metrics(ticker=ticker, signal_date=sd, horizon_days=horizon)
    else:
        observation_id = observation
        if fingerprint is None:
            fingerprint = "fp-1"
    if availability is LabelAvailability.UNAVAILABLE:
        outcome = None
        if metrics is None:
            metrics = {"unavailable_reason": "corporate_action_in_window"}
    if metrics is None:
        metrics = {}
    return LearningOutcomeLabel.create(
        contract_id=contract,
        observation_id=observation_id,
        outcome_basis=outcome_basis,
        availability=availability,
        outcome=outcome,
        metrics=metrics,
        fingerprint=fingerprint,
        labeled_at=NOW,
    )


def _rehash_label(label: LearningOutcomeLabel) -> LearningOutcomeLabel:
    """Rebuild artifact_digest for a reconstructed label (simulates load/rehash)."""
    digest = artifact_digest(
        _artifact_payload(label, id_field="label_id", digest_field="artifact_digest")
    )
    return replace(label, artifact_digest=digest)


def _snapshot(
    policy_id: str,
    *,
    contract: LearningContractId = LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2,
    compatibility_id: str = COMPAT,
    corrupt_digest: bool = False,
    material: str = MATERIAL,
    semantic_override: str | None = None,
    decision_override: str | None = None,
) -> ProductionPolicySnapshot:
    descriptor = ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V2.get(policy_id)
    if descriptor is not None and contract is LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2:
        decision_type = decision_override or descriptor.decision_type
        semantic = semantic_override or descriptor.semantic_engine_contract_id
        policy_version = descriptor.policy_version
    else:
        decision_type = decision_override or "score"
        semantic = semantic_override or "test.semantic.v1"
        policy_version = "v1"
    snap = ProductionPolicySnapshot.create(
        contract_id=contract,
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        learning_observation_contract_id=OBS_CONTRACT,
        producer_observation_contract=PRODUCER_CONTRACT,
        compatibility_id=compatibility_id,
        policy_id=policy_id,
        policy_version=policy_version,
        decision_type=decision_type,
        semantic_engine_contract_id=semantic,
        material_config_hash=material,
        canonical_payload={
            "policy_id": policy_id,
            "policy_version": policy_version,
            "decision_type": decision_type,
            "semantic_engine_contract_id": semantic,
            "components": [],
        },
        source_revision="ai-saham@test+git:deadbeef",
        created_at=NOW,
    )
    if corrupt_digest:
        return replace(snap, payload_digest="0" * 64)
    return snap


def _full_v2_set(
    compatibility_id: str = COMPAT, *, material: str = MATERIAL
) -> tuple[ProductionPolicySnapshot, ...]:
    return tuple(
        _snapshot(pid, compatibility_id=compatibility_id, material=material)
        for pid in ACCUMULATION_PRODUCTION_POLICY_IDS_V2
    )


def test_classify_legacy_when_active_set_not_verified() -> None:
    from src.application.services.accumulation_producer_readiness import SnapshotBindingReport

    snap = SnapshotBindingReport(
        binding_contract="production_policy_snapshot.v2",
        required_policy_ids=tuple(ACCUMULATION_PRODUCTION_POLICY_IDS_V2),
        required_count=7,
        verified_count=0,
        verified_policy_ids=(),
        missing_policy_ids=tuple(ACCUMULATION_PRODUCTION_POLICY_IDS_V2),
        extra_policy_ids=(),
        invalid_policy_ids=(),
        observed_contract_ids=(),
        material_config_hashes=(),
        active_set_verified=False,
        has_corruption=False,
        claims_active_binding=False,
    )
    ov = ObservationCohortValidation(
        expected_learning_observation_contract_id=OBS_CONTRACT,
        expected_producer_observation_contract=PRODUCER_CONTRACT,
        valid_observation_count=2,
        invalid_observation_count=0,
        invalid_reasons=(),
        session_dates=(),
        has_contract_corruption=False,
    )
    assert (
        classify_producer_status(
            snapshot=snap,
            observation_validation=ov,
            label_validation=_ok_labels(),
            session_count=42,
            available_h10_labels=100,
        )
        is ProducerReadinessStatus.LEGACY_RAW_ONLY
    )


def test_classify_blocked_on_observation_corruption() -> None:
    from src.application.services.accumulation_producer_readiness import SnapshotBindingReport

    snap = SnapshotBindingReport(
        binding_contract="production_policy_snapshot.v2",
        required_policy_ids=tuple(ACCUMULATION_PRODUCTION_POLICY_IDS_V2),
        required_count=7,
        verified_count=7,
        verified_policy_ids=tuple(ACCUMULATION_PRODUCTION_POLICY_IDS_V2),
        missing_policy_ids=(),
        extra_policy_ids=(),
        invalid_policy_ids=(),
        observed_contract_ids=("production_policy_snapshot.v2",),
        material_config_hashes=(MATERIAL,),
        active_set_verified=True,
        has_corruption=False,
        claims_active_binding=True,
    )
    ov = ObservationCohortValidation(
        expected_learning_observation_contract_id=OBS_CONTRACT,
        expected_producer_observation_contract=PRODUCER_CONTRACT,
        valid_observation_count=0,
        invalid_observation_count=2,
        invalid_reasons=("x:contract_id:pre_open",),
        session_dates=(),
        has_contract_corruption=True,
    )
    assert (
        classify_producer_status(
            snapshot=snap,
            observation_validation=ov,
            label_validation=_ok_labels(),
            session_count=2,
            available_h10_labels=2,
        )
        is ProducerReadinessStatus.BLOCKED_POLICY
    )


def test_classify_collecting_and_ready() -> None:
    from src.application.services.accumulation_producer_readiness import SnapshotBindingReport

    snap = SnapshotBindingReport(
        binding_contract="production_policy_snapshot.v2",
        required_policy_ids=tuple(ACCUMULATION_PRODUCTION_POLICY_IDS_V2),
        required_count=7,
        verified_count=7,
        verified_policy_ids=tuple(ACCUMULATION_PRODUCTION_POLICY_IDS_V2),
        missing_policy_ids=(),
        extra_policy_ids=(),
        invalid_policy_ids=(),
        observed_contract_ids=("production_policy_snapshot.v2",),
        material_config_hashes=(MATERIAL,),
        active_set_verified=True,
        has_corruption=False,
        claims_active_binding=True,
    )
    ov = ObservationCohortValidation(
        expected_learning_observation_contract_id=OBS_CONTRACT,
        expected_producer_observation_contract=PRODUCER_CONTRACT,
        valid_observation_count=2,
        invalid_observation_count=0,
        invalid_reasons=(),
        session_dates=(),
        has_contract_corruption=False,
        has_current_population_authority=True,
    )
    assert (
        classify_producer_status(
            snapshot=snap,
            observation_validation=ov,
            label_validation=_ok_labels(),
            session_count=1,
            available_h10_labels=10,
        )
        is ProducerReadinessStatus.COLLECTING
    )
    assert (
        classify_producer_status(
            snapshot=snap,
            observation_validation=ov,
            label_validation=_ok_labels(),
            session_count=2,
            available_h10_labels=0,
        )
        is ProducerReadinessStatus.COLLECTING
    )
    assert (
        classify_producer_status(
            snapshot=snap,
            observation_validation=ov,
            label_validation=_ok_labels(),
            session_count=2,
            available_h10_labels=1,
        )
        is ProducerReadinessStatus.CHALLENGE_INPUT_READY
    )


def test_verify_rejects_wrong_semantic_contract() -> None:
    snaps = list(_full_v2_set())
    snaps[0] = _snapshot(
        PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS, semantic_override="test.semantic.v1"
    )
    report = verify_snapshot_binding(
        snaps,
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
        compatibility_id=COMPAT,
    )
    assert report.active_set_verified is False
    assert report.has_corruption is True
    assert PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS in report.invalid_policy_ids


def test_verify_rejects_split_material_hash() -> None:
    snaps = list(_full_v2_set(material=MATERIAL))
    snaps[-1] = _snapshot(PRODUCTION_POLICY_ID_HARD_FILTERS, material="sha256:" + ("22" * 32))
    report = verify_snapshot_binding(
        snaps,
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
        compatibility_id=COMPAT,
    )
    assert report.active_set_verified is False
    assert report.has_corruption is True
    assert len(report.material_config_hashes) == 2 or report.verified_count == 0


def test_verify_accepts_authoritative_full_set() -> None:
    report = verify_snapshot_binding(
        _full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
        compatibility_id=COMPAT,
    )
    assert report.active_set_verified is True
    assert report.material_config_hashes == (MATERIAL,)
    assert report.verified_count == 7


def test_verify_zero_snapshots_is_legacy_not_blocked() -> None:
    report = verify_snapshot_binding(
        (),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
        compatibility_id=COMPAT,
    )
    assert report.active_set_verified is False
    assert report.has_corruption is False
    assert report.claims_active_binding is False


def test_verify_partial_v2_claims_active_and_lists_missing() -> None:
    snaps = tuple(_snapshot(pid) for pid in ACCUMULATION_PRODUCTION_POLICY_IDS_V2[:5])
    report = verify_snapshot_binding(
        snaps,
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
        compatibility_id=COMPAT,
    )
    assert report.claims_active_binding is True
    assert report.active_set_verified is False
    assert PRODUCTION_POLICY_ID_HARD_FILTERS in report.missing_policy_ids


def test_fingerprint_readiness_does_not_count_as_authoritative() -> None:
    payload = _payload(session_date="2026-07-01", readiness=None)
    assert extract_setup_readiness_status_from_payload(payload) is None
    # Fingerprint says READY but authoritative signal.setup_readiness is absent.
    assert (
        payload["features_by_window"]["7"]["sub_signal_fingerprint"]["setup_readiness_status"]
        == "READY"
    )


def test_extract_action_and_readiness_from_frozen_payload_only() -> None:
    payload = _payload(session_date="2026-07-01", action="ENTER", readiness="READY")
    assert extract_action_from_payload(payload) == "ENTER"
    assert extract_setup_readiness_status_from_payload(payload) == "READY"


def test_project_legacy_zero_snapshot_cohort() -> None:
    obs = [_legacy_observation(day=1), _legacy_observation(day=2, ticker="BBRI")]
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=(),
        snapshots=(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.LEGACY_RAW_ONLY
    assert cohort.observation_count == 2
    assert cohort.session_count == 2


def test_project_challenge_input_ready() -> None:
    obs = [
        _observation(day=1, action="WATCH", readiness=None),
        _observation(day=2, ticker="BBRI", action="ENTER", readiness="INCOMPLETE"),
    ]
    labels = [_label(obs[0])]
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=labels,
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.CHALLENGE_INPUT_READY
    assert cohort.setup_readiness_present == 1
    assert cohort.setup_readiness_missing == 1
    # Locked population identity stamped on production-shaped fixtures.
    assert obs[0].universe_id == LOCKED_UNIVERSE_ID
    assert type(obs[0].universe_id) is str
    assert len(obs[0].universe_id) == 64


def test_invented_universe_labels_cannot_be_challenge_input_ready() -> None:
    """Self-consistent inventable universe_id values are not population authority.

    Two observations with different invented labels still recompute observation_id
    from their own fields; readiness must fail closed for population_authority.
    """
    invented = ("made-up-population", "another-population")
    obs: list[LearningObservation] = []
    for day, universe_id, ticker in (
        (1, invented[0], "BBCA"),
        (2, invented[1], "BBRI"),
    ):
        at = datetime(2026, 7, day, 12, 0, tzinfo=timezone.utc)
        ticker_u = ticker.upper()
        sd = f"2026-07-{day:02d}"
        obs.append(
            LearningObservation.create(
                purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
                policy_contract="accumulation_discovery.policy.v1",
                horizon_contract="accum_10d",
                compatibility_id=COMPAT,
                cutoff_at=at,
                universe_id=universe_id,
                window_id=f"{ticker_u}:{sd}",
                decision_payload=_payload(session_date=sd, ticker=ticker_u, action="WATCH"),
                captured_at=at,
            )
        )
    # Prove inventable labels are self-consistent with observation identity.
    from src.domain.value_objects.learning_artifacts import validate_observation_identity

    for o in obs:
        validate_observation_identity(o)

    labels = [_label(obs[0])]
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=labels,
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is not ProducerReadinessStatus.CHALLENGE_INPUT_READY
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert cohort.observation_validation.has_contract_corruption is True
    reasons = " ".join(cohort.observation_validation.invalid_reasons)
    assert "population_authority_unbound" in reasons
    assert "made-up-population" in reasons
    assert "another-population" in reasons
    assert cohort.observation_validation.valid_observation_count == 0


def test_free_form_lq45_pit_label_is_not_population_authority() -> None:
    """Historical free-form test label is not dual-accepted as population authority."""
    at = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    at2 = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
    free = "lq45@pit"
    o1 = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id=COMPAT,
        cutoff_at=at,
        universe_id=free,
        window_id="BBCA:2026-07-01",
        decision_payload=_payload(session_date="2026-07-01", ticker="BBCA"),
        captured_at=at,
    )
    o2 = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id=COMPAT,
        cutoff_at=at2,
        universe_id=free,
        window_id="BBRI:2026-07-02",
        decision_payload=_payload(session_date="2026-07-02", ticker="BBRI"),
        captured_at=at2,
    )
    labels = [_label(o1)]
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[o1, o2],
        labels=labels,
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert "population_authority_unbound" in " ".join(cohort.observation_validation.invalid_reasons)


def test_project_blocked_on_preopen_contract_under_accum_purpose() -> None:
    """Adversarial pre-open contract observations must not yield READY."""
    bad = [
        _observation(day=1, force_contract=LearningContractId.PRE_OPEN_OBSERVATION),
        _observation(day=2, ticker="BBRI", force_contract=LearningContractId.PRE_OPEN_OBSERVATION),
    ]
    labels = [_label(o) for o in bad]
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=bad,
        labels=labels,
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert cohort.observation_validation.has_contract_corruption is True
    assert "pre_open" in cohort.observation_contract or "pre_open" in str(
        cohort.observation_validation.invalid_reasons
    )


def test_missing_session_date_does_not_count_sessions_via_cutoff() -> None:
    at = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    at2 = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
    # Build valid accum obs then strip session_date while keeping cutoff distinct.
    o1 = _observation(day=1)
    o2 = _observation(day=2, ticker="BBRI")
    o1 = replace(
        o1,
        decision_payload={
            k: v for k, v in dict(o1.decision_payload).items() if k != "session_date"
        },
        cutoff_at=at,
    )
    o2 = replace(
        o2,
        decision_payload={
            k: v for k, v in dict(o2.decision_payload).items() if k != "session_date"
        },
        cutoff_at=at2,
    )
    labels = [_label(o1)]
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[o1, o2],
        labels=labels,
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert cohort.session_count == 0
    assert cohort.observation_validation.has_contract_corruption is True


def test_project_blocked_on_partial_snapshots() -> None:
    obs = [_observation(day=1), _observation(day=2, ticker="BBRI")]
    snaps = tuple(_snapshot(pid) for pid in ACCUMULATION_PRODUCTION_POLICY_IDS_V2[:6])
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[_label(obs[0])],
        snapshots=snaps,
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert PRODUCTION_POLICY_ID_HARD_FILTERS in cohort.snapshot.missing_policy_ids


def test_session_date_requires_exact_yyyy_mm_dd() -> None:
    o = _observation(day=1, session_date="2026-07-01-not-a-date")
    assert observation_session_date(o) is None
    o_ok = _observation(day=1, session_date="2026-07-01")
    assert observation_session_date(o_ok).isoformat() == "2026-07-01"


def test_malformed_session_date_prefix_blocks_ready() -> None:
    obs = [
        _observation(day=1, session_date="2026-07-01-not-a-date"),
        _observation(day=2, ticker="BBRI", session_date="2026-07-02-not-a-date"),
    ]
    labels = [_label(obs[0])]
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=labels,
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert cohort.session_count == 0


def test_fuzzy_accumulation_artifact_type_rejected() -> None:
    obs = [
        _observation(day=1, artifact_type="accumulation_pre_open_fabricated"),
        _observation(day=2, ticker="BBRI", artifact_type="accumulation_pre_open_fabricated"),
    ]
    labels = [_label(o) for o in obs]
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=labels,
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert cohort.observation_validation.has_contract_corruption is True
    assert any("artifact_type" in r for r in cohort.observation_validation.invalid_reasons)


def test_tampered_label_digest_blocks_challenge_input_ready() -> None:
    """UNAVAILABLE→AVAILABLE without rehash must fail closed, not manufacture READY."""
    obs = [
        _observation(day=1),
        _observation(day=2, ticker="BBRI"),
    ]
    label = _label(
        obs[0].observation_id,
        availability=LabelAvailability.UNAVAILABLE,
        outcome=None,
    )
    tampered = replace(
        label,
        availability=LabelAvailability.AVAILABLE,
        outcome="SUCCESS",
        # artifact_digest intentionally left stale
    )
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[tampered],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert cohort.label_validation.has_integrity_corruption is True
    assert cohort.label_validation.invalid_label_count == 1
    # Must not count the forged AVAILABLE row toward H10 readiness.
    assert cohort.labels_by_horizon["H10"].available == 0


def test_rehashed_available_without_outcome_blocks_and_does_not_count_h10() -> None:
    """AVAILABLE+outcome=None after full rehash is corrupt — not CHALLENGE_INPUT_READY.

    Create-time rejection is insufficient: reconstruction can bypass create.
    """
    from src.domain.value_objects.learning_artifacts import (
        validate_artifact_integrity,
        validate_label_identity,
    )

    obs = [
        _observation(day=1),
        _observation(day=2, ticker="BBRI"),
    ]
    # create() rejects AVAILABLE+None; rebuild outside create then rehash.
    valid = _label(obs[0], outcome="SUCCESS")
    with_none = replace(valid, outcome=None, metrics={})
    rehashed = _rehash_label(with_none)
    # Digest + identity still consistent — only the availability↔outcome pair is wrong.
    validate_artifact_integrity(rehashed, id_field="label_id")
    validate_label_identity(rehashed)
    assert rehashed.availability is LabelAvailability.AVAILABLE
    assert rehashed.outcome is None

    # Shared invariant helper rejects (same as create).
    try:
        validate_label_availability_outcome(rehashed.availability, rehashed.outcome)
        raise AssertionError("expected create/read invariant to reject AVAILABLE+None")
    except LearningContractError as exc:
        assert "available label requires an outcome" in str(exc)

    counts = count_labels_by_horizon(
        observation_ids=[o.observation_id for o in obs],
        labels=[rehashed],
    )
    assert counts.has_integrity_corruption is True
    assert counts.invalid_label_count == 1
    assert counts.counts_by_horizon["H10"].available == 0
    assert any("available_without_outcome" in r for r in counts.invalid_reasons)

    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[rehashed],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is not ProducerReadinessStatus.CHALLENGE_INPUT_READY
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert cohort.labels_by_horizon["H10"].available == 0
    assert cohort.label_validation.invalid_reasons
    assert any("available_without_outcome" in r for r in cohort.label_validation.invalid_reasons)


def test_rehashed_unavailable_with_outcome_blocks_and_does_not_tally_unavailable() -> None:
    """UNAVAILABLE+non-None outcome after rehash is corruption, not normal unavailable."""

    obs = [
        _observation(day=1),
        _observation(day=2, ticker="BBRI"),
    ]
    valid = _label(
        obs[0],
        availability=LabelAvailability.UNAVAILABLE,
        outcome=None,
    )
    bad = replace(valid, outcome="SUCCESS", metrics={"forward_return_pct": 1.0})
    rehashed = _rehash_label(bad)
    assert rehashed.availability is LabelAvailability.UNAVAILABLE
    assert rehashed.outcome == "SUCCESS"

    counts = count_labels_by_horizon(
        observation_ids=[o.observation_id for o in obs],
        labels=[rehashed],
    )
    assert counts.has_integrity_corruption is True
    assert counts.counts_by_horizon["H10"].unavailable == 0
    assert counts.counts_by_horizon["H10"].available == 0
    assert any("unavailable_with_outcome" in r for r in counts.invalid_reasons)

    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[rehashed],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert cohort.labels_by_horizon["H10"].unavailable == 0


def test_valid_available_h10_outcome_still_enables_challenge_input_ready() -> None:
    """Production-shaped AVAILABLE+outcome still counts and can reach READY."""
    obs = [
        _observation(day=1, action="WATCH", readiness=None),
        _observation(day=2, ticker="BBRI", action="ENTER", readiness="INCOMPLETE"),
    ]
    labels = [_label(obs[0], outcome="SUCCESS")]
    assert labels[0].availability is LabelAvailability.AVAILABLE
    assert labels[0].outcome is not None
    # create path still rejects AVAILABLE+None
    try:
        LearningOutcomeLabel.create(
            contract_id=LearningContractId.ACCUM_10D_LABEL,
            observation_id=obs[0].observation_id,
            outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
            availability=LabelAvailability.AVAILABLE,
            outcome=None,
            metrics={},
            fingerprint="fp-1",
            labeled_at=NOW,
        )
        raise AssertionError("create must still reject AVAILABLE+None")
    except LearningContractError as exc:
        assert "available label requires an outcome" in str(exc)

    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=labels,
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.labels_by_horizon["H10"].available >= 1
    assert cohort.label_validation.has_integrity_corruption is False
    assert cohort.label_validation.invalid_reasons == ()
    assert cohort.producer_status is ProducerReadinessStatus.CHALLENGE_INPUT_READY


def test_tampered_observation_digest_blocks() -> None:
    o1 = _observation(day=1)
    o2 = _observation(day=2, ticker="BBRI")
    bad = replace(o1, artifact_digest="0" * 64)
    labels = [_label(o1), _label(o2)]
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[bad, o2],
        labels=labels,
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert any(
        "artifact_digest_mismatch" in r for r in cohort.observation_validation.invalid_reasons
    )


def test_wrong_policy_contract_blocks_ready() -> None:
    o1 = _observation(day=1)
    o2 = _observation(day=2, ticker="BBRI")
    # Recreate with wrong policy string while keeping a valid digest for that string,
    # then replace into cohort — create() will hash the wrong policy into the id.
    bad1 = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_screener.v1",
        horizon_contract="accum_10d",
        compatibility_id=COMPAT,
        cutoff_at=o1.cutoff_at,
        universe_id=o1.universe_id,
        window_id=o1.window_id,
        decision_payload=dict(o1.decision_payload),
        captured_at=o1.captured_at,
    )
    bad2 = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_screener.v1",
        horizon_contract="accum_10d",
        compatibility_id=COMPAT,
        cutoff_at=o2.cutoff_at,
        universe_id=o2.universe_id,
        window_id=o2.window_id,
        decision_payload=dict(o2.decision_payload),
        captured_at=o2.captured_at,
    )
    labels = [_label(bad1), _label(bad2)]
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[bad1, bad2],
        labels=labels,
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert any("policy_contract" in r for r in cohort.observation_validation.invalid_reasons)


def test_wrong_horizon_contract_blocks_ready() -> None:
    o1 = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="open_30m",
        compatibility_id=COMPAT,
        cutoff_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
        universe_id=LOCKED_UNIVERSE_ID,
        window_id="BBCA:2026-07-01",
        decision_payload=_payload(session_date="2026-07-01"),
        captured_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    o2 = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="open_30m",
        compatibility_id=COMPAT,
        cutoff_at=datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc),
        universe_id=LOCKED_UNIVERSE_ID,
        window_id="BBRI:2026-07-02",
        decision_payload=_payload(session_date="2026-07-02"),
        captured_at=datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc),
    )
    labels = [_label(o1)]
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[o1, o2],
        labels=labels,
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert any("horizon_contract" in r for r in cohort.observation_validation.invalid_reasons)


def test_wrong_label_outcome_basis_blocks_and_does_not_count_h10() -> None:
    obs = [_observation(day=1), _observation(day=2, ticker="BBRI")]
    forged = _label(
        obs[0].observation_id,
        outcome_basis=OutcomeBasis.SIMULATED_NET_EXECUTION,
    )
    # Valid digest for that basis, but wrong semantic for path labels.
    validate_artifact_integrity = __import__(
        "src.domain.value_objects.learning_artifacts", fromlist=["validate_artifact_integrity"]
    ).validate_artifact_integrity
    validate_artifact_integrity(forged, id_field="label_id")
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[forged],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert cohort.label_validation.has_integrity_corruption is True
    assert any("outcome_basis" in r for r in cohort.label_validation.invalid_reasons)
    assert cohort.labels_by_horizon["H10"].available == 0


def test_forged_observation_id_with_valid_digest_blocks() -> None:
    o1 = _observation(day=1)
    o2 = _observation(day=2, ticker="BBRI")
    # Swap ID without touching digest (digest excludes identity field).
    forged = replace(o1, observation_id=o2.observation_id)
    from src.domain.value_objects.learning_artifacts import validate_artifact_integrity

    validate_artifact_integrity(forged, id_field="observation_id")
    labels = [_label(o1), _label(o2)]
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[forged, o2],
        labels=labels,
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert any(
        "observation_id_mismatch" in r for r in cohort.observation_validation.invalid_reasons
    )


def test_forged_label_id_with_valid_digest_blocks() -> None:
    obs = [_observation(day=1), _observation(day=2, ticker="BBRI")]
    label = _label(obs[0])
    other = _label(obs[1])
    forged = replace(label, label_id=other.label_id)
    from src.domain.value_objects.learning_artifacts import validate_artifact_integrity

    validate_artifact_integrity(forged, id_field="label_id")
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[forged],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert any("label_id_mismatch" in r for r in cohort.label_validation.invalid_reasons)
    assert cohort.labels_by_horizon["H10"].available == 0


def test_happy_path_fixtures_are_production_shaped() -> None:
    o = _observation(day=1)
    assert o.policy_contract == "accumulation_discovery.policy.v1"
    assert o.horizon_contract == "accum_10d"
    from src.domain.value_objects.learning_artifacts import (
        validate_label_identity,
        validate_observation_identity,
    )

    validate_observation_identity(o)
    lab = _label(o)
    validate_label_identity(lab)
    assert lab.outcome_basis is OutcomeBasis.PRICE_PATH_ONLY


def test_unbound_payload_session_dates_do_not_manufacture_depth() -> None:
    """Identity on July 1 but payload claims July 2/3 must not yield two sessions."""
    day1 = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    # Fully valid rehashed rows with July-1 identity dimensions.
    o1 = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id=COMPAT,
        cutoff_at=day1,
        universe_id=LOCKED_UNIVERSE_ID,
        window_id="BBCA:2026-07-01",
        decision_payload=_payload(session_date="2026-07-02", ticker="BBCA"),
        captured_at=day1,
    )
    o2 = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id=COMPAT,
        cutoff_at=day1,
        universe_id=LOCKED_UNIVERSE_ID,
        window_id="BBRI:2026-07-01",
        decision_payload=_payload(session_date="2026-07-03", ticker="BBRI"),
        captured_at=day1,
    )
    labels = [_label(o1), _label(o2)]
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[o1, o2],
        labels=labels,
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is not ProducerReadinessStatus.CHALLENGE_INPUT_READY
    assert cohort.session_count == 0
    assert cohort.observation_validation.has_contract_corruption is True
    assert any(
        "session_date_window_mismatch" in r for r in cohort.observation_validation.invalid_reasons
    )


def test_ticker_window_mismatch_blocks_session() -> None:
    o = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id=COMPAT,
        cutoff_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
        universe_id=LOCKED_UNIVERSE_ID,
        window_id="BBCA:2026-07-01",
        decision_payload=_payload(session_date="2026-07-01", ticker="BBRI"),
        captured_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[o],
        labels=[],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert any("ticker_window_mismatch" in r for r in cohort.observation_validation.invalid_reasons)


def test_production_shaped_multi_session_can_reach_ready() -> None:
    obs = [
        _observation(day=1, ticker="BBCA"),
        _observation(day=2, ticker="BBRI"),
    ]
    labels = [_label(obs[0])]
    # Bound: window_id ticker:date matches payload.
    assert obs[0].window_id == "BBCA:2026-07-01"
    assert obs[0].decision_payload["session_date"] == "2026-07-01"
    assert obs[0].decision_payload["ticker"] == "BBCA"
    assert obs[1].window_id == "BBRI:2026-07-02"
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=labels,
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.session_count == 2
    assert cohort.observation_validation.has_contract_corruption is False
    assert cohort.label_validation.has_integrity_corruption is False
    assert cohort.labels_by_horizon["H10"].conflict == 0
    assert cohort.labels_by_horizon["H10"].available >= 1
    assert cohort.producer_status is ProducerReadinessStatus.CHALLENGE_INPUT_READY


def test_multi_row_h10_path_label_conflict_blocks_ready_fail_closed() -> None:
    """Multi-row path labels for one observation are integrity corruption.

    Production-shaped cohort: verified v2 snapshots, two sessions, observation A
    with two distinct H10 labels, observation B with one clean AVAILABLE H10.
    Must be BLOCKED_POLICY (not CHALLENGE_INPUT_READY); conflicted obs must not
    contribute to AVAILABLE H10.
    """
    obs_a = _observation(day=1, ticker="BBCA")
    obs_b = _observation(day=2, ticker="BBRI")
    # Two digest-valid H10 *rows* for the same observation. label_id is
    # (observation_id, contract) so ids may match; digests must differ.
    # Fingerprints must still recompute against the parent observation digest.
    conflict_a1 = _label(obs_a, outcome="SUCCESS")
    conflict_a2 = _label(obs_a, outcome="FAILURE")
    assert conflict_a1.observation_id == conflict_a2.observation_id
    assert conflict_a1.contract_id is conflict_a2.contract_id
    assert conflict_a1.fingerprint == conflict_a2.fingerprint
    assert conflict_a1.artifact_digest != conflict_a2.artifact_digest
    clean_b = _label(obs_b, outcome="SUCCESS")

    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[obs_a, obs_b],
        labels=[conflict_a1, conflict_a2, clean_b],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )

    assert cohort.session_count == 2
    assert cohort.observation_validation.has_contract_corruption is False
    assert cohort.label_validation.has_integrity_corruption is True
    assert cohort.labels_by_horizon["H10"].conflict >= 1
    # Conflicted observation must not count as AVAILABLE; sibling clean row still
    # tallied but cannot open READY when integrity corruption is present.
    assert cohort.labels_by_horizon["H10"].available == 1
    assert any(
        "path_label_conflict" in r and "H10" in r for r in cohort.label_validation.invalid_reasons
    )
    assert cohort.producer_status is not ProducerReadinessStatus.CHALLENGE_INPUT_READY
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY


def test_multi_row_h3_path_label_conflict_also_blocks_ready() -> None:
    """H3 multi-row conflict is authority-bearing even when H10 is clean."""

    obs_a = _observation(day=1, ticker="BBCA")
    obs_b = _observation(day=2, ticker="BBRI")
    h3_a1 = _label(obs_a, contract=LearningContractId.ACCUM_3D_LABEL)
    h3_a2 = _label(
        obs_a,
        contract=LearningContractId.ACCUM_3D_LABEL,
        outcome="FAILURE",
    )
    h10_b = _label(obs_b)

    counts = count_labels_by_horizon(
        observation_ids=[obs_a.observation_id, obs_b.observation_id],
        labels=[h3_a1, h3_a2, h10_b],
        observations_by_id={obs_a.observation_id: obs_a, obs_b.observation_id: obs_b},
    )
    assert counts.has_integrity_corruption is True
    assert counts.counts_by_horizon["H3"].conflict >= 1
    assert counts.counts_by_horizon["H10"].available == 1
    assert counts.counts_by_horizon["H10"].conflict == 0

    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[obs_a, obs_b],
        labels=[h3_a1, h3_a2, h10_b],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert cohort.label_validation.has_integrity_corruption is True
    assert any("path_label_conflict:H3" in r for r in cohort.label_validation.invalid_reasons)


def test_provenance_latest_session_mismatch_blocks() -> None:
    payload = _payload(session_date="2026-07-01", ticker="BBCA")
    payload["shared"]["provenance"]["latest_completed_session"] = "2026-07-02"
    o = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id=COMPAT,
        cutoff_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
        universe_id=LOCKED_UNIVERSE_ID,
        window_id="BBCA:2026-07-01",
        decision_payload=payload,
        captured_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[o],
        labels=[],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert any(
        "provenance_session_mismatch" in r for r in cohort.observation_validation.invalid_reasons
    )


def _rehash_observation(obs: LearningObservation) -> LearningObservation:
    """Recompute digest after field mutation so only the intended semantic fails."""
    import src.domain.value_objects.learning_artifacts as la

    digest = la.artifact_digest(
        la._artifact_payload(obs, id_field="observation_id", digest_field="artifact_digest")
    )
    return replace(obs, artifact_digest=digest)


def test_outer_schema_version_999_blocks_ready() -> None:
    o1 = _observation(day=1)
    o2 = _observation(day=2, ticker="BBRI")
    bad1 = _rehash_observation(replace(o1, schema_version=999))
    bad2 = _rehash_observation(replace(o2, schema_version=999))
    # Digests valid for schema 999; semantics still wrong for production.
    from src.domain.value_objects.learning_artifacts import validate_artifact_integrity

    validate_artifact_integrity(bad1, id_field="observation_id")
    labels = [_label(bad1), _label(bad2)]
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[bad1, bad2],
        labels=labels,
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is not ProducerReadinessStatus.CHALLENGE_INPUT_READY
    assert cohort.session_count == 0
    assert any("outer_schema_version" in r for r in cohort.observation_validation.invalid_reasons)


def test_payload_schema_version_999_blocks_ready() -> None:
    o1 = _observation(day=1)
    o2 = _observation(day=2, ticker="BBRI")
    p1 = dict(o1.decision_payload)
    p1["schema_version"] = 999
    p2 = dict(o2.decision_payload)
    p2["schema_version"] = 999
    bad1 = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract=o1.policy_contract,
        horizon_contract=o1.horizon_contract,
        compatibility_id=COMPAT,
        cutoff_at=o1.cutoff_at,
        universe_id=o1.universe_id,
        window_id=o1.window_id,
        decision_payload=p1,
        captured_at=o1.captured_at,
    )
    bad2 = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract=o2.policy_contract,
        horizon_contract=o2.horizon_contract,
        compatibility_id=COMPAT,
        cutoff_at=o2.cutoff_at,
        universe_id=o2.universe_id,
        window_id=o2.window_id,
        decision_payload=p2,
        captured_at=o2.captured_at,
    )
    from src.domain.value_objects.learning_artifacts import validate_artifact_integrity

    validate_artifact_integrity(bad1, id_field="observation_id")
    labels = [_label(bad1)]
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[bad1, bad2],
        labels=labels,
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is not ProducerReadinessStatus.CHALLENGE_INPUT_READY
    assert any("payload_schema_version" in r for r in cohort.observation_validation.invalid_reasons)


def test_wrong_workflow_blocks_ready() -> None:
    o = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id=COMPAT,
        cutoff_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
        universe_id=LOCKED_UNIVERSE_ID,
        window_id="BBCA:2026-07-01",
        decision_payload=_payload(
            session_date="2026-07-01", ticker="BBCA", workflow="screen_accum"
        ),
        captured_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[o, _observation(day=2, ticker="BBRI")],
        labels=[_label(o)],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert any("workflow:" in r for r in cohort.observation_validation.invalid_reasons)


def test_invalid_observation_contributes_zero_labels_actions_and_readiness() -> None:
    """P0: invalid rows block the cohort but contribute zero diagnostics authority.

    Adversarial shape: identity-complete observation with wrong workflow that still
    carries Action=ENTER, setup-readiness=INCOMPLETE, and an AVAILABLE H10 label.
    Matrix rule: invalid observations contribute zero labels, Actions, or readiness.
    """
    invalid = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id=COMPAT,
        cutoff_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
        universe_id=LOCKED_UNIVERSE_ID,
        window_id="BBCA:2026-07-01",
        decision_payload=_payload(
            session_date="2026-07-01",
            ticker="BBCA",
            workflow="screen_accum",
            action="ENTER",
            readiness="INCOMPLETE",
        ),
        captured_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    assert extract_action_from_payload(invalid.decision_payload) == "ENTER"
    assert extract_setup_readiness_status_from_payload(invalid.decision_payload) == "INCOMPLETE"
    # Solo invalid row: block closed; no Action/readiness/label contribution.
    solo = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[invalid],
        labels=[_label(invalid)],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert solo.observation_validation.has_contract_corruption is True
    assert solo.observation_validation.invalid_observation_count == 1
    assert solo.observation_validation.validated_observation_ids == ()
    assert any("workflow:" in r for r in solo.observation_validation.invalid_reasons)
    assert solo.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert solo.labels_by_horizon["H10"].available == 0
    assert solo.labels_by_horizon["H10"].unavailable == 0
    assert solo.labels_by_horizon["H10"].conflict == 0
    # Insufficient_horizon counts only against validated observation IDs (none).
    assert solo.labels_by_horizon["H10"].insufficient_horizon == 0
    assert solo.action_distribution == {}
    assert solo.setup_readiness_present == 0
    assert solo.setup_readiness_missing == 0
    assert solo.setup_readiness_state_distribution == {}

    # Co-present valid row still contributes its own Action/readiness; invalid does not.
    valid = _observation(day=2, ticker="BBRI", action="WATCH", readiness=None)
    mixed = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[invalid, valid],
        labels=[_label(invalid), _label(valid)],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert mixed.observation_validation.has_contract_corruption is True
    assert mixed.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert mixed.observation_validation.validated_observation_ids == (valid.observation_id,)
    # Only the valid row's AVAILABLE H10 counts; invalid row's label is excluded.
    assert mixed.labels_by_horizon["H10"].available == 1
    assert "ENTER" not in mixed.action_distribution
    assert mixed.action_distribution == {"WATCH": 1}
    assert mixed.setup_readiness_present == 0
    assert mixed.setup_readiness_missing == 1
    assert mixed.setup_readiness_state_distribution == {"null": 1}
    assert "INCOMPLETE" not in mixed.setup_readiness_state_distribution


def test_wrong_horizon_primary_blocks_ready() -> None:
    o = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id=COMPAT,
        cutoff_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
        universe_id=LOCKED_UNIVERSE_ID,
        window_id="BBCA:2026-07-01",
        decision_payload=_payload(
            session_date="2026-07-01", ticker="BBCA", horizon_primary="open_30m"
        ),
        captured_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[o, _observation(day=2, ticker="BBRI")],
        labels=[_label(o)],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert any("horizon_primary:" in r for r in cohort.observation_validation.invalid_reasons)


def test_missing_provenance_blocks_ready() -> None:
    o = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id=COMPAT,
        cutoff_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
        universe_id=LOCKED_UNIVERSE_ID,
        window_id="BBCA:2026-07-01",
        decision_payload=_payload(session_date="2026-07-01", ticker="BBCA", with_provenance=False),
        captured_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[o, _observation(day=2, ticker="BBRI")],
        labels=[_label(o)],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert any(
        "shared.provenance_missing" in r for r in cohort.observation_validation.invalid_reasons
    )


def test_missing_features_window_blocks_ready() -> None:
    payload = _payload(session_date="2026-07-01", ticker="BBCA")
    del payload["features_by_window"]["90"]
    o = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id=COMPAT,
        cutoff_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
        universe_id=LOCKED_UNIVERSE_ID,
        window_id="BBCA:2026-07-01",
        decision_payload=payload,
        captured_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[o, _observation(day=2, ticker="BBRI")],
        labels=[_label(o)],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert any(
        "features_by_window_keys" in r for r in cohort.observation_validation.invalid_reasons
    )


def test_schema9_without_binding_is_legacy_raw_only_even_with_snapshots() -> None:
    """Schema-9 historical rows never grant CHALLENGE_INPUT_READY (Option A)."""
    obs = [
        _legacy_observation(day=1),
        _legacy_observation(day=2, ticker="BBRI"),
    ]
    labels = [_label(obs[0])]
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=labels,
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.snapshot.active_set_verified is True
    assert cohort.observation_validation.has_current_population_authority is False
    assert cohort.observation_validation.legacy_observation_count == 2
    assert cohort.observation_validation.has_contract_corruption is False
    assert cohort.producer_status is ProducerReadinessStatus.LEGACY_RAW_ONLY
    assert cohort.producer_status is not ProducerReadinessStatus.CHALLENGE_INPUT_READY


def test_tampered_membership_count_and_named_digest_block_ready() -> None:
    """Adversarial: count=999 + invented named digest must not grant READY.

    Shape checks (positive count, hash-shaped digest, membership==universe_id)
    alone are insufficient after observation rehash.
    """
    from src.domain.value_objects.learning_artifacts import (
        stamp_universe_membership_id,
        validate_artifact_integrity,
    )

    invented = stamp_universe_membership_id(["ZZZZ", "YYYY"])

    def _tamper(obs: LearningObservation) -> LearningObservation:
        payload = dict(obs.decision_payload)
        binding = dict(payload["population_binding"])
        assert binding["membership_count"] == len(binding["membership_tickers"])
        binding["membership_count"] = 999
        binding["named_universe_digest"] = invented
        payload["population_binding"] = binding
        out = LearningObservation.create(
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            policy_contract="accumulation_discovery.policy.v1",
            horizon_contract="accum_10d",
            compatibility_id=COMPAT,
            cutoff_at=obs.cutoff_at,
            universe_id=obs.universe_id,
            window_id=obs.window_id,
            decision_payload=payload,
            captured_at=obs.captured_at,
        )
        validate_artifact_integrity(out, id_field="observation_id")
        return out

    tampered_a = _tamper(_observation(day=1, action="WATCH", readiness=None))
    tampered_b = _tamper(_observation(day=2, ticker="BBRI", action="ENTER", readiness="INCOMPLETE"))
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[tampered_a, tampered_b],
        labels=[_label(tampered_a)],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    reasons = " ".join(cohort.observation_validation.invalid_reasons)
    assert cohort.observation_validation.has_current_population_authority is False
    assert cohort.observation_validation.has_contract_corruption is True
    assert "membership_count" in reasons or "named_universe_digest" in reasons
    assert cohort.session_count == 0
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert cohort.producer_status is not ProducerReadinessStatus.CHALLENGE_INPUT_READY


def test_mixed_schema9_and_schema10_cohort_is_blocked_not_ready() -> None:
    """Cohorts never mix: schema-9 + schema-10 coexistence is fail-closed.

    Adversarial shape: 2 valid current schema-10 rows + 1 valid schema-9 legacy
    row + verified active snapshots + AVAILABLE H10. Must not become READY
    merely because has_current_population_authority is true from the current
    subset.
    """
    current = [
        _observation(day=1, action="WATCH", readiness=None),
        _observation(day=2, ticker="BBRI", action="ENTER", readiness="INCOMPLETE"),
    ]
    legacy = _legacy_observation(day=3, ticker="BBCA")
    assert current[0].decision_payload["schema_version"] == CANDIDATE_OBSERVATION_SCHEMA_VERSION
    assert legacy.decision_payload["schema_version"] == LEGACY_CANDIDATE_OBSERVATION_SCHEMA_VERSION
    obs = [*current, legacy]
    labels = [_label(current[0])]
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=labels,
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    ov = cohort.observation_validation
    assert ov.has_current_population_authority is True
    assert ov.legacy_observation_count == 1
    assert ov.valid_observation_count == 2
    assert ov.has_contract_corruption is True
    assert any("mixed_schema_cohort" in r for r in ov.invalid_reasons)
    assert cohort.snapshot.active_set_verified is True
    assert cohort.labels_by_horizon["H10"].available == 1
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert cohort.producer_status is not ProducerReadinessStatus.CHALLENGE_INPUT_READY
    assert cohort.producer_status is not ProducerReadinessStatus.LEGACY_RAW_ONLY
    assert cohort.producer_status is not ProducerReadinessStatus.COLLECTING


def test_current_schema_missing_population_binding_is_blocked_not_ready() -> None:
    o1 = _observation(day=1, with_population_binding=False)
    o2 = _observation(day=2, ticker="BBRI", with_population_binding=False)
    assert "population_binding" not in o1.decision_payload
    assert o1.decision_payload["schema_version"] == CANDIDATE_OBSERVATION_SCHEMA_VERSION
    labels = [_label(o1)]
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[o1, o2],
        labels=labels,
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY


def test_incomplete_schema10_without_attested_tickers_is_non_current_not_redefined() -> None:
    """P1: schema-10 incomplete shape is non-current, not silently current.

    Prior schema-10 rows without membership_tickers/named_universe_tickers must
    not be revalidated as the current schema (which would force BLOCKED_POLICY
    as if they were corrupt current rows). They classify as LEGACY_RAW_ONLY.
    """
    from src.domain.value_objects.signal_artifact_schema import (
        INCOMPLETE_POPULATION_ATTESTATION_CANDIDATE_OBSERVATION_SCHEMA_VERSION,
    )

    incomplete_schema = INCOMPLETE_POPULATION_ATTESTATION_CANDIDATE_OBSERVATION_SCHEMA_VERSION
    assert incomplete_schema == 10
    assert incomplete_schema != CANDIDATE_OBSERVATION_SCHEMA_VERSION

    def _schema10_incomplete(day: int, ticker: str = "BBCA") -> LearningObservation:
        # Shape that schema-10 writers could have persisted before attested tickers:
        # schema_version=10, no membership_tickers / named_universe_tickers fields.
        obs = _observation(
            day=day,
            ticker=ticker,
            schema_version=incomplete_schema,
            with_population_binding=False,
        )
        payload = dict(obs.decision_payload)
        # Optional: digest-only binding without attested tickers (incomplete authority).
        payload["population_binding"] = {
            "schema_version": 1,
            "contract_id": "population.accum.lq45_current_roster_pit_tradable.v1",
            "population_name": "lq45",
            "membership_session": f"2026-07-{day:02d}",
            "membership_digest": obs.universe_id,
            "membership_count": 5,
            "named_universe_digest": stamp_universe_membership_id(NAMED_ROSTER),
            "tradable_membership_contract": "pit_tradable.candle_presence.v1",
            "pit_tradable_lookback_sessions": 10,
            "benchmark_symbol": "IHSG",
            "producer_source_revision": PRODUCER_REV,
            # deliberately omit membership_tickers / named_universe_tickers
        }
        out = LearningObservation.create(
            purpose=obs.purpose,
            policy_contract=obs.policy_contract,
            horizon_contract=obs.horizon_contract,
            compatibility_id=obs.compatibility_id,
            cutoff_at=obs.cutoff_at,
            universe_id=obs.universe_id,
            window_id=obs.window_id,
            decision_payload=payload,
            captured_at=obs.captured_at,
        )
        return out

    obs = [
        _schema10_incomplete(1, "BBCA"),
        _schema10_incomplete(2, "BBRI"),
    ]
    assert obs[0].decision_payload["schema_version"] == 10
    assert "membership_tickers" not in obs[0].decision_payload.get("population_binding", {})

    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[_label(obs[0])],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    ov = cohort.observation_validation
    # Not revalidated as current → not contract corruption for missing tickers.
    assert ov.has_current_population_authority is False
    assert ov.has_contract_corruption is False
    assert ov.legacy_observation_count == 2
    assert ov.valid_observation_count == 0
    assert cohort.producer_status is ProducerReadinessStatus.LEGACY_RAW_ONLY
    assert cohort.producer_status is not ProducerReadinessStatus.CHALLENGE_INPUT_READY
    assert cohort.producer_status is not ProducerReadinessStatus.BLOCKED_POLICY


def test_hex_only_universe_without_binding_is_not_population_authority() -> None:
    """64-hex universe_id alone never yields CHALLENGE_INPUT_READY."""
    assert len(LOCKED_UNIVERSE_ID) == 64
    o1 = _observation(day=1, with_population_binding=False)
    o2 = _observation(day=2, ticker="BBRI", with_population_binding=False)
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[o1, o2],
        labels=[_label(o1)],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is not ProducerReadinessStatus.CHALLENGE_INPUT_READY
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY


def test_bad_decision_at_does_not_inflate_session_count_or_ready() -> None:
    o1 = _observation(day=1, decision_at="not-a-timestamp")
    o2 = _observation(day=2, ticker="BBRI", decision_at="not-a-timestamp")
    # Same July-1 cutoff identity with inventable session claim already bound;
    # malformed decision_at must fail closed.
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[o1, o2],
        labels=[_label(o1)],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is not ProducerReadinessStatus.CHALLENGE_INPUT_READY
    assert cohort.session_count == 0
    assert any("decision_at" in r for r in cohort.observation_validation.invalid_reasons)


def test_captured_at_mismatch_blocks_ready() -> None:
    at = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    other = datetime(2026, 7, 1, 15, 0, tzinfo=timezone.utc)
    payload = _payload(session_date="2026-07-01", ticker="BBCA", captured_at=other)
    o = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id=COMPAT,
        cutoff_at=at,
        universe_id=LOCKED_UNIVERSE_ID,
        window_id="BBCA:2026-07-01",
        decision_payload=payload,
        captured_at=at,
    )
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[o, _observation(day=2, ticker="BBRI")],
        labels=[_label(o)],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert any("captured_at_mismatch" in r for r in cohort.observation_validation.invalid_reasons)


def test_analysis_as_of_mismatch_blocks_ready() -> None:
    payload = _payload(session_date="2026-07-01", ticker="BBCA")
    payload["shared"]["provenance"]["analysis_as_of"] = "2026-07-03"
    o = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id=COMPAT,
        cutoff_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
        universe_id=LOCKED_UNIVERSE_ID,
        window_id="BBCA:2026-07-01",
        decision_payload=payload,
        captured_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[o, _observation(day=2, ticker="BBRI")],
        labels=[_label(o)],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert any(
        "analysis_as_of_session_mismatch" in r
        for r in cohort.observation_validation.invalid_reasons
    )


def test_available_h10_metrics_ticker_mismatch_blocks_not_challenge_input_ready() -> None:
    """P0: AVAILABLE H10 with metrics.ticker ≠ observation ticker is corruption.

    Adversarial: BBCA observation + full READY shape except H10 metrics.ticker=TLKM.
    Must not stay CHALLENGE_INPUT_READY; available tally must not include the row.
    """
    obs = [
        _observation(day=1, ticker="BBCA", action="WATCH", readiness=None),
        _observation(day=2, ticker="BBRI", action="ENTER", readiness="INCOMPLETE"),
    ]
    assert obs[0].decision_payload["ticker"] == "BBCA"
    session = observation_session_date(obs[0])
    assert session is not None
    mismatched = _available_metrics(
        ticker="TLKM",
        signal_date=session.isoformat(),
        horizon_days=10,
    )
    assert mismatched["ticker"] == "TLKM"
    bad_label = _label(obs[0], outcome="SUCCESS", metrics=mismatched)
    assert bad_label.availability is LabelAvailability.AVAILABLE
    assert bad_label.metrics["ticker"] == "TLKM"

    # Direct label counting path used by projection.

    counts = count_labels_by_horizon(
        observation_ids=[o.observation_id for o in obs],
        labels=[bad_label],
        observations_by_id={o.observation_id: o for o in obs},
    )
    assert counts.has_integrity_corruption is True
    assert counts.invalid_label_count == 1
    assert counts.counts_by_horizon["H10"].available == 0
    assert any("metrics.ticker_mismatch" in r for r in counts.invalid_reasons)

    # Solo mismatched H10: READY-shaped cohort must not become CHALLENGE_INPUT_READY.
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[bad_label],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.label_validation.has_integrity_corruption is True
    assert cohort.labels_by_horizon["H10"].available == 0
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert cohort.producer_status is not ProducerReadinessStatus.CHALLENGE_INPUT_READY
    assert any("metrics.ticker_mismatch" in r for r in cohort.label_validation.invalid_reasons)

    # Co-present valid H10 on the other observation: only the valid row tallies.
    good = _label(obs[1], outcome="SUCCESS")
    assert good.metrics["ticker"] == "BBRI"
    mixed = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[bad_label, good],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert mixed.label_validation.has_integrity_corruption is True
    assert mixed.labels_by_horizon["H10"].available == 1
    assert mixed.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert mixed.producer_status is not ProducerReadinessStatus.CHALLENGE_INPUT_READY


def test_unavailable_invented_reason_is_corruption_not_valid_unavailable() -> None:
    """P0: invented unavailable_reason is integrity corruption, not a valid UNAVAILABLE.

    Control: corporate_action_in_window (production terminal) still tallies unavailable.
    """

    obs = [
        _observation(day=1, ticker="BBCA"),
        _observation(day=2, ticker="BBRI"),
    ]
    invented = _label(
        obs[0],
        availability=LabelAvailability.UNAVAILABLE,
        outcome=None,
        metrics={"unavailable_reason": "invented_reason"},
    )
    assert invented.availability is LabelAvailability.UNAVAILABLE
    assert invented.metrics["unavailable_reason"] == "invented_reason"

    counts = count_labels_by_horizon(
        observation_ids=[o.observation_id for o in obs],
        labels=[invented],
        observations_by_id={o.observation_id: o for o in obs},
    )
    assert counts.has_integrity_corruption is True
    assert counts.counts_by_horizon["H10"].unavailable == 0
    assert counts.counts_by_horizon["H10"].available == 0
    assert any("metrics.unavailable_reason_unsupported" in r for r in counts.invalid_reasons)

    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[invented],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.label_validation.has_integrity_corruption is True
    assert cohort.labels_by_horizon["H10"].unavailable == 0
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert any(
        "metrics.unavailable_reason_unsupported" in r
        for r in cohort.label_validation.invalid_reasons
    )

    # Control: production terminal reason still counts as unavailable when otherwise valid.
    supported = _label(
        obs[0],
        availability=LabelAvailability.UNAVAILABLE,
        outcome=None,
        metrics={"unavailable_reason": "corporate_action_in_window"},
    )
    control_counts = count_labels_by_horizon(
        observation_ids=[o.observation_id for o in obs],
        labels=[supported],
        observations_by_id={o.observation_id: o for o in obs},
    )
    assert control_counts.has_integrity_corruption is False
    assert control_counts.counts_by_horizon["H10"].unavailable == 1
    assert control_counts.invalid_label_count == 0

    control = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[supported],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert control.label_validation.has_integrity_corruption is False
    assert control.labels_by_horizon["H10"].unavailable == 1
    # Zero AVAILABLE H10 → not READY; corporate-action unavailable alone is COLLECTING.
    assert control.producer_status is ProducerReadinessStatus.COLLECTING
    assert control.producer_status is not ProducerReadinessStatus.CHALLENGE_INPUT_READY
    assert control.producer_status is not ProducerReadinessStatus.BLOCKED_POLICY


def test_available_metrics_reject_coerced_types_and_extra_keys() -> None:
    """P0: day indices must be exact int; entry price exact numeric; metric set closed.

    Adversarial label with days_to_peak=1.9, entry_reference_price=\"100.0\", and an
    invented extra key must not count as AVAILABLE and must not yield
    CHALLENGE_INPUT_READY. Honest exact-type metrics still pass.
    """

    obs = [
        _observation(day=1, ticker="BBCA", action="WATCH", readiness=None),
        _observation(day=2, ticker="BBRI", action="ENTER", readiness="INCOMPLETE"),
    ]
    session = observation_session_date(obs[0])
    assert session is not None
    coerced = _available_metrics(
        ticker="BBCA",
        signal_date=session.isoformat(),
        horizon_days=10,
        entry_price=100.0,
    )
    coerced["days_to_peak"] = 1.9
    coerced["entry_reference_price"] = "100.0"
    coerced["invented_extra"] = "anything"
    bad_label = _label(obs[0], outcome="SUCCESS", metrics=coerced)

    counts = count_labels_by_horizon(
        observation_ids=[o.observation_id for o in obs],
        labels=[bad_label],
        observations_by_id={o.observation_id: o for o in obs},
    )
    assert counts.has_integrity_corruption is True
    assert counts.counts_by_horizon["H10"].available == 0
    reasons = " ".join(counts.invalid_reasons)
    assert "metrics.days_to_peak_not_int" in reasons
    assert "metrics.entry_reference_price_invalid" in reasons
    assert "metrics_extra_fields" in reasons
    assert "invented_extra" in reasons

    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[bad_label],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is not ProducerReadinessStatus.CHALLENGE_INPUT_READY
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert cohort.labels_by_horizon["H10"].available == 0

    # Control: exact production types still READY when the rest of the cohort is valid.
    good_h10 = _label(obs[0], outcome="SUCCESS")
    good_h10_b = _label(obs[1], outcome="SUCCESS")
    control = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[good_h10, good_h10_b],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert control.label_validation.has_integrity_corruption is False
    assert control.labels_by_horizon["H10"].available == 2
    assert control.producer_status is ProducerReadinessStatus.CHALLENGE_INPUT_READY


def test_label_schema_999_and_banana_outcome_and_invented_fingerprint_block() -> None:
    obs = [_observation(day=1), _observation(day=2, ticker="BBRI")]
    valid = _label(obs[0], outcome="SUCCESS")
    bad = _rehash_label(
        replace(
            valid,
            schema_version=999,
            outcome="BANANA",
            fingerprint="invented-fingerprint",
        )
    )
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[bad],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    reasons = " ".join(cohort.label_validation.invalid_reasons)
    assert "label_schema_version" in reasons or "outcome_vocabulary" in reasons
    assert "fingerprint_mismatch" in reasons or "invented" in reasons or "BANANA" in reasons
    assert cohort.labels_by_horizon["H10"].available == 0


def test_incompatible_preopen_label_family_blocks_cohort() -> None:
    """Pre-open label on accumulation observation fails closed (not ignored)."""
    obs = [_observation(day=1), _observation(day=2, ticker="BBRI")]
    # Construct pre-open label linked to accum observation id.
    pre = LearningOutcomeLabel.create(
        contract_id=LearningContractId.PRE_OPEN_LABEL,
        observation_id=obs[0].observation_id,
        outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
        availability=LabelAvailability.AVAILABLE,
        outcome="SUCCESS",
        metrics={"return_pct": 1.0},
        fingerprint=recompute_path_label_fingerprint(
            observation_id=obs[0].observation_id,
            observation_artifact_digest=obs[0].artifact_digest,
            label_contract=LearningContractId.PRE_OPEN_LABEL,
        ),
        labeled_at=NOW,
    )
    # Also include a clean H10 so only family incompatibility should block.
    clean = _label(obs[0], outcome="SUCCESS")
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[pre, clean],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY
    assert any("incompatible_label_family" in r for r in cohort.label_validation.invalid_reasons)


def test_snapshot_schema_version_999_fails_active_set_verified() -> None:
    snaps = list(_full_v2_set())
    bad = _rehash_snapshot(replace(snaps[0], schema_version=999))
    snaps[0] = bad
    report = verify_snapshot_binding(
        snaps,
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
        compatibility_id=COMPAT,
    )
    assert report.active_set_verified is False
    assert report.has_corruption is True

    obs = [_observation(day=1), _observation(day=2, ticker="BBRI")]
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[_label(obs[0])],
        snapshots=tuple(snaps),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.snapshot.active_set_verified is False
    assert cohort.producer_status is not ProducerReadinessStatus.CHALLENGE_INPUT_READY
    assert cohort.producer_status is ProducerReadinessStatus.BLOCKED_POLICY


def _rehash_snapshot(snap: ProductionPolicySnapshot) -> ProductionPolicySnapshot:
    # schema_version is outside payload_digest; integrity checks columns only.
    return snap


def test_candidate_observation_schema_version_is_11_with_attested_tickers() -> None:
    from src.domain.value_objects.learning_artifacts import (
        ACCUM_POPULATION_BINDING_SCHEMA_VERSION,
        LEGACY_ACCUM_POPULATION_BINDING_SCHEMA_VERSION,
    )
    from src.domain.value_objects.signal_artifact_schema import (
        INCOMPLETE_POPULATION_ATTESTATION_CANDIDATE_OBSERVATION_SCHEMA_VERSION,
    )

    assert CANDIDATE_OBSERVATION_SCHEMA_VERSION == 11
    assert INCOMPLETE_POPULATION_ATTESTATION_CANDIDATE_OBSERVATION_SCHEMA_VERSION == 10
    assert LEGACY_CANDIDATE_OBSERVATION_SCHEMA_VERSION == 9
    assert ACCUM_POPULATION_BINDING_SCHEMA_VERSION == 2
    assert LEGACY_ACCUM_POPULATION_BINDING_SCHEMA_VERSION == 1
    o = _observation(day=1)
    assert o.decision_payload["schema_version"] == 11
    assert "population_binding" in o.decision_payload
    binding = AccumPopulationBinding.from_mapping(o.decision_payload["population_binding"])
    assert binding.schema_version == 2
    assert binding.membership_digest == o.universe_id
    assert binding.contract_id.startswith("population.accum.")
    assert binding.membership_tickers
    assert binding.named_universe_tickers


def test_build_session_observation_payload_requires_population_binding() -> None:
    from src.application.services.accumulation_observation_fingerprint import (
        build_session_observation_payload,
    )

    features = {"7": {}, "30": {}, "90": {}}
    shared = {"current_price": "100"}
    try:
        build_session_observation_payload(
            ticker="BBCA",
            session_date=date(2026, 7, 1),
            captured_at=NOW,
            canonical_window=7,
            features_by_window=features,
            shared=shared,
        )
        raise AssertionError("expected population_binding required")
    except ValueError as exc:
        assert "population_binding" in str(exc)

    payload = build_session_observation_payload(
        ticker="BBCA",
        session_date=date(2026, 7, 1),
        captured_at=NOW,
        canonical_window=7,
        features_by_window=features,
        shared=shared,
        population_binding=_binding_for_session("2026-07-01"),
    )
    assert payload["schema_version"] == 11
    assert payload["population_binding"]["membership_session"] == "2026-07-01"
    assert payload["population_binding"]["schema_version"] == 2
    assert "membership_tickers" in payload["population_binding"]
    assert "named_universe_tickers" in payload["population_binding"]


def test_overlong_h10_label_window_rejected_not_challenge_input_ready() -> None:
    """Adversarial: multi-month H10 window must not grant AVAILABLE H10 authority.

    P0: readiness previously accepted any ordered window after signal with
    days_to_* in 1..N. An H10 span 2026-07-20..2026-12-31 must fail exact
    session-window proof and cannot alone elevate the cohort to READY.
    """
    obs = [
        _observation(day=1, action="WATCH", readiness=None),
        _observation(day=2, ticker="BBRI", action="ENTER", readiness="INCOMPLETE"),
    ]
    metrics = _available_metrics(
        ticker="BBCA",
        signal_date="2026-07-01",
        horizon_days=10,
        label_window_start="2026-07-20",
        label_window_end="2026-12-31",
    )
    overlong = _label(obs[0], metrics=metrics)
    counts = count_labels_by_horizon(
        observation_ids=[o.observation_id for o in obs],
        labels=[overlong],
        observations_by_id={o.observation_id: o for o in obs},
    )
    assert counts.counts_by_horizon["H10"].available == 0
    assert counts.invalid_label_count >= 1
    assert any("label_window_not_first_n_sessions" in r for r in counts.invalid_reasons)

    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[overlong],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.labels_by_horizon["H10"].available == 0
    assert cohort.producer_status is not ProducerReadinessStatus.CHALLENGE_INPUT_READY
    assert any(
        "label_window_not_first_n_sessions" in r for r in cohort.label_validation.invalid_reasons
    )


def test_exact_n_session_windows_accepted_for_h3_h10_h20() -> None:
    """Exact first N sessions after signal pass the window gate."""
    obs = [
        _observation(day=1, action="WATCH", readiness=None),
        _observation(day=2, ticker="BBRI", action="ENTER", readiness="INCOMPLETE"),
    ]
    contracts = (
        (LearningContractId.ACCUM_3D_LABEL, 3, "H3"),
        (LearningContractId.ACCUM_10D_LABEL, 10, "H10"),
        (LearningContractId.ACCUM_20D_LABEL, 20, "H20"),
    )
    labels: list[LearningOutcomeLabel] = []
    for contract, horizon, _key in contracts:
        metrics = _available_metrics(
            ticker="BBCA",
            signal_date="2026-07-01",
            horizon_days=horizon,
        )
        start = date.fromisoformat(metrics["label_window_start"])
        end = date.fromisoformat(metrics["label_window_end"])
        expected = DEFAULT_SESSION_CALENDAR.first_n_sessions_after(date(2026, 7, 1), horizon)
        assert expected is not None
        assert start == expected[0] and end == expected[-1]
        labels.append(_label(obs[0], contract=contract, metrics=metrics))

    counts = count_labels_by_horizon(
        observation_ids=[o.observation_id for o in obs],
        labels=labels,
        observations_by_id={o.observation_id: o for o in obs},
    )
    for _contract, _horizon, key in contracts:
        assert counts.counts_by_horizon[key].available == 1, key
    assert counts.invalid_label_count == 0
    assert not any("label_window_not_first_n_sessions" in r for r in counts.invalid_reasons)

    # Primary H10 alone still enables READY when other gates pass.
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[labels[1]],  # H10
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
    )
    assert cohort.labels_by_horizon["H10"].available == 1
    assert cohort.producer_status is ProducerReadinessStatus.CHALLENGE_INPUT_READY


def test_weekend_label_window_endpoint_rejected() -> None:
    """Endpoints that land on weekends are not market sessions."""
    obs = [_observation(day=1), _observation(day=2, ticker="BBRI")]
    # 2026-07-02 (Thu) .. 2026-07-11 (Sat) is the old calendar-day H10 shortcut.
    metrics = _available_metrics(
        ticker="BBCA",
        signal_date="2026-07-01",
        horizon_days=10,
        label_window_start="2026-07-02",
        label_window_end="2026-07-11",
    )
    label = _label(obs[0], metrics=metrics)
    counts = count_labels_by_horizon(
        observation_ids=[o.observation_id for o in obs],
        labels=[label],
        observations_by_id={o.observation_id: o for o in obs},
    )
    assert counts.counts_by_horizon["H10"].available == 0
    joined = " ".join(counts.invalid_reasons)
    assert "label_window_not_first_n_sessions" in joined


def test_holiday_crossing_and_shifted_window_fail_weekday_approx_path() -> None:
    """P0: first actual N sessions required — weekday length alone is not authority.

    Case A — holiday: Thu 2026-07-02 is a non-session. Honest H10 starts Fri
    2026-07-03; weekday-approx window starting Thu must be rejected.

    Case B — shifted exact weekday length: signal 2026-07-01 with window
    2026-07-20..2026-07-31 has 10 weekdays but is not the first 10 sessions.

    Case C — honest holiday-aware first-N window is accepted.
    """
    # Proven sessions omit 2026-07-02 (Thursday holiday).
    holiday = date(2026, 7, 2)
    sessions = tuple(s for s in DEFAULT_SESSION_CALENDAR.sessions if s != holiday)
    holiday_cal = KnownTradingSessionCalendar(
        sessions=sessions,
        coverage_start=DEFAULT_SESSION_CALENDAR.coverage_start,
        coverage_end=DEFAULT_SESSION_CALENDAR.coverage_end,
    )
    signal = date(2026, 7, 1)
    honest = holiday_cal.first_n_sessions_after(signal, 10)
    assert honest is not None
    assert honest[0] == date(2026, 7, 3)  # skips holiday Thursday
    assert first_weekday_session_after(signal) == date(2026, 7, 2)  # weekday approx wrong

    obs = [
        _observation(day=1, action="WATCH", readiness=None),
        _observation(day=2, ticker="BBRI", action="ENTER", readiness="INCOMPLETE"),
    ]

    # Case A: weekday-approx window (starts on holiday) fails under holiday calendar.
    forged_holiday_start = _available_metrics(
        ticker="BBCA",
        signal_date=signal.isoformat(),
        horizon_days=10,
        label_window_start="2026-07-02",
        label_window_end=nth_weekday_session_on_or_after(date(2026, 7, 2), 10).isoformat(),
        session_calendar=holiday_cal,
    )
    # Prove weekday length would have accepted this forged span.
    assert (
        inclusive_weekday_sessions(
            date.fromisoformat(forged_holiday_start["label_window_start"]),
            date.fromisoformat(forged_holiday_start["label_window_end"]),
        )
        == 10
    )
    bad_holiday = _label(obs[0], metrics=forged_holiday_start)
    counts_a = count_labels_by_horizon(
        observation_ids=[o.observation_id for o in obs],
        labels=[bad_holiday],
        observations_by_id={o.observation_id: o for o in obs},
        session_calendar=holiday_cal,
    )
    assert counts_a.counts_by_horizon["H10"].available == 0
    assert any("label_window_not_first_n_sessions" in r for r in counts_a.invalid_reasons)

    # Case B: shifted exact-length weekday window after the real first-N span.
    shifted = _available_metrics(
        ticker="BBCA",
        signal_date=signal.isoformat(),
        horizon_days=10,
        label_window_start="2026-07-20",
        label_window_end="2026-07-31",
        session_calendar=holiday_cal,
    )
    assert (
        inclusive_weekday_sessions(
            date.fromisoformat(shifted["label_window_start"]),
            date.fromisoformat(shifted["label_window_end"]),
        )
        == 10
    )
    bad_shift = _label(obs[0], metrics=shifted)
    counts_b = count_labels_by_horizon(
        observation_ids=[o.observation_id for o in obs],
        labels=[bad_shift],
        observations_by_id={o.observation_id: o for o in obs},
        session_calendar=holiday_cal,
    )
    assert counts_b.counts_by_horizon["H10"].available == 0
    assert any("label_window_not_first_n_sessions" in r for r in counts_b.invalid_reasons)
    cohort_b = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[bad_shift],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
        session_calendar=holiday_cal,
    )
    assert cohort_b.producer_status is not ProducerReadinessStatus.CHALLENGE_INPUT_READY

    # Case C: honest first-N after holiday is READY.
    honest_metrics = _available_metrics(
        ticker="BBCA",
        signal_date=signal.isoformat(),
        horizon_days=10,
        label_window_start=honest[0].isoformat(),
        label_window_end=honest[-1].isoformat(),
        session_calendar=holiday_cal,
    )
    good = _label(obs[0], metrics=honest_metrics)
    # READY needs ≥2 sessions + ≥1 AVAILABLE H10; obs validation uses payload dates.
    counts_c = count_labels_by_horizon(
        observation_ids=[o.observation_id for o in obs],
        labels=[good],
        observations_by_id={o.observation_id: o for o in obs},
        session_calendar=holiday_cal,
    )
    assert counts_c.counts_by_horizon["H10"].available == 1, counts_c.invalid_reasons
    assert counts_c.invalid_label_count == 0
    cohort_c = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=obs,
        labels=[good],
        snapshots=_full_v2_set(),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
        session_calendar=holiday_cal,
    )
    assert cohort_c.labels_by_horizon["H10"].available == 1
    assert cohort_c.producer_status is ProducerReadinessStatus.CHALLENGE_INPUT_READY

    # Missing calendar fails closed (never weekday approx).
    no_cal = _count_labels_by_horizon_impl(
        observation_ids=[o.observation_id for o in obs],
        labels=[good],
        observations_by_id={o.observation_id: o for o in obs},
        session_calendar=None,
    )
    assert no_cal.counts_by_horizon["H10"].available == 0
    assert any("label_window_session_calendar_unproven" in r for r in no_cal.invalid_reasons)
