# Future Quant And Machine-Learning Architecture

Status: future-facing architecture thought document  
Authority: non-authoritative for task ordering or evidence promotion  
Last revised: 2026-07-16

## 1. Purpose and authority

This document describes the long-term destination for evolving AI Saham into a
professional-grade quantitative research system that can host optional
machine-learning challengers.

It does **not** define current implementation order, declare current maturity,
or authorize model training, tuning, evidence promotion, or production use.
The authoritative execution sequence is:

- `tasks/backlog/signal_evidence_program.md`;
- task contracts in `tasks/backlog/audit_data_quality.md`;
- signal and promotion contracts in
  `tasks/backlog/audit_signal_refactor_contract.md`.

When this document conflicts with those sources, the authoritative backlog and
current code win.

The intended maturity sequence is:

```text
source/time truth
    -> corrected deterministic contract
    -> canonical observations and executable labels
    -> reproducible research datasets
    -> governed empirical validation
    -> optional ML research challenger
    -> shadow deployment
    -> narrowly scoped, reversible authority
```

ML readiness is an outcome of the Signal Evidence Program. It is not a parallel
shortcut around it.

## 2. Target outcome

The long-term system should support professional quantitative research with:

- point-in-time and survivorship-safe IDX datasets;
- deterministic, versioned baselines;
- exact lineage from raw source rows to features, predictions, decisions, and
  outcomes;
- reproducible experiments and independently verifiable evaluation artifacts;
- realistic IDX execution labels, costs, liquidity constraints, price limits,
  suspensions, and corporate actions;
- purged and embargoed walk-forward validation with an untouched final holdout;
- model and feature versioning;
- challenger/shadow deployment, drift monitoring, rollback, and recertification;
- optional ML implementations behind stable ports;
- complete operation without ML enabled.

The objective is not to replace the deterministic application with a black-box
predictor. The objective is to make the deterministic system a trustworthy
baseline and evidence platform against which additional models can be measured.

## 3. Non-negotiable architectural posture

### 3.1 Deterministic authority remains primary

- `SignalEngine` remains the canonical deterministic signal assessment.
- `RiskEngine` remains the owner of structural and execution risk gates.
- `AssessTradeSetupUseCase` remains the deterministic composition point into
  `TradeSetup`.
- A model cannot turn a blocked setup into `ENTER`.
- Missing, stale, partial, or invalid model inputs cannot improve authority.
- Disabling or removing the model must leave the deterministic workflow usable.

### 3.2 ML is a replaceable plugin capability

“Plugin” means a replaceable implementation behind an application/domain port,
not arbitrary code that can participate in decisions without validation.

The target boundary is:

```text
CLI / future API adapter
        |
        v
application research or inference use case
        |
        +--> deterministic engines and policies
        |
        +--> ModelPort / FeatureSetPort / ModelRegistryPort
                    |
                    v
        infrastructure model plugin
        (sklearn, XGBoost, LightGBM, PyTorch, ONNX, remote service, etc.)
```

Boundary rules:

- Domain objects contain no model framework, filesystem, database, network, or
  provider dependency.
- Application use cases own research/inference workflow, eligibility, fallback,
  authority caps, and status calculation.
- Infrastructure implements training runtimes, artifact storage, registries,
  local/remote inference, and framework adapters.
- CLI/API adapters only parse, wire, invoke, render, and map errors.
- A model implementation cannot write promotion state or production authority.

### 3.3 Research, prediction, and authority are separate

These states must never be collapsed:

```text
TRAINED
EVALUATED
SHADOW_ELIGIBLE
SHADOW_ACTIVE
LOW_WEIGHT_APPROVED
PRODUCTION_APPROVED
SUSPENDED
RETIRED
```

A successfully trained model has no decision authority. A favorable research
report has no authority unless its immutable evaluation artifact passes the
promotion contracts and receives the required human approval.

## 4. Relationship to the Signal Evidence Program

The Signal Evidence Program already supplies the foundation needed by future
ML. Its gates map to ML readiness as follows:

| Evidence-program gate | ML capability unlocked |
|---|---|
| `DQ-CONTRACT-GATE` | Source semantics and effective-time rules can be trusted when designing features |
| `LIVE-CONTRACT-GATE` | Feature and target schemas can bind corrected signal semantics |
| `CANONICAL-EVIDENCE-GATE` | Canonical research datasets can be assembled from observations, controls, and executable labels |
| `DQ-BASELINE-GATE` | Invalid legacy artifacts are excluded and a corrected deterministic baseline is frozen |
| `PROMOTION-GOVERNANCE-GATE` | Model evidence can be evaluated without granting itself authority |
| `EMPIRICAL-EDGE-GATE` | A challenger can demonstrate incremental executable edge over the same baseline population |
| `VALIDATED-PRODUCTION-GATE` | A proven challenger can progress through shadow and separately approved authority stages |

Current agents must follow that sequence rather than inventing ML-specific
shortcuts from this document.

## 5. ML modes and permitted authority

### Mode A — Offline research

Purpose:

- test whether canonical features contain stable incremental information;
- compare simple statistical and ML methods;
- find data defects and unstable relationships.

Authority:

- none;
- no change to CLI verdict, score, risk, sizing, or production config.

### Mode B — Report-only inference

Purpose:

- display predicted return bucket, probability estimate, rank, uncertainty, and
  unavailable reason beside deterministic output;
- collect live point-in-time predictions for later grading.

Authority:

- diagnostic only;
- cannot alter `SignalEngine`, `RiskEngine`, or `TradeSetup`.

### Mode C — Shadow challenger

Purpose:

- run the exact proposed production inference path;
- persist predictions and hypothetical actions without affecting the user-facing
  deterministic action;
- test operational latency, availability, drift, and live calibration.

Authority:

- no trading-decision authority;
- eligible only after governed offline evaluation.

### Mode D — Low-weight scoped feature

Purpose:

- contribute a bounded, explicitly scoped signal component after independent
  evidence and live shadow validation.

Authority:

- capped by the central evidence-authority mechanism;
- exact-scoped by model, feature contract, setup family, horizon, universe or
  liquidity tier, and market regime scope where supported by evidence;
- separately approved and reversible.

### Mode E — Production challenger

Purpose:

- provide a validated contribution within the deterministic authority chain.

Authority:

- never bypasses risk or setup composition;
- remains monitored, versioned, scoped, and suspendable;
- requires recertification after material data, feature, label, execution,
  config, or model changes.

The initial target should be Modes A–C. Modes D–E are optional future outcomes,
not assumptions.

## 6. Required quantitative data contracts

### 6.1 Observation identity

Every training or inference row must bind at least:

```text
observation_id
ticker
decision_at
effective_market_session
eligible_universe_id
population_role              # selected | rejected_control
workflow/setup/horizon
source_cutoff_identity
feature_contract_version
signal_contract_version
authority_registry_version
resolved_config_hash
code_revision
captured_at
```

Rows lacking compatible point-in-time and semantic identity are not silently
backfilled into a canonical training set.

### 6.2 Feature contract

Every feature requires:

```text
feature_name
semantic definition
unit
source owner
source fields
aggregation and lookback
availability rule
null/unavailable semantics
normalization or transformation
expected range
feature contract version
```

Feature extraction must be shared between historical dataset construction and
live inference. Training-serving skew is a correctness defect.

Feature values must be persisted or independently reproducible from recorded
source identities and cutoffs. Recomputing historical features from current
cache state is forbidden.

### 6.3 Label contract

Labels must distinguish:

- raw market return;
- executable gross return;
- net return after fees, taxes, spread, slippage, and modeled impact;
- maximum favorable and adverse excursion;
- target/stop ordering using an explicit intraday ambiguity policy;
- unavailable and censored outcomes;
- suspension, delisting, corporate-action, and price-limit effects;
- exact entry and exit policy version.

The label must bind the exact observation, not merely ticker and date.

### 6.4 Population contract

Training and evaluation must include the eligible control population, not only
stocks selected by the current screener.

The dataset must make explicit:

- historical universe membership;
- selection versus rejection;
- liquidity and listing eligibility;
- missing-data exclusion reason;
- suspended, delisted, renamed, and corporate-action-affected names;
- duplicate and correlated observations;
- sample weights, if any.

Without the control population, a model learns only conditional behavior within
the current selector and cannot prove that it improves selection.

## 7. Feature-store strategy

Do not begin with a generic feature-store platform. Begin with a versioned
research dataset contract over canonical local artifacts.

The logical layers are:

```text
raw source snapshots
    -> point-in-time normalized source facts
    -> versioned feature observations
    -> exact executable labels
    -> immutable dataset manifest
```

An immutable dataset manifest should include:

```text
dataset_id
created_at
observation query/population specification
observation and label schema versions
feature contract versions
source/database hashes
code and resolved-config identity
date/session range
universe definition
row/ticker/session counts
exclusion and unavailable counts
label horizons
split/fold specification
content hash
```

SQLite can remain the local system of record while scale permits. Columnar
exports such as Parquet may be introduced as immutable experiment artifacts,
not as an untracked alternative source of truth.

## 8. Model plugin contracts

Exact interfaces belong in future implementation tasks, but the conceptual
ports should remain narrow.

### Training

```text
ModelTrainerPort.train(dataset_manifest, model_spec) -> TrainingArtifact
```

The artifact records:

- model family and hyperparameters;
- random seed and determinism status;
- library/runtime versions;
- feature order and contract versions;
- training folds;
- fitted preprocessing;
- artifact hash and location;
- warnings and unsupported reproducibility conditions.

### Inference

```text
ModelPredictorPort.predict(model_identity, feature_vector) -> ModelPrediction
```

The prediction records:

- model identity;
- observation identity;
- prediction timestamp;
- output values and units;
- uncertainty/calibration status;
- feature-availability status;
- fallback/unavailable reason;
- latency and runtime version.

### Registry

```text
ModelRegistryPort
    .get(model_id)
    .resolve_challenger(scope)
    .record_artifact(...)
```

The registry stores identity and lifecycle metadata. It does not decide
promotion. Promotion remains a separate governed application workflow that
verifies immutable evidence.

## 9. Recommended initial model roles

The first models should solve narrow, measurable tasks:

1. Candidate ranking after deterministic eligibility and risk gates.
2. False-positive risk estimation for otherwise eligible setups.
3. Calibrated forward-return or outcome buckets by explicit horizon.
4. Data-unavailability or execution-risk prediction as diagnostic support.

Avoid initially:

- end-to-end action prediction;
- direct position sizing;
- reinforcement learning;
- unconstrained strategy discovery;
- one model spanning incompatible intraday and swing horizons;
- learning from only currently selected winners;
- opaque ensemble complexity before simple baselines are exhausted.

The first credible challengers should be simple:

- regularized linear/logistic models;
- monotonic or shallow tree models;
- calibrated gradient boosting where justified.

A complex model that cannot beat a simple baseline across worst folds and
material IDX subgroups is not progress.

## 10. Professional quantitative validation standard

### 10.1 Split design

Required:

- chronological splits;
- repeated walk-forward folds;
- purge overlapping label horizons;
- embargo adjacent observations where leakage remains possible;
- one untouched final holdout established before outcome inspection;
- fold definitions persisted in the dataset/evaluation artifact.

Random row splits are not acceptable for promotion evidence.

### 10.2 Baselines

Every model must be compared on the identical eligible population against:

- no-model deterministic ranking/action;
- simple heuristic ranking;
- constant/base-rate predictor;
- simple linear or logistic baseline where applicable;
- prior approved production challenger, if one exists.

### 10.3 Metrics

Prediction metrics alone are insufficient. Report both statistical and
executable metrics.

Examples:

- rank IC with uncertainty;
- ROC-AUC or precision-recall only where class definition is appropriate;
- Brier score and calibration error for probabilities;
- top-k precision/return and coverage;
- net average return and expectancy;
- hit rate, profit factor, drawdown, turnover, exposure, and capacity proxy;
- unavailable/rejection rate;
- worst fold and dispersion across folds;
- results by setup, horizon, regime, sector, liquidity, market-cap, and data
  availability;
- concentration by ticker, date, sector, and correlated theme.

Metric choice and pass/fail thresholds must be declared before inspecting the
final holdout.

### 10.4 IDX execution realism

Evaluation must explicitly model applicable IDX behavior:

- lot size;
- commissions, exchange fees, levy, VAT, and sell tax according to the
  versioned execution-cost policy;
- spread and slippage;
- liquidity and participation constraints;
- auto-rejection/price-limit effects;
- suspension and no-print sessions;
- opening/pre-closing auction constraints where relevant;
- corporate actions and symbol changes;
- settlement or provider availability cutoffs;
- delisting and survivorship.

Costs and rules must be versioned rather than hard-coded into an undocumented
metric.

### 10.5 Multiple-hypothesis control

Every evaluation artifact should expose:

- hypotheses/models/features tried;
- search space;
- selection procedure;
- whether the final holdout was inspected;
- effective independent sample estimate;
- confidence intervals or bootstrap methodology;
- known selection bias.

Repeated experimentation on the same holdout invalidates it as an untouched
holdout.

## 11. Mandatory ML entry gates

“Most criteria pass” is not sufficient. Before canonical ML training begins,
all foundation requirements below must pass:

- `CANONICAL-EVIDENCE-GATE`;
- `DQ-BASELINE-GATE`;
- canonical selected and rejected-control populations;
- point-in-time and survivorship-safe feature extraction;
- exact executable labels;
- immutable dataset identity;
- replay parity between historical and live feature construction.

Offline exploratory spikes may occur earlier only to validate tooling or
estimate feasibility. Their artifacts are disposable, diagnostic, and
ineligible for comparison, tuning, promotion, or production claims.

Before shadow deployment:

- `PROMOTION-GOVERNANCE-GATE`;
- purged/embargoed walk-forward evaluation;
- untouched holdout;
- deterministic and simple-model baselines;
- net-of-cost IDX evaluation;
- independent artifact recomputation;
- explicit human approval for shadow scope.

Before any decision contribution:

- `EMPIRICAL-EDGE-GATE`;
- successful live point-in-time shadow period;
- calibrated output and failure semantics;
- drift, rollback, suspension, and recertification mechanisms tested;
- exact authority scope and cap approved separately.

There is no universal minimum row count that proves readiness. Sample adequacy
depends on horizon overlap, ticker/date dependence, regime coverage, feature
dimension, event rarity, and uncertainty. Reports must show effective
independent samples and confidence, not only raw row counts.

## 12. Experiment and artifact governance

Every experiment should be reproducible from:

```text
experiment specification
dataset manifest
feature contract
model specification
fold manifest
execution-cost policy
evaluation code identity
random seed
runtime/environment lock
```

Required artifacts:

- training artifact;
- fold-level predictions;
- evaluation artifact;
- model card;
- data/feature quality report;
- failure and subgroup report;
- approval or rejection record.

Artifacts are immutable. A changed dataset, feature, model, cost policy, or
evaluation implementation produces a new identity.

Model selection and promotion must not be encoded as a mutable YAML status that
declares its own proof.

## 13. Operational monitoring

Shadow or authoritative inference must monitor:

- input schema and feature availability;
- source freshness and effective session;
- prediction distribution;
- calibration and realized outcome drift;
- missing/unavailable rate;
- latency, timeout, and model-load failures;
- population and liquidity drift;
- concentration;
- subgroup degradation;
- deterministic-baseline disagreement;
- artifact/config/code identity.

Fail-closed behavior:

- missing or incompatible model artifact: deterministic baseline only;
- missing required feature: prediction unavailable, never neutral zero;
- timeout/runtime failure: deterministic baseline only with visible status;
- scope mismatch: diagnostic/unavailable, never global fallback authority;
- drift or monitoring breach: suspend model contribution automatically where
  policy permits, then require human review.

Provider or framework fallback cannot silently change the model identity,
semantics, or authority.

## 14. Model lifecycle

Recommended lifecycle:

```text
EXPERIMENT
    -> EVALUATED_DIAGNOSTIC
    -> SHADOW_APPROVED
    -> SHADOW_ACTIVE
    -> LOW_WEIGHT_APPROVED
    -> PRODUCTION_APPROVED
    -> SUSPENDED / RETIRED
```

Material changes requiring a new evaluation identity include:

- feature addition/removal or semantic change;
- label or execution-policy change;
- population/universe change;
- retraining window or sampling change;
- model family or material hyperparameter change;
- preprocessing or calibration change;
- authority scope change;
- data-provider semantic change.

Routine retraining is not automatically safe. It is a new model artifact and
must follow the approved retraining and recertification policy.

## 15. Security and supply-chain requirements

Future model plugins may load executable or serialized artifacts and therefore
need explicit controls:

- allowlisted plugin/model formats;
- artifact hashing and provenance;
- dependency/runtime pinning;
- no arbitrary pickle loading from untrusted locations;
- resource and timeout limits;
- no network access from a local model unless explicitly configured;
- secrets remain in infrastructure/provider configuration;
- plugin failures cannot corrupt canonical observations or promotion records.

Portable inference formats such as ONNX may reduce framework coupling, but the
choice must follow measured fidelity, supported operations, reproducibility, and
operational needs.

## 16. Development sequence after the evidence program

This is a future decomposition, not an active backlog:

### ML-FUTURE-1 — Research dataset contract

Define immutable dataset, feature, population, fold, and label manifests over
canonical evidence.

### ML-FUTURE-2 — Offline baseline harness

Build deterministic, constant, linear, and shallow-tree comparisons with
purged walk-forward evaluation. No production inference.

### ML-FUTURE-3 — Model plugin ports

Introduce narrow trainer, predictor, artifact, and registry ports with one local
reference implementation. Preserve framework independence.

### ML-FUTURE-4 — Report-only inference

Record point-in-time predictions and show them separately from deterministic
actions. Grade availability, latency, calibration, and prediction outcomes.

### ML-FUTURE-5 — Shadow challenger

Run the proposed live path with immutable identity, monitoring, and no decision
authority.

### ML-FUTURE-6 — Scoped promotion evaluation

Evaluate incremental executable edge and operational stability under the same
governance used for deterministic evidence promotion.

### ML-FUTURE-7 — Optional bounded contribution

Only after all gates pass, allow a separately approved, capped, exact-scoped,
reversible model contribution. Keeping ML permanently report-only remains an
acceptable outcome.

Each future item must be converted into a Task Template-compliant backlog item
and vetted against then-current code before implementation.

## 17. Definition of ML-ready baseline

The application is ML-ready when:

- current deterministic outputs are semantically correct and reproducible;
- raw sources, effective time, observations, controls, labels, and outcomes have
  compatible immutable identities;
- historical and live feature extraction have parity;
- invalid or legacy evidence cannot enter canonical datasets;
- datasets and experiments are independently reproducible;
- baseline and challenger evaluations are net-of-cost and uncertainty-aware;
- model plugins can be added or removed without changing core domain authority;
- inference failure degrades visibly to deterministic behavior;
- no model can self-promote or bypass risk/setup guardrails;
- monitoring, suspension, rollback, and recertification are operational.

At that point, adding a model is an evidence-governed plugin decision rather
than an architectural rewrite.

## 18. Key principles for future agents

1. Data lineage before model sophistication.
2. Effective-time correctness before historical scale.
3. Control population before selection claims.
4. Executable labels before prediction claims.
5. Simple baseline before complex model.
6. Worst-fold stability before aggregate performance.
7. Immutable evidence before promotion.
8. Shadow operation before authority.
9. Exact scope before production contribution.
10. Deterministic fallback, monitoring, rollback, and recertification always.

## 19. Conclusion

The professional-grade path is not:

```text
more indicators -> larger model -> better prediction
```

It is:

```text
correct data
-> correct semantics
-> canonical evidence
-> reproducible evaluation
-> realistic IDX execution
-> governed challenger
-> monitored and reversible deployment
```

The Signal Evidence Program is the active path to that foundation. This
document defines what the system should be ready to support after those gates
pass: optional, replaceable, measurable ML challengers that improve the system
without weakening its deterministic architecture or evidence standards.
