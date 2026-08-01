"""Active signal observation contracts for clean-break producer/consumer gates."""

# ADR-056: ticker-session observation with features_by_window (clean break).
ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT = "accumulation-discovery.v2"
PRE_OPEN_OBSERVATION_CONTRACT = "pre-open-open-30m.v3"

# Production ACCUMULATION_DISCOVERY write-path locks (persister + readiness).
# Must match AccumulationCandidateObservationPersister LearningObservation.create.
ACCUMULATION_DISCOVERY_POLICY_CONTRACT = "accumulation_discovery.policy.v1"
ACCUMULATION_DISCOVERY_HORIZON_CONTRACT = "accum_10d"
