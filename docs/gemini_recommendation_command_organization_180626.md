# CLI Organization & UI/UX Recommendations
**Date:** 2026-06-15
**Goal:** Transition the CLI from a "database of flags" to a "trader's cockpit" optimized for the Indonesia Stock Exchange (IHSG).

---

## 1. The Problem: "Complexity Debt"

Following a deep audit of the CLI adapter layer (`swing_commands.py`, `screen_commands.py`), several friction points were identified:
- **Fragmentation:** Users must run 3-4 top-level command groups (`data`, `analyze`, `trade`) to perform a single morning ritual.
- **Cognitive Load:** Commands like `saham trade swing screen --multi --min-score 50` are powerful but require memorizing obscure flag combinations.
- **Visual Density:** Output is currently a "wall of text" where primary signals (ENTER/WATCH) compete with secondary technical data (RSI, BB%ILE) for the user's attention.

---

## 2. Recommendation: The "Daily Dashboard" (`saham daily`)

Instead of requiring the user to navigate the command hierarchy, we should provide a single, smart entry point that orchestrates the daily ritual.

### Proposed Workflow
Running `saham daily` (or `saham ritual`) will execute a composite use case:
1.  **Auto-Refresh:** Checks data freshness for favorite universes (e.g., LQ45) and updates if stale.
2.  **Regime Context:** Displays a 3-line summary of IHSG breadth and benchmark trend.
3.  **Top Movers:** Shows a "Mini-Screener" with the top 3 candidates for both **Swing** and **Intraday** workflows.
4.  **Interactive Prompts:** Ends with a "What would you like to do?" selection (e.g., Analyze BBRI, Log a trade, or Exit).

| Pro | Con |
| :--- | :--- |
| High utility; reduces morning friction. | Requires a new Orchestration Use Case. |
| Guided experience for new users. | None. |

---

## 3. Recommendation: Interactive Wizards (`saham log`)

Complex multi-step tasks like journaling entries or recording outcomes often lead to errors when using long flag strings.

### Proposed Workflow
Modify `saham log` and `saham outcome` to support an interactive mode if run without arguments.
- **Current:** `saham trade intraday outcome BBCA --entry 9000 --exit 9500 --result target`
- **Interactive:**
    - `Ticker? [BBCA]:`
    - `Style? (swing/intraday):`
    - `Exit Price? [9500]:`
    - `Result? (target/stop/manual):`

| Pro | Con |
| :--- | :--- |
| Eliminates flag fatigue. | Slightly slower for power users (keep flags as fallback). |
| Reduces database/journal corruption from typos. | |

---

## 4. Recommendation: Visual Hierarchy (Rich Display)

Upgrade the visual output using a library like `Rich` to separate **Primary Signals** from **Contextual Data**.

### UI/UX Refinements
- **Panels:** Group information into boxes (e.g., `[ACCUMULATION]`, `[RISK]`, `[PLAN]`).
- **Color Coding:** Use a consistent color palette:
    - **Green:** ★ PRIME / ENTER / BULLISH
    - **Yellow:** ◉ WATCH / SIDEWAYS
    - **Red:** ✗ SKIP / AVOID / BEARISH
- **Visual Weights:** Make the `PLAN` section (Entry/Stop/Target) the most prominent part of the output.

| Pro | Con |
| :--- | :--- |
| Dramatically improves scannability. | Adds `rich` as a dependency. |
| Professional, "terminal-app" feel. | |

---

## 5. Recommendation: Phase-Based Help Grouping

Reorganize the `saham --help` output to guide the user through the trading lifecycle.

### Proposed Categories
- **`[PREPARATION]`**: `data`, `indicator`
- **`[TRADING]`**: `trade`, `analyze`, `daily`
- **`[STRATEGY]`**: `strategy`, `skill`

---

## Implementation Roadmap

1.  **Phase 1 (Visual):** Integrate `Rich` for existing `swing analyze` and `pre-open` outputs to improve immediate readability.
2.  **Phase 2 (Orchestration):** Implement the `saham daily` command to consolidate the morning workflow.
3.  **Phase 3 (Interactive):** Add interactive prompts to the `log` and `outcome` command family.
4.  **Phase 4 (Organization):** Finalize the phase-based help grouping in `main.py`.
