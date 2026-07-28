# AI Saham

[![CI](https://github.com/satriyop/ai-saham/actions/workflows/ci.yml/badge.svg)](https://github.com/satriyop/ai-saham/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Local-first, deterministic stock screening and analysis for the Indonesia Stock
Exchange (IDX). The application combines cached market, broker-flow, company,
and market-context data into explainable evidence, risk gates, and paper-trade
workflows.

AI Saham is analysis software, not an order-execution bot or financial advice.
AI features are optional and never own a score, risk verdict, or config change.

## Start here

### Users

```bash
# Install
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Verify the command surface
saham version
saham --help

# Refresh the default universe, then open the read-only daily briefing
saham fetch market --universe lq45
saham today

# Discover and inspect swing candidates
saham screen accum --universe lq45 --multi
saham plan swing BBRI --capital 10000000
```

`saham today` is deliberately read-only. It summarizes cached data, the current
market regime, the latest saved pre-open candidates, and fresh accumulation
candidates. It does not fetch, tune, or persist data.

For command options, use `saham COMMAND --help`. See [CLI_README.md](CLI_README.md)
for the longer learning-oriented guide; when it conflicts with live `--help`,
the command implementation wins.

### Optional daily cockpit (TUI)

Install and launch the OpenCode-style local-first cockpit (Textual) separately
from the base CLI:

```bash
pip install -e ".[tui]"
saham tui
```

Design: `docs/design/tui-cockpit-opencode.md` · ADR-051 clean break.

The cockpit is keyboard-first (`Ctrl+P` command palette). It defaults to local
cache, does not auto-fetch on open, and never places broker orders. Explicit
fetch and full screen/plan power remain available via CLI; later cockpit phases
wire the same use cases behind the palette.

Use `1` for Today, `2` for Candidates, `r` for explicit local recomputation,
`Enter` to open the selected ticker, `Esc` to go back, `?` for Help, and `q` to
quit. Signal-readiness diagnostics remain available through the CLI. The CLI
remains the primary automation interface.

### Coding agents

Read these in order:

1. [AGENT_QUICKSTART.md](AGENT_QUICKSTART.md) — mandatory constraints and the
   task-specific reading matrix.
2. [AGENTS.md](AGENTS.md) and the active agent contract, if any.
3. [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md) — compact binding-decision hub and task-to-ADR reading matrix,
   current-state index, and amendment map.
4. Only the design/config/source files relevant to the task.

Use this authority order when documents disagree:

1. current executable code and tests describe implemented behavior;
2. accepted ADRs describe architectural intent, with newer amendments taking
   precedence;
3. configuration describes shipped policy and thresholds;
4. guides and historical plans provide context, not authority.

Do not infer a feature from a plan or old example. Confirm it in source and in
`saham --help`. Architecture boundaries are tested, with a small named legacy
allowlist in `tests/architecture/test_layer_boundaries.py`.

## Daily workflows

### Daily briefing

```bash
saham fetch status
saham fetch market --universe lq45
saham today --universe lq45 --top 5
```

The briefing is the first daily orientation command. Follow its freshness
warnings before treating any candidate list as current.

### Pre-open and opening session

Operator runbook: [`docs/runbook_pre_open.md`](docs/runbook_pre_open.md).

```bash
# Learning + decision write (cron owns most of this)
saham fetch iev
saham research pre-open capture
saham research pre-open track
saham research pre-open labels
saham research pre-open evaluate
saham research pre-open status

# Human post-open assess + optional paper notebook (not learning)
saham assess pre-open --session YYYY-MM-DD
saham trade pre-open log --observation-id … --opening-snapshot-id …
```

The pre-open workflow is session-specific: NCP capture freezes the plan in
SQLite, track samples the open, labels write `open_30m` once, and evaluate
reads labels only (never rereads tracks). `assess pre-open` is a separate
read-only post-open assess of the frozen plan.

### Swing discovery and analysis

```bash
saham screen accum --universe lq45 --multi
saham plan swing TICKER --with-market-context
saham plan swing TICKER --capital 10000000
saham policy accum backtest --help
saham trade accum log --ticker TICKER --from-analysis
```

The accumulation score and SignalEngine score are separate 0–100 systems. The
former measures foreign-flow discovery quality; the latter evaluates canonical
signal evidence. Neither bypasses RiskEngine.

### Guarded swing tuning

```bash
saham policy accum tune --help
saham policy accum review --help
saham policy accum validate PROPOSAL_ID
saham policy accum apply PROPOSAL_ID --yes
saham policy accum status
```

Swing policy review is deterministic and evidence-gated. Proposals are derived
from IS evidence only, then validated on an identical paired OOS population.
Only a passing, hash-current, unused proposal can be applied explicitly.

## How the system thinks

```text
external providers
      |
      v
local SQLite + dated journals/artifacts
      |
      v
candidate discovery and point-in-time feature assembly
      |
      +--> SignalEngine ---------+
      +--> RiskEngine -----------+--> AssessTradeSetupUseCase --> TradeSetup
      +--> MarketContextEngine --+          ENTER / WATCH / AVOID / BLOCKED_*
      |
      v
paper-trade, replay, attribution, and guarded tuning workflows
```

### Canonical engines

| Component | Question answered | Current authority |
|---|---|---|
| `SignalEngine` | Is evidence for an entry strong and sufficiently covered? | Canonical staged evidence: Setup Quality (60%) + Flow Confirmation (40%), followed by deterministic decision policy |
| `RiskEngine` | Is acting blocked by structural or execution risk? | Canonical OPEN/BLOCKED gate pipeline; no conservative/balanced/aggressive profiles |
| `MarketContextEngine` | What is the IDX regime and how should evidence be conditioned? | Canonical signal input when market context is requested; risk-side regime adjustment remains preview |
| `AssessTradeSetupUseCase` | What action follows from signal and risk? | Sole deterministic composition point for `TradeSetup` |
| AI integrations | How can existing results be explained or artifacts proposed? | Optional and non-authoritative; validation and human approval remain mandatory |

The legacy six-factor SignalEngine model (bandar, foreign flow, insider,
seasonality, analyst, valuation) is retained for compatibility/diagnostics, not
as the canonical production scoring path.

### Evidence authority

Signal evidence has an explicit authority status in `config/signal_engine.yaml`.
The shipped high-level posture is:

| Evidence group | Default status | Effect |
|---|---|---|
| Setup Quality | `PRODUCTION` | Canonical structural/setup evidence |
| Institutional Flow | `PRODUCTION` | Canonical flow-confirmation evidence |
| Market Context | `DIAGNOSTIC` as a scored evidence group | MCE regime conditioning is separately canonical when requested |
| Company Quality Context | `DIAGNOSTIC` | Recorded and displayed, with no production scoring authority |
| Sector/ticker-profile/strategy extensions | Diagnostic by default | Must earn promotion through out-of-sample proof and validator support |

Missing evidence reduces coverage; weak or conflicting evidence reduces
conviction. Do not convert missing data into neutral conviction.

## CLI map

The live top-level groups are registered in `src/adapters/cli/main.py`:

| Command | Role | Representative operations |
|---|---|---|
| `saham today` | Read-only daily orientation | freshness, regime, saved pre-open, accumulation candidates |
| `saham fetch` | Ingestion and data health | market, broker, IEV, calendar, enrichment history, status, audit, Stockbit, universes |
| `saham screen` | Candidate discovery | pre-open, accumulation, watchlists, comparisons |
| `saham research pre-open` | Pre-open learning lifecycle | capture, track, labels, evaluate, status |
| `saham view` | Cached-data inspection | ticker, universe, broker, market context |
| `saham indicator` | Indicator/formula operations | compute, snapshot, create, list, show, delete |
| `saham inspect` / `plan` / `assess` | Live lenses, TradeSetup plan, frozen assess | inspect risk/signal/…; plan swing; assess pre-open |
| `saham strategy` | Strategy lifecycle | initialize, validate, create, backtest, skill docs |
| `saham trade` | Paper trading and calibration | log/review (pre-open + swing), outcome, sizing, backtests, guarded swing tuning |

Run `saham GROUP --help` for the current subcommands. Do not maintain another
exhaustive command tree here; live Typer help is the source of truth.

## Architecture and boundaries

The repository follows ports and adapters:

| Layer | Location | Owns | Must not own |
|---|---|---|---|
| Domain | `src/domain/` | pure entities, value objects, rules, calculations, ports | database, network, filesystem, browser, CLI, AI |
| Application | `src/application/` | use cases, workflow/policy, engine services, application ports | concrete provider or UI concerns |
| Infrastructure | `src/infrastructure/` | SQLite, config loaders, API/browser providers, AI/provider adapters | user workflow or final policy |
| Adapters | `src/adapters/` | input parsing, dependency wiring, output formatting, error mapping | scoring, persistence policy, workflow logic |

Dependency direction is inward. Adapters may assemble concrete infrastructure,
but must stay thin. New workflow or policy belongs in an application use case.

Important composition points:

| Concern | Start here |
|---|---|
| CLI registration | `src/adapters/cli/main.py` |
| Engine factories | `src/application/services/engine_bootstrap/` |
| Signal facade | `src/application/services/signal_engine.py` |
| Canonical signal assessment | `src/application/use_case/assess_signal_evidence_use_case.py` |
| Risk facade | `src/application/services/risk_engine.py` |
| TradeSetup composition | `src/application/use_case/assess_trade_setup_use_case.py` |
| Market context | `src/application/services/market_context_engine.py` |
| Swing workflow | `src/application/use_case/swing_analysis_workflow_use_case.py` |
| Daily briefing | `src/application/use_case/daily_briefing_use_case.py` |
| Architecture enforcement | `tests/architecture/test_layer_boundaries.py` |

`src/application/services/bootstrap.py` is a compatibility facade. Put new
engine construction in the focused `engine_bootstrap/` modules rather than
growing the facade.

## Data and configuration

### Local state

The default database is `data/db/data.db` (SQLite). Other durable or operational
state is deliberately separated:

| Path | Purpose |
|---|---|
| `data/db/` | SQLite databases |
| `data/session/` | current workflow sidecars |
| `data/debug/` | raw/debug payloads |
| `journals/` | append-oriented paper-trade records |

Historical replay must use point-in-time data available on or before the replay
date. Current snapshots must not leak into historical observations. Run
`saham fetch enrichment-history --universe lq45` regularly to build usable PIT
coverage.

### Configuration precedence

```text
CLI option > config/user.yaml > config/default.yaml > code default
```

`config/user.yaml` is local and gitignored. Start from
`config/user.yaml.example`; do not commit credentials or personal capital.

| Config | Responsibility |
|---|---|
| `config/default.yaml` | application defaults, storage paths, provider and universe defaults |
| `config/signal_engine.yaml` | evidence authority, weights, scoring and decision policy |
| `config/risk_engine.yaml` | risk gates and thresholds |
| `config/market_context_engine.yaml` | IDX regime factors and policy |
| `config/accumulation_screener.yaml` | candidate discovery and foreign-flow scoring |
| `config/pre_open_screener.yaml` | opening/pre-open policy |
| `config/swing_setups.yaml` | named setup definitions and entry authority |
| `config/swing_targets.yaml` | regime/setup target policy |
| `config/swing_backtest.yaml` | replay assumptions |
| `config/analyze_swing.yaml` | swing analysis workflow defaults |

Config changes can alter analysis even when code does not change. Treat them as
behavior changes: validate, replay, and document them.

## Optional integrations

Stockbit data requires a valid local session for live provider calls; cached data
remains usable offline. Browser support is installed separately:

```bash
pip install -e ".[browser]"
playwright install chromium
saham fetch stockbit --help
```

AI is disabled by default (`config/default.yaml`). Provider credentials belong
in environment variables or local configuration, never in the repository. The
deterministic workflows must remain usable when AI or the network is absent.

## Documentation map

| Need | Document |
|---|---|
| Binding architecture decisions, amendments, and task routing | [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md) |
| Agent constraints and task reading matrix | [AGENT_QUICKSTART.md](AGENT_QUICKSTART.md) |
| CLI learning guide | [CLI_README.md](CLI_README.md) |
| Signal engine model | [docs/signal_engine_design_overview.md](docs/signal_engine_design_overview.md) |
| Signal evidence semantics | [docs/signal_engine_evidence_model.md](docs/signal_engine_evidence_model.md) |
| Signal output contract | [docs/signal_engine_output_contract.md](docs/signal_engine_output_contract.md) |
| IDX data sources | [docs/data_sources.md](docs/data_sources.md) |
| Database schema | [docs/data_database_erd.md](docs/data_database_erd.md) |
| Intraday workflow | [docs/workflow_pre_open_learning_lifecycle.md](docs/workflow_pre_open_learning_lifecycle.md) |
| Swing workflow | [docs/workflow_swing_foreign_accumulation.md](docs/workflow_swing_foreign_accumulation.md) |
| Contribution and verification | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Change history | [CHANGELOG.md](CHANGELOG.md) |

Documents under `notes/` and implementation plans under `docs/` may describe
historical proposals. Verify their claims against current code before acting.

## Development and verification

```bash
pip install -e ".[dev]"
pytest
pytest tests/architecture/test_layer_boundaries.py
ruff check src tests
```

For focused changes, follow the verification matrix in
[AGENT_QUICKSTART.md](AGENT_QUICKSTART.md). Preserve unrelated worktree changes
and never use destructive Git cleanup without explicit approval and file scope.

## Known constraints

- Results depend on local data freshness, provider coverage, and point-in-time
  history. A numeric score is not a guarantee of future returns.
- Stockbit and IDX endpoints can change or become unavailable; cached-data paths
  should fail visibly and remain usable where possible.
- Diagnostic evidence is intentionally prevented from silently acquiring
  production weight.
- Backtests are sensitive to costs, liquidity, corporate actions, survivorship,
  and look-ahead leakage. Use walk-forward/out-of-sample evidence for tuning.
- Some older guides still contain retired risk profiles, command names, or
  pre-staged SignalEngine descriptions. The source-of-truth order above applies.

## License

MIT. See [LICENSE](LICENSE).
