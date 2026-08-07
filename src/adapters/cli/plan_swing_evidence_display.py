"""Detailed evidence rendering for ``saham plan swing``.

Layer: Adapter

The plan surface renders the exact screen judgment plus plan-owned structure.
It must not expose a second risk, technical-gate, or market-context judgment
path.
"""

from __future__ import annotations

from rich.text import Text

from src.adapters.cli.plan_swing_corporate_calendar_display import (
    print_corporate_calendar_panel,
)
from src.adapters.cli.plan_swing_flow_detail_display import print_flow_detail_panel
from src.adapters.cli.plan_swing_institutional_display import (
    print_institutional_accumulation_section,
)
from src.adapters.cli.plan_swing_output_context import SwingOutputDisplayContext
from src.adapters.cli.plan_swing_overview_display import (
    print_swing_rich_overview,
    setup_gates_group,
)
from src.adapters.cli.plan_swing_sentiment_display import print_sentiment_evidence_panel
from src.adapters.cli.plan_swing_signal_detail_display import (
    print_alpha_trigger_detail_panel,
    print_signal_detail_panel,
)
from src.adapters.cli.plan_swing_strategy_evidence_display import (
    print_strategy_evidence_panel,
)
from src.adapters.cli.rich_display import console, panel


def print_setup_evidence_panel(ctx: SwingOutputDisplayContext) -> None:
    setup_eval = ctx.evidence.setup_eval
    if setup_eval is not None:
        console().print("")
        console().print(
            panel(
                setup_gates_group(setup_eval, ctx.diagnostics.broker_quality_note),
                title="SETUP DIAGNOSTIC EVIDENCE",
            )
        )


def print_swing_output(ctx: SwingOutputDisplayContext) -> None:
    print_swing_rich_overview(
        ticker=ctx.ticker,
        today=ctx.today,
        data_freshness=ctx.diagnostics.data_freshness,
        broker_detail=ctx.diagnostics.broker_detail,
        accum=ctx.evidence.accumulation_candidate,
        atr_value=ctx.atr_value,
        sizing=ctx.sizing,
        setup_eval=ctx.evidence.setup_eval,
        setup_sizing=ctx.setup_sizing,
        broker_quality_note=ctx.diagnostics.broker_quality_note,
        capital=ctx.capital,
        config=ctx.config,
        screen_judgment=ctx.verdict.judgment_ref,
        include_signal_detail=ctx.options.include_signal_detail,
        signal_assessment=ctx.verdict.signal_assessment,
        trade_setup=ctx.verdict.trade_setup,
        effective_session=ctx.effective_session,
    )

    print_setup_evidence_panel(ctx)
    if ctx.options.include_signal_detail:
        print_signal_detail_panel(ctx)
        print_alpha_trigger_detail_panel(ctx)

    if (
        ctx.options.include_flow_detail
        and ctx.evidence.institutional_accumulation_evidence is not None
    ):
        print_institutional_accumulation_section(ctx.evidence.institutional_accumulation_evidence)

    print_flow_detail_panel(ctx)
    print_strategy_evidence_panel(ctx)
    print_sentiment_evidence_panel(ctx)
    print_corporate_calendar_panel(ctx)
    console().print(
        Text(
            f"Structure desk · judgment: saham screen accum {ctx.ticker} · engine detail: --full",
            style="dim",
        )
    )
    console().print("")
