"""
tools/diff_tools.py
===================
Deterministic tools for the Diff Agent.

Both functions are plain Python — no LLM calls, fully testable.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# parse_diff
# ---------------------------------------------------------------------------

def parse_diff(diff_text: str) -> List[Dict[str, Any]]:
    """
    Parse a unified diff into a list of per-file dictionaries.

    Each dictionary contains:
        file         (str)  – path of the modified file
        added_lines  (list) – text of lines starting with '+' (prefix stripped)
        removed_lines(list) – text of lines starting with '-' (prefix stripped)
        hunks        (list) – raw hunk headers (@@ … @@)

    Returns an empty list if the diff is empty or contains no file headers.
    Raises ValueError if the text is clearly not a unified diff (no '---'/'+++'
    markers at all while also being non-empty).
    """
    diff_text = diff_text.strip()

    if not diff_text:
        # Caller (Diff Agent) will treat this as an error
        return []

    # A valid unified diff must have at least one '+++' header line
    if "+++" not in diff_text:
        raise ValueError("Not a valid unified diff: missing '+++' file header.")

    files: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None

    for raw_line in diff_text.splitlines():
        # --- New file block ---
        if raw_line.startswith("+++ "):
            # Extract filename: strip leading 'b/' prefix added by git
            filename = raw_line[4:].strip()
            filename = re.sub(r"^[ab]/", "", filename)
            current = {
                "file": filename,
                "added_lines": [],
                "removed_lines": [],
                "hunks": [],
            }
            files.append(current)

        elif raw_line.startswith("--- "):
            # Ignore the '---' line; we key on '+++'
            continue

        elif raw_line.startswith("@@ "):
            if current is not None:
                current["hunks"].append(raw_line)

        elif raw_line.startswith("+") and current is not None:
            # Added line — strip the leading '+'
            current["added_lines"].append(raw_line[1:])

        elif raw_line.startswith("-") and current is not None:
            # Removed line — strip the leading '-'
            current["removed_lines"].append(raw_line[1:])

    return files


# ---------------------------------------------------------------------------
# summarize_change
# ---------------------------------------------------------------------------

def summarize_change(parsed_files: List[Dict[str, Any]]) -> str:
    """
    Produce a one-line human-readable summary of the diff.

    Example output:
        "3 file(s) changed: +45 lines added, -12 lines removed."

    Args:
        parsed_files: Output of parse_diff().

    Returns:
        A summary string.  Returns "No files changed." for an empty list.
    """
    if not parsed_files:
        return "No files changed."

    total_added   = sum(len(f["added_lines"])   for f in parsed_files)
    total_removed = sum(len(f["removed_lines"]) for f in parsed_files)
    n_files       = len(parsed_files)

    return (
        f"{n_files} file(s) changed: "
        f"+{total_added} lines added, -{total_removed} lines removed."
    )
