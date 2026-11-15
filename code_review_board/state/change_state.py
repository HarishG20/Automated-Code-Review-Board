"""
state/change_state.py
=====================
Shared data model for the Code Review Board pipeline.

Every agent reads from and writes to a single ChangeState instance that is
passed through the whole pipeline.  Pydantic is used so that every field is
validated automatically and the whole state can be serialised to JSON for
logging.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    """Severity levels for review findings, ordered from worst to best."""
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"


class Decision(str, Enum):
    """Possible review decisions produced by the Reviewer Manager."""
    APPROVE          = "APPROVE"
    REQUEST_CHANGES  = "REQUEST_CHANGES"
    CANNOT_REVIEW    = "CANNOT_REVIEW"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class DiffFile(BaseModel):
    """Represents one file touched by the diff."""
    filename: str                   # e.g. "src/utils.py"
    added_lines: List[str]          # raw text of '+' lines (without leading '+')
    removed_lines: List[str]        # raw text of '-' lines (without leading '-')
    hunks: List[str]                # raw hunk headers, e.g. "@@ -1,4 +1,6 @@"


class Finding(BaseModel):
    """
    A single review finding produced by any agent.

    Every finding gets a unique UUID so the manager can deduplicate them
    even when two agents flag the same problem independently.
    """
    id: str           = Field(default_factory=lambda: str(uuid.uuid4()))
    agent: str        # name of the agent that raised this finding
    file: str         # filename the finding refers to
    line: int         # 1-based line number inside the added lines (0 = unknown)
    rule: str         # short rule code, e.g. "SECRET_API_KEY"
    message: str      # human-readable description
    severity: Severity


# ---------------------------------------------------------------------------
# Main shared state
# ---------------------------------------------------------------------------

class ChangeState(BaseModel):
    """
    The single shared object that flows through the entire pipeline.

    The Diff Agent populates it first; then the Style, Security, and
    Test-Coverage agents append their findings in parallel; finally the
    Reviewer Manager reads it to produce the decision.
    """
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # --- Input ---
    diff_raw: str = ""              # the raw unified diff text submitted for review

    # --- Diff Agent output ---
    parsed_files: List[DiffFile] = Field(default_factory=list)
    diff_summary: str = ""          # human-readable one-liner from summarize_change

    # --- Findings collected by all agents ---
    findings: List[Finding] = Field(default_factory=list)

    # --- Reviewer Manager output ---
    decision: Optional[str] = None          # "APPROVE" / "REQUEST_CHANGES" / "CANNOT_REVIEW"
    decision_reason: str = ""               # explanation of the decision

    # --- Error flag ---
    error: Optional[str] = None             # set by Diff Agent on empty / malformed diff

    # --- Per-agent error tracking (fan-out resilience) ---
    agent_errors: dict = Field(default_factory=dict)
    # e.g. {"StyleAgent": "timeout", "SecurityAgent": None}

    class Config:
        # allow mutation after construction
        validate_assignment = True
