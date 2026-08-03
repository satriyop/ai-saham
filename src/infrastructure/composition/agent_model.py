"""Optional agent-model composition with fail-soft configuration."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.application.dto.accumulation_agent import (
    AgentModelUnavailableReason,
    AgentTurnPolicy,
)
from src.application.dto.agent_session import AgentSessionPolicy
from src.application.dto.agent_tools import AgentToolName, AgentToolTurnPolicy
from src.application.services.agent_accumulation_judge_tool import AccumulationJudgeTool
from src.application.services.agent_broker_desk_tool import BrokerDeskTool
from src.application.services.agent_ro_data_query_tool import RoDataQueryTool
from src.application.services.agent_session_store import InMemoryAgentSessionStore
from src.application.services.agent_ticker_broker_flow_tool import TickerBrokerFlowTool
from src.application.services.agent_ticker_dashboard_tool import TickerDashboardTool
from src.application.services.agent_tool_registry import AgentToolRegistry
from src.application.services.agent_visible_cockpit_tool import VisibleCockpitResultTool
from src.application.services.agent_web_research_tool import (
    NullWebResearchClient,
    WebResearchTool,
)
from src.application.use_case.explain_accumulation_candidate_use_case import (
    ExplainAccumulationCandidateUseCase,
)
from src.application.use_case.orchestrate_agent_turn_use_case import AgentTurnOrchestrator
from src.application.use_case.session_aware_agent_turn_use_case import (
    DEEPSEEK_SESSION_CERTIFICATION,
    SessionAwareAgentTurnUseCase,
)
from src.infrastructure.ai.deepseek_agent_model import DeepSeekAgentModel
from src.infrastructure.ai.provider_config import resolve_ai_provider
from src.infrastructure.composition.view_broker_deps import (
    build_read_only_broker_desk_use_cases,
)
from src.infrastructure.composition.view_ticker_deps import (
    build_read_only_ticker_broker_flow_deps,
    build_read_only_ticker_dashboard_use_case,
)
from src.infrastructure.config.local_env import read_local_env_value
from src.infrastructure.persistence.sqlite_allowlisted_ro_query import (
    SqliteAllowlistedRoQuery,
)


@dataclass(frozen=True)
class AgentComposition:
    use_case: (
        ExplainAccumulationCandidateUseCase | AgentTurnOrchestrator | SessionAwareAgentTurnUseCase
    )
    provider_available: bool
    configured_provider: str
    tools_requested: bool
    tools_enabled: bool
    tools_multi_round: bool
    external_tools: bool
    session_requested: bool
    session_enabled: bool
    registered_tools: tuple[AgentToolName, ...]


def build_agent_composition(
    ai_config: object,
    *,
    provider: str | None = None,
    db_path: Path | str | None = None,
    accumulation_judge_factory: Callable[[], Callable] | None = None,
) -> AgentComposition:
    explicit = provider
    if explicit is None and not os.getenv("AI_PROVIDER"):
        explicit = str(getattr(ai_config, "provider", "deepseek"))
    configured = resolve_ai_provider(explicit).strip().lower()
    enabled = bool(getattr(ai_config, "enabled", False))
    tools_requested = enabled and bool(getattr(ai_config, "tools_enabled", False))
    multi_round_requested = tools_requested and bool(getattr(ai_config, "tools_multi_round", False))
    external_master = tools_requested and bool(getattr(ai_config, "external_tools", False))
    web_research_on = external_master and bool(getattr(ai_config, "web_research", False))
    ro_data_on = external_master and bool(getattr(ai_config, "ro_data_query", False))
    session_requested = enabled and bool(getattr(ai_config, "session_enabled", False))
    model = None
    reason = None
    if not enabled:
        reason = AgentModelUnavailableReason.DISABLED
    elif configured != "deepseek":
        reason = AgentModelUnavailableReason.UNSUPPORTED_PROVIDER
    else:
        api_key = (
            os.getenv("DEEPSEEK_API_KEY", "").strip()
            or (read_local_env_value("DEEPSEEK_API_KEY") or "").strip()
        )
        if not api_key:
            reason = AgentModelUnavailableReason.MISSING_CREDENTIAL
        else:
            model = DeepSeekAgentModel(api_key)
    phase_one_use_case = ExplainAccumulationCandidateUseCase(
        model,
        AgentTurnPolicy(
            enabled=enabled,
            configured_provider=configured,
            model_unavailable_reason=reason,
        ),
    )
    tools_enabled = tools_requested and model is not None and configured == "deepseek"
    tools_multi_round = multi_round_requested and tools_enabled
    use_case: (
        ExplainAccumulationCandidateUseCase | AgentTurnOrchestrator | SessionAwareAgentTurnUseCase
    )
    registered_tools: tuple[AgentToolName, ...] = ()
    if tools_enabled:
        tools = [VisibleCockpitResultTool()]
        if db_path is not None:
            try:
                dashboard = build_read_only_ticker_dashboard_use_case(db_path)
            except (OSError, ValueError):
                dashboard = None
            if dashboard is not None:
                tools.append(TickerDashboardTool(dashboard))
            try:
                desk = build_read_only_broker_desk_use_cases(db_path)
            except (OSError, ValueError):
                desk = None
            if desk is not None:
                tools.append(BrokerDeskTool(desk))
            try:
                ticker_flow = build_read_only_ticker_broker_flow_deps(db_path)
            except (OSError, ValueError):
                ticker_flow = None
            if ticker_flow is not None:
                tools.append(
                    TickerBrokerFlowTool(
                        ticker_flow.top_brokers,
                        ticker_flow.bandar_source,
                    )
                )
        if accumulation_judge_factory is not None:
            try:
                judge_ticker = accumulation_judge_factory()
            except (OSError, ValueError):
                judge_ticker = None
            if judge_ticker is not None:
                tools.append(AccumulationJudgeTool(judge_ticker))
        if web_research_on:
            # Default null client is offline-safe; live composition may inject HTTP later.
            tools.append(WebResearchTool(NullWebResearchClient()))
        if ro_data_on and db_path is not None:
            try:
                tools.append(RoDataQueryTool(SqliteAllowlistedRoQuery(db_path)))
            except (OSError, ValueError):
                pass
        registered_tools = tuple(tool.definition.name for tool in tools)
        policy = (
            AgentToolTurnPolicy.l3(tools_enabled=True)
            if tools_multi_round
            else AgentToolTurnPolicy.l1(tools_enabled=True)
        )
        use_case = AgentTurnOrchestrator(
            model,
            AgentToolRegistry(tuple(tools)),
            policy,
        )
    else:
        use_case = phase_one_use_case

    session_enabled = (
        session_requested
        and model is not None
        and configured == DEEPSEEK_SESSION_CERTIFICATION.provider
        and DEEPSEEK_SESSION_CERTIFICATION.passed
    )
    if session_enabled:
        store = InMemoryAgentSessionStore(AgentSessionPolicy(enabled=True))
        use_case = SessionAwareAgentTurnUseCase(
            use_case,
            store,
            AgentSessionPolicy(enabled=True),
            certification=DEEPSEEK_SESSION_CERTIFICATION,
            configured_provider=configured,
        )

    return AgentComposition(
        use_case,
        model is not None,
        configured,
        tools_requested,
        tools_enabled,
        tools_multi_round,
        external_master and tools_enabled,
        session_requested,
        session_enabled,
        registered_tools,
    )
