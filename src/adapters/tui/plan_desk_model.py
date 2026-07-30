"""Structured Plan desk model for Geometry-mast widget (ADR-054).

Present-only structure: inherits Action from board / structure result.
Does not re-score, invent prices, or place orders.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.adapters.tui.plan_structure_result import (
    PlanStructureResult,
    plan_structure_from_runner_object,
)


@dataclass(frozen=True)
class PlanCard:
    """One bordered context card under the geometry mast."""

    key: str
    title: str
    headline: str
    lines: tuple[str, ...] = ()
    tone: str = "neutral"  # open | block | watch | neutral


@dataclass(frozen=True)
class PlanDeskModel:
    """Everything the Geometry-mast widget needs to paint (no IO)."""

    ticker: str
    source: str
    rank: int
    total: int
    action: str
    gate: str
    signal: str
    accum: str
    why: str
    inherit_note: str
    running: bool
    entry: str
    stop: str
    target: str
    lots: str
    risk_pct: str
    plan_id: str
    horizon: str
    incomplete_reason: str
    summary: str
    has_geometry: bool
    no_order: bool
    cards: tuple[PlanCard, ...]
    footer: str


def build_plan_desk_model(
    row: Any | None,
    *,
    ticker: str,
    source: str = "Screen · accumulation",
    rank: int = 1,
    total: int = 1,
    structure: PlanStructureResult | Any | None = None,
    result_line: str = "",
    running: bool = False,
) -> PlanDeskModel:
    """Pure build of Plan desk model from board row + structure result."""
    struct = plan_structure_from_runner_object(structure) if structure is not None else None
    if struct is None and result_line:
        struct = PlanStructureResult(summary=result_line, ticker=ticker)
    if struct is None:
        struct = PlanStructureResult(summary="—", ticker=ticker)

    board_action, gate, signal, accum, why = _board_judgment(row)
    # Prefer board Action for inherit strip when present; structure may echo it.
    action = board_action if board_action not in {"", "—"} else (struct.action or "—")
    if action in {"", None}:
        action = "—"

    cards = _cards(
        struct=struct,
        action=action,
        gate=gate,
        signal=signal,
        accum=accum,
        why=why,
        source=source,
        rank=rank,
        total=total,
        running=running,
    )

    footer = "esc board · p re-run · l paper log · no broker order · structure only"
    if running:
        footer = "structure running · local plan swing · esc cancel wait"

    return PlanDeskModel(
        ticker=str(ticker or struct.ticker or "—"),
        source=source,
        rank=rank,
        total=max(total, 1),
        action=str(action),
        gate=gate,
        signal=signal,
        accum=accum,
        why=why,
        inherit_note="inherited from screen judgment · structure does not re-score Action",
        running=running,
        entry=str(struct.entry or "—"),
        stop=str(struct.stop or "—"),
        target=str(struct.target or "—"),
        lots=str(struct.lots or "—"),
        risk_pct=str(struct.risk_pct or "—"),
        plan_id=str(struct.plan_id_short or "—"),
        horizon=str(struct.horizon or "swing"),
        incomplete_reason=str(struct.incomplete_reason or ""),
        summary=str(struct.summary or result_line or "—"),
        has_geometry=struct.has_geometry(),
        no_order=bool(struct.no_order),
        cards=cards,
        footer=footer,
    )


def _board_judgment(row: Any | None) -> tuple[str, str, str, str, str]:
    if row is None:
        return "—", "—", "—", "—", "—"
    if _is_accum_row(row):
        from src.adapters.tui.presenters.accum_presenter import build_accum_focus

        action = str(getattr(row, "action", "—") or "—")
        gate = str(getattr(row, "gate", "—") or "—")
        signal = str(getattr(row, "signal", "—") or "—")
        accum = str(getattr(row, "accum", "—") or "—")
        why = build_accum_focus(row).why or "—"
        return action, gate, signal, accum, why
    if _is_preopen_row(row):
        from src.adapters.tui.presenters.preopen_presenter import format_preopen_why

        grade = str(getattr(row, "grade", "—") or "—")
        risk = str(getattr(row, "risk", "—") or "—")
        why = format_preopen_why(row) or "—"
        return (
            "—",
            risk,
            grade,
            str(getattr(row, "iep", "—") or "—"),
            why,
        )
    return "—", "—", "—", "—", "—"


def _cards(
    *,
    struct: PlanStructureResult,
    action: str,
    gate: str,
    signal: str,
    accum: str,
    why: str,
    source: str,
    rank: int,
    total: int,
    running: bool,
) -> tuple[PlanCard, ...]:
    out: list[PlanCard] = []

    # Board context — judgment inherit facts
    ctx_lines = [
        f"Signal {signal} · Accum {accum}",
        f"Gate {gate} · #{rank}/{total}",
    ]
    if why and why != "—":
        w = why if len(why) <= 64 else why[:61] + "…"
        ctx_lines.append(w)
    out.append(
        PlanCard(
            key="board",
            title="Board context",
            headline=f"{action} · {gate}" if gate != "—" else str(action),
            lines=tuple(ctx_lines),
            tone=_tone_action(action),
        )
    )

    # Sizing / meta under geometry
    meta_lines = [
        f"lots   {struct.lots or '—'}",
        f"risk%  {struct.risk_pct or '—'}",
        f"id     {struct.plan_id_short or '—'}",
        f"horiz  {struct.horizon or 'swing'}",
    ]
    out.append(
        PlanCard(
            key="sizing",
            title="Sizing · meta",
            headline=str(struct.lots or "—") + " lots"
            if (struct.lots or "—") != "—"
            else "sizing —",
            lines=tuple(meta_lines),
            tone="neutral",
        )
    )

    if running and not struct.has_geometry():
        out.append(
            PlanCard(
                key="status",
                title="Status",
                headline="Running…",
                lines=("local plan swing · structure only",),
                tone="watch",
            )
        )
    elif struct.incomplete_reason:
        note = struct.incomplete_reason
        if len(note) > 72:
            note = note[:69] + "…"
        out.append(
            PlanCard(
                key="status",
                title="Incomplete",
                headline="cannot size fully",
                lines=(note, "no silent paper write"),
                tone="watch",
            )
        )
    else:
        out.append(
            PlanCard(
                key="status",
                title="Authority",
                headline="structure only",
                lines=(
                    "inherits Action · no re-score",
                    "l paper confirm · not auto-write",
                    source,
                ),
                tone="open",
            )
        )

    return tuple(out)


def _tone_action(action: str) -> str:
    a = (action or "").strip().upper()
    if a in {"ENTER", "BUY"}:
        return "open"
    if a in {"AVOID", "BLOCK", "SELL"}:
        return "block"
    if a in {"WATCH", "HOLD"}:
        return "watch"
    return "neutral"


def _is_accum_row(row: Any) -> bool:
    return all(hasattr(row, k) for k in ("signal", "accum", "action", "gate"))


def _is_preopen_row(row: Any) -> bool:
    return all(hasattr(row, k) for k in ("iep", "grade", "risk", "delta_pct"))
