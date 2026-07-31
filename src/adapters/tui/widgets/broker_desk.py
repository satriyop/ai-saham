"""Broker desk-home widget — day-net hero + pulse side + hub keys.

Present-only browse. Design ref: docs/design/tui-cockpit-opencode.md broker home.
OpenCode-adjacent tokens (dark panel + peach accents), not journey skin.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from src.adapters.tui.broker_desk_home_model import BrokerDeskHomeModel
from src.adapters.tui.widgets.flag_chip import FlagChip


class BrokerDesk(Vertical):
    """Structured desk home mounted inside stage-scroll."""

    DEFAULT_CSS = """
    BrokerDesk {
        height: auto;
        width: 100%;
        padding: 0 0 1 0;
        background: #0b0b0b;
    }

    BrokerDesk .bd-title {
        text-style: bold;
        color: #e8e8e8;
    }

    BrokerDesk .bd-sub {
        color: #6b6b6b;
        margin-bottom: 1;
    }

    BrokerDesk .bd-scope {
        color: #9b8fb8;
        margin-bottom: 1;
        height: auto;
    }

    BrokerDesk .bd-hero {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #c9a68a;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
    }

    BrokerDesk .bd-hero-main {
        width: 3fr;
        height: auto;
        padding-right: 2;
    }

    BrokerDesk .bd-lab {
        color: #c9a68a;
        text-style: bold;
    }

    BrokerDesk .bd-net-row {
        height: auto;
        margin: 1 0 0 0;
    }

    BrokerDesk .bd-sign {
        width: auto;
        text-style: bold;
        color: #e8e8e8;
        padding-right: 1;
        content-align: left bottom;
    }

    BrokerDesk .bd-amt {
        width: auto;
        text-style: bold;
        color: #e8e8e8;
        padding-right: 1;
    }

    BrokerDesk .bd-unit {
        width: auto;
        color: #6b6b6b;
        content-align: left bottom;
    }

    BrokerDesk .bd-net-row.pos .bd-sign,
    BrokerDesk .bd-net-row.pos .bd-amt {
        color: #6fbf8a;
    }

    BrokerDesk .bd-net-row.neg .bd-sign,
    BrokerDesk .bd-net-row.neg .bd-amt {
        color: #c97a72;
    }

    BrokerDesk .bd-subline {
        color: #6b6b6b;
        margin-top: 1;
        height: auto;
        border-top: solid #1c1c1c;
        padding-top: 1;
    }

    BrokerDesk .bd-side {
        width: 2fr;
        height: auto;
        padding-left: 1;
        border-left: solid #1c1c1c;
    }

    BrokerDesk .bd-stat {
        height: auto;
        color: #a0a0a0;
        margin-bottom: 0;
    }

    BrokerDesk .bd-stat .k {
        color: #6b6b6b;
        width: 12;
    }

    BrokerDesk .bd-stat .v {
        color: #e8e8e8;
        text-style: bold;
    }

    BrokerDesk .bd-stat .v.pos { color: #6fbf8a; }
    BrokerDesk .bd-stat .v.neg { color: #c97a72; }

    BrokerDesk .bd-cols {
        height: auto;
        margin-bottom: 1;
    }

    BrokerDesk .bd-col {
        width: 1fr;
        height: auto;
        padding: 0 1 1 1;
        margin-right: 1;
        background: #141414;
        border: solid #1c1c1c;
    }

    BrokerDesk .bd-col.buy {
        border-left: solid #6fbf8a;
    }

    BrokerDesk .bd-col.sell {
        border-left: solid #c97a72;
        margin-right: 0;
    }

    BrokerDesk .bd-col-title {
        color: #c9a68a;
        text-style: bold;
        margin-bottom: 0;
        height: auto;
        border-bottom: solid #1c1c1c;
        padding-bottom: 0;
    }

    BrokerDesk .bd-row {
        height: auto;
        color: #c8c8c8;
        border-top: solid #1c1c1c;
        padding: 0 0;
    }

    BrokerDesk .bd-row .tk {
        width: 8;
        text-style: bold;
        color: #ececec;
    }

    BrokerDesk .bd-row .nv.pos { color: #6fbf8a; }
    BrokerDesk .bd-row .nv.neg { color: #c97a72; }

    BrokerDesk .bd-hub {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #3a4252;
        padding: 0 1;
        height: auto;
        color: #9b8fb8;
    }

    BrokerDesk .bd-empty {
        color: #6b6b6b;
        height: auto;
        margin: 1 0;
    }

    BrokerDesk .bd-flags {
        height: auto;
        margin: 0 0 1 0;
        padding: 0 0 1 0;
        border-bottom: solid #1c1c1c;
    }

    BrokerDesk .bd-flag-lab {
        width: auto;
        color: #6b6b6b;
        text-style: bold;
        padding-right: 1;
    }

    BrokerDesk .bd-flag-chip {
        width: auto;
        color: #8a8a8a;
        background: #141414;
        border: solid #1c1c1c;
        padding: 0 1;
        margin-right: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="bd-title", classes="bd-title")
        yield Static("", id="bd-sub", classes="bd-sub")
        yield Static("", id="bd-scope", classes="bd-scope")
        with Horizontal(classes="bd-hero", id="bd-hero"):
            with Vertical(classes="bd-hero-main"):
                yield Static("Day net · desk", id="bd-lab", classes="bd-lab")
                with Horizontal(id="bd-net-row", classes="bd-net-row"):
                    yield Static("", id="bd-sign", classes="bd-sign")
                    yield Static("", id="bd-amt", classes="bd-amt")
                    yield Static("IDR", id="bd-unit", classes="bd-unit")
                yield Static("", id="bd-subline", classes="bd-subline")
            with Vertical(classes="bd-side", id="bd-side"):
                for i in range(4):
                    yield Static("", id=f"bd-stat-{i}", classes="bd-stat")
        with Horizontal(classes="bd-cols", id="bd-cols"):
            with Vertical(classes="bd-col buy", id="bd-buy-col"):
                yield Static("Top buy · day", classes="bd-col-title")
                for i in range(5):
                    yield Static("", id=f"bd-buy-{i}", classes="bd-row")
            with Vertical(classes="bd-col sell", id="bd-sell-col"):
                yield Static("Top sell · day", classes="bd-col-title")
                for i in range(5):
                    yield Static("", id=f"bd-sell-{i}", classes="bd-row")
        with Horizontal(classes="bd-flags", id="bd-flags"):
            yield Static("Deep", classes="bd-flag-lab", id="bd-flag-lab")
            for key, lab in (
                ("t", "deep.t"),
                ("f", "deep.f"),
                ("c", "deep.c"),
                ("h", "deep.h"),
                ("m", "deep.m"),
            ):
                yield FlagChip(key, lab, id=f"bd-flag-{key}")
        yield Static("", id="bd-empty", classes="bd-empty")
        yield Static("", id="bd-hub", classes="bd-hub")

    def on_mount(self) -> None:
        self.display = False

    def paint(self, model: BrokerDeskHomeModel) -> None:
        """Paint structured desk home from pure model."""
        self.query_one("#bd-title", Static).update(f"Broker · {model.broker_code}")
        self.query_one("#bd-sub", Static).update(
            f"{model.broker_name} · {model.type_label} · as of {model.as_of} · local cache"
        )
        self.query_one("#bd-scope", Static).update(model.scope_note)
        self.query_one("#bd-lab", Static).update("Day net · desk")

        net_row = self.query_one("#bd-net-row", Horizontal)
        net_row.remove_class("pos", "neg", "flat")
        net_row.add_class(model.day_net_tone if model.day_net_tone in {"pos", "neg"} else "flat")
        self.query_one("#bd-sign", Static).update(model.day_net_sign or " ")
        self.query_one("#bd-amt", Static).update(model.day_net_amount)
        self.query_one("#bd-unit", Static).update("IDR")
        self.query_one("#bd-subline", Static).update(model.day_net_sub)

        for i in range(4):
            slot = self.query_one(f"#bd-stat-{i}", Static)
            if i < len(model.side_stats):
                s = model.side_stats[i]
                if s.tone == "pos":
                    color = "#6fbf8a"
                elif s.tone == "neg":
                    color = "#c97a72"
                else:
                    color = "#e8e8e8"
                slot.update(f"[dim]{s.key:<12}[/] [bold {color}]{s.value}[/]")
            else:
                slot.update("")

        for i in range(5):
            buy = self.query_one(f"#bd-buy-{i}", Static)
            if i < len(model.top_buy):
                r = model.top_buy[i]
                col = "#6fbf8a" if r.tone == "pos" else "#c97a72"
                buy.update(f"[bold #ececec]{r.ticker:<6}[/]  [{col}]{r.net_display}[/]")
            else:
                buy.update("[dim]—[/]" if i == 0 and not model.top_buy else "")

        for i in range(5):
            sell = self.query_one(f"#bd-sell-{i}", Static)
            if i < len(model.top_sell):
                r = model.top_sell[i]
                col = "#6fbf8a" if r.tone == "pos" else "#c97a72"
                sell.update(f"[bold #ececec]{r.ticker:<6}[/]  [{col}]{r.net_display}[/]")
            else:
                sell.update("[dim]—[/]" if i == 0 and not model.top_sell else "")

        empty = self.query_one("#bd-empty", Static)
        if model.empty:
            empty.update(model.empty_reason)
            empty.display = True
        else:
            empty.update("")
            empty.display = False

        # Deep affordance chips (keys navigate; chips = bible deep.* flags)
        for key in ("t", "f", "c", "h", "m"):
            chip = self.query_one(f"#bd-flag-{key}", FlagChip)
            chip.set_chip_state(available=not model.empty, expanded=False)

        self.query_one("#bd-hub", Static).update(model.hub_keys)

    def on_flag_chip_selected(self, event: FlagChip.Selected) -> None:
        """deep.t/f/c/h/m → same hub actions as keys."""
        event.stop()
        key = event.flag_key
        try:
            app = self.app
        except Exception:
            return
        actions = {
            "t": "action_broker_top",
            "f": "action_broker_flow",
            "c": "action_broker_calendar",
            "h": "action_broker_history",
            "m": "action_broker_matrix",
        }
        meth = actions.get(key)
        if meth and hasattr(app, meth):
            getattr(app, meth)()
