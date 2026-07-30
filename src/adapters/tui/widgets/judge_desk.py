"""Verdict-mast Judge desk widget (design: tui-judge-desk.html).

Composed mast + phase + **per-section cards** (2-col grid). Present-only.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from src.adapters.tui.judge_desk_model import (
    CARD_ORDER_FULL,
    CARD_SCALARS,
    JudgeCard,
    JudgeDeskModel,
    action_css_class,
    gate_css_class,
)

# Max cards we pre-compose (full desk + limited scalars).
_CARD_SLOT_KEYS: tuple[str, ...] = CARD_ORDER_FULL + (CARD_SCALARS,)
_TONE_CLASSES = ("tone-open", "tone-block", "tone-watch", "tone-neutral")


class JudgeDesk(Vertical):
    """Visual Judge instrument mounted inside stage-scroll."""

    DEFAULT_CSS = """
    JudgeDesk {
        height: auto;
        width: 100%;
        padding: 0 0 1 0;
        background: #080b12;
    }

    JudgeDesk .judge-title {
        text-style: bold;
        color: #e8e8e8;
    }

    JudgeDesk .judge-sub {
        color: #5c6575;
        margin-bottom: 1;
    }

    JudgeDesk .limited-banner {
        background: #1a160e;
        color: #d4b06a;
        border: solid #3a3220;
        padding: 0 1;
        margin-bottom: 1;
        height: auto;
    }

    JudgeDesk .verdict-mast {
        background: #121a28;
        border: solid #2a2430;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
    }

    JudgeDesk .verdict-lab {
        color: #e8b86d;
        text-style: bold;
    }

    JudgeDesk .verdict-row {
        height: auto;
        margin: 1 0;
    }

    JudgeDesk .verdict-action {
        width: auto;
        text-style: bold;
        color: #e8e8e8;
        padding-right: 2;
    }

    JudgeDesk .verdict-action.action-enter { color: #7ecfb8; }
    JudgeDesk .verdict-action.action-watch { color: #d4b06a; }
    JudgeDesk .verdict-action.action-avoid { color: #e87a6e; }
    JudgeDesk .verdict-action.action-other { color: #e8e8e8; }

    JudgeDesk .verdict-gate {
        width: auto;
        color: #d4b06a;
        padding: 0 1;
    }

    JudgeDesk .verdict-gate.gate-open {
        color: #7ecfb8;
        background: #14241c;
    }

    JudgeDesk .verdict-gate.gate-block {
        color: #e87a6e;
        background: #241414;
    }

    JudgeDesk .verdict-gate.gate-other { color: #d4b06a; }

    JudgeDesk .score-strip {
        height: auto;
        margin-top: 1;
    }

    JudgeDesk .score-cell {
        width: 1fr;
        height: auto;
        padding-right: 1;
    }

    JudgeDesk .score-k {
        color: #5c6575;
        text-style: bold;
    }

    JudgeDesk .score-v {
        color: #f0ebe3;
        text-style: bold;
    }

    JudgeDesk .verdict-why {
        margin-top: 1;
        color: #8b92a0;
        height: auto;
    }

    JudgeDesk .phase-block {
        background: #0d121c;
        border: solid #1c2430;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
    }

    JudgeDesk .phase-title {
        color: #5c6575;
        text-style: bold;
    }

    JudgeDesk .phase-arrow {
        color: #e8e8e8;
        text-style: bold;
        margin-top: 1;
        height: auto;
    }

    JudgeDesk .phase-detail {
        color: #5c6575;
        height: auto;
    }

    JudgeDesk .phase-foot {
        color: #3a4252;
    }

    JudgeDesk .decision-block {
        background: #0d121c;
        border: solid #1c2430;
        border-left: solid #e8b86d;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
        color: #c9c3b8;
    }

    JudgeDesk .decision-title {
        color: #5c6575;
        text-style: bold;
    }

    JudgeDesk .cards-grid {
        height: auto;
        width: 100%;
        margin-bottom: 0;
    }

    JudgeDesk .cards-row {
        height: auto;
        width: 100%;
        margin-bottom: 1;
    }

    JudgeDesk .judge-card {
        width: 1fr;
        background: #0d121c;
        border: solid #1c2430;
        border-left: solid #3a4252;
        padding: 1 1;
        margin-right: 1;
        height: auto;
        color: #8b92a0;
    }

    JudgeDesk .judge-card.card-solo {
        width: 1fr;
        margin-right: 0;
    }

    JudgeDesk .judge-card.tone-open {
        border-left: solid #7ecfb8;
    }

    JudgeDesk .judge-card.tone-block {
        border-left: solid #e87a6e;
    }

    JudgeDesk .judge-card.tone-watch {
        border-left: solid #d4b06a;
    }

    JudgeDesk .judge-card.tone-neutral {
        border-left: solid #a89cc9;
    }

    JudgeDesk .judge-footer {
        color: #5c6575;
        margin-top: 1;
        height: auto;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._model: JudgeDeskModel | None = None

    def compose(self) -> ComposeResult:
        yield Static("", classes="judge-title", id="jd-title")
        yield Static("", classes="judge-sub", id="jd-sub")
        yield Static("", classes="limited-banner", id="jd-limited")
        with Vertical(classes="verdict-mast", id="jd-mast"):
            yield Static("JUDGMENT · VERDICT MAST", classes="verdict-lab", id="jd-lab")
            with Horizontal(classes="verdict-row", id="jd-verdict-row"):
                yield Static("—", classes="verdict-action action-other", id="jd-action")
                yield Static("Gate —", classes="verdict-gate gate-other", id="jd-gate")
            with Horizontal(classes="score-strip", id="jd-scores"):
                for i in range(6):
                    with Vertical(classes="score-cell", id=f"jd-score-{i}"):
                        yield Static("", classes="score-k", id=f"jd-score-k-{i}")
                        yield Static("", classes="score-v", id=f"jd-score-v-{i}")
            yield Static("", classes="verdict-why", id="jd-why")
        with Vertical(classes="phase-block", id="jd-phase"):
            yield Static("Phase sequence · ledger", classes="phase-title", id="jd-phase-title")
            yield Static("", classes="phase-arrow", id="jd-phase-arrow")
            yield Static("", classes="phase-detail", id="jd-phase-detail")
            yield Static("", classes="phase-foot", id="jd-phase-foot")
        with Vertical(classes="decision-block", id="jd-decision"):
            yield Static("DECISION STACK", classes="decision-title")
            yield Static("", id="jd-decision-body")
        # Fixed card slots: 2-col rows; each section has its own bordered card.
        with Vertical(classes="cards-grid", id="jd-cards-grid"):
            keys = list(_CARD_SLOT_KEYS)
            for i in range(0, len(keys), 2):
                left, right = keys[i], keys[i + 1] if i + 1 < len(keys) else None
                with Horizontal(classes="cards-row", id=f"jd-row-{i // 2}"):
                    yield Static("", classes="judge-card tone-neutral", id=f"jd-card-{left}")
                    if right:
                        yield Static(
                            "",
                            classes="judge-card tone-neutral",
                            id=f"jd-card-{right}",
                        )
        yield Static("", classes="judge-footer", id="jd-footer")

    def paint(self, model: JudgeDeskModel) -> None:
        """Refresh all child statics from model."""
        self._model = model
        self.query_one("#jd-title", Static).update(f"Judge · {model.ticker}")
        self.query_one("#jd-sub", Static).update(
            f"Screen · accumulation · #{model.rank}/{model.total} by Signal · present-only"
            + (f"\nBoard  {model.board_summary}" if model.board_summary else "")
        )
        limited = self.query_one("#jd-limited", Static)
        if model.limited:
            limited.display = True
            limited.update(
                "Limited judge · snapshot / no candidate · "
                "scalars only · j re-judge or r live for full desk"
            )
        else:
            limited.display = False
            limited.update("")

        action_el = self.query_one("#jd-action", Static)
        for c in ("action-enter", "action-watch", "action-avoid", "action-other"):
            action_el.remove_class(c)
        action_el.add_class("verdict-action")
        action_el.add_class(action_css_class(model.action))
        action_el.update(f"  {model.action or '—'}  ")

        gate_el = self.query_one("#jd-gate", Static)
        for c in ("gate-open", "gate-block", "gate-other"):
            gate_el.remove_class(c)
        gate_el.add_class("verdict-gate")
        gate_el.add_class(gate_css_class(model.gate))
        gate_el.update(f" Gate {model.gate or '—'} ")

        for i in range(6):
            if i < len(model.scores):
                cell = model.scores[i]
                self.query_one(f"#jd-score-k-{i}", Static).update(cell.label.upper())
                self.query_one(f"#jd-score-v-{i}", Static).update(cell.value)
            else:
                self.query_one(f"#jd-score-k-{i}", Static).update("")
                self.query_one(f"#jd-score-v-{i}", Static).update("")

        why = model.why if model.why and model.why != "—" else "—"
        self.query_one("#jd-why", Static).update(
            f"[bold #c9c3b8]Why {model.action or '—'}[/]  {why}"
        )

        self.query_one("#jd-phase-title", Static).update(
            model.phase_section_title.upper()
            if model.phase_section_title
            else "PHASE SEQUENCE · LEDGER"
        )
        self.query_one("#jd-phase-arrow", Static).update(
            _format_phase_arrow(model.phase_arrow) if model.phase_arrow else "—"
        )
        detail_parts = [
            f"· {x}" if not x.startswith("·") and not x.startswith("now") else x
            for x in model.phase_detail_lines
        ]
        self.query_one("#jd-phase-detail", Static).update("\n".join(detail_parts))
        self.query_one("#jd-phase-foot", Static).update(model.phase_footer)

        body_lines = [ln for ln in model.decision_lines if not ln.startswith("[")]
        if body_lines and "Decision" in body_lines[0]:
            body_lines = body_lines[1:]
        self.query_one("#jd-decision-body", Static).update("\n".join(body_lines) or "—")

        by_key = {c.key: c for c in model.cards}
        # Paint slots + hide empties; solo cards expand when pair mate missing.
        keys = list(_CARD_SLOT_KEYS)
        for i in range(0, len(keys), 2):
            left_k = keys[i]
            right_k = keys[i + 1] if i + 1 < len(keys) else None
            left_card = by_key.get(left_k)
            right_card = by_key.get(right_k) if right_k else None
            row = self.query_one(f"#jd-row-{i // 2}", Horizontal)
            left_el = self.query_one(f"#jd-card-{left_k}", Static)
            right_el = self.query_one(f"#jd-card-{right_k}", Static) if right_k else None

            if left_card is None and right_card is None:
                row.display = False
                left_el.display = False
                left_el.update("")
                if right_el is not None:
                    right_el.display = False
                    right_el.update("")
                continue

            row.display = True
            _paint_card_slot(left_el, left_card, solo=right_card is None and right_el is not None)
            if right_el is not None:
                _paint_card_slot(right_el, right_card, solo=left_card is None)

        self.query_one("#jd-footer", Static).update(model.footer)


def _paint_card_slot(el: Static, card: JudgeCard | None, *, solo: bool) -> None:
    for t in _TONE_CLASSES:
        el.remove_class(t)
    el.remove_class("card-solo")
    if card is None:
        el.display = False
        el.update("")
        return
    el.display = True
    tone = card.tone if card.tone in {"open", "block", "watch", "neutral"} else "neutral"
    el.add_class(f"tone-{tone}")
    if solo:
        el.add_class("card-solo")
    el.update(_format_card_markup(card))


def _format_card_markup(card: JudgeCard) -> str:
    """Title + headline + short body — design: uppercase label, bright value."""
    title = card.title.upper()
    lines = [f"[bold #5c6575]{title}[/]"]
    if card.headline:
        head_color = {
            "open": "#7ecfb8",
            "block": "#e87a6e",
            "watch": "#d4b06a",
            "neutral": "#f0ebe3",
        }.get(card.tone, "#f0ebe3")
        lines.append(f"[bold {head_color}]{card.headline}[/]")
    for ln in card.lines:
        if not ln:
            continue
        lines.append(_colorize_body_line(ln))
    return "\n".join(lines)


def _colorize_body_line(ln: str) -> str:
    """Tint gate chips; leave plain body mist-grey."""
    if "✓" in ln or "✗" in ln:
        # Color each chip token
        parts = ln.split()
        out: list[str] = []
        for p in parts:
            if p.startswith("✓"):
                out.append(f"[#7ecfb8]{p}[/]")
            elif p.startswith("✗"):
                out.append(f"[#e87a6e]{p}[/]")
            else:
                out.append(p)
        return " ".join(out)
    return f"[#8b92a0]{ln}[/]"


def _format_phase_arrow(arrow: str) -> str:
    """Highlight the last node (current phase) in brass."""
    if "→" not in arrow:
        return f"[bold #e8e8e8]{arrow}[/]"
    parts = [p.strip() for p in arrow.split("→")]
    if not parts:
        return arrow
    *head, last = parts
    bits = [f"[#8b92a0]{h}[/]" for h in head]
    bits.append(f"[bold #d4b06a]{last}[/]")
    return " [dim]→[/] ".join(bits)
