# ADR-018: CLI Command Depth — `saham view broker` Exception

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** Not recorded (legacy decision)
**Current implementation:** Implemented — saham view broker remains the documented command-depth exception; live help is authoritative.
**Decision**
The CLI follows a "max 2 levels" depth rule (`saham <group> <command>`). The `saham view broker` sub-group is an explicit, documented exception at 3 levels (`saham view broker <subcommand>`).

**Affected commands**
`saham view broker status|flow|top|history|top-foreign|mappings`

**Rationale**
Broker data has multiple distinct display modes (flow, top buyers/sellers, history, foreign activity, mappings) that are all conceptually under one data source. Flattening these to `saham view flow`, `saham view top`, etc. would pollute the `view` namespace and lose the broker grouping signal. The `broker` sub-group is the right structural cut; the depth cost is accepted.

**Implications**
* No other `view` sub-groups may be introduced without a new ADR.
* New broker display commands are added under `view broker`, not at `view` level.
* All other `saham` command groups remain at max 2 levels.
