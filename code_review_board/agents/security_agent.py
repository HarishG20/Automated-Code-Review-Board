"""
agents/security_agent.py
========================
Security Agent — Fan-Out Worker #2.

Responsibilities
----------------
1. `scan_for_secrets` — detect hardcoded API keys, passwords, tokens (HIGH).
2. `find_unsafe_calls` — detect eval/exec/pickle/subprocess-shell (HIGH/MEDIUM).

Runs in parallel with StyleAgent and TestCoverageAgent via asyncio.gather.
Appends Finding objects to `state.findings`.
"""

from __future__ import annotations

import json

from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.functions import kernel_function

from code_review_board.agents.kernel_factory import build_kernel
from code_review_board.agents.logger import log_action
from code_review_board.state.change_state import ChangeState, Finding, Severity
from code_review_board.tools.security_tools import find_unsafe_calls, scan_for_secrets

AGENT_NAME = "SecurityAgent"


class SecurityPlugin:
    """Semantic Kernel plugin that wraps the security tools."""

    @kernel_function(
        name="scan_for_secrets",
        description="Scan added lines for hardcoded secrets.",
    )
    def scan_for_secrets_fn(self, diff_text: str) -> str:
        result = scan_for_secrets(diff_text)
        return json.dumps(result)

    @kernel_function(
        name="find_unsafe_calls",
        description="Find unsafe function calls (eval, exec, pickle, shell=True).",
    )
    def find_unsafe_calls_fn(self, diff_text: str) -> str:
        result = find_unsafe_calls(diff_text)
        return json.dumps(result)


async def run(state: ChangeState) -> ChangeState:
    """
    Execute the Security Agent.

    Appends any security findings to `state.findings`.
    If an unexpected error occurs it is recorded in `state.agent_errors`.

    Args:
        state: Shared pipeline state.

    Returns:
        The same (mutated) state object.
    """
    try:
        kernel = build_kernel()
        kernel.add_plugin(SecurityPlugin(), plugin_name="SecurityPlugin")

        _agent = ChatCompletionAgent(  # noqa: F841
            kernel=kernel,
            name=AGENT_NAME,
            instructions=(
                "You are the Security Agent. Scan the diff for hardcoded secrets "
                "and unsafe function calls. All secrets must be reported as HIGH severity."
            ),
        )

        # --- Tool 1: scan_for_secrets ---
        secret_findings = scan_for_secrets(state.diff_raw)
        log_action(
            agent=AGENT_NAME,
            tool="scan_for_secrets",
            input_summary=f"diff length={len(state.diff_raw)} chars",
            output_summary=f"{len(secret_findings)} finding(s)",
            run_id=state.run_id,
        )

        # --- Tool 2: find_unsafe_calls ---
        unsafe_findings = find_unsafe_calls(state.diff_raw)
        log_action(
            agent=AGENT_NAME,
            tool="find_unsafe_calls",
            input_summary=f"diff length={len(state.diff_raw)} chars",
            output_summary=f"{len(unsafe_findings)} finding(s)",
            run_id=state.run_id,
        )

        for raw in secret_findings + unsafe_findings:
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
