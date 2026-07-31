"""Session health poster desk — composed hierarchy (not markup soup only).

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from src.adapters.tui.health_poster_model import HealthPosterModel


class HealthPosterDesk(Vertical):
    DEFAULT_CSS = """
    HealthPosterDesk {
        height: auto;
        width: 100%;
        padding: 1 2;
        background: #0b0b0b;
    }
    HealthPosterDesk .hp-card {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #c9a68a;
        padding: 1 2;
        height: auto;
        margin-bottom: 0;
    }
    HealthPosterDesk .hp-kicker {
        color: #c9a68a;
        text-style: bold;
    }
    HealthPosterDesk .hp-title {
        color: #e8e8e8;
        text-style: bold;
        margin: 1 0;
        height: auto;
        border-top: solid #1c1c1c;
        padding-top: 1;
    }
    HealthPosterDesk .hp-body {
        color: #a0a0a0;
        height: auto;
        margin-bottom: 1;
    }
    HealthPosterDesk .hp-next {
        color: #d4b06a;
        height: auto;
        margin-bottom: 1;
        border-top: solid #1c1c1c;
        padding-top: 1;
    }
    HealthPosterDesk .hp-why {
        color: #6b6b6b;
        height: auto;
    }
    HealthPosterDesk .hp-footer {
        color: #555555;
        margin-top: 1;
        height: auto;
        border-top: solid #1c1c1c;
        padding-top: 1;
    }
    HealthPosterDesk.kind-empty .hp-card { border-left: solid #c97a72; }
    HealthPosterDesk.kind-lag .hp-card { border-left: solid #d4b06a; }
    HealthPosterDesk.kind-ready .hp-card { border-left: solid #6fbf8a; }
    HealthPosterDesk.kind-zero .hp-card { border-left: solid #8eb4d8; }
    HealthPosterDesk.kind-preopen .hp-card { border-left: solid #8eb4d8; }
    HealthPosterDesk.kind-broker .hp-card { border-left: solid #a89cc9; }
    """

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
