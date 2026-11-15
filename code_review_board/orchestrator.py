"""
orchestrator.py
===============
Main pipeline entry point for the Automated Code Review Board.

Architecture: FAN-OUT / FAN-IN
-------------------------------
                    ┌─────────────┐
                    │  Diff Agent │  ← GATE: parse & validate diff
                    └──────┬──────┘
                           │  (error → manager decides CANNOT_REVIEW)
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   ┌────────────┐  ┌──────────────┐  ┌──────────────────┐
   │ Style Agent│  │Security Agent│  │Test-Coverage Agent│   FAN-OUT (parallel)
   └────────────┘  └──────────────┘  └──────────────────┘
          │                │                │
          └────────────────┼────────────────┘
                           ▼
                  ┌─────────────────┐
                  │ Reviewer Manager│  ← FAN-IN: dedupe, rank, decide
                  └────────┬────────┘
                           │
                  ┌────────▼────────┐
                  │ Fix-Suggestion  │  ← BONUS: patch for top finding
                  │     Agent       │
                  └─────────────────┘

Usage
-----
    import asyncio
    from code_review_board.orchestrator import run_pipeline

    state = asyncio.run(run_pipeline(diff_text="...", repo_root="."))
    print(state.decision)
"""

from __future__ import annotations

import asyncio
import os

from code_review_board.agents import (
    diff_agent,
    fix_suggestion_agent,
    reviewer_manager,
    security_agent,
    style_agent,
    test_coverage_agent,
)
from code_review_board.state.change_state import ChangeState


async def run_pipeline(
    diff_text: str,
    repo_root: str = ".",
    include_fix_suggestion: bool = True,
) -> ChangeState:
    """
    Run the full multi-agent code review pipeline.

    Steps:
        1. Create a fresh ChangeState.
        2. Run the Diff Agent (gate).
        3. If the diff is invalid, skip to the manager (CANNOT_REVIEW).
        4. Fan-out: run Style, Security, and TestCoverage agents in parallel.
        5. Fan-in: run the Reviewer Manager.
        6. (Optional) Run the Fix-Suggestion Agent.

    Args:
        diff_text:             Raw unified diff text to review.
        repo_root:             Path to the repository root (used to locate test files).
        include_fix_suggestion: Whether to run the bonus Fix-Suggestion Agent.

    Returns:
        The completed ChangeState with all findings and the final decision.
    """
    # Respect LLM_MODE from environment (default: offline for safety)
    if "LLM_MODE" not in os.environ:
        os.environ["LLM_MODE"] = "offline"

    # --- Step 1: Initialise shared state ---
    state = ChangeState(diff_raw=diff_text)

    # --- Step 2: Diff Agent (gate) ---
    state = await diff_agent.run(state)

    # --- Step 3: If diff is invalid, go straight to manager ---
    if state.error:
        state = await reviewer_manager.run(state)
        return state

    # --- Step 4: FAN-OUT (parallel) ---
    # asyncio.gather runs all three coroutines concurrently.
    # Each agent catches its own exceptions and records them in state.agent_errors,
    # so a single agent crash does not abort the whole pipeline.
    await asyncio.gather(
        style_agent.run(state),
        security_agent.run(state),
        test_coverage_agent.run(state, repo_root=repo_root),
    )

    # --- Step 5: FAN-IN (Reviewer Manager) ---
    state = await reviewer_manager.run(state)

    # --- Step 6: Fix-Suggestion Agent (bonus) ---
    if include_fix_suggestion:
        state = await fix_suggestion_agent.run(state)

    return state
