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
from src.adapters.tui.theme import OC, bake_css
from src.adapters.tui.widgets.chip_bar import BROKER_HOME_CHIPS, ChipBar
from src.adapters.tui.widgets.flag_chip import FlagChip


class BrokerDesk(Vertical):
    """Structured desk home mounted inside stage-scroll."""

    DEFAULT_CSS = bake_css("""
    BrokerDesk {
        height: auto;
        width: 100%;
        padding: 0 0 1 0;
        background: $oc_bg;
    }

    BrokerDesk .bd-title {
        text-style: bold;
        color: $oc_text_bright;
    }

    BrokerDesk .bd-sub {
        color: $oc_dim;
        margin-bottom: 1;
    }

    BrokerDesk .bd-scope {
        color: $oc_purple;
        margin-bottom: 1;
        height: auto;
    }

    BrokerDesk .bd-hero {
        background: $oc_bg_elevated;
        border: solid $oc_border;
        border-left: solid $oc_peach;
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
        color: $oc_peach;
        text-style: bold;
    }

    BrokerDesk .bd-net-row {
        height: auto;
        margin: 1 0 0 0;
    }

    BrokerDesk .bd-sign {
        width: auto;
        text-style: bold;
        color: $oc_text_bright;
        padding-right: 1;
        content-align: left bottom;
    }

    BrokerDesk .bd-amt {
        width: auto;
        text-style: bold;
        color: $oc_text_bright;
        padding-right: 1;
    }

    BrokerDesk .bd-unit {
        width: auto;
        color: $oc_dim;
        content-align: left bottom;
    }

    BrokerDesk .bd-net-row.pos .bd-sign,
    BrokerDesk .bd-net-row.pos .bd-amt {
        color: $oc_mint;
    }

    BrokerDesk .bd-net-row.neg .bd-sign,
    BrokerDesk .bd-net-row.neg .bd-amt {
        color: $oc_coral;
    }

    BrokerDesk .bd-subline {
        color: $oc_dim;
        margin-top: 1;
        height: auto;
        border-top: solid $oc_border;
        padding-top: 1;
    }

    BrokerDesk .bd-side {
        width: 2fr;
        height: auto;
        padding-left: 1;
        border-left: solid $oc_border;
    }

    BrokerDesk .bd-stat {
        height: auto;
        color: $oc_text_dim;
        margin-bottom: 0;
    }

    BrokerDesk .bd-stat .k {
        color: $oc_dim;
        width: 12;
    }

    BrokerDesk .bd-stat .v {
        color: $oc_text_bright;
        text-style: bold;
    }

    BrokerDesk .bd-stat .v.pos { color: $oc_mint; }
    BrokerDesk .bd-stat .v.neg { color: $oc_coral; }

    BrokerDesk .bd-cols {
        height: auto;
        margin-bottom: 1;
    }

    BrokerDesk .bd-col {
        width: 1fr;
        height: auto;
        padding: 0 1 1 1;
        margin-right: 1;
        background: $oc_bg_elevated;
        border: solid $oc_border;
    }

    BrokerDesk .bd-col.buy {
        border-left: solid $oc_mint;
    }

    BrokerDesk .bd-col.sell {
        border-left: solid $oc_coral;
        margin-right: 0;
    }

    BrokerDesk .bd-col-title {
        color: $oc_peach;
        text-style: bold;
        margin-bottom: 0;
        height: auto;
        border-bottom: solid $oc_border;
        padding-bottom: 0;
    }

    BrokerDesk .bd-row {
        height: auto;
        color: $oc_text;
        border-top: solid $oc_border;
        padding: 0 0;
    }

    BrokerDesk .bd-row .tk {
        width: 8;
        text-style: bold;
        color: $oc_text_bright;
    }

    BrokerDesk .bd-row .nv.pos { color: $oc_mint; }
    BrokerDesk .bd-row .nv.neg { color: $oc_coral; }

    BrokerDesk .bd-hub {
        background: $oc_bg_elevated;
        border: solid $oc_border;
        border-left: solid $oc_hairline_strong;
        padding: 0 1;
        height: auto;
        color: $oc_purple;
    }

    BrokerDesk .bd-empty {
        color: $oc_dim;
        height: auto;
        margin: 1 0;
    }

    BrokerDesk .bd-flags {
        height: auto;
        margin: 0 0 1 0;
        padding: 0 0 1 0;
        border-bottom: solid $oc_border;
    }

    """)

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
        yield ChipBar(
            id="bd-flags",
            chips=BROKER_HOME_CHIPS,
            chip_id_prefix="bd-flag",
        )
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
                    color = OC.mint
                elif s.tone == "neg":
                    color = OC.coral
                else:
                    color = OC.text_bright
                slot.update(f"[dim]{s.key:<12}[/] [bold {color}]{s.value}[/]")
            else:
                slot.update("")

        for i in range(5):
            buy = self.query_one(f"#bd-buy-{i}", Static)
            if i < len(model.top_buy):
                r = model.top_buy[i]
                col = OC.mint if r.tone == "pos" else OC.coral
                buy.update(f"[bold {OC.text_bright}]{r.ticker:<6}[/]  [{col}]{r.net_display}[/]")
            else:
                buy.update("[dim]—[/]" if i == 0 and not model.top_buy else "")

        for i in range(5):
            sell = self.query_one(f"#bd-sell-{i}", Static)
            if i < len(model.top_sell):
                r = model.top_sell[i]
                col = OC.mint if r.tone == "pos" else OC.coral
                sell.update(f"[bold {OC.text_bright}]{r.ticker:<6}[/]  [{col}]{r.net_display}[/]")
            else:
                sell.update("[dim]—[/]" if i == 0 and not model.top_sell else "")

        empty = self.query_one("#bd-empty", Static)
        if model.empty:
            empty.update(model.empty_reason)
            empty.display = True
        else:
            empty.update("")
            empty.display = False

        # Job chips (product labels · power t f c h m)
        try:
            bar = self.query_one("#bd-flags", ChipBar)
            if model.empty:
                bar.paint_states(dim_keys=("t", "f", "c", "h", "m"))
            else:
                bar.paint_states(on_keys=())
        except Exception:
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
