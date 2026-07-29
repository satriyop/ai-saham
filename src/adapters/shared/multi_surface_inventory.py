"""Durable inventory of product jobs exposed on both CLI and TUI.

Anti-drift contract (AGENT_QUICKSTART multi-surface + ADR-045):
each dual-surface job declares the shared application entry and any
**intentional** presentation-only deltas. Tests fail if a required job is
missing or unmarked.

Layer: Adapter (shared governance / inventory)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DualSurfaceJob:
    """One product job available on CLI and TUI with a shared semantic path."""

    job_id: str
    product_name: str
    cli_surface: str
    tui_surface: str
    shared_application_path: str
    intentional_deltas: tuple[str, ...]


# Required dual-surface jobs — must stay complete as surfaces grow.
REQUIRED_DUAL_SURFACE_JOB_IDS: frozenset[str] = frozenset(
    {
        "screen-accum",
        "screen-preopen",
        "view-ticker-show",
        "view-ticker-top-brokers",
        "view-broker-list",
        "view-broker-show",
        "view-broker-top-stocks",
        "view-broker-flow",
        "view-broker-history",
        "plan-swing-structure",
    }
)


DUAL_SURFACE_JOBS: tuple[DualSurfaceJob, ...] = (
    DualSurfaceJob(
        job_id="screen-accum",
        product_name="Screen accumulation",
        cli_surface="saham screen accum",
        tui_surface="s a / palette screen-accum · accum board",
        shared_application_path=(
            "src.adapters.composition.screen_accum_request.build_default_screen_accum_request "
            "+ RunAccumulationScreenWorkflowUseCase; board fields via "
            "screen_accum_board_fields + decision_display"
        ),
        intentional_deltas=(
            "TUI board columns/widgets vs CLI Rich table (presentation only)",
            "TUI Enter = present-only inspect (accum_engine_inspect_presenter), "
            "not CLI view ticker show",
        ),
    ),
    DualSurfaceJob(
        job_id="screen-preopen",
        product_name="Screen pre-open",
        cli_surface="saham screen pre-open",
        tui_surface="s p / palette screen-preopen · preopen board",
        shared_application_path="PreOpenScreenUseCase (IEV snapshot path in TUI loader)",
        intentional_deltas=(
            "TUI pre-open board is IEV snapshot only (no full CLI pre-open flag surface)",
            "TUI Enter = present-only preopen inspect, not re-run",
        ),
    ),
    DualSurfaceJob(
        job_id="view-ticker-show",
        product_name="View ticker show (cache dashboard)",
        cli_surface="saham view ticker show",
        tui_surface="v t / palette view-ticker",
        shared_application_path=(
            "GetTickerDashboardUseCase via build_view_ticker_deps; "
            "format via adapters.shared.view_ticker_dashboard_text"
        ),
        intentional_deltas=(
            "TUI detail stage chrome/actions (b desks, esc trail) vs CLI stdout",
            "JSON envelope is CLI-only (ADR-046)",
        ),
    ),
    DualSurfaceJob(
        job_id="view-ticker-top-brokers",
        product_name="View ticker top-brokers / stock→desks",
        cli_surface="saham view ticker top-brokers",
        tui_surface="b on view ticker · ticker-desks stage",
        shared_application_path=(
            "ViewTickerTopBrokersUseCase (summary tops + tracked daily-flow fallback); "
            "pulse via desk_session_pulse; rows via view_ticker_top_brokers_rows"
        ),
        intentional_deltas=(
            "TUI table adds stock-scoped Net3/5/7/10/20 + partial *(used/X) markers "
            "(presentation; ranking still use-case tops)",
            "CLI Rich buyer/seller tables; TUI DataTable stage",
        ),
    ),
    DualSurfaceJob(
        job_id="view-broker-list",
        product_name="View broker list",
        cli_surface="saham view broker list",
        tui_surface="v b / palette view-broker · broker-list stage",
        shared_application_path=(
            "broker_daily_flow + classify_desk_type + desk_session_pulse "
            "(cache-only tracked desks); no parallel ranking policy in adapters"
        ),
        intentional_deltas=(
            "TUI multi-column Net5 radar sort |Net5|; CLI list may be thinner text",
            "TUI stages/chords navigation only",
        ),
    ),
    DualSurfaceJob(
        job_id="view-broker-show",
        product_name="View broker desk show",
        cli_surface="saham view broker show",
        tui_surface="Enter on desk row · broker show page",
        shared_application_path=(
            "ViewBrokerDeskShowUseCase; format via view_broker_desk_text.format_desk_show_text"
        ),
        intentional_deltas=(
            "TUI may append stock-scoped pulse line on show body (presentation)",
            "TUI t/f/h/v hub keys",
        ),
    ),
    DualSurfaceJob(
        job_id="view-broker-top-stocks",
        product_name="View broker top-stocks",
        cli_surface="saham view broker top-stocks",
        tui_surface="t on desk hub",
        shared_application_path=(
            "ViewBrokerDeskTopStocksUseCase; format via format_desk_top_stocks_text"
        ),
        intentional_deltas=("TUI plain text in detail stage vs CLI Rich table",),
    ),
    DualSurfaceJob(
        job_id="view-broker-flow",
        product_name="View broker flow",
        cli_surface="saham view broker flow",
        tui_surface="f on desk hub",
        shared_application_path=("ViewBrokerDeskFlowUseCase; format via format_desk_flow_text"),
        intentional_deltas=("TUI plain text in detail stage vs CLI Rich table",),
    ),
    DualSurfaceJob(
        job_id="view-broker-history",
        product_name="View broker history",
        cli_surface="saham view broker history",
        tui_surface="h on desk hub",
        shared_application_path=(
            "ViewBrokerDeskHistoryUseCase; format via format_desk_history_text"
        ),
        intentional_deltas=("TUI plain text row-capped; CLI may show fuller Rich table",),
    ),
    DualSurfaceJob(
        job_id="plan-swing-structure",
        product_name="Plan swing structure desk",
        cli_surface="saham plan swing",
        tui_surface="p / palette plan-swing · plan stage",
        shared_application_path=(
            "PlanSwingWorkflowUseCase (structure path; ADR-054); TUI thin local defaults"
        ),
        intentional_deltas=(
            "TUI plan depth thinner than full CLI flag surface "
            "(capital/strategy/detail flags not all exposed)",
            "TUI stage chrome vs CLI stdout; no broker order on either",
        ),
    ),
)


def dual_surface_job_ids() -> frozenset[str]:
    return frozenset(j.job_id for j in DUAL_SURFACE_JOBS)


def get_dual_surface_job(job_id: str) -> DualSurfaceJob | None:
    for job in DUAL_SURFACE_JOBS:
        if job.job_id == job_id:
            return job
    return None
