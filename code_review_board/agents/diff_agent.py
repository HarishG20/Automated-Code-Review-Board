"""
agents/diff_agent.py
====================
Diff Agent — GATE of the pipeline.

Responsibilities
----------------
1. Parse the raw unified diff with `parse_diff`.
2. Produce a one-line summary with `summarize_change`.
3. If the diff is empty or malformed, set `state.error` and return immediately.
   The pipeline will NOT fan-out to the other agents.

This agent is registered as a Semantic Kernel ChatCompletionAgent whose kernel
has two kernel functions (parse_diff, summarize_change).  In offline mode the
LLM layer is a no-op stub — all real work is done by the tool functions.
"""

from __future__ import annotations

import json
import os

from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.functions import kernel_function

from code_review_board.agents.kernel_factory import build_kernel
from code_review_board.agents.logger import log_action
from code_review_board.state.change_state import ChangeState, DiffFile
from code_review_board.tools.diff_tools import parse_diff, summarize_change

AGENT_NAME = "DiffAgent"

# ---------------------------------------------------------------------------
# Kernel-function wrappers
# (Semantic Kernel discovers tools via the @kernel_function decorator)
# ---------------------------------------------------------------------------

class DiffPlugin:
    """Semantic Kernel plugin that wraps the diff tools."""

    @kernel_function(name="parse_diff", description="Parse a unified diff into file blocks.")
    def parse_diff_fn(self, diff_text: str) -> str:
        """Wrapper so SK can call parse_diff as a kernel function."""
        result = parse_diff(diff_text)
        return json.dumps(result)

    @kernel_function(name="summarize_change", description="Summarise the parsed diff.")
    def summarize_change_fn(self, parsed_files_json: str) -> str:
        """Wrapper so SK can call summarize_change as a kernel function."""
        parsed = json.loads(parsed_files_json)
        return summarize_change(parsed)


# ---------------------------------------------------------------------------
# Public run function
# ---------------------------------------------------------------------------

async def run(state: ChangeState) -> ChangeState:
    """
    Execute the Diff Agent on the given state.

    Mutates `state` in place:
      - On success: populates `state.parsed_files` and `state.diff_summary`.
      - On empty/malformed diff: sets `state.error`.

    Args:
        state: Shared pipeline state.

    Returns:
        The same (mutated) state object.
    """
    # Build the kernel and agent (construction is cheap)
    kernel = build_kernel()
    kernel.add_plugin(DiffPlugin(), plugin_name="DiffPlugin")

    _agent = ChatCompletionAgent(  # noqa: F841  (kept for SK architecture)
        kernel=kernel,
        name=AGENT_NAME,
        instructions=(
            "You are the Diff Agent. Your job is to parse the submitted code diff "
            "and populate the shared state with the list of changed files. "
            "If the diff is empty or malformed, signal an error immediately."
        ),
    )

    # --- Tool 1: parse_diff ---
    try:
        parsed = parse_diff(state.diff_raw)
    except ValueError as exc:
        state.error = f"Malformed diff: {exc}"
        log_action(
            agent=AGENT_NAME,
            tool="parse_diff",
            input_summary=f"diff length={len(state.diff_raw)}",
            output_summary=f"ERROR: {exc}",
            run_id=state.run_id,
        )
        return state

    if not parsed:
        state.error = "Empty diff — nothing to review."
        log_action(
            agent=AGENT_NAME,
            tool="parse_diff",
            input_summary="diff length=0",
            output_summary="ERROR: empty diff",
            run_id=state.run_id,
        )
        return state

    log_action(
        agent=AGENT_NAME,
        tool="parse_diff",
        input_summary=f"diff length={len(state.diff_raw)} chars",
        output_summary=f"{len(parsed)} file(s) parsed",
        run_id=state.run_id,
    )

    # Populate state with DiffFile objects
    state.parsed_files = [
        DiffFile(
            filename=f["file"],
            added_lines=f["added_lines"],
            removed_lines=f["removed_lines"],
            hunks=f["hunks"],
        )
        for f in parsed
    ]

    # --- Tool 2: summarize_change ---
    summary = summarize_change(parsed)
    state.diff_summary = summary

    log_action(
        agent=AGENT_NAME,
        tool="summarize_change",
        input_summary=f"{len(parsed)} file(s)",
        output_summary=summary,
        run_id=state.run_id,
    )

    return state
