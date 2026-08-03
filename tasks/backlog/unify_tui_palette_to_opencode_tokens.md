# Task: Unify TUI palette onto OpenCode tokens + fix scalar-bar `%` contract

> Source: TUI UI/UX audit, 2026-08-03. Audit-only pass; no code changed. This file
> captures the findings so implementation can be scheduled per the refactor workflow.
> Authority for all visual rules: `docs/design/tui-cockpit-opencode.md` (the bible),
> ADR-051. Design tokens: `src/adapters/tui/theme.py` (`OPENCODE_TOKENS`).

---

## 1. Task Metadata

**Task Title:** Unify TUI widget palette onto `OPENCODE_TOKENS`, fix flow-desk scalar-bar `%`, and detox the AI Research Cockpit skin

**Task Type:** Refactor (visual system) + one Bugfix (scalar-bar contract)

**Priority:** Medium (no functional regression today; correctness of the visual
contract + future re-theme velocity). The scalar-bar `%` item (P1) is a locked-rule
violation and may be split out as a fast standalone Bugfix.

---

## 2. Problem Statement

The design bible defines a canonical **22-token palette** in `theme.py`
(`OPENCODE_TOKENS`: near-black surfaces, peach selection, semantic mint/amber/coral,
one blue, one purple). In practice that dict is **never imported by any widget** — every
desk's `DEFAULT_CSS` re-hardcodes its own hexes. Consequences observed in the audit:

- **Palette fragmentation (unguarded).** ~30 off-token hexes across ~13 widget files:
  two competing body-text grays (`#a0a0a0` ×21, `#c8c8c8` ×16) plus a brighter
  `#ececec` ×7 — none of which are token `text #d8d8d8` / `text_dim #7a7a7a`; and a
  whole **blue/purple family not in the bible**: `#8eb4d8` (vs bible blue `#7aa2c4`),
  `#a89cc9` (vs bible purple `#9b8fb8`), `#3a4252` slate. Desks are subtly different
  shades of "gray," and a global re-theme is impossible from one place.
- **The one palette test only guards `theme.py`.** `test_opencode_tokens_locked_in_theme`
  in `tests/adapters/tui/test_visual_parity_contracts.py` asserts token values +
  `COCKPIT_CSS` + the night-ink `FORBIDDEN_PRODUCT_MARKERS` absence. It does **not**
  inspect per-widget `DEFAULT_CSS`, so all the drift above is invisible to CI.
- **AI Research Cockpit ships a cool-tinted skin.** `widgets/agent_commentary.py`
  hardcodes its own blue-purple ramp (`#101014 / #0e0e12 / #24242c / #686878 /
  #8a8aaa / #aaaabc / #9a9aac / #858596`) — the exact "night-ink" family the bible
  bans as a ship look. This is the actively-developed L4 surface, so it is the
  highest-value one to bring back onto neutral + peach.
- **Scalar-bar `%` contract violation (P1).** `widgets/broker_flow_desk.py` paints a
  16-cell glyph track `_bar(d.bar_pct)` in a row of `date · net · lot · n · bar` with
  **no adjacent integer percent**. The bible locks `%` as mandatory ("*never a bar
  alone*") and names this exact case: "*TUI anti-pattern (fix): foreign/flow solid
  glyph bars with no percent (mystery sugar)*". The reference surface
  `widgets/ticker_desk.py` already complies (`:1470`, `:1575` → `{cp.pct}%`), so two
  surfaces under the same contract disagree.
- **Flow-bar tone off-palette.** `broker_flow_desk.py:58-59` `.fl-bar #3a5a48` /
  `.neg #5a3a3a` are desaturated custom green/red; the bible mandates mint `#6fbf8a` /
  coral `#c97a72` for signed bars.
- **Agent title flicker (polish).** `agent_commentary.py` prints "Agent" in
  `show_stage_ready`, "AI Research Cockpit" in `show_loading`/`show_progress`, and
  `show_result` inherits whatever was last — one surface, two product names by state.

Affected: anyone reading the cockpit (visual inconsistency between desks), and any
future themer/maintainer (no single source of truth). Matters for day-1 usefulness
because the cockpit is the primary human surface and the bible treats its visual
contract as product, not decoration.

**Not in scope of the problem statement:** layout, IA, chip semantics, or data — those
already conform. This is purely the color/token system + one bar-label bug.

---

## 3. Desired Outcome

- Every widget `DEFAULT_CSS` and inline Rich markup color resolves to a value in
  `OPENCODE_TOKENS` (or a small, documented derived-shade helper built from tokens).
  No bespoke grays/blues/purples outside the token set.
- `OPENCODE_TOKENS` becomes the **real** single source of truth: widgets import token
  values (via a helper) rather than literal hexes, so a one-place edit re-themes the TUI.
- `broker_flow_desk` (and any sibling foreign/flow glyph-bar surface) renders an integer
  `%` label adjacent to every bar, in the mute tone the Scalar bar contract specifies,
  matching `ticker_desk` behavior. Bar tone uses token mint/coral.
- The AI Research Cockpit surface renders on neutral-near-black + the token
  purple/peach accents only — no cool night-ink ramp.
- Agent surface uses one consistent product name across all states.
- A test extends `test_visual_parity_contracts.py` to **fail on off-token hexes in
  widget `DEFAULT_CSS`** (allowlist = `OPENCODE_TOKENS` values + documented derived
  shades), so drift cannot silently return.

Observable change from the operator's view: desks read as one consistent skin; flow
bars are no longer "mystery magnitude"; the agent cockpit matches the rest of the app.

---

## 4. Non-Goals (Explicitly Out of Scope)

- No layout, IA, chip-bar semantics, keycap, or navigation changes.
- No new data providers, no AI model changes, no risk/signal/evidence-authority changes.
- No change to what any bar *means* or how `bar_pct` is computed — only that a `%` label
  is shown alongside it.
- No `main.py` carve-up (tracked separately as a structural note; not this task).
- No new tokens invented casually — if a genuinely new semantic color is required,
  it is added to `OPENCODE_TOKENS` with a bible/ADR note, not sprinkled inline.
- No change to `theme.py` `COCKPIT_CSS` structure beyond token alignment (it already
  passes its parity test).

---

## 5. Architecture Impact Assessment

- Layer(s) touched: **Adapter only** (`src/adapters/tui/**`, `theme.py`, TUI tests).
  Domain / Application / Infrastructure: **not touched**.
- New dependency: **No**.
- Affects determinism: **No** (presentation only).
- Persistence changes: **No**.
- Indicator warm-up: **No**.
- Places orchestration/policy inside an adapter: **No** — this is pure adapter
  presentation (color tokens + a display `%` label). No fetch/cache/business logic added.

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: theme.py token-consumption helper; migrate ~13 widget DEFAULT_CSS blocks and
  inline markup colors onto tokens; add `%` label + token tones to broker_flow_desk;
  detox agent_commentary skin; single agent title; extend visual-parity test.
```

---

## 6. AI Usage Declaration

**No AI involved.** Pure visual/adapter refactor. AI mode ON/OFF is irrelevant to this
change; the agent-commentary *widget* is restyled but its behavior/wiring is untouched.

---

## 7. Risk, Signal, And Evidence Authority Considerations

None. No decision component is touched (SignalEngine / RiskEngine / TradeSetup / market
context / setup policy / evidence authority all unaffected). Does not change what
produces ENTER/WATCH/AVOID. Does not promote diagnostic evidence or change tuning
eligibility. The `%` label surfaces an already-computed `bar_pct` — no new authority.

---

## 8. Data & Persistence

- Reads: nothing new — `bar_pct` already exists on the flow model.
- Writes: none.
- Storage: none.
- Schema change: **No**.
- Source equivalence: **N/A** — no data source, provider, repository method, field
  mapping, or persisted field changes. Purely how existing values are colored/labeled.

---

## 9. Acceptance Criteria

- [ ] Every color in `src/adapters/tui/**` widget `DEFAULT_CSS` and inline Rich markup
      resolves to an `OPENCODE_TOKENS` value or a documented token-derived shade; the
      audit greps below return only allowlisted hexes.
- [ ] `broker_flow_desk` renders an integer `%` next to every bar (mute tone), and bar
      tone uses token mint/coral; any sibling foreign/flow glyph-bar surface audited for
      the same and fixed or confirmed compliant.
- [ ] AI Research Cockpit surface (`agent_commentary.py`) uses only neutral-near-black +
      token purple/peach; no cool night-ink ramp remains.
- [ ] Agent surface shows one consistent product name across ready/loading/progress/result.
- [ ] New/extended test in `test_visual_parity_contracts.py` fails on off-token hexes in
      widget `DEFAULT_CSS` (allowlist = token values + documented derived shades).
- [ ] Behavior matches Desired Outcome; works with AI disabled; deterministic; complies
      with DoD; no non-goals violated; ADR-051 + bible considered.
- [ ] Adapter thinness reviewed — no workflow/policy added.
- [ ] **Lint Gate:** whole-repo `ruff check src/ tests/` and
      `ruff format --check src/ tests/` pass. No rule weakening, blanket `# noqa`, or new
      per-file ignores.

---

## 10. Testing Expectations

- Unit-test the new palette guard (off-token hex scanner over widget `DEFAULT_CSS`).
- Extend/adjust flow-desk paint test to assert a `%` token appears in the rendered row
  alongside the bar (mirror line at `broker_flow_desk.py:128-132` is a convenient hook).
- Existing `test_visual_parity_contracts.py` and any agent-commentary snapshot/behavior
  tests must stay green (behavior unchanged; only colors/label/title copy).
- All offline; no network. TUI test-weight note: run under the `tui`-aware fast loop
  (`pytest -m "not tui"` for the inner loop; run the `tui`-marked visual tests before
  close). Confirm whole-repo Ruff check/format before close.

---

## 11. Documentation Impact

- README.md update: **No**.
- New config options: **No**.
- Limitations to state: **No** (may add a one-line note in `theme.py` / bible that
  `OPENCODE_TOKENS` is now the enforced source of truth for widget CSS).

---

## 12. Agent Execution Instructions

Before implementation, the agent must:

- Confirm compliance with `AGENT_QUICKSTART.md` + the Refactor `AI_AGENT_CHECKLIST.md`.
- Re-read `docs/design/tui-cockpit-opencode.md` § Visual + § Scalar bar contract, and
  `theme.py` `OPENCODE_TOKENS` / `FORBIDDEN_PRODUCT_MARKERS`.
- State the layer plan (Adapter-only, as above).
- Decide the token-consumption mechanism first (e.g. a `theme.py` helper that emits
  token-substituted `DEFAULT_CSS` strings, or a documented derived-shade map) before
  mass-migrating widgets — get that seam right, then apply per widget.
- Suggested order: (1) scalar-bar `%` fix in flow desk — smallest isolated win, may ship
  alone; (2) token-consumption seam + parity guard test; (3) migrate widget CSS in
  batches (broker desks, ticker desk, judge/plan/health, agent cockpit last); (4) agent
  title unification.

### Audit greps (repeatable — should shrink to zero off-token hits as work lands)

```bash
# off-palette hexes in TUI python (allowlist = OPENCODE_TOKENS values + derived shades)
grep -rhoE '#[0-9a-fA-F]{6}' --include='*.py' src/adapters/tui \
 | grep -viE '#0b0b0b|#141414|#101010|#0e0e0e|#161616|#1c1c1c|#181818|#121212|#090909|#d8d8d8|#e8e8e8|#7a7a7a|#555555|#3d3d3d|#c9a68a|#1a120c|#a8896f|#6fbf8a|#d4b06a|#c97a72|#7aa2c4|#9b8fb8|#3a3a3a|#2a2a2a|#6b6b6b|#1a1810|#121a14' \
 | sort | uniq -c | sort -rn

# flow-desk bar must carry a % (P1)
grep -nE '_bar\(|%|bar_pct' src/adapters/tui/widgets/broker_flow_desk.py
```

Known off-token families to eliminate (from audit): `#a0a0a0`, `#c8c8c8`, `#ececec`
(body grays); `#3a4252`, `#8eb4d8`, `#a89cc9` (slate/blue/purple family); flow-bar tones
`#3a5a48` / `#5a3a3a`; agent ramp `#101014 #0e0e12 #24242c #14141a #686878 #8a8aaa
#aaaabc #9a9aac #858596 #5a5a6a #2a2a34 #d0d0d8 #555566`. Note: the night-ink hexes
`#080b12 #0d121c #121a28 #1c2430` appear **only** in `theme.py`'s `FORBIDDEN_PRODUCT_MARKERS`
assert-list — leave those; they are the guard, not a leak.

## Final Gate — DoD compliance

Deterministic-first (no behavior/data change), adapter-thin (presentation only), no
guardrail bypassed, visual contract brought into conformance with the bible and made
CI-enforceable. Answerable: yes.
