"""Session health poster desk — composed hierarchy (not markup soup only).

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from src.adapters.tui.health_poster_model import HealthPosterModel
from src.adapters.tui.theme import bake_css


class HealthPosterDesk(Vertical):
    DEFAULT_CSS = bake_css("""
    HealthPosterDesk {
        height: auto;
        width: 100%;
        padding: 1 2;
        background: $oc_bg;
    }
    HealthPosterDesk .hp-card {
        background: $oc_bg_elevated;
        border: solid $oc_border;
        border-left: solid $oc_peach;
        padding: 1 2;
        height: auto;
        margin-bottom: 0;
    }
    HealthPosterDesk .hp-kicker {
        color: $oc_peach;
        text-style: bold;
    }
    HealthPosterDesk .hp-title {
        color: $oc_text_bright;
        text-style: bold;
        margin: 1 0;
        height: auto;
        border-top: solid $oc_border;
        padding-top: 1;
    }
    HealthPosterDesk .hp-body {
        color: $oc_text_dim;
        height: auto;
        margin-bottom: 1;
    }
    HealthPosterDesk .hp-next {
        color: $oc_brass;
        height: auto;
        margin-bottom: 1;
        border-top: solid $oc_border;
        padding-top: 1;
    }
    HealthPosterDesk .hp-why {
        color: $oc_dim;
        height: auto;
    }
    HealthPosterDesk .hp-footer {
        color: $oc_text_mute;
        margin-top: 1;
        height: auto;
        border-top: solid $oc_border;
        padding-top: 1;
    }
    HealthPosterDesk.kind-empty .hp-card { border-left: solid $oc_coral; }
    HealthPosterDesk.kind-lag .hp-card { border-left: solid $oc_brass; }
    HealthPosterDesk.kind-ready .hp-card { border-left: solid $oc_mint; }
    HealthPosterDesk.kind-zero .hp-card { border-left: solid $oc_blue; }
    HealthPosterDesk.kind-preopen .hp-card { border-left: solid $oc_blue; }
    HealthPosterDesk.kind-broker .hp-card { border-left: solid $oc_purple; }
    """)

    def compose(self) -> ComposeResult:
        with Vertical(classes="hp-card", id="hp-card"):
            yield Static("", id="hp-kicker", classes="hp-kicker")
            yield Static("", id="hp-title", classes="hp-title")
            yield Static("", id="hp-body", classes="hp-body")
            yield Static("", id="hp-next", classes="hp-next")
            yield Static("", id="hp-why", classes="hp-why")
        yield Static("", id="hp-footer", classes="hp-footer")

    def on_mount(self) -> None:
        self.display = False

    def paint(self, model: HealthPosterModel) -> None:
        for c in list(self.classes):
            if str(c).startswith("kind-"):
                self.remove_class(str(c))
        self.add_class(f"kind-{model.kind}")
        self.query_one("#hp-kicker", Static).update(model.kicker)
        self.query_one("#hp-title", Static).update(model.title)
        self.query_one("#hp-body", Static).update("\n".join(model.body_lines))
        self.query_one("#hp-next", Static).update(f"Next  {model.next_cue}")
        why = "\n".join(f"· {w}" for w in model.why_lines)
        self.query_one("#hp-why", Static).update(why)
        self.query_one("#hp-footer", Static).update(model.footer)
