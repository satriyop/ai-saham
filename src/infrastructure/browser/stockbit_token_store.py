"""
StockbitTokenStore — persists the Exodus RS256 Bearer token to disk.

Reads the JWT `exp` claim to determine validity; falls back to a fixed TTL
(default 8 hours) when the claim is absent.

Atomic writes prevent partial reads during concurrent CLI invocations.
File is chmod 0600 to protect the JWT credential.

Layer: Infrastructure
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_SKEW_SECONDS = 60  # treat token as expired 60s before its `exp` claim


class StockbitTokenStore:
    """Read/write the persisted Exodus JWT token from `.stockbit_profile/token.json`."""

    def __init__(self, path: Path, ttl_hours: float = 8.0) -> None:
        self._path = path
        self._ttl_hours = ttl_hours

    def load(self) -> str | None:
        """Return a still-valid token, or None. Never touches a browser."""
        if not self._path.exists():
            return None
        try:
            record = json.loads(self._path.read_text())
            if not isinstance(record, dict) or "token" not in record:
                return None
            if self._is_valid(record):
                return record["token"]
            logger.debug("Cached Stockbit token expired; will re-extract on next fetch")
            return None
        except Exception as e:
            logger.debug("Failed to read token store %s: %s", self._path, e)
            return None

    def save(self, token: str) -> None:
        """Persist token to disk atomically. chmod 0600 to protect the JWT."""
        exp = self._decode_exp(token)
        record = {
            "token": token,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "exp": exp,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record))
        os.replace(tmp, self._path)
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            pass  # best-effort; Windows or read-only fs

    def clear(self) -> None:
        try:
            self._path.unlink(missing_ok=True)
        except OSError:
            pass

    # ── Internal ──────────────────────────────────────────────────────────────

    def _is_valid(self, record: dict) -> bool:
        exp = record.get("exp")
        if exp is not None:
            return time.time() < int(exp) - _SKEW_SECONDS
        fetched_at_str = record.get("fetched_at")
        if not fetched_at_str:
            return False
        try:
            fetched_at = datetime.fromisoformat(fetched_at_str).timestamp()
            return time.time() < fetched_at + self._ttl_hours * 3600
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _decode_exp(token: str) -> int | None:
        """Base64-decode JWT payload segment (no signature verify) → exp or None."""
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None
            payload_b64 = parts[1]
            # Restore base64 padding
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            exp = payload.get("exp")
            return int(exp) if exp is not None else None
        except Exception:
            return None
