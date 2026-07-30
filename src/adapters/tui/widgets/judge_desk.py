"""Verdict-mast Judge desk widget (design: tui-judge-desk.html).

Composed surfaces + CSS — not a CLI text dump. Present-only data via JudgeDeskModel.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from src.adapters.tui.judge_desk_model import (
    JudgeDeskModel,
    action_css_class,
    gate_css_class,
)


class JudgeDesk(Vertical):
    """Visual Judge instrument mounted inside stage-scroll."""

    DEFAULT_CSS = """
    JudgeDesk {
        height: auto;
        width: 100%;
        padding: 0 0 1 0;
        background: #080b12;
    }

    JudgeDesk .judge-chrome {
        color: #5c6575;
        margin-bottom: 1;
    }

    JudgeDesk .judge-title {
        text-style: bold;
        color: #e8e8e8;
    }

    JudgeDesk .judge-sub {
        color: #5c6575;
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
        margin-bottom: 0;
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

    JudgeDesk .verdict-action.action-enter {
        color: #6fbf8a;
    }

    JudgeDesk .verdict-action.action-watch {
        color: #d4b06a;
    }

    JudgeDesk .verdict-action.action-avoid {
        color: #c97a72;
    }

    JudgeDesk .verdict-action.action-other {
        color: #e8e8e8;
    }

    JudgeDesk .verdict-gate {
        width: auto;
        color: #d4b06a;
        padding: 0 1;
    }

    JudgeDesk .verdict-gate.gate-open {
        color: #6fbf8a;
        background: #14241c;
    }

    JudgeDesk .verdict-gate.gate-block {
        color: #c97a72;
        background: #241414;
    }

    JudgeDesk .verdict-gate.gate-other {
        color: #d4b06a;
    }

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
        color: #9b8fb8;
        text-style: bold;
    }

    JudgeDesk .phase-arrow {
        color: #e8e8e8;
        text-style: bold;
        margin: 1 0 0 0;
        height: auto;
    }

    JudgeDesk .phase-detail {
        color: #5c6575;
        height: auto;
    }

    JudgeDesk .phase-foot {
        color: #3a4252;
        margin-top: 0;
    }

    JudgeDesk .decision-block {
        background: #0d121c;
        border: solid #1c2430;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
        color: #c9c3b8;
    }

    JudgeDesk .decision-title {
        color: #d4b06a;
        text-style: bold;
    }

    JudgeDesk .cards-row {
        height: auto;
        margin-bottom: 1;
    }

    JudgeDesk .judge-card {
        width: 1fr;
        background: #0d121c;
        border: solid #1c2430;
        padding: 1 1;
        margin-right: 1;
        height: auto;
        color: #8b92a0;
    }

    JudgeDesk .judge-card-title {
        color: #9b8fb8;
        text-style: bold;
        margin-bottom: 0;
    }

    JudgeDesk .judge-card-body {
        color: #c9c3b8;
        height: auto;
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
            yield Static("Decision stack", classes="decision-title")
            yield Static("", id="jd-decision-body")
        with Horizontal(classes="cards-row", id="jd-cards"):
            yield Static("", classes="judge-card", id="jd-card-0")
            yield Static("", classes="judge-card", id="jd-card-1")
        yield Static("", classes="judge-card", id="jd-card-more")
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
        # Large-ish label via padded text (terminal type scale)
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
        self.query_one("#jd-why", Static).update(f"Why {model.action or '—'}  {why}")

        self.query_one("#jd-phase-title", Static).update(model.phase_section_title)
        self.query_one("#jd-phase-arrow", Static).update(model.phase_arrow or "—")
        detail_parts = [f"· {x}" if not x.startswith("·") else x for x in model.phase_detail_lines]
        self.query_one("#jd-phase-detail", Static).update("\n".join(detail_parts))
        self.query_one("#jd-phase-foot", Static).update(model.phase_footer)

        # Drop section color headers from decision_lines if present
        body_lines = [ln for ln in model.decision_lines if not ln.startswith("[")]
        if body_lines and "Decision" in body_lines[0]:
            body_lines = body_lines[1:]
        self.query_one("#jd-decision-body", Static).update("\n".join(body_lines) or "—")

        # Two primary cards + overflow
        cards = list(model.cards)
        for i, slot in enumerate(("jd-card-0", "jd-card-1")):
            el = self.query_one(f"#{slot}", Static)
            if i < len(cards):
                title, lines = cards[i]
                el.display = True
                el.update(f"[bold #9b8fb8]{title}[/]\n" + "\n".join(lines))
            else:
                el.display = False
                el.update("")

        more = self.query_one("#jd-card-more", Static)
        if len(cards) > 2:
            chunks: list[str] = []
            for title, lines in cards[2:]:
                chunks.append(f"[bold #9b8fb8]{title}[/]")
                chunks.extend(lines)
                chunks.append("")
            more.display = True
            more.update("\n".join(chunks).rstrip())
        else:
            more.display = False
            more.update("")

        self.query_one("#jd-footer", Static).update(model.footer)
