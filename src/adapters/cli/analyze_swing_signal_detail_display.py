"""
Signal and Alpha/Trigger detail panels for saham analyze swing full output.

Layer: Adapter

This module renders facts already produced by SignalEngine/AlphaTriggerScore.
It must not compute business action, and must not introduce or alter
thresholds.
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from src.adapters.cli.analyze_swing_output_context import SwingOutputDisplayContext
from src.adapters.cli.analyze_swing_overview_display import flow_trigger_blocked_text
from src.adapters.cli.rich_display import compact_table, console, panel
from src.domain.value_objects.alpha_trigger_score import AlphaTriggerScore, EvidenceAuthorityStatus


def print_signal_detail_panel(ctx: SwingOutputDisplayContext) -> None:
    signal_assessment = ctx.verdict.signal_assessment
    signal_text = []
    if ctx.options.include_signal_detail and signal_assessment is not None:
        sa = signal_assessment.assessment
        _sig_style = {
            "STRONG": "bold green",
            "MODERATE": "yellow",
            "WEAK": "red",
        }.get(sa.strength.value, "white")
        evidence_coverage = sa.signal_authority_coverage
        signal_text.append(Text(
            f"Explains the Signal column in Verdict: {sa.score_label} "
            f"{sa.strength.value} / {evidence_coverage:.0%} coverage "
            f"-> {sa.entry_quality.value}",
            style=_sig_style,
        ))
        signal_text.append(Text(
            "Scale: SignalEngine 0-100. Used in final TradeSetup: yes.",
            style="dim",
        ))
        breakdown = getattr(sa, "breakdown_dict", None) or {}
        active_flags = getattr(signal_assessment, "active_flags", ())
        flag_adj = getattr(signal_assessment, "flag_adjustment", 0)
        raw_score = getattr(signal_assessment, "raw_group_score", None)
        conf = sa.signal_authority_coverage
        if breakdown:
            _group_labels = {
                "setup_quality_group": "Setup Quality",
                "flow_confirmation_group": "Flow Confirmation",
                "signal_authority_coverage": "Signal Authority Coverage",
                "flag_adjustment": "Flag Adjustment",
            }
            _group_sources = {
                "setup_quality_group": "SetupEvidence.match_strength (MATCH=100, PARTIAL=60, NO_MATCH=20)",
                "flow_confirmation_group": "FlowConfirmationEvidence.capped_strength × 100",
                "signal_authority_coverage": "present-authoritative PRODUCTION weight / required PRODUCTION weight (60% Setup + 40% Flow)",
                "flag_adjustment": "sum of active flag penalties",
            }
            bd_table = compact_table()
            bd_table.add_column("Group")
            bd_table.add_column("Value", justify="right")
            bd_table.add_column("Source", style="dim")
            for _key, _val in breakdown.items():
                _label = _group_labels.get(_key, _key)
                _source = _group_sources.get(_key, "")
                if _key == "signal_authority_coverage":
                    bd_table.add_row(_label, f"{_val:.0f}%", _source)
                else:
                    bd_table.add_row(_label, f"{_val:.1f}", _source)
            signal_text.append(bd_table)
        if active_flags:
            _flag_names = {
                "VALUATION_STRETCHED": f"VALUATION_STRETCHED ({flag_adj:+d} pts total)",
                "ANALYST_BEARISH": "ANALYST_BEARISH",
                "INSIDER_SELLING": "INSIDER_SELLING",
            }
            flag_detail = ", ".join(_flag_names.get(f, f) for f in active_flags)
            signal_text.append(Text(f"  Flags: {flag_detail}", style="dim yellow"))
        if raw_score is not None and flag_adj != 0:
            signal_text.append(Text(
                f"  Raw group score {raw_score} + flag adjustment {flag_adj:+d} = {sa.score}",
                style="dim",
            ))
        if conf is not None:
            signal_text.append(Text(
                f"  Signal authority coverage: {conf:.0%} of scoring weight covered",
                style="dim",
            ))
        for line in sa.rationale[-3:]:
            signal_text.append(Text(f"  {line}", style="dim"))
        if signal_assessment.coverage_warning:
            signal_text.append(Text(f"  ⚠ {signal_assessment.coverage_warning}", style="dim yellow"))
        constraints = getattr(sa, "decision_constraints", None)
        if constraints is not None:
            signal_text.append(Text("  Decision constraints", style="bold cyan"))
            signal_text.append(Text(
                f"    max_decision={constraints.max_decision} "
                f"regime={constraints.regime or 'none'} "
                f"enter_allowed={constraints.regime_enter_allowed} "
                f"size={constraints.effective_size_multiplier:.2f}",
                style="dim",
            ))
            if constraints.setup_family or constraints.setup_regime_action:
                signal_text.append(Text(
                    f"    setup={constraints.setup_family or 'none'} "
                    f"action={constraints.setup_regime_action or 'none'}",
                    style="dim",
                ))
            for reason in constraints.constraint_reasons:
                signal_text.append(Text(f"    - {reason}", style="dim yellow"))

    if signal_text:
        console().print("")
        console().print(
            panel(
                Group(*signal_text),
                title="SIGNAL DETAIL",
            )
        )


def print_alpha_trigger_detail_panel(ctx: SwingOutputDisplayContext) -> None:
    signal_assessment = ctx.verdict.signal_assessment
    alpha_trigger_text = []
    if ctx.options.include_signal_detail and signal_assessment is not None:
        ats: AlphaTriggerScore | None = getattr(signal_assessment, "alpha_trigger_score", None)
        if ats is not None:
            alpha_wt_pct = int(ats.alpha_weight * 100)
            trigger_wt_pct = 100 - alpha_wt_pct
            alpha_s = f"{ats.alpha_score:.1f}" if ats.alpha_score is not None else "—"
            trig_s = f"{ats.trigger_score:.1f}" if ats.trigger_score is not None else "—"
            final_s = f"{ats.final_exact_score:.1f}" if ats.final_exact_score is not None else "—"
            alpha_trigger_text.append(Text(
                f"α {alpha_s}  trigger {trig_s}  final {final_s}  "
                f"horizon {ats.horizon}  "
                f"alpha {alpha_wt_pct}% · trigger {trigger_wt_pct}%",
                style="bold cyan",
            ))
            alpha_trigger_text.append(Text(
                f"coverage {ats.coverage_score:.2f}  authority {ats.authority_coverage_score:.2f}  "
                f"conviction {ats.conviction_score:.2f}  "
                f"flow_trigger {'✓ allowed' if ats.flow_trigger_allowed else '✗ blocked'}",
                style="dim",
            ))
            if ats.group_contributions:
                ct = compact_table()
                ct.add_column("Group")
                ct.add_column("Score", justify="right")
                ct.add_column("Present")
                ct.add_column("Status")
                ct.add_column("CfgWt", justify="right")
                ct.add_column("EffWt", justify="right")
                ct.add_column("AlphaWtd", justify="right")
                ct.add_column("TrigWtd", justify="right")
                ct.add_column("TrigOK")
                for c in ats.group_contributions:
                    is_diag = (
                        c.evidence_status == EvidenceAuthorityStatus.DIAGNOSTIC
                        or c.effective_weight == 0.0
                    )
                    status_text = Text(
                        c.evidence_status.value + (" — no weight" if is_diag else ""),
                        style="dim" if is_diag else "",
                    )
                    eff_wt_text = Text(f"{c.effective_weight:.3f}", style="dim" if is_diag else "")
                    ct.add_row(
                        Text(c.group, style="dim" if is_diag else ""),
                        Text(f"{c.score:.1f}" if c.present else "—", style="dim" if is_diag else ""),
                        Text("✓" if c.present else "✗", style="dim" if is_diag else ""),
                        status_text,
                        Text(f"{c.configured_weight:.3f}", style="dim" if is_diag else ""),
                        eff_wt_text,
                        Text(f"{c.alpha_weighted:.3f}", style="dim" if is_diag else ""),
                        Text(f"{c.trigger_weighted:.3f}", style="dim" if is_diag else ""),
                        Text("✓" if c.trigger_allowed else "✗", style="dim" if is_diag else ""),
                    )
                alpha_trigger_text.append(ct)
                for c in ats.group_contributions:
                    if c.group == "institutional_flow" and not c.trigger_allowed:
                        for reason in c.reasons:
                            text = flow_trigger_blocked_text(reason)
                            if text is not None:
                                alpha_trigger_text.append(
                                    Text(f"  {text}", style="dim yellow")
                                )
            for reason in list(ats.unavailable_reasons)[-3:]:
                alpha_trigger_text.append(Text(f"  ⚠ {reason}", style="dim yellow"))

    if alpha_trigger_text:
        console().print("")
        console().print(panel(Group(*alpha_trigger_text), title="ALPHA/TRIGGER DETAIL"))
