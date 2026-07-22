# Signal Evidence Authority (current meaning)

Plain-language guide to what **PRODUCTION** means in today’s SignalEngine, what
is diagnostic, and what parked “promotion” work is for.

**Authoritative for runtime behavior:** current config, code, and tests.  
**Authoritative for open work:** `tasks/backlog/parked_*.md` (and
`tui_phase_*.md` when relevant). Archived program/lane docs live under
`tasks/done/`. This page explains **meanings**. It is not a task checklist.

Related design docs (deeper / historical):
[`signal_engine_design_overview.md`](signal_engine_design_overview.md),
[`signal_engine_evidence_model.md`](signal_engine_evidence_model.md),
[`signal_engine_output_contract.md`](signal_engine_output_contract.md).

---

## Two different “status” ideas (do not mix them)

| Idea | What it is | Who owns it today |
|------|------------|-------------------|
| **Central authority** (`EvidenceAuthorityStatus`) | Whether a registered evidence **group** may count toward authority weight / coverage | `config/signal_engine.yaml` → `alpha_trigger.evidence_registrations` |
| **Producer-local status** (`EvidenceStatus` on some evidence objects) | Metadata stamped by builders (almost always DIAGNOSTIC) | Evidence builders — **cannot** grant scoring authority |

A YAML file on a producer (e.g. institutional accumulation) **cannot** self-promote
to PRODUCTION. The central registry wins.

---

## Authority levels (simple)

| Status | Meaning |
|--------|---------|
| **DIAGNOSTIC** | Report / display / project; **effective weight = 0** for Alpha/Trigger |
| **LOW_WEIGHT** | May count, but capped |
| **PRODUCTION** | May use the normal configured weight |

Promotion of a **non-baseline** group to LOW_WEIGHT or PRODUCTION is a governed
change (deferred lane). It is not “flip a producer flag.”

---

## What is PRODUCTION in the live engine today

Only these central registrations are baseline **PRODUCTION**:

1. **`setup_quality`** — canonical setup-quality group  
2. **`institutional_flow`** — flow-confirmation group (registration name; maps to flow evidence)

Still **DIAGNOSTIC** in the central registry (examples):

- `sector_context`
- `company_quality_context`

Institutional-accumulation **producer** objects are also DIAGNOSTIC locally;
they are not a shortcut into PRODUCTION authority.

---

## What PRODUCTION does (and does not do)

**Does:**

- Count toward **`signal_authority_coverage`** for required production groups  
- Allow full **Alpha/Trigger `effective_weight`** for that registration  
- Interact with **DecisionPolicy** coverage thresholds (can cap ENTER → WATCH, etc.)

**Does not:**

- Mean “the whole product is finished”  
- Bypass setup readiness, regime policy, or RiskEngine  
- Equal readiness report field **`promotion_eligible`** (that stays **false** by
  design after DQ-006 — sample readiness ≠ production authority)  
- Let directional setup+flow math invent authority from diagnostic groups

Rough split:

```text
signal_score              → how strong the evidence looks
signal_authority_coverage → whether required PRODUCTION inputs are present
PRODUCTION registration   → whether that group is allowed to count
```

---

## Example

BBCA has strong sector context but weak setup + flow.

- **Today:** sector may appear in panels/projections; it does **not** pull
  Alpha/Trigger weight; ENTER still depends on setup/flow authority and policy.  
- **If sector were later promoted to PRODUCTION:** sector could start counting
  toward weighted projections / authority (only after the promotion lane
  proves and records that change).

---

## Parked concepts (not required for today’s PRODUCTION model)

These live as **future work** in backlog when a product trigger fires. They are
not missing pieces of the current setup+flow PRODUCTION baseline.

| Concept | One-line meaning |
|---------|------------------|
| **Named-setup capture** | Persist population evaluations for an explicit setup name (e.g. breakout), not user-picked tickers |
| **Net-executable labels** | Outcomes after fees/slippage/limits — not raw price move alone |
| **Purged walk-forward** | Time-ordered validation with a purge gap so labels don’t leak into training |
| **Staged promotion** | Shadow → LOW_WEIGHT → PRODUCTION with monitoring and rollback |

Task order and activation rules:
[`tasks/backlog/parked_evidence_promotion_lane.md`](../tasks/backlog/parked_evidence_promotion_lane.md).  
Parked residuals:
[`tasks/backlog/parked_*.md`](../tasks/backlog/).  
Archived program/lane docs:
[`tasks/done/signal_evidence_program.md`](../tasks/done/signal_evidence_program.md),
[`deterministic_signal_engine.md`](../tasks/done/deterministic_signal_engine.md),
[`evidence_validation_and_promotion.md`](../tasks/done/evidence_validation_and_promotion.md).  
CLI routing (clean break to `research` / `analyze signal`):
[`tasks/done/improvement_cli_restructure.md`](../tasks/done/improvement_cli_restructure.md).

---

## When to change this page

Update this doc when central registrations change, when a group’s authority
status changes in validated config, or when DecisionPolicy’s use of
`signal_authority_coverage` changes. Do not use this page to track backlog Done
boxes.
