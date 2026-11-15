"""
agents/fix_suggestion_agent.py
==============================
Fix-Suggestion Agent — Bonus Agent.

Responsibilities
----------------
1. `get_top_finding` — retrieve the single highest-severity finding.
2. `generate_patch`  — produce a concrete code snippet that fixes it.

This agent runs AFTER the Reviewer Manager and only when there are findings.
It writes `state.fix_suggestion` (a plain dict) for display in the demo.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.functions import kernel_function

from code_review_board.agents.kernel_factory import build_kernel
from code_review_board.agents.logger import log_action
from code_review_board.state.change_state import ChangeState
from code_review_board.tools.fix_suggestion_tools import generate_patch, get_top_finding

AGENT_NAME = "FixSuggestionAgent"


class FixPlugin:
    """Semantic Kernel plugin that wraps the fix-suggestion tools."""

    @kernel_function(
        name="get_top_finding",
        description="Return the highest-severity finding.",
    )
    def get_top_finding_fn(self) -> str:
        return "get_top_finding registered"

    @kernel_function(
        name="generate_patch",
        description="Generate a fix patch for a finding.",
    )
    def generate_patch_fn(self) -> str:
        return "generate_patch registered"


async def run(state: ChangeState) -> ChangeState:
    """
    Execute the Fix-Suggestion Agent.

    Adds `state.fix_suggestion` dict (or None if no findings).

    Args:
        state: Shared pipeline state (findings must already be ranked).

    Returns:
        The same (mutated) state object.
    """
    # Attach fix_suggestion as a plain attribute (not in Pydantic model to
    # keep ChangeState simple; demo reads it directly)
    state.__dict__.setdefault("fix_suggestion", None)

    if not state.findings:
        log_action(
            agent=AGENT_NAME,
            tool="get_top_finding",
            input_summary="0 findings",
            output_summary="no findings — skipped",
            run_id=state.run_id,
        )
        return state

    try:
        kernel = build_kernel()
        kernel.add_plugin(FixPlugin(), plugin_name="FixPlugin")

        _agent = ChatCompletionAgent(  # noqa: F841
            kernel=kernel,
            name=AGENT_NAME,
            instructions=(
                "You are the Fix-Suggestion Agent. Identify the worst finding and "
                "propose a concrete code fix for it."
            ),
        )

        # --- Tool 1: get_top_finding ---
        top = get_top_finding(state.findings)
        log_action(
            agent=AGENT_NAME,
            tool="get_top_finding",
            input_summary=f"{len(state.findings)} finding(s)",
            output_summary=f"top={top.rule if top else 'None'}",
            run_id=state.run_id,
        )

        if top is None:
            return state

        # --- Tool 2: generate_patch ---
        patch = generate_patch(top)
        state.__dict__["fix_suggestion"] = patch
        log_action(
            agent=AGENT_NAME,
            tool="generate_patch",
            input_summary=f"finding rule={top.rule}",
            output_summary=f"patch generated ({len(patch['patch_text'])} chars)",
            run_id=state.run_id,
        )

    except Exception as exc:  # noqa: BLE001
        state.agent_errors[AGENT_NAME] = str(exc)
        log_action(
            agent=AGENT_NAME,
            tool="<exception>",
            input_summary="",
            output_summary=f"AGENT ERROR: {exc}",
            run_id=state.run_id,
        )

    return state
