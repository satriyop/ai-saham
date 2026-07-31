"""Geometry-mast Plan desk widget (design: tui-plan-desk.html).

Inherit strip + Entry/Stop/Target triangle + context cards. Present-only.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from src.adapters.tui.judge_desk_model import action_css_class
from src.adapters.tui.plan_desk_model import PlanCard, PlanDeskModel

_CARD_KEYS: tuple[str, ...] = ("board", "sizing", "status")
_TONE_CLASSES = ("tone-open", "tone-block", "tone-watch", "tone-neutral")


class PlanDesk(Vertical):
    """Visual Plan instrument mounted inside stage-scroll."""

    DEFAULT_CSS = """
    PlanDesk {
        height: auto;
        width: 100%;
        padding: 0 0 1 0;
        background: #0b0b0b;
    }

    PlanDesk .plan-title {
        text-style: bold;
        color: #e8e8e8;
    }

    PlanDesk .plan-sub {
        color: #555555;
        margin-bottom: 1;
    }

    PlanDesk .inherit-strip {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #c9a68a;
        padding: 1 1;
        margin-bottom: 1;
        height: auto;
    }

    PlanDesk .inherit-action {
        width: auto;
        text-style: bold;
        padding-right: 2;
        color: #d4b06a;
        content-align: left middle;
    }

    PlanDesk .inherit-action.action-enter { color: #6fbf8a; }
    PlanDesk .inherit-action.action-watch { color: #d4b06a; }
    PlanDesk .inherit-action.action-avoid { color: #c97a72; }
    PlanDesk .inherit-action.action-other { color: #e8e8e8; }

    PlanDesk .inherit-note {
        color: #6b6b6b;
        height: auto;
        content-align: left middle;
    }

    PlanDesk .geo-mast {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #6fbf8a;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
    }

    PlanDesk .geo-lab {
        color: #6fbf8a;
        text-style: bold;
    }

    PlanDesk .geo-tri {
        height: auto;
        margin: 1 0;
        padding: 1 0;
        border-top: solid #1c1c1c;
        border-bottom: solid #1c1c1c;
    }

    PlanDesk .geo-pt {
        width: 1fr;
        height: auto;
        padding-right: 1;
    }

    PlanDesk .geo-k {
        color: #6b6b6b;
        text-style: bold;
    }

    PlanDesk .geo-v {
        color: #e8e8e8;
        text-style: bold;
        margin-top: 0;
    }

    PlanDesk .geo-v.entry { color: #c9a68a; }
    PlanDesk .geo-v.stop { color: #c97a72; }
    PlanDesk .geo-v.target { color: #6fbf8a; }

    PlanDesk .geo-arr {
        width: auto;
        color: #555555;
        padding: 1 1 0 0;
        content-align: center middle;
    }

    PlanDesk .lots-row {
        height: auto;
        margin-top: 1;
        padding-top: 0;
    }

    PlanDesk .lots-cell {
        width: 1fr;
        height: auto;
        padding-right: 1;
    }

    PlanDesk .lots-k {
        color: #6b6b6b;
        text-style: bold;
    }

    PlanDesk .lots-v {
        color: #e8e8e8;
        text-style: bold;
    }

    PlanDesk .no-order {
        margin-top: 1;
        background: #1a1810;
        color: #c9a68a;
        border: solid #3a3220;
        padding: 0 1;
        height: auto;
    }

    PlanDesk .running-banner {
        background: #1a1810;
        color: #d4b06a;
        border: solid #3a3220;
        padding: 0 1;
        margin-bottom: 1;
        height: auto;
    }

    PlanDesk .cards-grid {
        height: auto;
        width: 100%;
    }

    PlanDesk .cards-row {
        height: auto;
        width: 100%;
        margin-bottom: 1;
    }

    PlanDesk .plan-card {
        width: 1fr;
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #3a4252;
        padding: 1 2;
        margin-right: 1;
        height: auto;
        color: #7a7a7a;
    }

    PlanDesk .plan-card.card-solo {
        margin-right: 0;
    }

    PlanDesk .plan-card.tone-open { border-left: solid #6fbf8a; }
    PlanDesk .plan-card.tone-block { border-left: solid #c97a72; }
    PlanDesk .plan-card.tone-watch { border-left: solid #d4b06a; }
    PlanDesk .plan-card.tone-neutral { border-left: solid #a89cc9; }

    PlanDesk .paper-tape {
        background: #1a1810;
        border: solid #3a3220;
        border-left: solid #c9a68a;
        padding: 1 1;
        margin-bottom: 1;
        height: auto;
        color: #d8d8d8;
    }

    PlanDesk .plan-footer {
        color: #555555;
        margin-top: 0;
        height: auto;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._model: PlanDeskModel | None = None

    def compose(self) -> ComposeResult:
        yield Static("", classes="plan-title", id="pd-title")
        yield Static("", classes="plan-sub", id="pd-sub")
        yield Static("", classes="running-banner", id="pd-running")
        with Horizontal(classes="inherit-strip", id="pd-inherit"):
            yield Static("—", classes="inherit-action action-other", id="pd-action")
            yield Static("", classes="inherit-note", id="pd-inherit-note")
        with Vertical(classes="geo-mast", id="pd-geo"):
            yield Static("Structure · plan geometry", classes="geo-lab", id="pd-geo-lab")
            with Horizontal(classes="geo-tri", id="pd-tri"):
                with Vertical(classes="geo-pt", id="pd-pt-entry"):
                    yield Static("ENTRY", classes="geo-k")
                    yield Static("—", classes="geo-v entry", id="pd-entry")
                yield Static("→", classes="geo-arr")
                with Vertical(classes="geo-pt", id="pd-pt-stop"):
                    yield Static("STOP", classes="geo-k")
                    yield Static("—", classes="geo-v stop", id="pd-stop")
                yield Static("→", classes="geo-arr")
                with Vertical(classes="geo-pt", id="pd-pt-target"):
                    yield Static("TARGET", classes="geo-k")
                    yield Static("—", classes="geo-v target", id="pd-target")
            with Horizontal(classes="lots-row", id="pd-lots-row"):
                for key, label in (
                    ("lots", "LOTS"),
                    ("risk", "RISK %"),
                    ("planid", "PLAN ID"),
                    ("horizon", "HORIZON"),
                ):
                    with Vertical(classes="lots-cell", id=f"pd-meta-{key}"):
                        yield Static(label, classes="lots-k")
                        yield Static("—", classes="lots-v", id=f"pd-meta-v-{key}")
            yield Static("", classes="no-order", id="pd-no-order")
        with Vertical(classes="cards-grid", id="pd-cards"):
            # 2 + 1: board|sizing, then status full-width
            with Horizontal(classes="cards-row", id="pd-row-0"):
                yield Static("", classes="plan-card tone-neutral", id="pd-card-board")
                yield Static("", classes="plan-card tone-neutral", id="pd-card-sizing")
            with Horizontal(classes="cards-row", id="pd-row-1"):
                yield Static(
                    "",
                    classes="plan-card tone-neutral card-solo",
                    id="pd-card-status",
                )
        yield Static("", classes="paper-tape", id="pd-paper-tape")
        yield Static("", classes="plan-footer", id="pd-footer")

    def paint(self, model: PlanDeskModel) -> None:
        """Refresh all child statics from model."""
        self._model = model
        self.query_one("#pd-title", Static).update(f"Plan · {model.ticker}")
        self.query_one("#pd-sub", Static).update(
            f"from {model.source} · #{model.rank}/{model.total} · local structure"
        )

        running = self.query_one("#pd-running", Static)
        if model.running and not model.has_geometry:
            running.display = True
            running.update("Running… local plan swing · no order")
        else:
            running.display = False
            running.update("")

        act = self.query_one("#pd-action", Static)
        for c in ("action-enter", "action-watch", "action-avoid", "action-other"):
            act.remove_class(c)
        act.add_class("inherit-action")
        act.add_class(action_css_class(model.action))
        act.update(f" {model.action or '—'} ")
        note = model.inherit_note or "inherited from board · structure only"
        self.query_one("#pd-inherit-note", Static).update(note)

        # Geometry hero label: Structure · horizon (mock geo-hero)
        horizon = model.horizon or "swing"
        self.query_one("#pd-geo-lab", Static).update(f"Structure · {horizon}")
        self.query_one("#pd-entry", Static).update(model.entry or "—")
        self.query_one("#pd-stop", Static).update(model.stop or "—")
        self.query_one("#pd-target", Static).update(model.target or "—")

        self.query_one("#pd-meta-v-lots", Static).update(model.lots or "—")
        self.query_one("#pd-meta-v-risk", Static).update(model.risk_pct or "—")
        self.query_one("#pd-meta-v-planid", Static).update(model.plan_id or "—")
        self.query_one("#pd-meta-v-horizon", Static).update(model.horizon or "swing")

        no_order = self.query_one("#pd-no-order", Static)
        if model.no_order:
            no_order.display = True
            extra = ""
            if model.incomplete_reason:
                extra = f" · {model.incomplete_reason}"
            no_order.update("No broker order · geometry for paper journal · l to paper log" + extra)
        else:
            no_order.display = False

        by_key = {c.key: c for c in model.cards}
        for key in _CARD_KEYS:
            el = self.query_one(f"#pd-card-{key}", Static)
            card = by_key.get(key)
            _paint_card(el, card)

        tape = self.query_one("#pd-paper-tape", Static)
        if model.paper_outcome:
            tape.display = True
            tape.update(model.paper_outcome)
        else:
            tape.display = False
            tape.update("")

        self.query_one("#pd-footer", Static).update(model.footer)


def _paint_card(el: Static, card: PlanCard | None) -> None:
    for t in _TONE_CLASSES:
        el.remove_class(t)
    if card is None:
        el.display = False
        el.update("")
        return
    el.display = True
    tone = card.tone if card.tone in {"open", "block", "watch", "neutral"} else "neutral"
    el.add_class(f"tone-{tone}")
    el.update(_format_card(card))


def _format_card(card: PlanCard) -> str:
    lines = [f"[bold #555555]{card.title.upper()}[/]"]
    if card.headline:
        head_color = {
            "open": "#6fbf8a",
            "block": "#c97a72",
            "watch": "#d4b06a",
            "neutral": "#e8e8e8",
        }.get(card.tone, "#e8e8e8")
        lines.append(f"[bold {head_color}]{card.headline}[/]")
    for ln in card.lines:
        if ln:
            lines.append(f"[#7a7a7a]{ln}[/]")
    return "\n".join(lines)
