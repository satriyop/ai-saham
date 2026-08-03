"""Non-authoritative agent response surface (card or OpenCode-style stage).

Stage layout (chat-first, modern TUI):
  sticky status (chips only)
  → one 1fr transcript scroll (question + answer + compact foot) — PRIMARY
  → one-line hint
Meta / tools / honesty details live *inside* the scroll so they never steal
viewport from the answer. Full multi-line Do guides are not permanent chrome.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from src.adapters.tui.theme import bake_css
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

    DEFAULT_CSS = bake_css("""
    AgentCommentary {
        display: none;
        height: auto;
        width: 100%;
        margin-bottom: 1;
        padding: 1 2;
        background: $oc_bg_panel;
        border: solid $oc_border;
        border-left: solid $oc_text_dim;
        layout: vertical;
    }
    AgentCommentary.is-stage {
        height: 1fr;
        margin: 0;
        padding: 1 2 0 2;
        border: solid $oc_hairline_strong;
        border-left: solid $oc_purple;
        background: $oc_bg_sidebar;
    }
    AgentCommentary .agent-title {
        color: $oc_text;
        text-style: bold;
        height: auto;
    }
    AgentCommentary .agent-status {
        color: $oc_text_dim;
        height: auto;
        margin-top: 1;
        padding: 1 1;
        background: $oc_bg_elevated;
        border-left: solid $oc_text_mute;
    }
    AgentCommentary.is-stage .agent-status {
        margin-top: 0;
        padding: 0 1;
        max-height: 3;
    }
    AgentCommentary .agent-status.has-warn {
        color: $oc_brass;
        border-left: solid $oc_brass;
        background: $oc_warn_bg;
    }
    AgentCommentary .agent-status.is-fail {
        color: $oc_coral;
        border-left: solid $oc_coral;
        background: $oc_fail_bg;
    }
    /* Primary surface: one transcript scroll fills remaining stage height. */
    AgentCommentary .agent-transcript {
        height: auto;
        max-height: 24;
        margin-top: 1;
        scrollbar-color: $oc_scrollbar $oc_track_inactive;
        scrollbar-size-vertical: 1;
    }
    AgentCommentary.is-stage .agent-transcript {
        height: 1fr;
        min-height: 8;
        max-height: 100%;
        margin-top: 1;
        margin-bottom: 0;
    }
    AgentCommentary .agent-question {
        color: $oc_text_mute;
        height: auto;
        margin-bottom: 1;
    }
    AgentCommentary .agent-answer {
        color: $oc_text;
        height: auto;
    }
    AgentCommentary .agent-meta {
        color: $oc_text_dim;
        height: auto;
        margin-top: 1;
    }
    AgentCommentary .agent-tools {
        color: $oc_text_mute;
        height: auto;
        margin-top: 0;
    }
    AgentCommentary .agent-more {
        color: $oc_text_mute;
        height: auto;
        margin-top: 0;
    }
    AgentCommentary .agent-error {
        color: $oc_coral;
        height: auto;
        margin-top: 1;
    }
    AgentCommentary .agent-hint {
        color: $oc_text_mute;
        height: auto;
        margin-top: 0;
        padding-top: 0;
    }
    AgentCommentary.is-stage .agent-hint {
        dock: bottom;
        height: 1;
        margin: 0;
        padding: 0;
    }
    """)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._stage_turns: list[str] = []

    def compose(self) -> ComposeResult:
        yield Static("AI Research Cockpit", classes="agent-title")
        yield Static("", classes="agent-status")
        # Transcript is the only flex child — answer is primary; chrome scrolls with it.
        with VerticalScroll(classes="agent-transcript"):
            yield Static("", classes="agent-question")
            yield Static("", classes="agent-answer")
            yield Static("", classes="agent-meta")
            yield Static("", classes="agent-tools")
            yield Static("", classes="agent-more")
            yield Static("", classes="agent-error")
        yield Static("", classes="agent-hint")

    def set_stage_mode(self, enabled: bool) -> None:
        self.set_class(enabled, "is-stage")
        if not enabled:
            self._stage_turns = []

    def clear(self) -> None:
        self.display = False
        self.set_stage_mode(False)
        self._stage_turns = []
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
        self._stage_turns = []
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
            Text("Esc leave · / ask again · Judge unchanged")
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
        if not self.has_class("is-stage"):
            self.query_one(".agent-hint", Static).update("")
        self._scroll_transcript_end()

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
        self._scroll_transcript_end()

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
        stage = self.has_class("is-stage")
        self._paint_status(
            turn_ok=turn_ok,
            ticker=ticker or "—",
            as_of=as_of,
            notes=notes,
            # Stage: chips only on the sticky header.
            compact_honesty=stage,
        )

        answer = result.answer if answered else ""
        q = question.strip()

        if stage and answered:
            # Grow a transcript of turns — answer remains the bulk of each block.
            block_lines: list[str] = []
            if q:
                block_lines.append(f"› {q}")
                block_lines.append("")
            block_lines.append(answer)
            self._stage_turns.append("\n".join(block_lines))
            self.query_one(".agent-question", Static).update("")
            self.query_one(".agent-answer", Static).update(
                Text("\n\n────────\n\n".join(self._stage_turns))
            )
        else:
            if q:
                self.query_one(".agent-question", Static).update(Text(f"› {q}"))
            else:
                self.query_one(".agent-question", Static).update("")
            self.query_one(".agent-answer", Static).update(Text(answer))

        # Compact foot *inside* transcript (scrolls with answer; never steals 1fr).
        meta = ""
        if answered:
            parts = [f"{result.provider} · {result.model} · as-of {as_of}"]
            session_id = getattr(result, "session_id", None)
            turn_sequence = getattr(result, "turn_sequence", None)
            if session_id and turn_sequence:
                parts.append(f"session {session_id} · turn {turn_sequence}")
            # Full context sha on second line for card; stage keeps one line + tools.
            if stage:
                n_tools = len(result.tool_results)
                if n_tools:
                    parts[0] += f" · {n_tools} tool{'s' if n_tools != 1 else ''}"
                meta = parts[0] if len(parts) == 1 else " · ".join(parts)
            else:
                meta = parts[0] + f"\ncontext {result.context_reference}"
                if session_id and turn_sequence:
                    meta += f"\nsession {session_id} · turn {turn_sequence}"
        self.query_one(".agent-meta", Static).update(Text(meta))

        if stage:
            # One line per tool — still scrollable with transcript, not fixed chrome.
            trace = "\n".join(
                f"tool {item.name.value} · {item.status.value}" for item in result.tool_results
            )
            # Keep result_reference available for tests / operators who scroll.
            if result.tool_results:
                trace = "\n".join(
                    f"tool {item.name.value} · {item.status.value} · {item.result_reference}"
                    for item in result.tool_results
                )
            self.query_one(".agent-tools", Static).update(Text(trace))
            # No permanent multi-line Do guides — chips already on status.
            # Overflow note titles only if primary strip collapsed extras.
            more_n = len(notes.more)
            more_line = f"Honesty · +{more_n} more (chips above)" if more_n else ""
            self.query_one(".agent-more", Static).update(Text(more_line))
        else:
            trace = "\n".join(
                f"tool {item.name.value} · {item.status.value} · {item.result_reference}"
                for item in result.tool_results
            )
            self.query_one(".agent-tools", Static).update(Text(trace))
            self.query_one(".agent-more", Static).update(
                Text(format_agent_more_notes(notes, include_primary_guides=False))
            )

        self.query_one(".agent-error", Static).update(Text(result.error_message or ""))
        self.query_one(".agent-hint", Static).update(
            Text("Esc leave · / ask again · Judge unchanged") if stage else Text("")
        )
        self._scroll_transcript_end()

    def _scroll_transcript_end(self) -> None:
        try:
            scroll = self.query_one(".agent-transcript", VerticalScroll)
            scroll.scroll_end(animate=False)
        except Exception:
            pass

    def _paint_status(
        self,
        *,
        turn_ok: bool,
        ticker: str,
        as_of: str,
        notes: AgentDataHonestyView,
        loading: bool = False,
        force_empty_msg: bool = False,
        compact_honesty: bool = False,
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
                    "Data  honesty chips appear here after a reply"
                )
            )
            return
        body = format_agent_status_strip(
            turn_ok=turn_ok,
            ticker=ticker,
            as_of=as_of,
            notes=notes,
            include_do_guides=not compact_honesty,
        )
        status.update(Text(body))
        if not turn_ok:
            status.add_class("is-fail")
        elif any(n.severity is AgentNoteSeverity.WARN for n in notes.primary):
            status.add_class("has-warn")
