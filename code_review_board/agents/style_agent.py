"""
agents/style_agent.py
=====================
Style Agent — Fan-Out Worker #1.

Responsibilities
----------------
1. `check_line_length_and_naming` — flag lines > 100 chars and non-snake_case
   function names (MEDIUM severity).
2. `check_docstrings_with_ast` — flag functions without docstrings (LOW severity).

Runs in parallel with SecurityAgent and TestCoverageAgent via asyncio.gather.
Appends Finding objects to `state.findings`.
"""

from __future__ import annotations

import json

from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.functions import kernel_function

from code_review_board.agents.kernel_factory import build_kernel
from code_review_board.agents.logger import log_action
from code_review_board.state.change_state import ChangeState, Finding, Severity
from code_review_board.tools.style_tools import (
    check_docstrings_with_ast,
    check_line_length_and_naming,
)

AGENT_NAME = "StyleAgent"


class StylePlugin:
    """Semantic Kernel plugin that wraps the style tools."""

    @kernel_function(
        name="check_line_length_and_naming",
        description="Check for long lines and non-snake_case function names.",
    )
    def check_line_length_and_naming_fn(self, diff_text: str) -> str:
        result = check_line_length_and_naming(diff_text)
        return json.dumps(result)

    @kernel_function(
        name="check_docstrings_with_ast",
        description="Check for missing docstrings using the AST.",
    )
    def check_docstrings_with_ast_fn(self, diff_text: str) -> str:
        result = check_docstrings_with_ast(diff_text)
        return json.dumps(result)


async def run(state: ChangeState) -> ChangeState:
    """
    Execute the Style Agent.

    Appends any style findings to `state.findings`.
    If an unexpected error occurs it is recorded in `state.agent_errors`.

    Args:
        state: Shared pipeline state.

    Returns:
        The same (mutated) state object.
    """
    try:
        kernel = build_kernel()
        kernel.add_plugin(StylePlugin(), plugin_name="StylePlugin")

        _agent = ChatCompletionAgent(  # noqa: F841
            kernel=kernel,
            name=AGENT_NAME,
            instructions=(
                "You are the Style Agent. Check the diff for style issues: "
                "line length, naming conventions, and missing docstrings."
            ),
        )

        # --- Tool 1: check_line_length_and_naming ---
        raw_findings = check_line_length_and_naming(state.diff_raw)
        log_action(
            agent=AGENT_NAME,
            tool="check_line_length_and_naming",
            input_summary=f"diff length={len(state.diff_raw)} chars",
            output_summary=f"{len(raw_findings)} finding(s)",
            run_id=state.run_id,
        )

        # --- Tool 2: check_docstrings_with_ast ---
        doc_findings = check_docstrings_with_ast(state.diff_raw)
        log_action(
            agent=AGENT_NAME,
            tool="check_docstrings_with_ast",
            input_summary=f"diff length={len(state.diff_raw)} chars",
            output_summary=f"{len(doc_findings)} finding(s)",
            run_id=state.run_id,
        )

        # Convert raw dicts → Finding objects and append to shared state
        for raw in raw_findings + doc_findings:
            state.findings.append(
                Finding(
                    agent=AGENT_NAME,
                    file=raw["file"],
                    line=raw["line"],
                    rule=raw["rule"],
                    message=raw["message"],
                    severity=Severity(raw["severity"]),
                )
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
