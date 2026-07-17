# ADR-017: Plugin-Based Indicator Registration

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** Not recorded (legacy decision)
**Current implementation:** Implemented — indicator plugins load through infrastructure and register through the application registry.
**Decision**
Indicators can be registered at runtime via auto-discovered plugin files, not just hardcoded in `domain/indicators/`.

**Components**

* `domain/ports/indicator_plugin.py` — Port defining the plugin interface.
* `infrastructure/plugins/indicator_loader.py` — Loader that scans `plugins/` directories at startup.
* `application/services/indicator_registry.py` — Central registry making all indicators (built-in, plugin, formula) available to analysis.

**Implications**

* Plugin files live in `plugins/` at project root or custom path.
* Each plugin must implement the `IndicatorPlugin` port interface.
* Plugins can include a `.skill.yaml` sidecar for self-documentation.
* Plugins are auto-discovered once at startup and registered in the `IndicatorRegistry`.
* Built-in indicators (`domain/indicators/sma.py`, `ema.py`, `rsi.py`) are also registered through the same registry for uniform access.
* The registry is used by the formula evaluator, CLI commands, and rule interpreter.

**Rationale**
Enables third-party indicator development without modifying core code. Maintains the hexagonal architecture boundary by keeping plugin integration behind the `IndicatorPlugin` port.
