"""Last-run accumulation board snapshot (adapter-local presentation cache).

Stores a prior successful local screen presentation for instant cockpit open.
Does not invent candidates, fetch network, or re-score. Corrupt/missing files
are refused.

Layer: Adapter
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.adapters.composition.screen_accum_request import (
    DEFAULT_SORT_BY,
    DEFAULT_TOP,
    DEFAULT_WINDOW,
)
from src.adapters.shared.screen_accum_board_fields import BOARD_COLUMN_LABELS
from src.adapters.tui.presenters.accum_presenter import AccumBoardView, AccumRowView

SNAPSHOT_SCHEMA_VERSION = 1
BOARD_KIND_ACCUM = "accum"
SNAPSHOT_FILENAME = "tui_last_accum_board.json"


@dataclass(frozen=True)
class AccumBoardSnapshotIdentity:
    """Identity of the screen request shape + data as_of for freshness cues."""

    board_kind: str
    universe: str
    window: int
    sort_by: str
    top: int
    as_of: str
    captured_at: str

    def is_complete(self) -> bool:
        return (
            self.board_kind == BOARD_KIND_ACCUM
            and bool(self.universe)
            and self.window > 0
            and bool(self.sort_by)
            and self.top > 0
            and bool(self.captured_at)
        )


@dataclass(frozen=True)
class AccumBoardSnapshot:
    schema_version: int
    identity: AccumBoardSnapshotIdentity
    meta: str
    cache_label: str
    summary: str
    columns: tuple[str, ...]
    rows: tuple[dict[str, str], ...]

    def is_restorable(self) -> bool:
        if self.schema_version != SNAPSHOT_SCHEMA_VERSION:
            return False
        if not self.identity.is_complete():
            return False
        if not self.rows:
            return False
        return True


def default_accum_snapshot_path(db_path: Path | str) -> Path:
    """Colocate snapshot with the SQLite DB directory (local-first)."""
    return Path(db_path).expanduser().resolve().parent / SNAPSHOT_FILENAME


def build_identity_from_board_view(
    view: AccumBoardView,
    *,
    universe: str,
    window: int = DEFAULT_WINDOW,
    sort_by: str = DEFAULT_SORT_BY,
    top: int = DEFAULT_TOP,
    as_of: str = "",
    captured_at: str | None = None,
) -> AccumBoardSnapshotIdentity:
    resolved_as_of = (as_of or _as_of_from_meta(view.meta) or "").strip()
    captured = captured_at or datetime.now(UTC).replace(microsecond=0).isoformat()
    return AccumBoardSnapshotIdentity(
        board_kind=BOARD_KIND_ACCUM,
        universe=(universe or "local").strip().lower(),
        window=int(window) if window else DEFAULT_WINDOW,
        sort_by=(sort_by or DEFAULT_SORT_BY).strip().lower(),
        top=int(top) if top else max(len(view.rows), DEFAULT_TOP),
        as_of=resolved_as_of,
        captured_at=captured,
    )


def snapshot_from_board_view(
    view: AccumBoardView,
    identity: AccumBoardSnapshotIdentity,
) -> AccumBoardSnapshot:
    rows: list[dict[str, str]] = []
    for row in view.rows:
        rows.append(
            {
                "ticker": str(row.ticker),
                "signal": str(row.signal),
                "accum": str(row.accum),
                "action": str(row.action),
                "phase": str(row.phase),
                "streak": str(row.streak),
                "rsi": str(row.rsi),
                "net_pct": str(row.net_pct),
                "disc_pct": str(row.disc_pct),
                "price": str(row.price),
                "gate": str(row.gate),
                "name": str(row.name or ""),
            }
        )
    return AccumBoardSnapshot(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        identity=identity,
        meta=str(view.meta or ""),
        cache_label=str(view.cache_label or ""),
        summary=str(view.summary or ""),
        columns=tuple(str(c) for c in (view.columns or BOARD_COLUMN_LABELS)),
        rows=tuple(rows),
    )


def board_view_from_snapshot(snapshot: AccumBoardSnapshot) -> AccumBoardView:
    rows = tuple(
        AccumRowView(
            ticker=str(r.get("ticker", "?")),
            signal=str(r.get("signal", "—")),
            accum=str(r.get("accum", "—")),
            action=str(r.get("action", "—")),
            phase=str(r.get("phase", "—")),
            streak=str(r.get("streak", "—")),
            rsi=str(r.get("rsi", "—")),
            net_pct=str(r.get("net_pct", "—")),
            disc_pct=str(r.get("disc_pct", "—")),
            price=str(r.get("price", "—")),
            gate=str(r.get("gate", "—")),
            name=str(r.get("name", "") or ""),
            source=None,
        )
        for r in snapshot.rows
    )
    columns = snapshot.columns if snapshot.columns else BOARD_COLUMN_LABELS
    return AccumBoardView(
        rows=rows,
        meta=snapshot.meta,
        cache_label=snapshot.cache_label,
        summary=snapshot.summary,
        columns=columns,
    )


def write_accum_board_snapshot(path: Path, snapshot: AccumBoardSnapshot) -> None:
    if not snapshot.is_restorable():
        raise ValueError("refusing to write non-restorable snapshot")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": snapshot.schema_version,
        "identity": asdict(snapshot.identity),
        "meta": snapshot.meta,
        "cache_label": snapshot.cache_label,
        "summary": snapshot.summary,
        "columns": list(snapshot.columns),
        "rows": list(snapshot.rows),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_accum_board_snapshot(path: Path) -> AccumBoardSnapshot | None:
    """Return a restorable snapshot or None when missing/corrupt/incomplete."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        ident_raw = raw.get("identity") or {}
        if not isinstance(ident_raw, dict):
            return None
        identity = AccumBoardSnapshotIdentity(
            board_kind=str(ident_raw.get("board_kind", "")),
            universe=str(ident_raw.get("universe", "")),
            window=int(ident_raw.get("window") or 0),
            sort_by=str(ident_raw.get("sort_by", "")),
            top=int(ident_raw.get("top") or 0),
            as_of=str(ident_raw.get("as_of", "") or ""),
            captured_at=str(ident_raw.get("captured_at", "") or ""),
        )
        rows_raw = raw.get("rows") or []
        if not isinstance(rows_raw, list):
            return None
        rows: list[dict[str, str]] = []
        for item in rows_raw:
            if not isinstance(item, dict):
                return None
            rows.append({str(k): str(v) for k, v in item.items()})
        columns_raw = raw.get("columns") or list(BOARD_COLUMN_LABELS)
        columns = tuple(str(c) for c in columns_raw)
        snap = AccumBoardSnapshot(
            schema_version=int(raw.get("schema_version") or 0),
            identity=identity,
            meta=str(raw.get("meta") or ""),
            cache_label=str(raw.get("cache_label") or ""),
            summary=str(raw.get("summary") or ""),
            columns=columns,
            rows=tuple(rows),
        )
    except (TypeError, ValueError):
        return None
    if not snap.is_restorable():
        return None
    return snap


def identity_from_live_payload(
    payload: Any,
    view: AccumBoardView,
    *,
    universe: str,
) -> AccumBoardSnapshotIdentity:
    """Build identity from a live workflow payload + presented view."""
    projection = getattr(payload, "single_projection", None) or payload
    window = int(getattr(projection, "window_days", None) or DEFAULT_WINDOW)
    sort_by = DEFAULT_SORT_BY
    top = DEFAULT_TOP
    applied = getattr(projection, "applied_filters", None)
    if applied is not None:
        sort_by = str(getattr(applied, "sort_by", None) or sort_by)
        top_val = getattr(applied, "top", None)
        if top_val is not None:
            top = int(top_val)
    as_of = ""
    data_as_of = getattr(projection, "data_as_of", None) or {}
    if isinstance(data_as_of, dict):
        as_of = str(
            data_as_of.get("latest_candle_date")
            or data_as_of.get("as_of")
            or data_as_of.get("latest_broker_date")
            or ""
        )
    if not as_of:
        as_of = _as_of_from_meta(view.meta)
    return build_identity_from_board_view(
        view,
        universe=universe,
        window=window,
        sort_by=sort_by,
        top=top,
        as_of=as_of,
    )


def _as_of_from_meta(meta: str) -> str:
    # Presenter meta often starts with "as of YYYY-MM-DD · …"
    text = (meta or "").strip()
    marker = "as of "
    if marker in text:
        rest = text.split(marker, 1)[1]
        token = rest.split("·", 1)[0].strip()
        return token
    return ""
