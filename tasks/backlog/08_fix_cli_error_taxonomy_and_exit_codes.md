# CLI Error Taxonomy, Honest Empty States, And Exit Codes

Status: `DONE` (MVP) — taxonomy + high-traffic honesty shipped; full 38-site migration deferred.
Sequence: **8 of 8** — see `tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md`

## 1. Task Metadata

**Task Title**
Give the CLI one error taxonomy so users can tell "nothing found" from "your
install is broken."

**Task Type**
Bugfix (adapter)

**Priority**
Medium — low engine risk, high trust impact.

---

## 2. Product locks (MVP — 2026-08-08)

These locks supersede the original aspirational full migration for this pass:

| Lock | Decision |
|---|---|
| Scope | **Taxonomy + high-traffic honesty**, not all 38 bare `Error:` sites |
| Engine / scoring | **No** changes to scoring, gates, Action, or TradeSetup |
| Adapter role | Map errors only — no fetch/cache/freshness policy in adapters |
| Accum freeze | Preserved (display-only MCE stays display-only) |
| Valid empty | **exit 0**, never `Error:` prefix (`echo_cli_empty`) |
| User / config / bad args / explicit missing `--db` | **exit 1** |
| Internal unexpected (MVP) | **exit 1** (same code; category label differs) |
| Data / env unavailable (missing cache, auth, network) | **exit 2** |
| Explicit `--db` | **Fail closed** — never create DB or parent dirs |
| Configured default DB | May be created by first-run SQLite open (local-first) |

### High-traffic surfaces (this MVP)

1. Shared module: `src/adapters/cli/cli_errors.py`
2. `saham screen accum` — taxonomy errors, `--db` resolve, honest empty/bad data
3. `saham view ticker show` (+ shorthand `view TICKER`) — `--db`, format errors, empty cache
4. `saham fetch status` — configured path + explicit `--db` fail-closed
5. Fix synthetic universe leak: `Universe '1 tickers' not found` on explicit-ticker screen
6. Docs: exit-code table + troubleshooting alignment for MVP paths

### Deferred (post-MVP)

- Bulk replace of remaining ~38 bare `Error: {e}` sites
- `saham today` warning truncation / severity ordering
- Rich markup escaping for dynamic `[…]` strings
- Doc-truth test for every historical `Error:` string in `CLI_TROUBLESHOOTING.md`

---

## 3. Problem Statement (verified)

There is no shared error-mapping layer. Commands do local `try/except` →
`typer.echo(..., err=True)`.

Verified counts across `src/adapters/cli/*.py` (2026-08-04):

| pattern | count |
|---|---|
| `typer.echo(f"Error` | **38** |
| any `typer.echo(..."Error` | **50** |
| any `err=True` call | **250** |
| files containing `err=True` | **57** |

Live-tested defects:

| Input | Actual behavior |
|---|---|
| `screen accum ZZZZ` | exit **0**, `No candidates found…`, plus leaked: `Universe '1 tickers' not found…` |
| `view BOGUSTICKER` | exit **0**, full dashboard of empty panels |
| `--db /nonexistent.db` | silently **creates** a new empty SQLite file |
| `view ticker show --db …` | `No such option: --db` (siblings accept it) |

`CLI_TROUBLESHOOTING.md` documents messages that are partly **aspirational**.

---

## 4. Desired Outcome (MVP)

- One shared taxonomy module with categories + exit codes 0/1/2.
- High-traffic commands route failures through that module.
- Explicit `--db` missing → exit 1, no file created.
- Explicit-ticker screen does not leak synthetic universe names into MCE warnings.
- Empty **filter** results remain exit 0 without `Error:`.
- Missing cache / unusable ticker data → clear message, exit 2.
- `fetch status` uses configured storage path; explicit missing `--db` fails closed.
- Lint Gate passes.

---

## 5. Non-Goals

- **No engine, scoring, or gate changes.**
- No new commands / no `doctor` command.
- No full-repo migration of all 38 sites in this task.
- No `today` truncation / Rich-escape work in this MVP (deferred).
- No flag renames beyond adding missing `--db` on `view ticker show`.

---

## 6. Architecture Impact Assessment

```md
Layer plan:
- Domain: not touched
- Application: display-MCE universe selection only (skip synthetic "N tickers"
  labels) — no scoring / DecisionPolicy change
- Infrastructure: not touched (explicit --db fail-closed is adapter-side before open)
- Adapter: cli_errors taxonomy, high-traffic command mapping, --db parity on view show
```

New dependency: **No.**
Determinism: **No.**
Persistence: **Behavioral** — stop creating DBs on bad explicit `--db`.
Policy in adapter: **No.** Error *mapping* only.

---

## 7. AI Usage Declaration

**No AI involved.**

---

## 8. Risk, Signal, And Evidence Authority

**Does this change what can produce ENTER/WATCH/AVOID? No.**

Display-only MCE universe selection does not inject MCE into DecisionPolicy.

---

## 9. Acceptance Criteria (MVP)

- [x] `cli_errors` module with `CliErrorCategory`, exit 0/1/2, helpers, `resolve_cli_db_path`
- [x] High-traffic commands use taxonomy + `resolve_cli_db_path`
- [x] Explicit missing `--db` → exit 1, no file/dir created
- [x] Explicit-ticker screen: no `Universe 'N tickers' not found` leak
- [x] Valid empty (filters) → exit 0, no `Error:` prefix
- [x] Missing cache for explicit ticker / view show → clear message, exit 2
- [x] `view ticker show --db` accepted
- [x] `fetch status` default path from config; explicit missing fails closed
- [x] MVP docs: exit codes in troubleshooting / reference
- [x] **Lint Gate** passes

---

## 10. Slices (each slice = one commit)

**Slice 1 — Taxonomy and exit codes.**
Module + unit tests.
Commit: `feat(cli): add error taxonomy and exit code contract`

**Slice 2 — DB path honesty + high-traffic wire-up.**
`resolve_cli_db_path` on screen accum, view ticker show, fetch status; taxonomy
on those error paths; view `--db`.
Commit: `fix(cli): honest high-traffic errors and fail-closed --db`

**Slice 3 — Synthetic universe leak + empty honesty.**
Application: MCE display universe ignores synthetic labels. CLI: insufficient
data for explicit ticker / empty view cache use data_unavailable.
Commit: `fix(cli): stop universe leak; honest empty vs missing data`

**Slice 4 — Docs + completion.**
Update troubleshooting/reference exit table; task completion record.
Commit: `docs(cli): document exit codes for error taxonomy MVP`

---

## 11. Testing Expectations

- Category → exit code mapping.
- Explicit `--db` missing creates nothing.
- Default path may be missing without exit 1.
- Synthetic universe label does not call MCE with `"1 tickers"`.
- High-traffic CLI tests offline (stub providers). Ruff before close.

---

## 12. Documentation Impact

- `CLI_TROUBLESHOOTING.md`: exit-code table + MVP-true messages
- `CLI_REFERENCE.md`: short exit-code note (if section exists / light touch)
- README: **No.**

---

## 13. Required Reading

- `AGENT_QUICKSTART.md` — adapter thinness + lint gate
- `CLI_TROUBLESHOOTING.md`

---

## 14. Do Not Interpret This As

- Permission to move fetch/cache policy into adapters.
- Permission to change scoring or Action.
- Permission to require full 38-site migration before shipping MVP.

---

## 15. Completion Record

- Completed date: 2026-08-08
- Exit code table: 0 ok/valid-empty · 1 user/internal · 2 data unavailable
- High-traffic sites wired:
  - `src/adapters/cli/cli_errors.py`
  - `screen accum` (`resolve_cli_db_path` + taxonomy + missing-cache exit 2)
  - `view ticker show` (`--db`, empty cache exit 2)
  - `fetch status` (config path + explicit fail-closed)
  - Application: synthetic universe label ignored for display-only MCE
- Test / Lint result: focused pytest green; `ruff check/format` whole-repo green
