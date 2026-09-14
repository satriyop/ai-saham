"""
JSON sidecar writer/reader for IEV snapshots.

Layer: Infrastructure
"""

import json
from datetime import date, datetime
from pathlib import Path

from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.screener_result import MoverData


class IEVJsonSidecarWriter:
    """Persist an inspectable JSON copy of a captured IEV snapshot."""

    def __init__(self, root_dir: str | Path = Path("data/iev")) -> None:
        self._root_dir = Path(root_dir).expanduser()

    def snapshot_path(self, snapshot_date: date) -> Path:
        return self._root_dir / snapshot_date.strftime("%Y%m%d") / "iev.json"

    def read_captured_at(self, snapshot_date: date) -> datetime | None:
        """Return sidecar ``captured_at`` for the session date, or None if absent."""
        path = self.snapshot_path(snapshot_date)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return None
        raw = payload.get("captured_at") if isinstance(payload, dict) else None
        if not raw:
            return None
        try:
            captured = datetime.fromisoformat(str(raw))
        except ValueError:
            return None
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=IDX_TIMEZONE)
        return captured

    def write_snapshot(
        self,
        snapshot_date: date,
        movers: list[MoverData],
        captured_at: datetime,
        top_n: int,
    ) -> Path:
        payload = {
            "captured_at": captured_at.isoformat(timespec="seconds"),
            "snapshot_date": snapshot_date.isoformat(),
            "top_n": top_n,
            "count": len(movers),
            "movers": [
                {
                    "rank": rank,
                    "ticker": mover.ticker.upper(),
                    "iev": mover.iev,
                    "iep": mover.iep,
                }
                for rank, mover in enumerate(movers, 1)
            ],
        }

        target_path = self.snapshot_path(snapshot_date)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return target_path
