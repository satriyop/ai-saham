"""Unit tests for Package C risk field extraction in the research panel."""

from __future__ import annotations

import json

from research.lab.panel import (
    _risk_fields_from_child,
    _risk_fields_from_payload,
)


def test_risk_fields_from_payload_open() -> None:
    payload = {
        "candidate": {
            "risk_status": "OPEN",
            "risk_confidence": 0,
            "risk_gate": None,
        },
        "trade_setup": {"action": "ENTER"},
    }
    fields = _risk_fields_from_payload(json.dumps(payload))
    assert fields["risk_status"] == "OPEN"
    assert fields["risk_gate"] is None
    assert fields["risk_confidence"] == 0
    assert fields["gate_is_structural"] is None
    assert fields["risk_source"] == "payload"


def test_risk_fields_from_payload_blocked_structural() -> None:
    payload = {
        "candidate": {
            "risk_status": "BLOCKED",
            "risk_confidence": 100,
            "risk_gate": "FreeFloatGate",
        },
        "trade_setup": {"action": "BLOCKED_STRUCTURAL", "gate_triggered": "FreeFloatGate"},
    }
    fields = _risk_fields_from_payload(json.dumps(payload))
    assert fields["risk_status"] == "BLOCKED"
    assert fields["risk_gate"] == "FreeFloatGate"
    assert fields["gate_is_structural"] is True
    assert fields["risk_source"] == "payload"


def test_risk_fields_from_payload_falls_back_to_trade_setup_gate() -> None:
    payload = {
        "candidate": {"risk_status": "BLOCKED", "risk_confidence": 80},
        "trade_setup": {
            "action": "BLOCKED_EXECUTION",
            "gate_triggered": "BandarGate",
        },
    }
    fields = _risk_fields_from_payload(json.dumps(payload))
    assert fields["risk_gate"] == "BandarGate"
    assert fields["gate_is_structural"] is False


def test_risk_fields_from_child_prefers_assessment_json() -> None:
    assessment = {
        "gate_triggered": "LiquidityGate",
        "gate_is_structural": True,
        "gate_confidence": 100,
        "confidence": 100,
        "rationale": ["market cap below floor"],
    }
    fields = _risk_fields_from_child(
        json.dumps(assessment),
        gate_triggered="ignored",
        setup_action="BLOCKED_STRUCTURAL",
    )
    assert fields is not None
    assert fields["risk_status"] == "BLOCKED"
    assert fields["risk_gate"] == "LiquidityGate"
    assert fields["gate_is_structural"] is True
    assert fields["risk_confidence"] == 100
    assert fields["risk_source"] == "child_table"


def test_risk_fields_from_child_open_when_no_gate() -> None:
    assessment = {
        "gate_triggered": None,
        "gate_is_structural": False,
        "gate_confidence": 0,
        "confidence": 0,
        "rationale": ["all gates passed"],
    }
    fields = _risk_fields_from_child(json.dumps(assessment), None, "ENTER")
    assert fields is not None
    assert fields["risk_status"] == "OPEN"
    assert fields["risk_gate"] is None
    assert fields["risk_source"] == "child_table"


def test_risk_fields_from_child_none_when_empty() -> None:
    assert _risk_fields_from_child(None, None, None) is None
    assert _risk_fields_from_child("not-json", None, None) is None
