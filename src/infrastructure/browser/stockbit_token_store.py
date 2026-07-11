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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

_SKEW_SECONDS = 60  # treat token as expired 60s before its `exp` claim

TokenState = Literal["valid", "expired", "missing", "invalid"]
TokenExpirySource = Literal["jwt_exp", "fallback_ttl"]


@dataclass(frozen=True)
class StockbitTokenMetadata:
    """Non-secret facts about a Stockbit JWT. Never carries the token string."""

    exists: bool
    state: TokenState
    expires_at: datetime | None
    seconds_remaining: int | None
    expiry_source: TokenExpirySource | None
    algorithm: str | None


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
            if not isinstance(record, dict) or not isinstance(record.get("token"), str):
                return None
            metadata = self._describe(record["token"], record.get("fetched_at"))
            if metadata.state == "valid":
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

    def inspect(self) -> StockbitTokenMetadata:
        """Return metadata about the stored token without exposing it.

        Never touches a browser or network. Distinct from `load()`: this
        reports the token's *state* (valid/expired/missing/invalid) for
        display and health-check purposes rather than gating access.
        """
        if not self._path.exists():
            return StockbitTokenMetadata(False, "missing", None, None, None, None)
        try:
            record = json.loads(self._path.read_text())
        except Exception:
            return StockbitTokenMetadata(False, "invalid", None, None, None, None)
        if not isinstance(record, dict) or not record.get("token"):
            return StockbitTokenMetadata(False, "invalid", None, None, None, None)
        return self._describe(record["token"], record.get("fetched_at"))

    def describe_candidate(self, token: str) -> StockbitTokenMetadata:
        """Return metadata for a token string not yet persisted, as if captured now."""
        return self._describe(token, datetime.now(timezone.utc).isoformat())

    def is_worth_saving(self, candidate_token: str) -> bool:
        """
        True if candidate_token should replace the currently stored token.

        The candidate must be locally valid AND an RS256 Exodus-eligible JWT
        (HS256 local-storage fallback tokens are never eligible). It is then
        accepted when the stored token is missing/expired/invalid, or when
        the candidate differs from the stored token and expires later.
        """
        candidate = self.describe_candidate(candidate_token)
        if candidate.state != "valid" or candidate.algorithm != "RS256":
            return False
        if self._read_raw_token() == candidate_token:
            return False
        stored = self.inspect()
        if stored.state != "valid":
            return True
        if candidate.expires_at is None or stored.expires_at is None:
            return False
        return candidate.expires_at > stored.expires_at

    # ── Internal ──────────────────────────────────────────────────────────────

    def _read_raw_token(self) -> str | None:
        if not self._path.exists():
            return None
        try:
            record = json.loads(self._path.read_text())
        except Exception:
            return None
        return record.get("token") if isinstance(record, dict) else None

    def _describe(self, token: str, fetched_at_str: str | None) -> StockbitTokenMetadata:
        decoded = self._decode_jwt(token)
        if decoded is None:
            return StockbitTokenMetadata(True, "invalid", None, None, None, None)
        algorithm, payload = decoded
        if algorithm != "RS256":
            return StockbitTokenMetadata(True, "invalid", None, None, None, algorithm)

        if "exp" in payload:
            try:
                exp = int(payload["exp"])
                expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
            except (ValueError, TypeError, OverflowError, OSError):
                return StockbitTokenMetadata(True, "invalid", None, None, None, algorithm)
            remaining = exp - _SKEW_SECONDS - time.time()
            if remaining > 0:
                return StockbitTokenMetadata(
                    True, "valid", expires_at, int(remaining), "jwt_exp", algorithm
                )
            return StockbitTokenMetadata(True, "expired", expires_at, 0, "jwt_exp", algorithm)

        if not fetched_at_str:
            return StockbitTokenMetadata(True, "invalid", None, None, None, algorithm)
        try:
            fetched_at = datetime.fromisoformat(fetched_at_str)
        except (ValueError, TypeError):
            return StockbitTokenMetadata(True, "invalid", None, None, None, algorithm)
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        expires_at = fetched_at + timedelta(hours=self._ttl_hours)
        remaining_td = (expires_at - datetime.now(timezone.utc)).total_seconds()
        if remaining_td > 0:
            return StockbitTokenMetadata(
                True, "valid", expires_at, int(remaining_td), "fallback_ttl", algorithm
            )
        return StockbitTokenMetadata(True, "expired", expires_at, 0, "fallback_ttl", algorithm)

    @staticmethod
    def _decode_exp(token: str) -> int | None:
        """Base64-decode JWT payload segment (no signature verify) → exp or None."""
        decoded = StockbitTokenStore._decode_jwt(token)
        if decoded is None:
            return None
        payload = decoded[1]
        try:
            return int(payload["exp"]) if "exp" in payload else None
        except (ValueError, TypeError, OverflowError):
            return None

    @staticmethod
    def _decode_alg(token: str) -> str | None:
        """Base64-decode JWT header segment (no signature verify) → alg or None."""
        decoded = StockbitTokenStore._decode_jwt(token)
        return decoded[0] if decoded is not None else None

    @staticmethod
    def _decode_jwt(token: str) -> tuple[str | None, dict] | None:
        """Decode a structurally valid JWT header and payload without verifying its signature."""
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None
            header = StockbitTokenStore._decode_segment(parts[0])
            payload = StockbitTokenStore._decode_segment(parts[1])
            if not isinstance(header, dict) or not isinstance(payload, dict):
                return None
            alg = header.get("alg")
            return (str(alg) if alg else None, payload)
        except Exception:
            return None

    @staticmethod
    def _decode_segment(segment: str) -> object:
        padding = (-len(segment)) % 4
        decoded = base64.b64decode(
            segment + "=" * padding,
            altchars=b"-_",
            validate=True,
        )
        return json.loads(decoded)
