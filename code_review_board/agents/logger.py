"""
agents/logger.py
================
Append-only JSONL run logger shared by every agent.

Usage:
    from code_review_board.agents.logger import log_action

    log_action(
        agent="StyleAgent",
        tool="check_line_length_and_naming",
        input_summary="diff for utils.py",
        output_summary="2 findings",
    )

The log file path defaults to  <package_root>/logs/run_log.jsonl  and can
be overridden with the LOG_PATH environment variable.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Resolve log path
# ---------------------------------------------------------------------------

_DEFAULT_LOG = Path(__file__).resolve().parent.parent / "logs" / "run_log.jsonl"
LOG_PATH = Path(os.environ.get("LOG_PATH", str(_DEFAULT_LOG)))


def log_action(
    agent: str,
    tool: str,
    input_summary: str,
    output_summary: str,
    run_id: str = "",
) -> None:
    """
    Append a single JSON line to the run log.

    The file is opened in append mode every call so it is never truncated.

    Args:
        agent:          Name of the calling agent.
        tool:           Name of the tool that was called.
        input_summary:  Short description of the tool inputs.
        output_summary: Short description of the tool outputs.
        run_id:         Optional pipeline run identifier.
    """
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "run_id":         run_id,
        "agent":          agent,
        "tool":           tool,
        "input_summary":  input_summary,
        "output_summary": output_summary,
    }

    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
