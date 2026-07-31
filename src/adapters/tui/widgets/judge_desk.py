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
from src.adapters.tui.widgets.flag_chip import FlagChip

# Max cards we pre-compose (full desk + limited scalars).
_CARD_SLOT_KEYS: tuple[str, ...] = CARD_ORDER_FULL + (CARD_SCALARS,)
_TONE_CLASSES = ("tone-open", "tone-block", "tone-watch", "tone-neutral")

# Mock flag-chip row (design: judgeFlags). Single chips expand panels; detail · d = all.
FLAG_CHIP_DEFS: tuple[tuple[str, str], ...] = (
    ("detail", "detail · d"),
    ("stack", "stack"),
    ("readiness", "readiness"),
    ("named", "named"),
    ("mce", "mce"),
    ("phase_plus", "phase+"),
    ("limited", "limited"),
)
# Expandable panel keys (not limited state chip; not the master detail chip)
_EXPANDABLE_FLAGS = frozenset({"stack", "readiness", "named", "mce", "phase_plus"})


class JudgeDesk(Vertical):
    """Visual Judge instrument mounted inside stage-scroll."""

    DEFAULT_CSS = """
    JudgeDesk {
        height: auto;
        width: 100%;
        padding: 0 0 1 0;
        background: #0b0b0b;
    }

    JudgeDesk .judge-title {
        text-style: bold;
        color: #e8e8e8;
    }

    JudgeDesk .judge-sub {
        color: #555555;
        margin-bottom: 1;
    }

    JudgeDesk .limited-banner {
        background: #1a1810;
        color: #d4b06a;
        border: solid #3a3220;
        padding: 0 1;
        margin-bottom: 1;
        height: auto;
    }

    JudgeDesk .verdict-mast {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #c9a68a;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
    }

    JudgeDesk .verdict-lab {
        color: #c9a68a;
        text-style: bold;
        height: 1;
        margin-bottom: 0;
    }

    /* Single baseline row: Action hero + Gate badge (mock: flex align baseline) */
    JudgeDesk .verdict-row {
        height: 3;
        width: 100%;
        margin: 0 0 1 0;
        align: left middle;
    }

    JudgeDesk .verdict-action {
        width: auto;
        height: 3;
        text-style: bold;
        color: #e8e8e8;
        padding: 0 2 0 0;
        content-align: left middle;
    }

    JudgeDesk .verdict-action.action-enter { color: #6fbf8a; }
    JudgeDesk .verdict-action.action-watch { color: #d4b06a; }
    JudgeDesk .verdict-action.action-avoid { color: #c97a72; }
    JudgeDesk .verdict-action.action-other { color: #e8e8e8; }

    JudgeDesk .verdict-gate {
        width: auto;
        height: 3;
        color: #d4b06a;
        padding: 0 1;
        border: solid #2a2a2a;
        background: #121212;
        content-align: center middle;
    }

    JudgeDesk .verdict-gate.gate-open {
        color: #6fbf8a;
        background: #121a14;
        border: solid #1c4038;
    }

    JudgeDesk .verdict-gate.gate-block {
        color: #c97a72;
        background: #1a1212;
        border: solid #3a2220;
    }

    JudgeDesk .verdict-gate.gate-other { color: #d4b06a; }

    JudgeDesk .score-strip {
        height: auto;
        margin-top: 1;
        padding-top: 1;
        border-top: solid #1c1c1c;
    }

    JudgeDesk .score-cell {
        width: 1fr;
        height: auto;
        min-width: 8;
        max-width: 18;
        padding-right: 1;
    }

    JudgeDesk .score-k {
        color: #6b6b6b;
        text-style: bold;
        height: 1;
    }

    JudgeDesk .score-v {
        color: #e8e8e8;
        text-style: bold;
        height: auto;
    }

    JudgeDesk .verdict-why {
        margin-top: 1;
        color: #a0a0a0;
        height: auto;
        border-top: solid #1c1c1c;
        padding-top: 1;
    }

    JudgeDesk .flag-row {
        height: 3;
        width: 100%;
        margin: 0 0 1 0;
        padding: 0 0 0 0;
        border-bottom: solid #1c1c1c;
        align: left middle;
    }

    JudgeDesk .flag-lab {
        width: 8;
        height: 3;
        color: #6b6b6b;
        text-style: bold;
        padding-right: 1;
        content-align: left middle;
    }

    JudgeDesk .phase-block {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #c9a68a;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
    }

    JudgeDesk .phase-title {
        color: #6b6b6b;
        text-style: bold;
    }

    JudgeDesk .phase-arrow {
        color: #e8e8e8;
        text-style: bold;
        margin-top: 1;
        height: auto;
    }

    JudgeDesk .phase-detail {
        color: #6b6b6b;
        height: auto;
        margin-top: 1;
    }

    JudgeDesk .phase-foot {
        color: #555555;
    }

    JudgeDesk .decision-block {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #c9a68a;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
        color: #d8d8d8;
    }

    JudgeDesk .decision-title {
        color: #6b6b6b;
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
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #3a4252;
        padding: 1 2;
        margin-right: 1;
        height: auto;
        color: #7a7a7a;
    }

    JudgeDesk .judge-card.card-solo {
        width: 1fr;
        margin-right: 0;
    }

    JudgeDesk .judge-card.tone-open {
        border-left: solid #6fbf8a;
    }

    JudgeDesk .judge-card.tone-block {
        border-left: solid #c97a72;
    }

    JudgeDesk .judge-card.tone-watch {
        border-left: solid #d4b06a;
    }

    JudgeDesk .judge-card.tone-neutral {
        border-left: solid #a89cc9;
    }

    JudgeDesk .judge-footer {
        color: #555555;
        margin-top: 1;
        height: auto;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._model: JudgeDeskModel | None = None
        self._open_flags: set[str] = set()
        self._detail_all: bool = False

    def compose(self) -> ComposeResult:
        yield Static("", classes="judge-title", id="jd-title")
        yield Static("", classes="judge-sub", id="jd-sub")
        yield Static("", classes="limited-banner", id="jd-limited")
        with Vertical(classes="verdict-mast", id="jd-mast"):
            yield Static("Verdict", classes="verdict-lab", id="jd-lab")
            with Horizontal(classes="verdict-row", id="jd-verdict-row"):
                yield Static("—", classes="verdict-action action-other", id="jd-action")
                yield Static("Gate —", classes="verdict-gate gate-other", id="jd-gate")
            with Horizontal(classes="score-strip", id="jd-scores"):
                for i in range(6):
                    with Vertical(classes="score-cell", id=f"jd-score-{i}"):
                        yield Static("", classes="score-k", id=f"jd-score-k-{i}")
                        yield Static("", classes="score-v", id=f"jd-score-v-{i}")
            yield Static("", classes="verdict-why", id="jd-why")
        # Phase timeline is primary hierarchy (design bible), not detail-only.
        with Vertical(classes="phase-block", id="jd-phase"):
            yield Static("Phase", classes="phase-title", id="jd-phase-title")
            yield Static("", classes="phase-arrow", id="jd-phase-arrow")
            yield Static("", classes="phase-detail", id="jd-phase-detail")
            yield Static("", classes="phase-foot", id="jd-phase-foot")
        # Flag chip row (mock judgeFlags) — interactive expand
        with Horizontal(classes="flag-row", id="jd-flags"):
            yield Static("Detail", classes="flag-lab", id="jd-flag-lab")
            for key, label in FLAG_CHIP_DEFS:
                yield FlagChip(key, label, id=f"jd-flag-{key}", classes="is-dim")
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

    def on_flag_chip_selected(self, event: FlagChip.Selected) -> None:
        """Toggle named panel or master detail · d."""
        event.stop()
        if self._model is None:
            return
        key = event.flag_key
        if key == "detail":
            self._detail_all = not self._detail_all
            if self._detail_all:
                self._open_flags = set(self._available_expandable_flags(self._model))
            else:
                self._open_flags.clear()
        elif key == "limited":
            # State chip only — no toggle expand
            return
        else:
            avail = self._available_expandable_flags(self._model)
            if key not in avail:
                return
            if key in self._open_flags:
                self._open_flags.discard(key)
            else:
                self._open_flags.add(key)
            self._detail_all = self._open_flags >= avail and bool(avail)
        self.paint(self._model, detail_open=self._detail_all, sync_from_detail=False)
        # Keep app chrome in sync when d-equivalent toggled from chip
        try:
            app = self.app
            if hasattr(app, "_judge_detail_open"):
                app._judge_detail_open = self._detail_all  # type: ignore[attr-defined]
        except Exception:
            pass

    def paint(
        self,
        model: JudgeDeskModel,
        *,
        detail_open: bool = False,
        sync_from_detail: bool = True,
    ) -> None:
        """Refresh all child statics from model.

        Compact: verdict mast + phase timeline + flag chips + primary cards.
        Expanded flags / ``d``: decision stack, phase+, secondary cards.
        """
        self._model = model
        if sync_from_detail:
            self._detail_all = detail_open
            if detail_open:
                self._open_flags = set(self._available_expandable_flags(model))
            else:
                self._open_flags.clear()
        open_flags = set(self._open_flags)
        if self._detail_all:
            open_flags |= self._available_expandable_flags(model)

        mode = "full" if (self._detail_all or open_flags) else "compact"
        self.query_one("#jd-title", Static).update(f"Judge · {model.ticker}")
        self.query_one("#jd-sub", Static).update(
            f"Screen · accumulation · #{model.rank}/{model.total} by Signal · {mode}"
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
        # Hero action + Gate badge on shared baseline (verdict-row height:3)
        action_el.update(f" {model.action or '—'} ")

        gate_el = self.query_one("#jd-gate", Static)
        for c in ("gate-open", "gate-block", "gate-other"):
            gate_el.remove_class(c)
        gate_el.add_class("verdict-gate")
        gate_el.add_class(gate_css_class(model.gate))
        gate_el.update(f" Gate {model.gate or '—'} ")

        for i in range(6):
            k_el = self.query_one(f"#jd-score-k-{i}", Static)
            v_el = self.query_one(f"#jd-score-v-{i}", Static)
            cell_wrap = self.query_one(f"#jd-score-{i}", Vertical)
            if i < len(model.scores):
                cell = model.scores[i]
                cell_wrap.display = True
                k_el.update(cell.label.upper())
                v_el.update(cell.value)
            else:
                cell_wrap.display = False
                k_el.update("")
                v_el.update("")

        why = model.why if model.why and model.why != "—" else "—"
        self.query_one("#jd-why", Static).update(
            f"[bold #c9a68a]Why[/] [bold #e8e8e8]{model.action or '—'}[/]  [#a0a0a0]{why}[/]"
        )

        # Phase timeline: always on (primary). Extra detail when phase+ open.
        phase_block = self.query_one("#jd-phase", Vertical)
        phase_block.display = True
        self.query_one("#jd-phase-title", Static).update(
            model.phase_section_title.upper() if model.phase_section_title else "PHASE"
        )
        self.query_one("#jd-phase-arrow", Static).update(
            _format_phase_arrow(model.phase_arrow) if model.phase_arrow else "—"
        )
        detail_el = self.query_one("#jd-phase-detail", Static)
        foot_el = self.query_one("#jd-phase-foot", Static)
        show_phase_plus = "phase_plus" in open_flags
        if show_phase_plus:
            detail_parts = [
                f"· {x}" if not x.startswith("·") and not x.startswith("now") else x
                for x in model.phase_detail_lines
            ]
            detail_el.update("\n".join(detail_parts))
            detail_el.display = True
            foot_el.update(model.phase_footer)
            foot_el.display = True
        else:
            detail_el.update("")
            detail_el.display = False
            foot_el.update("")
            foot_el.display = False

        # Flag chips reflect availability + expanded open_flags
        by_key = {c.key: c for c in model.cards}
        has_stack = bool(model.decision_lines)
        has_readiness = bool(model.readiness and model.readiness != "—")
        has_named = by_key.get("named_setups") is not None
        has_mce = by_key.get("market") is not None
        has_phase = bool(model.phase_arrow)
        self._paint_flag_chip(
            "detail",
            available=True,
            expanded=self._detail_all,
            warn=False,
        )
        self._paint_flag_chip(
            "stack",
            available=has_stack,
            expanded="stack" in open_flags,
            warn=False,
        )
        self._paint_flag_chip(
            "readiness",
            available=has_readiness,
            expanded="readiness" in open_flags,
            warn=False,
        )
        self._paint_flag_chip(
            "named",
            available=has_named,
            expanded="named" in open_flags,
            warn=False,
        )
        self._paint_flag_chip(
            "mce",
            available=has_mce,
            expanded="mce" in open_flags,
            warn=False,
        )
        self._paint_flag_chip(
            "phase_plus",
            available=has_phase,
            expanded="phase_plus" in open_flags,
            warn=False,
        )
        self._paint_flag_chip(
            "limited",
            available=model.limited,
            expanded=model.limited,
            warn=True,
        )

        # Decision stack when stack flag open
        decision_block = self.query_one("#jd-decision", Vertical)
        if "stack" in open_flags:
            decision_block.display = True
            body_lines = [ln for ln in model.decision_lines if not ln.startswith("[")]
            if body_lines and "Decision" in body_lines[0]:
                body_lines = body_lines[1:]
            self.query_one("#jd-decision-body", Static).update("\n".join(body_lines) or "—")
        else:
            decision_block.display = False

        # Primary cards always; secondary cards when matching flag / detail all
        # readiness → data card; named → named_setups; mce → market; detail all → all secondary
        show_secondary = {
            "session": self._detail_all,
            "market": "mce" in open_flags or self._detail_all,
            "named_setups": "named" in open_flags or self._detail_all,
            "signal": self._detail_all,
            "scalars": self._detail_all,
            "data": "readiness" in open_flags or True,  # data is primary-ish
        }
        # Compact primary: risk / trade_setup / accum / data always
        primary_keys = frozenset({"risk", "trade_setup", "accum", "data"})
        keys = list(_CARD_SLOT_KEYS)
        for i in range(0, len(keys), 2):
            left_k = keys[i]
            right_k = keys[i + 1] if i + 1 < len(keys) else None
            left_card = by_key.get(left_k)
            right_card = by_key.get(right_k) if right_k else None
            if left_k not in primary_keys and not show_secondary.get(left_k, self._detail_all):
                left_card = None
            if (
                right_k
                and right_k not in primary_keys
                and not show_secondary.get(right_k, self._detail_all)
            ):
                right_card = None
            # readiness alone forces data card visible (already primary)
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

        foot = model.footer
        if "d detail" not in foot and "d collapse" not in foot:
            foot = f"d detail · {foot}"
        if self._detail_all:
            foot = foot.replace("d detail", "d collapse", 1)
        # strip present-only implementer chrome from footer if present
        foot = foot.replace(" · present-only", "").replace("present-only · ", "")
        self.query_one("#jd-footer", Static).update(foot)

    def _available_expandable_flags(self, model: JudgeDeskModel) -> set[str]:
        by_key = {c.key: c for c in model.cards}
        out: set[str] = set()
        if model.decision_lines:
            out.add("stack")
        if model.readiness and model.readiness != "—":
            out.add("readiness")
        if by_key.get("named_setups") is not None:
            out.add("named")
        if by_key.get("market") is not None:
            out.add("mce")
        if model.phase_arrow:
            out.add("phase_plus")
        return out

    def _paint_flag_chip(
        self,
        key: str,
        *,
        available: bool,
        expanded: bool,
        warn: bool,
    ) -> None:
        el = self.query_one(f"#jd-flag-{key}", FlagChip)
        el.set_chip_state(available=available, expanded=expanded, warn=warn)


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
    lines = [f"[bold #555555]{title}[/]"]
    if card.headline:
        head_color = {
            "open": "#6fbf8a",
            "block": "#c97a72",
            "watch": "#d4b06a",
            "neutral": "#e8e8e8",
        }.get(card.tone, "#e8e8e8")
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
                out.append(f"[#6fbf8a]{p}[/]")
            elif p.startswith("✗"):
                out.append(f"[#c97a72]{p}[/]")
            else:
                out.append(p)
        return " ".join(out)
    return f"[#7a7a7a]{ln}[/]"


def _format_phase_arrow(arrow: str) -> str:
    """Timeline nodes: prior dim · arrows mute · current brass (mock timeline)."""
    if "→" not in arrow:
        return f"[bold #d4b06a]{arrow}[/]"
    parts = [p.strip() for p in arrow.split("→") if p.strip()]
    if not parts:
        return arrow
    *head, last = parts
    bits = [f"[#6b6b6b]{h}[/]" for h in head]
    bits.append(f"[bold #d4b06a]{last}[/]")
    return " [#3a4252]→[/] ".join(bits)
