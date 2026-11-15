"""
tests/test_scenarios.py
=======================
Pytest test suite for the Code Review Board.

All tests run in OFFLINE mode (no API key required).
Scenarios:
  1. clean.diff        → APPROVE
  2. secret.diff       → REQUEST_CHANGES (HIGH finding ranked first)
  3. untested.diff     → REQUEST_CHANGES (MEDIUM finding from missing test file)
  4. empty diff        → CANNOT_REVIEW
  5. malformed diff    → CANNOT_REVIEW

Run with:
    pytest code_review_board/tests/test_scenarios.py -v
"""

from __future__ import annotations

import os
import asyncio
from pathlib import Path

import pytest

# Force offline mode for all tests
os.environ["LLM_MODE"] = "offline"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
# Repo root for test-file discovery: the code_review_board directory
REPO_ROOT = str(Path(__file__).resolve().parent.parent)


def _load_sample(name: str) -> str:
    return (SAMPLES_DIR / name).read_text(encoding="utf-8")


def _run(diff_text: str, repo_root: str = REPO_ROOT):
    """Synchronous wrapper around the async pipeline."""
    from code_review_board.orchestrator import run_pipeline
    return asyncio.run(run_pipeline(diff_text, repo_root=repo_root))


# ---------------------------------------------------------------------------
# Scenario 1: Clean diff → APPROVE
# ---------------------------------------------------------------------------

class TestCleanDiff:
    """
    A well-styled, documented change that includes a companion test file.
    Expected decision: APPROVE.
    """

    def test_decision_is_approve(self):
        diff = _load_sample("clean.diff")
        state = _run(diff)
        assert state.decision == "APPROVE", (
            f"Expected APPROVE but got {state.decision}. "
            f"Findings: {[f.rule for f in state.findings]}"
        )

    def test_no_high_findings(self):
        diff = _load_sample("clean.diff")
        state = _run(diff)
        high = [f for f in state.findings if f.severity == "HIGH"]
        assert high == [], f"Unexpected HIGH findings: {high}"

    def test_no_error(self):
        diff = _load_sample("clean.diff")
        state = _run(diff)
        assert state.error is None


# ---------------------------------------------------------------------------
# Scenario 2: Secret diff → REQUEST_CHANGES, secret ranked first
# ---------------------------------------------------------------------------

class TestSecretDiff:
    """
    A diff with a hardcoded API key and eval() call.
    Expected decision: REQUEST_CHANGES with at least one HIGH finding.
    """

    def test_decision_is_request_changes(self):
        diff = _load_sample("secret.diff")
        state = _run(diff)
        assert state.decision == "REQUEST_CHANGES", (
            f"Expected REQUEST_CHANGES but got {state.decision}"
        )

    def test_has_high_severity_finding(self):
        diff = _load_sample("secret.diff")
        state = _run(diff)
        high = [f for f in state.findings if f.severity == "HIGH"]
        assert len(high) >= 1, "Expected at least one HIGH finding"

    def test_secret_ranked_first(self):
        diff = _load_sample("secret.diff")
        state = _run(diff)
        # After ranking, the first finding must be HIGH
        assert state.findings, "No findings at all — unexpected"
        assert state.findings[0].severity == "HIGH", (
            f"Expected first finding to be HIGH, got {state.findings[0].severity}"
        )

    def test_secret_rule_present(self):
        diff = _load_sample("secret.diff")
        state = _run(diff)
        rules = [f.rule for f in state.findings]
        secret_rules = {r for r in rules if r.startswith("SECRET_")}
        assert secret_rules, f"No SECRET_ rule found. Rules: {rules}"


# ---------------------------------------------------------------------------
# Scenario 3: Untested change → REQUEST_CHANGES (MEDIUM)
# ---------------------------------------------------------------------------

class TestUntestedDiff:
    """
    A diff adding new functions with no accompanying test file.
    Expected decision: REQUEST_CHANGES (MEDIUM finding for missing test file).
    """

    def test_decision_is_request_changes(self):
        diff = _load_sample("untested.diff")
        state = _run(diff)
        assert state.decision == "REQUEST_CHANGES", (
            f"Expected REQUEST_CHANGES but got {state.decision}. "
            f"Findings: {[(f.rule, f.severity) for f in state.findings]}"
        )

    def test_has_blocking_finding(self):
        """Missing test file is HIGH; there should be at least one HIGH finding."""
        diff = _load_sample("untested.diff")
        state = _run(diff)
        blocking = [f for f in state.findings if f.severity in ("HIGH", "MEDIUM")]
        assert blocking, "Expected at least one HIGH or MEDIUM finding"

    def test_missing_test_file_rule_present(self):
        diff = _load_sample("untested.diff")
        state = _run(diff)
        rules = [f.rule for f in state.findings]
        assert "MISSING_TEST_FILE" in rules or "UNTESTED_FUNCTION" in rules, (
            f"Expected MISSING_TEST_FILE or UNTESTED_FUNCTION. Got: {rules}"
        )


# ---------------------------------------------------------------------------
# Scenario 4: Empty diff → CANNOT_REVIEW
# ---------------------------------------------------------------------------

class TestEmptyDiff:
    """
    An empty string submitted as a diff.
    Expected decision: CANNOT_REVIEW.
    """

    def test_decision_is_cannot_review(self):
        state = _run("")
        assert state.decision == "CANNOT_REVIEW", (
            f"Expected CANNOT_REVIEW but got {state.decision}"
        )

    def test_error_is_set(self):
        state = _run("")
        assert state.error is not None, "state.error should be set for empty diff"

    def test_no_findings(self):
        state = _run("")
        assert state.findings == [], "No findings expected for empty diff"


# ---------------------------------------------------------------------------
# Scenario 5: Malformed diff → CANNOT_REVIEW
# ---------------------------------------------------------------------------

class TestMalformedDiff:
    """
    A non-diff string submitted (no +++ header).
    Expected decision: CANNOT_REVIEW.
    """

    def test_decision_is_cannot_review(self):
        state = _run("this is not a diff at all, just random text")
        assert state.decision == "CANNOT_REVIEW", (
            f"Expected CANNOT_REVIEW but got {state.decision}"
        )

    def test_error_message_informative(self):
        state = _run("this is not a diff at all, just random text")
        assert state.error is not None
        assert len(state.error) > 5  # non-trivial error message
