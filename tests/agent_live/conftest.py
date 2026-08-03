"""Shared gates and fixtures for agent-live-call smoke tests.

Hard gate: ``AI_SAHAM_AGENT_LIVE=1`` — without it every live test skips.
Additional skips for missing credentials, flags, or local cache data.

Live provider HTTP is hard-capped via ``LIVE_HTTP_TIMEOUT_S`` on the DeepSeek
client and a wall-clock wrapper around ``generate``. Suite-wide provider calls
are capped by ``LIVE_PROVIDER_CALL_BUDGET``.
"""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
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
_provider_calls: dict[str, int] = {"n": 0}


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


def make_budgeted_deepseek_factory(
    *,
    call_counter: dict[str, int] | None = None,
    timeout_s: float = LIVE_HTTP_TIMEOUT_S,
    budget: int = LIVE_PROVIDER_CALL_BUDGET,
):
    """Return a DeepSeekAgentModel factory with HTTP timeout + call budget.

    Used by the live autouse fixture and unit-tested so the caps are not dead.
    """
    from src.infrastructure.ai.deepseek_agent_model import DeepSeekAgentModel

    counter = call_counter if call_counter is not None else _provider_calls

    def _factory(api_key: str, *, client: Any | None = None) -> DeepSeekAgentModel:
        if client is None:
            import openai

            client = openai.OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com",
                timeout=timeout_s,
                max_retries=0,
            )
        model = DeepSeekAgentModel(api_key, client=client)
        original = model.generate

        def _guarded_generate(req: Any) -> Any:
            counter["n"] += 1
            if counter["n"] > budget:
                raise RuntimeError(
                    f"live provider call budget exceeded ({counter['n']} > {budget})"
                )
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(original, req)
                try:
                    return future.result(timeout=timeout_s)
                except FuturesTimeout as exc:
                    raise TimeoutError(f"DeepSeek generate exceeded {timeout_s}s live cap") from exc

        model.generate = _guarded_generate  # type: ignore[method-assign]
        return model

    return _factory


@pytest.fixture(autouse=True)
def _enforce_live_http_timeout_and_budget(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Apply hard HTTP timeout + suite provider-call budget to live DeepSeek models.

    Only active when the operator opted into live runs; skipped tests never
    construct a client. Monkeypatch targets composition import site so every
    ``build_agent_composition`` path is covered.
    """
    if request.node.get_closest_marker("agent-live-call") is None:
        return
    if not live_env_enabled():
        return

    from src.infrastructure.composition import agent_model as agent_model_mod

    monkeypatch.setattr(
        agent_model_mod,
        "DeepSeekAgentModel",
        make_budgeted_deepseek_factory(),
    )


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
