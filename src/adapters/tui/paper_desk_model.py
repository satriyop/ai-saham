"""Paper notebook tape model (present-only session outcomes).

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.adapters.shared.trade_action_labels import ACTION_SCAN_TOKENS


@dataclass(frozen=True)
class PaperTapeRow:
    kind: str  # ok | refuse | fail
    ticker: str
    headline: str
    sub: str


@dataclass(frozen=True)
class PaperDeskModel:
    title: str
    subtitle: str
    rows: tuple[PaperTapeRow, ...]
    empty: bool
    empty_reason: str
    footer: str

    def body_contains_action_authority(self) -> bool:
        text = f"{self.subtitle} {self.footer} {self.empty_reason}".upper()
        for token in ACTION_SCAN_TOKENS[:3]:
            if token in f" {text} ":
                return True
        return False


def build_paper_desk_model(
    outcomes: list[Any] | tuple[Any, ...] | None = None,
    *,
    focus_ticker: str = "",
) -> PaperDeskModel:
    rows: list[PaperTapeRow] = []
    for raw in list(outcomes or ()):
        if isinstance(raw, PaperTapeRow):
            rows.append(raw)
            continue
        if isinstance(raw, str):
            # Parse outcome tape markup lightly
            kind = "ok"
            if "REFUSED" in raw.upper():
                kind = "refuse"
            elif "NO WRITE" in raw.upper() or "FAIL" in raw.upper():
                kind = "fail"
            ticker = focus_ticker or "—"
            for line in raw.splitlines():
                if line and not line.startswith("["):
                    # first plain-ish content
                    break
            rows.append(
                PaperTapeRow(
                    kind=kind,
                    ticker=ticker.upper() if ticker else "—",
                    headline=raw.splitlines()[0][:80] if raw else "—",
                    sub="\n".join(raw.splitlines()[1:3])[:120],
                )
            )
            continue
        ticker = str(getattr(raw, "ticker", focus_ticker) or "—").upper()
        refused = bool(getattr(raw, "refused", False))
        written = bool(getattr(raw, "written", False))
        msg = str(getattr(raw, "message", "") or "")
        if refused:
            kind = "refuse"
            headline = f"REFUSED · {ticker}"
        elif written:
            kind = "ok"
            headline = f"LOGGED · {ticker}"
        else:
            kind = "fail"
            headline = f"NO WRITE · {ticker}"
        geo = []
        for attr, lab in (
            ("planned_entry", "entry"),
            ("planned_stop", "stop"),
            ("planned_target", "target"),
        ):
            v = getattr(raw, attr, None)
            if v:
                geo.append(f"{lab} {v}")
        sub = " · ".join(geo) if geo else msg
        rows.append(PaperTapeRow(kind=kind, ticker=ticker, headline=headline, sub=sub or "—"))

    empty = not rows
    return PaperDeskModel(
        title="Paper · notebook",
        subtitle="Session tape · paper only · no broker order",
        rows=tuple(rows),
        empty=empty,
        empty_reason="No paper notes this session · from plan stage press l to log"
        if empty
        else "",
        footer="l log from plan · esc back · Ctrl+P · paper only",
    )
