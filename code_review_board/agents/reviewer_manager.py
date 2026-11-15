"""
agents/reviewer_manager.py
==========================
Reviewer Manager — Fan-In Aggregator.

Responsibilities
----------------
1. `dedupe_findings`  — merge duplicate (file, line, rule) findings.
2. `rank_by_severity` — sort HIGH → MEDIUM → LOW.
3. Apply the decision rule and write `state.decision` + `state.decision_reason`.

Decision rule
-------------
  state.error present        → CANNOT_REVIEW
  any HIGH finding           → REQUEST_CHANGES
  ≥ 2 MEDIUM findings        → REQUEST_CHANGES
  otherwise                  → APPROVE

Also notes which fan-out agents (if any) failed.
"""

from __future__ import annotations

from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.functions import kernel_function

from code_review_board.agents.kernel_factory import build_kernel
from code_review_board.agents.logger import log_action
from code_review_board.state.change_state import ChangeState, Decision, Finding, Severity
from code_review_board.tools.manager_tools import dedupe_findings, rank_by_severity

AGENT_NAME = "ReviewerManager"


class ManagerPlugin:
    """Semantic Kernel plugin that wraps the manager tools."""

    @kernel_function(
        name="dedupe_findings",
        description="Remove duplicate findings on the same file, line, and rule.",
    )
    def dedupe_findings_fn(self) -> str:
        return "dedupe_findings registered"

    @kernel_function(
        name="rank_by_severity",
        description="Sort findings HIGH → MEDIUM → LOW.",
    )
    def rank_by_severity_fn(self) -> str:
        return "rank_by_severity registered"


def _make_decision(findings: list[Finding], state: ChangeState) -> tuple[str, str]:
    """
    Apply the decision rule and return (decision, reason).

    Args:
        findings: Deduplicated, ranked findings.
        state:    Shared state (checked for .error and .agent_errors).

    Returns:
        (decision_string, reason_string)
    """
    # Rule 0: pipeline error
    if state.error:
        reason = f"Pipeline error: {state.error}"
        return Decision.CANNOT_REVIEW, reason

    high_findings   = [f for f in findings if f.severity == Severity.HIGH]
    medium_findings = [f for f in findings if f.severity == Severity.MEDIUM]

    # Rule 1: any HIGH → REQUEST_CHANGES
    if high_findings:
        rules = ", ".join(f.rule for f in high_findings[:3])
        reason = (
            f"Found {len(high_findings)} HIGH-severity finding(s): {rules}. "
            "HIGH findings always require changes."
        )
        return Decision.REQUEST_CHANGES, reason

    # Rule 2: ≥ 2 MEDIUM → REQUEST_CHANGES
    if len(medium_findings) >= 2:
        rules = ", ".join(f.rule for f in medium_findings[:3])
        reason = (
            f"Found {len(medium_findings)} MEDIUM-severity finding(s): {rules}. "
            "Two or more MEDIUM findings require changes."
        )
        return Decision.REQUEST_CHANGES, reason

    # Rule 3: APPROVE
    total = len(findings)
    if total == 0:
        reason = "No findings. The change looks clean."
    elif len(medium_findings) == 1:
        reason = (
            f"Only 1 MEDIUM finding and no HIGH findings ({medium_findings[0].rule}). "
            "Approved with a minor note."
        )
    else:
        reason = (
            f"{total} LOW finding(s) only. "
            "No blocking issues detected."
        )
    return Decision.APPROVE, reason


async def run(state: ChangeState) -> ChangeState:
    """
    Execute the Reviewer Manager.

    Reads all findings from `state.findings`, deduplicates and ranks them,
    applies the decision rule, and writes `state.decision` and
    `state.decision_reason`.

    Args:
        state: Shared pipeline state.

    Returns:
        The same (mutated) state object.
    """
    kernel = build_kernel()
    kernel.add_plugin(ManagerPlugin(), plugin_name="ManagerPlugin")

    _agent = ChatCompletionAgent(  # noqa: F841
        kernel=kernel,
        name=AGENT_NAME,
        instructions=(
            "You are the Reviewer Manager. Deduplicate and rank findings from all "
            "agents, then apply the decision rule to produce a final verdict."
        ),
    )

    # --- Tool 1: dedupe_findings ---
    deduped = dedupe_findings(state.findings)
    log_action(
        agent=AGENT_NAME,
        tool="dedupe_findings",
        input_summary=f"{len(state.findings)} finding(s) total",
        output_summary=f"{len(deduped)} after dedup",
        run_id=state.run_id,
    )

    # --- Tool 2: rank_by_severity ---
    ranked = rank_by_severity(deduped)
    state.findings = ranked  # replace findings with deduplicated, ranked list
    log_action(
        agent=AGENT_NAME,
        tool="rank_by_severity",
        input_summary=f"{len(deduped)} finding(s)",
        output_summary=(
            f"Ranked: "
            f"{sum(1 for f in ranked if f.severity==Severity.HIGH)} HIGH, "
            f"{sum(1 for f in ranked if f.severity==Severity.MEDIUM)} MEDIUM, "
            f"{sum(1 for f in ranked if f.severity==Severity.LOW)} LOW"
        ),
        run_id=state.run_id,
    )

    # --- Decision ---
    decision, reason = _make_decision(ranked, state)

    # Note if any fan-out agents failed
    if state.agent_errors:
        failed = ", ".join(
            f"{k} ({v})" for k, v in state.agent_errors.items()
        )
        reason += f"  [NOTE: Some agents had errors — results may be incomplete: {failed}]"

    state.decision        = decision
    state.decision_reason = reason

    log_action(
        agent=AGENT_NAME,
        tool="decision",
        input_summary=f"{len(ranked)} ranked finding(s)",
        output_summary=f"decision={decision}, reason={reason[:80]}",
        run_id=state.run_id,
    )

    return state
