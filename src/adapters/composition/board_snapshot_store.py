"""Filesystem persistence for TUI accumulation board snapshots.

IO lives outside ``src.adapters.tui`` so the TUI package stays free of
pathlib write calls (architecture boundary). Pure snapshot models and
view conversion remain in ``src.adapters.tui.board_snapshot``.

Layer: Adapter (composition)
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from src.adapters.tui.board_snapshot import AccumBoardSnapshot, AccumBoardSnapshotIdentity


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


def invalidate_accum_board_snapshot(path: Path | str | None) -> bool:
    """Remove last-run snapshot so next open cannot restore a stale board."""
    if path is None:
        return False
    target = Path(path)
    if not target.is_file():
        return False
    try:
        target.unlink()
        return True
    except OSError:
        return False


def read_accum_board_snapshot(path: Path) -> AccumBoardSnapshot | None:
    """Return a restorable snapshot or None when missing/corrupt/incomplete."""
    from src.adapters.shared.screen_accum_board_fields import BOARD_COLUMN_LABELS
    from src.adapters.tui.board_snapshot import (
        AccumBoardSnapshot,
    )

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
