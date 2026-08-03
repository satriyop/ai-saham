"""Shared gates and fixtures for agent-live-call smoke tests.

Hard gate: ``AI_SAHAM_AGENT_LIVE=1`` — without it every live test skips.
Additional skips for missing credentials, flags, or local cache data.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.application.dto.agent_tools import AgentToolName
from src.infrastructure.composition.agent_model import (
    AgentComposition,
    build_agent_composition,
)
from src.infrastructure.config.app_config import AiConfig
from src.infrastructure.config.local_env import read_local_env_value
from tests.application.services.test_agent_accumulation_context import make_candidate

# Cap live HTTP so a hung provider cannot stall the suite.
LIVE_HTTP_TIMEOUT_S = 45.0
LIVE_PROVIDER_CALL_BUDGET = 15

# Hyphenated marker name from pyproject (select with -m agent-live-call).
agent_live_call = getattr(pytest.mark, "agent-live-call")

_SHA256_REF = re.compile(r"^sha256:[0-9a-f]{64}$")
_CLOSED_TOOL_NAMES = frozenset(item.value for item in AgentToolName)


def live_env_enabled() -> bool:
    return os.getenv("AI_SAHAM_AGENT_LIVE", "").strip() == "1"


def deepseek_api_key() -> str:
    return (
        os.getenv("DEEPSEEK_API_KEY", "").strip()
        or (read_local_env_value("DEEPSEEK_API_KEY") or "").strip()
    )


def live_ticker() -> str:
    return (os.getenv("AI_SAHAM_LIVE_TICKER") or "BBCA").strip().upper()


def live_broker() -> str:
    return (os.getenv("AI_SAHAM_LIVE_BROKER") or "YP").strip().upper()


def default_db_path() -> Path:
    override = os.getenv("AI_SAHAM_LIVE_DB", "").strip()
    if override:
        return Path(override)
    candidates = (
        Path("data/db/data.db"),
        Path("data.db"),
        Path("saham.db"),
    )
    for path in candidates:
        if path.is_file() and path.stat().st_size > 0:
            return path
    return candidates[0]


@pytest.fixture(autouse=True)
def _require_agent_live_gate(request: pytest.FixtureRequest) -> None:
    """Skip every agent-live-call test unless the operator opted in."""
    if request.node.get_closest_marker("agent-live-call") is None:
        return
    if not live_env_enabled():
        pytest.skip("AI_SAHAM_AGENT_LIVE=1 required for agent-live-call tests")


@pytest.fixture
def require_live_env() -> None:
    """Explicit alias for tests that document the gate dependency."""
    if not live_env_enabled():
        pytest.skip("AI_SAHAM_AGENT_LIVE=1 required")


@pytest.fixture
def require_deepseek_key() -> str:
    key = deepseek_api_key()
    if not key:
        pytest.skip("DEEPSEEK_API_KEY missing (env or local env file)")
    return key


@pytest.fixture
def live_db_path() -> Path:
    path = default_db_path()
    if not path.is_file() or path.stat().st_size == 0:
        pytest.skip(f"local DB missing or empty: {path}")
    return path


@pytest.fixture
def live_candidate():
    """Frozen full AccumulationCandidate for one-turn / session live paths."""
    return make_candidate(trade_ticker=live_ticker())


@dataclass(frozen=True)
class LiveAiFlags:
    enabled: bool = True
    provider: str = "deepseek"
    tools_enabled: bool = False
    session_enabled: bool = False


def _ai_config(flags: LiveAiFlags) -> AiConfig:
    return AiConfig(
        enabled=flags.enabled,
        provider=flags.provider,
        tools_enabled=flags.tools_enabled,
        session_enabled=flags.session_enabled,
    )


@pytest.fixture
def live_ai_config_phase1() -> AiConfig:
    return _ai_config(LiveAiFlags(tools_enabled=False, session_enabled=False))


@pytest.fixture
def live_ai_config_tools() -> AiConfig:
    return _ai_config(LiveAiFlags(tools_enabled=True, session_enabled=False))


@pytest.fixture
def live_ai_config_session() -> AiConfig:
    return _ai_config(LiveAiFlags(tools_enabled=True, session_enabled=True))


def build_live_composition(
    flags: LiveAiFlags,
    *,
    db_path: Path | None = None,
    accumulation_judge_factory=None,
) -> AgentComposition:
    return build_agent_composition(
        _ai_config(flags),
        db_path=db_path,
        accumulation_judge_factory=accumulation_judge_factory,
    )


@pytest.fixture
def live_composition_phase1(require_deepseek_key: str) -> AgentComposition:
    del require_deepseek_key
    composition = build_live_composition(LiveAiFlags())
    if not composition.provider_available:
        pytest.skip("DeepSeek composition unavailable (credential/provider)")
    return composition


@pytest.fixture
def live_composition_tools(
    require_deepseek_key: str,
    live_db_path: Path,
) -> AgentComposition:
    del require_deepseek_key
    composition = build_live_composition(
        LiveAiFlags(tools_enabled=True),
        db_path=live_db_path,
    )
    if not composition.provider_available:
        pytest.skip("DeepSeek composition unavailable")
    if not composition.tools_enabled:
        pytest.skip("tools_enabled composition did not activate")
    return composition


@pytest.fixture
def live_composition_session(
    require_deepseek_key: str,
    live_db_path: Path,
) -> AgentComposition:
    del require_deepseek_key
    composition = build_live_composition(
        LiveAiFlags(tools_enabled=True, session_enabled=True),
        db_path=live_db_path,
    )
    if not composition.provider_available:
        pytest.skip("DeepSeek composition unavailable")
    if not composition.session_enabled:
        pytest.skip("session_enabled composition did not activate")
    return composition


def assert_context_reference(ref: str | None) -> None:
    assert ref is not None
    assert _SHA256_REF.match(ref), f"expected sha256 context reference, got {ref!r}"


def assert_tool_trace_closed(tool_results: tuple[Any, ...]) -> None:
    for item in tool_results:
        name = getattr(item, "name", None)
        value = name.value if hasattr(name, "value") else str(name)
        assert value in _CLOSED_TOOL_NAMES, f"tool outside ADR-061 registry: {value}"
        status = getattr(item, "status", None)
        status_value = status.value if hasattr(status, "value") else str(status)
        assert status_value in {
            "SUCCESS",
            "PARTIAL",
            "UNAVAILABLE",
            "FAILED",
            "REJECTED",
            "TIMEOUT",
        }, status_value
        ref = getattr(item, "result_reference", None)
        if ref:
            assert str(ref).startswith("sha256:"), ref


def action_identity(candidate: Any) -> str:
    setup = getattr(candidate, "trade_setup", None)
    action = getattr(setup, "action", None)
    return str(getattr(action, "value", action))


# Re-export helper namespace for tests that need SimpleNamespace AiConfig-like objects.
AiFlags = LiveAiFlags
SimpleAi = SimpleNamespace
