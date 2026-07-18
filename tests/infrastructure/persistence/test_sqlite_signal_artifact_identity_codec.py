"""Tests for strict SQLite SignalArtifactIdentity codec."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from src.domain.value_objects.signal_artifact_identity import (
    ArtifactId,
    ArtifactProvenance,
    ArtifactSourceProvenance,
    SemanticCompatibilityId,
    SignalArtifactIdentity,
)
from src.infrastructure.persistence.sqlite_signal_artifact_identity_codec import (
    decode_signal_artifact_identity,
    encode_signal_artifact_identity,
)


def _source(
    *,
    source_family: str = "exchange",
    provider: str = "idx",
    source_snapshot_id: str | None = "snap-001",
    observed_through: date | None = date(2026, 7, 3),
    available_at: datetime | None = datetime(2026, 7, 3, 7, 0, 0, tzinfo=timezone.utc),
    cutoff_at: datetime | None = datetime(2026, 7, 3, 8, 0, 0, tzinfo=timezone.utc),
) -> ArtifactSourceProvenance:
    return ArtifactSourceProvenance(
        source_family=source_family,
        provider=provider,
        source_snapshot_id=source_snapshot_id,
        observed_through=observed_through,
        available_at=available_at,
        cutoff_at=cutoff_at,
    )


def _provenance(
    *,
    sources: tuple[ArtifactSourceProvenance, ...] | None = None,
    invocation_command: str | None = None,
    invocation_actor: str | None = None,
) -> ArtifactProvenance:
    return ArtifactProvenance(
        application_revision="abc1234",
        complete_config_hash="a" * 64,
        complete_authority_registry_hash="b" * 64,
        universe_snapshot_id="univ-001",
        idx_calendar_version="2026-v3",
        session_rule_version="sr-v2",
        decision_at=datetime(2026, 7, 3, 16, 0, 0, 123456, tzinfo=timezone.utc),
        captured_at=datetime(2026, 7, 3, 9, 30, 0, 456789, tzinfo=timezone.utc),
        latest_completed_session=date(2026, 7, 3),
        analysis_as_of=date(2026, 7, 3),
        sources=sources or (_source(),),
        invocation_command=invocation_command,
        invocation_actor=invocation_actor,
    )


def _identity(
    *, provenance: ArtifactProvenance | None = None
) -> SignalArtifactIdentity:
    return SignalArtifactIdentity(
        artifact_id=ArtifactId(
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ),
        semantic_compatibility_id=SemanticCompatibilityId(
            "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        ),
        provenance=provenance or _provenance(),
    )


# ── Encode: None ──────────────────────────────────────────────────────────────


class TestEncodeNone:
    def test_none_returns_three_empty_strings(self):
        encoded = encode_signal_artifact_identity(None)
        assert encoded == ("", "", "")

    def test_wrong_type_raises_typeerror(self):
        with pytest.raises(TypeError, match="Expected SignalArtifactIdentity"):
            encode_signal_artifact_identity("not-an-identity")  # type: ignore[arg-type]


# ── Decode: empty / partial ───────────────────────────────────────────────────


class TestDecodeEmpty:
    def test_all_empty_strings_returns_none(self):
        result = decode_signal_artifact_identity(
            artifact_id_raw="",
            semantic_compatibility_id_raw="",
            provenance_json_raw="",
        )
        assert result is None

    def test_none_raises(self):
        with pytest.raises(ValueError, match="NULL"):
            decode_signal_artifact_identity(
                artifact_id_raw=None,
                semantic_compatibility_id_raw=None,
                provenance_json_raw=None,
            )

    def test_mixed_empty_and_none_raises(self):
        with pytest.raises(ValueError, match="NULL"):
            decode_signal_artifact_identity(
                artifact_id_raw="",
                semantic_compatibility_id_raw=None,
                provenance_json_raw="",
            )

    def test_single_none_raises(self):
        with pytest.raises(ValueError, match="NULL"):
            decode_signal_artifact_identity(
                artifact_id_raw="",
                semantic_compatibility_id_raw=None,
                provenance_json_raw="",
            )

    def test_partial_artifact_id_only_raises(self):
        with pytest.raises(ValueError, match="Partial"):
            decode_signal_artifact_identity(
                artifact_id_raw="sha256:aaa",
                semantic_compatibility_id_raw="",
                provenance_json_raw="",
            )

    def test_partial_missing_provenance_raises(self):
        with pytest.raises(ValueError, match="Partial"):
            decode_signal_artifact_identity(
                artifact_id_raw="sha256:aaa",
                semantic_compatibility_id_raw="sha256:bbb",
                provenance_json_raw="",
            )

    def test_non_string_artifact_id_raises(self):
        with pytest.raises(ValueError, match="must be a string"):
            decode_signal_artifact_identity(
                artifact_id_raw=123,  # type: ignore[arg-type]
                semantic_compatibility_id_raw="",
                provenance_json_raw="",
            )


# ── Round-trip ────────────────────────────────────────────────────────────────


class TestRoundTrip:
    def test_complete_identity_round_trips(self):
        identity = _identity()
        encoded = encode_signal_artifact_identity(identity)
        decoded = decode_signal_artifact_identity(
            artifact_id_raw=encoded[0],
            semantic_compatibility_id_raw=encoded[1],
            provenance_json_raw=encoded[2],
        )
        assert decoded is not None
        assert decoded.artifact_id == identity.artifact_id
        assert decoded.semantic_compatibility_id == identity.semantic_compatibility_id
        assert decoded.provenance == identity.provenance

    def test_invocation_fields_round_trip(self):
        identity = _identity(
            provenance=_provenance(
                invocation_command="screen --ticker BBCA",
                invocation_actor="satriyo",
            )
        )
        encoded = encode_signal_artifact_identity(identity)
        decoded = decode_signal_artifact_identity(
            artifact_id_raw=encoded[0],
            semantic_compatibility_id_raw=encoded[1],
            provenance_json_raw=encoded[2],
        )
        assert decoded is not None
        assert decoded.provenance.invocation_command == "screen --ticker BBCA"
        assert decoded.provenance.invocation_actor == "satriyo"

    def test_multiple_sources_round_trip(self):
        identity = _identity(
            provenance=_provenance(
                sources=(
                    _source(
                        source_family="exchange",
                        provider="idx",
                        source_snapshot_id="snap-a",
                        observed_through=date(2026, 7, 3),
                    ),
                    _source(
                        source_family="data_vendor",
                        provider="stockbit",
                        source_snapshot_id="snap-b",
                        observed_through=date(2026, 7, 2),
                    ),
                    _source(
                        source_family="corporate",
                        provider="ksei",
                        source_snapshot_id=None,
                        observed_through=None,
                        available_at=datetime(2026, 7, 3, 10, 0, 0, tzinfo=timezone.utc),
                        cutoff_at=None,
                    ),
                )
            )
        )
        encoded = encode_signal_artifact_identity(identity)
        decoded = decode_signal_artifact_identity(
            artifact_id_raw=encoded[0],
            semantic_compatibility_id_raw=encoded[1],
            provenance_json_raw=encoded[2],
        )
        assert decoded is not None
        assert decoded.artifact_id == identity.artifact_id
        assert decoded.semantic_compatibility_id == identity.semantic_compatibility_id
        assert decoded.provenance.application_revision == identity.provenance.application_revision
        assert len(decoded.provenance.sources) == 3
        decoded_sorted = sorted(
            decoded.provenance.sources,
            key=lambda s: (s.source_family, s.provider, s.source_snapshot_id or ""),
        )
        orig_sorted = sorted(
            identity.provenance.sources,
            key=lambda s: (s.source_family, s.provider, s.source_snapshot_id or ""),
        )
        assert decoded_sorted == orig_sorted

    def test_microseconds_preserved(self):
        identity = _identity(
            provenance=_provenance(
                sources=(
                    _source(
                        available_at=datetime(
                            2026, 7, 3, 7, 0, 0, 123456, tzinfo=timezone.utc
                        ),
                        cutoff_at=datetime(
                            2026, 7, 3, 8, 0, 0, 654321, tzinfo=timezone.utc
                        ),
                    ),
                )
            )
        )
        encoded = encode_signal_artifact_identity(identity)
        decoded = decode_signal_artifact_identity(
            artifact_id_raw=encoded[0],
            semantic_compatibility_id_raw=encoded[1],
            provenance_json_raw=encoded[2],
        )
        assert decoded is not None
        src = decoded.provenance.sources[0]
        assert src.available_at.microsecond == 123456
        assert src.cutoff_at.microsecond == 654321


# ── Decode: invalid IDs ──────────────────────────────────────────────────────


class TestDecodeInvalidIds:
    def test_artifact_id_not_sha256_prefixed(self):
        with pytest.raises(ValueError, match="artifact_id"):
            decode_signal_artifact_identity(
                artifact_id_raw="not-a-valid-id",
                semantic_compatibility_id_raw="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                provenance_json_raw=encode_signal_artifact_identity(_identity())[2],
            )

    def test_semantic_compatibility_id_not_sha256_prefixed(self):
        with pytest.raises(ValueError, match="semantic_compatibility_id"):
            decode_signal_artifact_identity(
                artifact_id_raw="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                semantic_compatibility_id_raw="not-valid",
                provenance_json_raw=encode_signal_artifact_identity(_identity())[2],
            )

    def test_both_ids_invalid(self):
        with pytest.raises(ValueError):
            decode_signal_artifact_identity(
                artifact_id_raw="bad",
                semantic_compatibility_id_raw="also-bad",
                provenance_json_raw=encode_signal_artifact_identity(_identity())[2],
            )


# ── Decode: malformed provenance JSON ─────────────────────────────────────────


class TestDecodeMalformedProvenance:
    def test_not_json(self):
        with pytest.raises(ValueError, match="malformed JSON"):
            decode_signal_artifact_identity(
                artifact_id_raw="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                semantic_compatibility_id_raw="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                provenance_json_raw="not-json-at-all",
            )

    def test_not_object(self):
        with pytest.raises(ValueError, match="must be a JSON object"):
            decode_signal_artifact_identity(
                artifact_id_raw="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                semantic_compatibility_id_raw="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                provenance_json_raw='["not", "an", "object"]',
            )


# ── Decode: missing/extra provenance keys ─────────────────────────────────────


class TestDecodeProvenanceKeys:
    def test_missing_key(self):
        valid = encode_signal_artifact_identity(_identity())[2]
        data = __import__("json").loads(valid)
        del data["application_revision"]
        faulty = __import__("json").dumps(data, sort_keys=True, separators=(",", ":"))
        with pytest.raises(ValueError, match="missing keys"):
            decode_signal_artifact_identity(
                artifact_id_raw="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                semantic_compatibility_id_raw="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                provenance_json_raw=faulty,
            )

    def test_extra_key(self):
        valid = encode_signal_artifact_identity(_identity())[2]
        data = __import__("json").loads(valid)
        data["extra_key"] = "should-not-be-here"
        faulty = __import__("json").dumps(data, sort_keys=True, separators=(",", ":"))
        with pytest.raises(ValueError, match="unexpected keys"):
            decode_signal_artifact_identity(
                artifact_id_raw="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                semantic_compatibility_id_raw="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                provenance_json_raw=faulty,
            )


# ── Decode: timestamp format ──────────────────────────────────────────────────


class TestDecodeTimestampFormat:
    def test_non_utc_timestamp_raises(self):
        valid = encode_signal_artifact_identity(_identity())[2]
        data = __import__("json").loads(valid)
        data["captured_at"] = "2026-07-03T09:30:00.456789+07:00"
        faulty = __import__("json").dumps(data, sort_keys=True, separators=(",", ":"))
        with pytest.raises(ValueError, match="must end with 'Z'"):
            decode_signal_artifact_identity(
                artifact_id_raw="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                semantic_compatibility_id_raw="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                provenance_json_raw=faulty,
            )

    def test_naive_timestamp_raises(self):
        valid = encode_signal_artifact_identity(_identity())[2]
        data = __import__("json").loads(valid)
        data["captured_at"] = "2026-07-03T09:30:00.456789"
        faulty = __import__("json").dumps(data, sort_keys=True, separators=(",", ":"))
        with pytest.raises(ValueError, match="must end with 'Z'"):
            decode_signal_artifact_identity(
                artifact_id_raw="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                semantic_compatibility_id_raw="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                provenance_json_raw=faulty,
            )

    def test_bad_date_format_raises(self):
        valid = encode_signal_artifact_identity(_identity())[2]
        data = __import__("json").loads(valid)
        data["analysis_as_of"] = "not-a-date"
        faulty = __import__("json").dumps(data, sort_keys=True, separators=(",", ":"))
        with pytest.raises(ValueError, match="invalid date"):
            decode_signal_artifact_identity(
                artifact_id_raw="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                semantic_compatibility_id_raw="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                provenance_json_raw=faulty,
            )


# ── Decode: canonical JSON enforcement ────────────────────────────────────────


class TestDecodeCanonicalJson:
    def test_pretty_printed_json_raises(self):
        valid = encode_signal_artifact_identity(_identity())[2]
        pretty = __import__("json").dumps(
            __import__("json").loads(valid), indent=2, sort_keys=True
        )
        with pytest.raises(ValueError, match="canonical provenance serialization"):
            decode_signal_artifact_identity(
                artifact_id_raw="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                semantic_compatibility_id_raw="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                provenance_json_raw=pretty,
            )

    def test_missing_microseconds_raises(self):
        valid = encode_signal_artifact_identity(_identity())[2]
        data = __import__("json").loads(valid)
        data["captured_at"] = "2026-07-03T09:30:00Z"
        faulty = __import__("json").dumps(data, sort_keys=True, separators=(",", ":"))
        with pytest.raises(ValueError, match="canonical provenance serialization"):
            decode_signal_artifact_identity(
                artifact_id_raw="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                semantic_compatibility_id_raw="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                provenance_json_raw=faulty,
            )

    def test_reordered_keys_raises(self):
        valid = encode_signal_artifact_identity(_identity())[2]
        data = __import__("json").loads(valid)
        keys = sorted(data.keys(), reverse=True)
        reordered = "{" + ",".join(
            f"{__import__('json').dumps(k, separators=(',',':'))}:"
            f"{__import__('json').dumps(data[k], separators=(',',':'))}"
            for k in keys
        ) + "}"
        with pytest.raises(ValueError, match="canonical provenance serialization"):
            decode_signal_artifact_identity(
                artifact_id_raw="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                semantic_compatibility_id_raw="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                provenance_json_raw=reordered,
            )

    def test_duplicate_json_keys_raises(self):
        valid = encode_signal_artifact_identity(_identity())[2]
        first_comma = valid.index(",")
        first_key_val = valid[1:first_comma]
        dup = "{" + first_key_val + "," + first_key_val + valid[first_comma:]
        with pytest.raises(ValueError, match="canonical provenance serialization"):
            decode_signal_artifact_identity(
                artifact_id_raw="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                semantic_compatibility_id_raw="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                provenance_json_raw=dup,
            )


# ── Decode: source validation ─────────────────────────────────────────────────


class TestDecodeSourceValidation:
    def test_source_missing_key_raises(self):
        valid = encode_signal_artifact_identity(_identity())[2]
        data = __import__("json").loads(valid)
        del data["sources"][0]["source_family"]
        faulty = __import__("json").dumps(data, sort_keys=True, separators=(",", ":"))
        with pytest.raises(ValueError, match="missing keys"):
            decode_signal_artifact_identity(
                artifact_id_raw="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                semantic_compatibility_id_raw="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                provenance_json_raw=faulty,
            )

    def test_source_extra_key_raises(self):
        valid = encode_signal_artifact_identity(_identity())[2]
        data = __import__("json").loads(valid)
        data["sources"][0]["bogus"] = "value"
        faulty = __import__("json").dumps(data, sort_keys=True, separators=(",", ":"))
        with pytest.raises(ValueError, match="unexpected keys"):
            decode_signal_artifact_identity(
                artifact_id_raw="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                semantic_compatibility_id_raw="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                provenance_json_raw=faulty,
            )

    def test_duplicate_sources_raises(self):
        valid_json = encode_signal_artifact_identity(_identity())[2]
        data = __import__("json").loads(valid_json)
        first = data["sources"][0]
        data["sources"] = [first, first]
        faulty = __import__("json").dumps(data, sort_keys=True, separators=(",", ":"))
        with pytest.raises(ValueError, match="Duplicate"):
            decode_signal_artifact_identity(
                artifact_id_raw="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                semantic_compatibility_id_raw="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                provenance_json_raw=faulty,
            )

    def test_source_not_a_dict_raises(self):
        valid = encode_signal_artifact_identity(_identity())[2]
        data = __import__("json").loads(valid)
        data["sources"] = ["not", "a", "dict"]
        faulty = __import__("json").dumps(data, sort_keys=True, separators=(",", ":"))
        with pytest.raises(ValueError, match="must be a JSON object"):
            decode_signal_artifact_identity(
                artifact_id_raw="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                semantic_compatibility_id_raw="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                provenance_json_raw=faulty,
            )

    def test_sources_not_a_list_raises(self):
        valid = encode_signal_artifact_identity(_identity())[2]
        data = __import__("json").loads(valid)
        data["sources"] = "not-a-list"
        faulty = __import__("json").dumps(data, sort_keys=True, separators=(",", ":"))
        with pytest.raises(ValueError, match="sources: must be a list"):
            decode_signal_artifact_identity(
                artifact_id_raw="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                semantic_compatibility_id_raw="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                provenance_json_raw=faulty,
            )


# ── Encode: wrong type ────────────────────────────────────────────────────────


class TestEncodeWrongType:
    def test_encode_wrong_type_raises(self):
        with pytest.raises(TypeError, match="Expected SignalArtifactIdentity"):
            encode_signal_artifact_identity(42)  # type: ignore[arg-type]

    def test_encode_dict_raises(self):
        with pytest.raises(TypeError, match="Expected SignalArtifactIdentity"):
            encode_signal_artifact_identity({"a": 1})  # type: ignore[arg-type]
