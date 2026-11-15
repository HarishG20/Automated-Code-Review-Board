"""
tools/style_tools.py
====================
Deterministic style-checking tools for the Style Agent.

Uses regex and the built-in `ast` module — no LLM calls.
"""

from __future__ import annotations

import ast
import re
from typing import Any, Dict, List


# Regex: matches a valid snake_case identifier
# (lowercase letters, digits, underscores; must start with a letter or '_')
_SNAKE_CASE_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

# Regex: matches a Python function definition line
_FUNC_DEF_RE = re.compile(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")

MAX_LINE_LENGTH = 100


# ---------------------------------------------------------------------------
# check_line_length_and_naming
# ---------------------------------------------------------------------------

def check_line_length_and_naming(diff_text: str) -> List[Dict[str, Any]]:
    """
    Scan added lines of a unified diff for style violations.

    Checks:
      1. Lines longer than 100 characters  → rule "LINE_TOO_LONG"
      2. Function definitions whose name is not snake_case → rule "BAD_FUNC_NAME"

    Args:
        diff_text: Raw unified diff text.

    Returns:
        List of finding dicts with keys: file, line, rule, message, severity.
        Severity is always "MEDIUM".
    """
    findings: List[Dict[str, Any]] = []

    current_file = "unknown"
    added_line_number = 0   # tracks position within the file's added lines

    for raw_line in diff_text.splitlines():
        # Track which file we are in
        if raw_line.startswith("+++ "):
            current_file = re.sub(r"^[ab]/", "", raw_line[4:].strip())
            added_line_number = 0
            continue

        if raw_line.startswith("--- ") or raw_line.startswith("@@ "):
            continue

        if not raw_line.startswith("+"):
            continue

        # Strip the leading '+' to get the actual code line
        code_line = raw_line[1:]
        added_line_number += 1

        # Check 1: line length
        if len(code_line) > MAX_LINE_LENGTH:
            findings.append({
                "file": current_file,
                "line": added_line_number,
                "rule": "LINE_TOO_LONG",
                "message": (
                    f"Line is {len(code_line)} characters "
                    f"(limit {MAX_LINE_LENGTH})."
                ),
                "severity": "MEDIUM",
            })

        # Check 2: function naming
        m = _FUNC_DEF_RE.match(code_line)
        if m:
            func_name = m.group(1)
            if not _SNAKE_CASE_RE.match(func_name):
                findings.append({
                    "file": current_file,
                    "line": added_line_number,
                    "rule": "BAD_FUNC_NAME",
                    "message": (
                        f"Function '{func_name}' is not snake_case."
                    ),
                    "severity": "MEDIUM",
                })

    return findings


# ---------------------------------------------------------------------------
# check_docstrings_with_ast
# ---------------------------------------------------------------------------

def check_docstrings_with_ast(diff_text: str) -> List[Dict[str, Any]]:
    """
    Use Python's `ast` module to find new functions that lack a docstring.

    Strategy:
      1. Collect all added lines per file from the diff.
      2. Try to parse them as a Python module with `ast.parse`.
      3. Walk the AST; for each FunctionDef / AsyncFunctionDef check for a
         docstring (a Constant string as the first statement in the body).

    Rule: "MISSING_DOCSTRING" at MEDIUM severity (upgraded later if needed).

    Args:
        diff_text: Raw unified diff text.

    Returns:
        List of finding dicts with keys: file, line, rule, message, severity.
    """
    findings: List[Dict[str, Any]] = []

    # --- Collect added lines per file ---
    file_added: Dict[str, List[str]] = {}
    current_file = "unknown"

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("+++ "):
            current_file = re.sub(r"^[ab]/", "", raw_line[4:].strip())
            file_added.setdefault(current_file, [])
            continue
        if raw_line.startswith("--- ") or raw_line.startswith("@@ "):
            continue
        if raw_line.startswith("+"):
            file_added.setdefault(current_file, []).append(raw_line[1:])

    # --- Parse each file's added lines ---
    for filename, lines in file_added.items():
        # Only attempt to parse Python files
        if not filename.endswith(".py"):
            continue

        source = "\n".join(lines)

        try:
            tree = ast.parse(source)
        except SyntaxError:
            # Added lines alone may not form valid Python (partial snippets).
            # Skip silently — we cannot check what we cannot parse.
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            has_docstring = (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            )

            if not has_docstring:
                findings.append({
                    "file": filename,
                    "line": node.lineno,
                    "rule": "MISSING_DOCSTRING",
                    "message": (
                        f"Function '{node.name}' is missing a docstring."
                    ),
                    "severity": "LOW",
                })

    return findings
