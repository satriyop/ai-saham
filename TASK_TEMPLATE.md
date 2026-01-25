# Task Template

This template defines how **all work items** must be specified before an AI agent (or human) begins implementation.

If a task does not conform to this template, it is **not ready for execution**.

This template enforces:

* Deterministic-first development
* Architectural safety
* Compliance with `PROMPT_CONTRACT.md` and `DEFINITION_OF_DONE.md`

---

## 1. Task Metadata

**Task Title**
Clear, concise, outcome-oriented

**Task Type**

* Feature
* Refactor
* Bugfix
* Spike / Research

**Priority**

* High / Medium / Low

---

## 2. Problem Statement

Describe:

* What problem exists today
* Who or what is affected
* Why this matters for day-1 usefulness

Avoid describing solutions here.

---

## 3. Desired Outcome

Describe the expected result in observable terms:

* What should the system be able to do?
* What should change from the user’s perspective?
* What remains explicitly out of scope?

---

## 4. Non-Goals (Explicitly Out of Scope)

List what this task must **not** do, for example:

* No new data providers
* No AI model changes
* No UI changes
* No risk profile changes

This prevents scope creep.

---

## 5. Architecture Impact Assessment

Answer explicitly:

* Which layer(s) will be touched?

  * Domain
  * Application
  * Adapter (CLI / Bot / Web)
  * Infrastructure

* Does this introduce a new dependency? (Yes / No)

* Does this affect determinism? (Yes / No)

* Does this require persistence changes? (Yes / No)

* Does this indicator require warm-up data? (Yes / No)


If "Yes" appears anywhere, explain why.

---

## 6. AI Usage Declaration

Choose one:

* No AI involved
* AI-assisted (non-authoritative)
* AI exploratory (optional, bypassable)

If AI is used:

* Why is AI needed?
* What happens when AI is disabled?
* How is AI output constrained or verified?

---

## 7. Risk Profile Considerations

* Which risk profiles are affected?

  * Conservative
  * Balanced
  * Aggressive

* How does behavior differ (if at all)?

* Does conservative behavior remain unchanged?

---

## 8. Data & Persistence

* What data is read?
* What data is written?
* Where is it stored?
* Is schema change required? (Yes / No)

---

## 9. Acceptance Criteria

A task is acceptable when:

* [ ] Behavior matches Desired Outcome
* [ ] Works without AI enabled
* [ ] Deterministic for same inputs
* [ ] Complies with DoD
* [ ] No non-goals violated
* [ ] relevant ADRs considered

---

## 10. Testing Expectations

* What logic must be unit-tested?
* Are mocks or stubs required?
* Can tests run offline?

Skipping tests requires justification.

---

## 11. Documentation Impact

* README.md update required? (Yes / No)
* New config options to document? (Yes / No)
* Limitations to state? (Yes / No)

---

## 12. Agent Execution Instructions

Before implementation, the agent must:

* Confirm understanding of the task
* Confirm compliance with AI_AGENT_CHECKLIST.md
* State any risks or ambiguities

Only then may implementation begin.

---

## Final Gate

If the agent cannot confidently answer:

> "How does this task comply with the Definition of Done?"

The task must be revised before execution.
