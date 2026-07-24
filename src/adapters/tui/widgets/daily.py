"""Policy-free text rendering for the Daily workspace.

Layer: Adapter
"""

from __future__ import annotations

from src.adapters.tui.action_display import decorate_action
from src.adapters.tui.presenters.daily_presenter import DailyViewModel


def render_clocks(view: DailyViewModel) -> str:
    return "\n".join(f"{clock.label}: {clock.value or '-'}" for clock in view.clocks)


def render_readiness(view: DailyViewModel) -> str:
    lines = [f"Overall authority: {view.overall_authority}"]
    lines.extend(
        f"{item.dataset}: {item.status} "
        f"({item.coverage_count}/{item.total_count})" + (f" — {item.reason}" if item.reason else "")
        for item in view.readiness
    )
    return "\n".join(lines)


def render_freshness(view: DailyViewModel) -> str:
    if not view.freshness:
        return "No freshness observations."
    return "\n".join(
        f"{item.ticker}: candles {item.candle_state} ({item.candle_as_of or '-'}), "
        f"brokers {item.broker_state} ({item.broker_as_of or '-'}), "
        f"alignment {item.alignment_state}"
        for item in view.freshness
    )


def render_regime(view: DailyViewModel) -> str:
    regime = view.regime
    if regime is None:
        return "No regime result."
    parts = [
        f"{regime.regime} | conviction {regime.conviction:.2f}",
        *(f"{factor.name}: {factor.label}" for factor in regime.factors),
    ]
    for warning in (
        regime.transition_warning,
        regime.staleness_warning,
        regime.coverage_warning,
    ):
        if warning:
            parts.append(warning)
    return "\n".join(parts)


def render_opening(view: DailyViewModel) -> str:
    lines = [
        f"{item.ticker}: {item.opening_setup} | IEV {item.iev or '-'} | "
        f"IEP {item.iep or '-'} | trend {item.trend or '-'}"
        for item in view.opening_candidates
    ]
    lines.extend(
        f"Market-wide {item.ticker}: {item.opening_setup} | trend {item.trend or '-'}"
        for item in view.market_wide_opening_observations
    )
    return "\n".join(lines) if lines else "No opening observations."


def render_accumulation(view: DailyViewModel) -> str:
    lines: list[str] = []
    summary = view.accumulation_summary
    if summary is not None:
        lines.append(
            f"Checked {summary.checked} | ready {summary.data_ready} | "
            f"flow {summary.flow_candidates} | enter {summary.enter_count} | "
            f"watch {summary.watch_count} | blocked {summary.blocked_count}"
        )
    for idx, item in enumerate(view.accumulation_candidates, 1):
        action_symbol = decorate_action(item.action)
        lines.append(
            f"│ {idx:<2} {item.ticker:<5} | accum {item.accum_score:5.1f} | "
            f"signal {item.signal_score if item.signal_score is not None else '-':>3} | "
            f"risk {item.risk_status:<6} | {action_symbol}"
        )
    return "\n".join(lines) if lines else "No accumulation candidates."


def render_setup_lens(view: DailyViewModel) -> str:
    lines = []
    for row in view.setup_lens_rows:
        cells = "; ".join(f"{cell.setup_name}: {_setup_cell_text(cell)}" for cell in row.cells)
        lines.append(f"{row.ticker} ({row.base_action or '-'}): {cells}")
    lines.extend(f"Warning: {warning}" for warning in view.setup_lens_warnings)
    return "\n".join(lines) if lines else "No setup-lens impact."


def _setup_cell_text(cell) -> str:
    if cell.warning:
        return cell.warning
    return f"{cell.action or '-'} {cell.setup_match}"


def render_warnings(view: DailyViewModel) -> str:
    return "\n".join(view.warnings) if view.warnings else "No warnings."
