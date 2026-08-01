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
        "view-ticker-flow",
        "view-ticker-foreign-history",
        "view-ticker-distribution",
        "view-ticker-financials",
        "view-broker-list",
        "view-broker-show",
        "view-broker-top-stocks",
        "view-broker-top-matrix",
        "view-broker-flow",
        "view-broker-calendar",
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
            "TUI Enter = ADR-054 present-only Judge (accum_engine_inspect_presenter / "
            "decision_display); not CLI view ticker show; not CLI --full diagnostic suite",
            "TUI j on Judge = optional single-ticker local re-screen (same request builder); "
            "full-board r stays separate; snapshot-restored rows are limited judge until j",
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
            "TUI board columns Tkr·Act·IEP·Δ%·IEV·NCP·ΔIEV·Risk; NCP=lock flag not intensity; "
            "Act/ΔIEV honest — when snapshot lacks TradeSetup/locked baseline; "
            "session strip Source·Phase·Funnel·window; inspect Judge-shaped (Why+AUCTION always)",
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
        job_id="view-ticker-flow",
        product_name="View ticker flow (foreign summary)",
        cli_surface="saham view ticker flow",
        tui_surface="flow chip / f on view ticker",
        shared_application_path=(
            "ViewTickerFlowUseCase via build_view_ticker_deps; "
            "format via adapters.shared.view_ticker_job_text.format_ticker_flow_job"
        ),
        intentional_deltas=(
            "TUI mono job panel under ticker chip bar vs CLI Rich panel/table",
            "JSON envelope is CLI-only",
        ),
    ),
    DualSurfaceJob(
        job_id="view-ticker-foreign-history",
        product_name="View ticker foreign-history",
        cli_surface="saham view ticker foreign-history",
        tui_surface="foreign chip / o on view ticker",
        shared_application_path=(
            "ViewTickerForeignHistoryUseCase via build_view_ticker_deps; "
            "format via view_ticker_job_text.format_ticker_foreign_history_job"
        ),
        intentional_deltas=("TUI mono job panel vs CLI Rich table",),
    ),
    DualSurfaceJob(
        job_id="view-ticker-distribution",
        product_name="View ticker distribution",
        cli_surface="saham view ticker distribution",
        tui_surface="dist chip / x on view ticker",
        shared_application_path=(
            "ViewTickerDistributionUseCase via build_view_ticker_deps; "
            "format via view_ticker_job_text.format_ticker_distribution_job"
        ),
        intentional_deltas=("TUI mono job panel vs CLI typer ASCII tables",),
    ),
    DualSurfaceJob(
        job_id="view-ticker-financials",
        product_name="View ticker financials",
        cli_surface="saham view ticker financials",
        tui_surface="fin chip / n on view ticker",
        shared_application_path=(
            "ViewTickerFinancialsUseCase (income+balance+cashflow default) via "
            "build_view_ticker_deps; format via view_ticker_job_text.format_ticker_financials_job"
        ),
        intentional_deltas=(
            "TUI compact metric lines vs CLI Rich multi-column tables",
            "Default all three statements (same as CLI --statement all)",
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
            "TUI t/f/h/m/v hub keys",
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
        intentional_deltas=("TUI BrokerTopDesk dual-heat widget vs CLI Rich table",),
    ),
    DualSurfaceJob(
        job_id="view-broker-top-matrix",
        product_name="View broker top-matrix",
        cli_surface="saham view broker top-matrix",
        tui_surface="m on desk hub",
        shared_application_path=(
            "ViewBrokerDeskTopMatrixUseCase; format via format_desk_top_matrix_text; "
            "rank_desk_top_buy_matrix (net · lot-weighted avg buy · desk×ticker streak)"
        ),
        intentional_deltas=(
            "TUI BrokerMatrixDesk widget vs CLI Rich multi-column table",
            "Calendar (c) deferred — not this job",
        ),
    ),
    DualSurfaceJob(
        job_id="view-broker-flow",
        product_name="View broker flow",
        cli_surface="saham view broker flow",
        tui_surface="f on desk hub",
        shared_application_path=("ViewBrokerDeskFlowUseCase; format via format_desk_flow_text"),
        intentional_deltas=("TUI BrokerFlowDesk day-net table vs CLI Rich table",),
    ),
    DualSurfaceJob(
        job_id="view-broker-calendar",
        product_name="View broker calendar",
        cli_surface="saham view broker calendar",
        tui_surface="c on desk hub",
        shared_application_path=(
            "ViewBrokerDeskCalendarUseCase; format via format_desk_calendar_text; "
            "build_desk_calendar_days (top stock · net · B/S)"
        ),
        intentional_deltas=("TUI BrokerCalendarDesk widget vs CLI Rich table",),
    ),
    DualSurfaceJob(
        job_id="view-broker-history",
        product_name="View broker history",
        cli_surface="saham view broker history",
        tui_surface="h on desk hub",
        shared_application_path=(
            "ViewBrokerDeskHistoryUseCase; format via format_desk_history_text"
        ),
        intentional_deltas=(
            "TUI BrokerHistoryDesk row-capped widget; CLI may show fuller Rich table",
        ),
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
