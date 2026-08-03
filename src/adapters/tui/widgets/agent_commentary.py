"""Non-authoritative agent response surface (card or OpenCode-style stage)."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from src.application.dto.accumulation_agent import AgentTurnResult, AgentTurnStatus


class AgentCommentary(Vertical):
    """Model commentary — compact card under Judge, or full stage replace."""

    DEFAULT_CSS = """
    AgentCommentary {
        display: none;
        height: auto;
        width: 100%;
        margin-bottom: 1;
        padding: 1 2;
        background: #101014;
        border: solid #24242c;
        border-left: solid #686878;
    }
    AgentCommentary.is-stage {
        height: 1fr;
        margin: 0;
        padding: 1 2 1 2;
        border: solid #2a2a34;
        border-left: solid #8a8aaa;
        background: #0e0e12;
    }
    AgentCommentary .agent-title { color: #aaaabc; text-style: bold; height: auto; }
    AgentCommentary .agent-question {
        color: #858596;
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
    AgentCommentary .agent-answer { color: #d0d0d8; height: auto; }
    AgentCommentary .agent-meta { color: #686878; height: auto; margin-top: 1; }
    AgentCommentary .agent-tools { color: #858596; height: auto; margin-top: 1; }
    AgentCommentary .agent-warning { color: #d4b06a; height: auto; }
    AgentCommentary .agent-error { color: #c97a72; height: auto; margin-top: 1; }
    AgentCommentary .agent-hint { color: #555566; height: auto; margin-top: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Static("Agent", classes="agent-title")
        yield Static("", classes="agent-question")
        with VerticalScroll(classes="agent-answer-scroll"):
            yield Static("", classes="agent-answer")
        yield Static("", classes="agent-meta")
        yield Static("", classes="agent-tools")
        yield Static("", classes="agent-warning")
        yield Static("", classes="agent-error")
        yield Static("", classes="agent-hint")

    def set_stage_mode(self, enabled: bool) -> None:
        self.set_class(enabled, "is-stage")

    def clear(self) -> None:
        self.display = False
        self.set_stage_mode(False)
        for selector in (
            ".agent-question",
            ".agent-answer",
            ".agent-meta",
            ".agent-tools",
            ".agent-warning",
            ".agent-error",
            ".agent-hint",
        ):
            self.query_one(selector, Static).update("")
        self.query_one(".agent-title", Static).update("Agent")

    def show_stage_ready(self, *, ticker: str, action: str, provider: str) -> None:
        """Empty OpenCode-style stage before the first question."""
        self.set_stage_mode(True)
        self.display = True
        self.query_one(".agent-title", Static).update("Agent")
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
        self.query_one(".agent-warning", Static).update("")
        self.query_one(".agent-error", Static).update("")
        self.query_one(".agent-hint", Static).update(
            Text("Judge facts stay authoritative · model cannot change Action")
        )

    def show_loading(self, *, provider: str, ticker: str, question: str = "") -> None:
        self.display = True
        self.query_one(".agent-title", Static).update("Agent")
        if question.strip():
            self.query_one(".agent-question", Static).update(Text(f"› {question.strip()}"))
        else:
            self.query_one(".agent-question", Static).update("")
        self.query_one(".agent-answer", Static).update("Thinking…")
        self.query_one(".agent-meta", Static).update(Text(f"remote · {provider} · {ticker}"))
        self.query_one(".agent-tools", Static).update("")
        self.query_one(".agent-warning", Static).update("")
        self.query_one(".agent-error", Static).update("")
        self.query_one(".agent-hint", Static).update("")

    def show_result(self, result: AgentTurnResult, *, as_of: str, question: str = "") -> None:
        self.display = True
        answered = result.status in {AgentTurnStatus.SUCCESS, AgentTurnStatus.PARTIAL}
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
        warnings = "\n".join(f"Warning: {item}" for item in result.warnings)
        self.query_one(".agent-warning", Static).update(Text(warnings))
        self.query_one(".agent-error", Static).update(Text(result.error_message or ""))
        self.query_one(".agent-hint", Static).update(
            Text("Esc leave agent · / ask again · deterministic Judge unchanged")
            if self.has_class("is-stage")
            else Text("")
        )
