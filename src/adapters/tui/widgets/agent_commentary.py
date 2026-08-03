"""Non-authoritative agent response surface (card or OpenCode-style stage)."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from src.application.dto.accumulation_agent import AgentTurnResult, AgentTurnStatus
from src.application.services.agent_data_honesty import (
    AgentDataHonestyView,
    AgentNoteSeverity,
    format_agent_more_notes,
    format_agent_status_strip,
    normalize_agent_data_notes,
)


class AgentCommentary(Vertical):
    """Model commentary — compact card under Judge, or full stage replace."""

    DEFAULT_CSS = """
    AgentCommentary {
        display: none;
        height: auto;
        width: 100%;
        margin-bottom: 1;
        padding: 1 2;
        background: #101010;
        border: solid #1c1c1c;
        border-left: solid #7a7a7a;
    }
    AgentCommentary.is-stage {
        height: 1fr;
        margin: 0;
        padding: 1 2 1 2;
        border: solid #2a2a2a;
        border-left: solid #9b8fb8;
        background: #0e0e0e;
    }
    AgentCommentary .agent-title { color: #d8d8d8; text-style: bold; height: auto; }
    AgentCommentary .agent-status {
        color: #7a7a7a;
        height: auto;
        margin-top: 1;
        padding: 1 1;
        background: #141414;
        border-left: solid #555555;
    }
    AgentCommentary .agent-status.has-warn {
        color: #d4b06a;
        border-left: solid #d4b06a;
        background: #1a1810;
    }
    AgentCommentary .agent-status.is-fail {
        color: #c97a72;
        border-left: solid #c97a72;
        background: #1a1212;
    }
    AgentCommentary .agent-question {
        color: #555555;
        height: auto;
        margin-top: 1;
    }
    AgentCommentary .agent-answer-scroll {
        height: auto;
        max-height: 24;
        margin-top: 1;
        scrollbar-color: #3a3a3a #121212;
        scrollbar-size-vertical: 1;
    }
    AgentCommentary.is-stage .agent-answer-scroll {
        height: 1fr;
        max-height: 100%;
    }
    AgentCommentary .agent-answer { color: #d8d8d8; height: auto; }
    AgentCommentary .agent-meta { color: #7a7a7a; height: auto; margin-top: 1; }
    AgentCommentary .agent-tools { color: #555555; height: auto; margin-top: 1; }
    AgentCommentary .agent-more {
        color: #555555;
        height: auto;
        margin-top: 1;
    }
    AgentCommentary .agent-error { color: #c97a72; height: auto; margin-top: 1; }
    AgentCommentary .agent-hint { color: #555555; height: auto; margin-top: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Static("AI Research Cockpit", classes="agent-title")
        yield Static("", classes="agent-status")
        yield Static("", classes="agent-question")
        with VerticalScroll(classes="agent-answer-scroll"):
            yield Static("", classes="agent-answer")
        yield Static("", classes="agent-meta")
        yield Static("", classes="agent-tools")
        yield Static("", classes="agent-more")
        yield Static("", classes="agent-error")
        yield Static("", classes="agent-hint")

    def set_stage_mode(self, enabled: bool) -> None:
        self.set_class(enabled, "is-stage")

    def clear(self) -> None:
        self.display = False
        self.set_stage_mode(False)
        for selector in (
            ".agent-status",
            ".agent-question",
            ".agent-answer",
            ".agent-meta",
            ".agent-tools",
            ".agent-more",
            ".agent-error",
            ".agent-hint",
        ):
            self.query_one(selector, Static).update("")
        status = self.query_one(".agent-status", Static)
        status.remove_class("has-warn", "is-fail")
        self.query_one(".agent-title", Static).update("AI Research Cockpit")

    def show_stage_ready(self, *, ticker: str, action: str, provider: str) -> None:
        """Empty OpenCode-style stage before the first question."""
        self.set_stage_mode(True)
        self.display = True
        self.query_one(".agent-title", Static).update("AI Research Cockpit")
        self._paint_status(
            turn_ok=True,
            ticker=ticker,
            as_of="—",
            notes=normalize_agent_data_notes(()),
            force_empty_msg=True,
        )
        self.query_one(".agent-question", Static).update("")
        self.query_one(".agent-answer", Static).update(
            Text(
                f"Ask about {ticker} · deterministic Action {action}\n\n"
                "Type a question in the prompt · Enter to send · Esc to leave agent"
            )
        )
        remote = "remote" if provider else "local"
        self.query_one(".agent-meta", Static).update(
            Text(f"{remote} · {provider or '—'} · non-authoritative commentary")
        )
        self.query_one(".agent-tools", Static).update("")
        self.query_one(".agent-more", Static).update("")
        self.query_one(".agent-error", Static).update("")
        self.query_one(".agent-hint", Static).update(
            Text("Judge facts stay authoritative · model cannot change Action")
        )

    def show_loading(self, *, provider: str, ticker: str, question: str = "") -> None:
        self.display = True
        self.query_one(".agent-title", Static).update("AI Research Cockpit")
        self._paint_status(
            turn_ok=True,
            ticker=ticker,
            as_of="…",
            notes=normalize_agent_data_notes(()),
            loading=True,
        )
        if question.strip():
            self.query_one(".agent-question", Static).update(Text(f"› {question.strip()}"))
        else:
            self.query_one(".agent-question", Static).update("")
        self.query_one(".agent-answer", Static).update("Thinking…")
        self.query_one(".agent-meta", Static).update(Text(f"remote · {provider} · {ticker}"))
        self.query_one(".agent-tools", Static).update("")
        self.query_one(".agent-more", Static).update("")
        self.query_one(".agent-error", Static).update("")
        self.query_one(".agent-hint", Static).update("")

    def show_progress(self, message: str, *, provider: str = "", ticker: str = "") -> None:
        """Multi-round progress (ADR-064) — not Turn OK answer content."""
        self.display = True
        line = (message or "").strip() or "Working…"
        self.query_one(".agent-title", Static).update("AI Research Cockpit")
        self.query_one(".agent-answer", Static).update(Text(line))
        if provider or ticker:
            self.query_one(".agent-meta", Static).update(
                Text(f"remote · {provider or '—'} · {ticker or '—'}")
            )

    def show_result(
        self,
        result: AgentTurnResult,
        *,
        as_of: str,
        question: str = "",
        ticker: str = "—",
    ) -> None:
        self.display = True
        self.query_one(".agent-title", Static).update("AI Research Cockpit")
        answered = result.status in {AgentTurnStatus.SUCCESS, AgentTurnStatus.PARTIAL}
        turn_ok = answered
        notes = normalize_agent_data_notes(result.warnings)
        self._paint_status(
            turn_ok=turn_ok,
            ticker=ticker or "—",
            as_of=as_of,
            notes=notes,
        )
        answer = result.answer if answered else ""
        if question.strip():
            self.query_one(".agent-question", Static).update(Text(f"› {question.strip()}"))
        self.query_one(".agent-answer", Static).update(Text(answer))
        meta = ""
        if answered:
            meta = (
                f"{result.provider} · {result.model} · as-of {as_of}\n"
                f"context {result.context_reference}"
            )
            session_id = getattr(result, "session_id", None)
            turn_sequence = getattr(result, "turn_sequence", None)
            if session_id and turn_sequence:
                meta += f"\nsession {session_id} · turn {turn_sequence}"
        self.query_one(".agent-meta", Static).update(Text(meta))
        trace = "\n".join(
            f"tool {item.name.value} · {item.status.value} · {item.result_reference}"
            for item in result.tool_results
        )
        self.query_one(".agent-tools", Static).update(Text(trace))
        self.query_one(".agent-more", Static).update(Text(format_agent_more_notes(notes)))
        self.query_one(".agent-error", Static).update(Text(result.error_message or ""))
        self.query_one(".agent-hint", Static).update(
            Text("Esc leave agent · / ask again · deterministic Judge unchanged")
            if self.has_class("is-stage")
            else Text("")
        )

    def _paint_status(
        self,
        *,
        turn_ok: bool,
        ticker: str,
        as_of: str,
        notes: AgentDataHonestyView,
        loading: bool = False,
        force_empty_msg: bool = False,
    ) -> None:
        status = self.query_one(".agent-status", Static)
        status.remove_class("has-warn", "is-fail")
        if loading:
            status.update(Text(f"Turn  … · {ticker or '—'} · waiting on model"))
            return
        if force_empty_msg and notes.empty:
            status.update(
                Text(
                    f"Turn  ready · {ticker or '—'} · as-of {as_of or '—'}\n"
                    "Data  honesty notes appear here after a reply (with Do guides)"
                )
            )
            return
        body = format_agent_status_strip(
            turn_ok=turn_ok,
            ticker=ticker,
            as_of=as_of,
            notes=notes,
        )
        status.update(Text(body))
        if not turn_ok:
            status.add_class("is-fail")
        elif any(n.severity is AgentNoteSeverity.WARN for n in notes.primary):
            status.add_class("has-warn")
