"""
tools/manager_tools.py
======================
Deterministic tools used by the Reviewer Manager agent.

These tools deduplicate and rank the findings collected from all fan-out
agents before the manager produces its final decision.
"""

from __future__ import annotations

from typing import List

from code_review_board.state.change_state import Finding, Severity


# Severity ordering for ranking: lower index = higher priority
_SEVERITY_ORDER = {
    Severity.HIGH:   0,
    Severity.MEDIUM: 1,
    Severity.LOW:    2,
}


# ---------------------------------------------------------------------------
# dedupe_findings
# ---------------------------------------------------------------------------

def dedupe_findings(findings: List[Finding]) -> List[Finding]:
    """
    Remove duplicate findings that share the same (file, line, rule) triple.

    When duplicates exist, the copy with the highest severity is kept.
    Within ties the first occurrence is kept.

    Args:
        findings: Flat list of Finding objects from all agents.

    Returns:
        Deduplicated list of Finding objects.
    """
    seen: dict[tuple[str, int, str], Finding] = {}

    for finding in findings:
        key = (finding.file, finding.line, finding.rule)

        if key not in seen:
            seen[key] = finding
        else:
            existing = seen[key]
            # Keep the one with higher severity
            if _SEVERITY_ORDER[finding.severity] < _SEVERITY_ORDER[existing.severity]:
                seen[key] = finding

    return list(seen.values())


# ---------------------------------------------------------------------------
# rank_by_severity
# ---------------------------------------------------------------------------

def rank_by_severity(findings: List[Finding]) -> List[Finding]:
    """
    Sort findings from most severe to least severe.

    Within the same severity level the findings are sorted by file name and
    then by line number so the output is stable and easy to read.

    Args:
        findings: List of Finding objects (may contain duplicates or not).

    Returns:
        A new list sorted HIGH → MEDIUM → LOW.
    """
    return sorted(
        findings,
        key=lambda f: (
            _SEVERITY_ORDER[f.severity],
            f.file,
            f.line,
        ),
    )
