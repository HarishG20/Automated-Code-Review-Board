"""
agents/test_coverage_agent.py
=============================
Test-Coverage Agent — Fan-Out Worker #3.

Responsibilities
----------------
1. `find_matching_test_files` — check if test files exist for changed source
   files (MEDIUM severity when missing).
2. `count_new_functions_vs_tests` — flag new functions not covered by test
   functions in the same diff (LOW severity).

Runs in parallel with StyleAgent and SecurityAgent via asyncio.gather.
Appends Finding objects to `state.findings`.
"""

from __future__ import annotations

import json
import os

from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.functions import kernel_function

from code_review_board.agents.kernel_factory import build_kernel
from code_review_board.agents.logger import log_action
from code_review_board.state.change_state import ChangeState, Finding, Severity
from code_review_board.tools.test_coverage_tools import (
    count_new_functions_vs_tests,
    find_matching_test_files,
)

AGENT_NAME = "TestCoverageAgent"


class TestCoveragePlugin:
    """Semantic Kernel plugin that wraps the test-coverage tools."""

    @kernel_function(
        name="find_matching_test_files",
        description="Check if test files exist for each changed source file.",
    )
    def find_matching_test_files_fn(
        self, parsed_files_json: str, repo_root: str = "."
    ) -> str:
        parsed = json.loads(parsed_files_json)
        result = find_matching_test_files(parsed, repo_root)
        return json.dumps(result)

    @kernel_function(
        name="count_new_functions_vs_tests",
        description="Count new functions vs new test functions in the diff.",
    )
    def count_new_functions_vs_tests_fn(self, diff_text: str) -> str:
        result = count_new_functions_vs_tests(diff_text)
        return json.dumps(result)


async def run(state: ChangeState, repo_root: str = ".") -> ChangeState:
    """
    Execute the Test-Coverage Agent.

    Appends any coverage findings to `state.findings`.
    If an unexpected error occurs it is recorded in `state.agent_errors`.

    Args:
        state:     Shared pipeline state.
        repo_root: Path to the repository root (for locating test files).

    Returns:
        The same (mutated) state object.
    """
    try:
        kernel = build_kernel()
        kernel.add_plugin(TestCoveragePlugin(), plugin_name="TestCoveragePlugin")

        _agent = ChatCompletionAgent(  # noqa: F841
            kernel=kernel,
            name=AGENT_NAME,
            instructions=(
                "You are the Test-Coverage Agent. Check whether test files exist "
                "for all changed source files and whether new functions have tests."
            ),
        )

        # Serialise parsed_files for the tool (it expects a plain list of dicts)
        parsed_dicts = [
            {
                "file":          f.filename,
                "added_lines":   f.added_lines,
                "removed_lines": f.removed_lines,
                "hunks":         f.hunks,
            }
            for f in state.parsed_files
        ]

        # --- Tool 1: find_matching_test_files ---
        missing_tests = find_matching_test_files(parsed_dicts, repo_root)
        log_action(
            agent=AGENT_NAME,
            tool="find_matching_test_files",
            input_summary=f"{len(parsed_dicts)} file(s), repo_root={repo_root}",
            output_summary=f"{len(missing_tests)} finding(s)",
            run_id=state.run_id,
        )

        # --- Tool 2: count_new_functions_vs_tests ---
        func_findings = count_new_functions_vs_tests(state.diff_raw)
        log_action(
            agent=AGENT_NAME,
            tool="count_new_functions_vs_tests",
            input_summary=f"diff length={len(state.diff_raw)} chars",
            output_summary=f"{len(func_findings)} finding(s)",
            run_id=state.run_id,
        )

        for raw in missing_tests + func_findings:
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
