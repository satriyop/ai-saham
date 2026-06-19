"""
JSON sidecar writer for IEV snapshots.

Layer: Infrastructure
"""

import json
from datetime import date, datetime
from pathlib import Path

from src.domain.value_objects.screener_result import MoverData


class IEVJsonSidecarWriter:
    """Persist an inspectable JSON copy of a captured IEV snapshot."""

    def __init__(self, root_dir: str | Path = Path("data/iev")) -> None:
        self._root_dir = Path(root_dir).expanduser()

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

        target_dir = self._root_dir / snapshot_date.strftime("%Y%m%d")
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / "iev.json"
        target_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return target_path
