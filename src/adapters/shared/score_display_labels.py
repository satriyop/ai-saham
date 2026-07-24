"""
Human-facing score labels for CLI and TUI (ADR-043).

These names must stay distinct. Do not reuse a short word like "Flow" or
"Score" for more than one concept on the same surface.

Layer: Adapter (display vocabulary only; no scoring policy)
"""

from __future__ import annotations

# --- Canonical short column headers ---

# Accumulation screener composite (foreign-broker flow evidence) 0–100.
ACCUM = "Accum"

# SignalEngine total staged score 0–100.
SIGNAL = "Signal"

# SignalEngine group contributions (also 0–100 each; not the total).
SETUP_GRP = "SetupGrp"
FLOW_GRP = "FlowGrp"

# Net foreign % of daily turnover — one *component* of Accum, not Accum itself.
FLOW_RATIO_PCT = "FlowRatio%"

# Evidence confidence / authority coverage for Signal.
SIGNAL_CONF = "SigConf%"


# --- One-line definitions (guides, explain panels) ---

ACCUM_DEFINITION = (
    "Accum score (0–100): foreign-accumulation composite from broker-flow "
    "evidence (consistency, streak, VWAP discount, RSI headroom, flow ratio, "
    "BCI). Not SignalEngine."
)

SIGNAL_DEFINITION = (
    "Signal score (0–100): SignalEngine staged-evidence total. "
    f"{SETUP_GRP} and {FLOW_GRP} are group contributions inside Signal, "
    "not Accum."
)

FLOW_RATIO_DEFINITION = (
    f"{FLOW_RATIO_PCT}: average net foreign share of total daily turnover "
    "(Accum component only). Not Accum total and not Signal FlowGrp."
)

FLOW_GRP_DEFINITION = (
    f"{FLOW_GRP}: SignalEngine flow-confirmation group (0–100). "
    f"Not Accum and not {FLOW_RATIO_PCT}."
)
