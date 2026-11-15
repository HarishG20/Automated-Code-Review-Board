"""
tools/security_tools.py
=======================
Deterministic security-scanning tools for the Security Agent.

Uses regex patterns and Python's `ast` module — no LLM calls.
All secrets are reported at HIGH severity.
"""

from __future__ import annotations

import ast
import re
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Secret-detection regex patterns
# Each tuple: (rule_code, human_label, compiled_regex)
# We only scan lines that START with '+' (added lines).
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: List[tuple[str, str, re.Pattern]] = [
    (
        "SECRET_API_KEY",
        "Possible API key",
        re.compile(
            r'(?:api[_\-]?key|apikey)\s*[=:]\s*["\']?([A-Za-z0-9\-_]{20,})["\']?',
            re.IGNORECASE,
        ),
    ),
    (
        "SECRET_PASSWORD",
        "Hardcoded password",
        re.compile(
            r'(?:password|passwd|pwd)\s*[=:]\s*["\'](.+?)["\']',
            re.IGNORECASE,
        ),
    ),
    (
        "SECRET_TOKEN",
        "Hardcoded token",
        re.compile(
            r'(?:token|secret|access_token|auth_token)\s*[=:]\s*["\']([A-Za-z0-9\-_\.]{10,})["\']',
            re.IGNORECASE,
        ),
    ),
    (
        "SECRET_AWS_KEY",
        "AWS access key ID",
        re.compile(r'AKIA[0-9A-Z]{16}'),
    ),
    (
        "SECRET_GENERIC_HIGH_ENTROPY",
        "Generic high-entropy string (possible secret)",
        re.compile(
            r'["\']([A-Za-z0-9+/]{32,}={0,2})["\']',
        ),
    ),
]


# ---------------------------------------------------------------------------
# scan_for_secrets
# ---------------------------------------------------------------------------

def scan_for_secrets(diff_text: str) -> List[Dict[str, Any]]:
    """
    Scan added lines of a unified diff for hardcoded secrets.

    Looks for API keys, passwords, tokens, AWS credentials, and other
    high-entropy strings using regex patterns.  Only lines starting with '+'
    (i.e., newly added lines) are examined.

    Args:
        diff_text: Raw unified diff text.

    Returns:
        List of finding dicts with keys: file, line, rule, message, severity.
        All findings have severity "HIGH".
    """
    findings: List[Dict[str, Any]] = []

    current_file = "unknown"
    added_line_number = 0

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("+++ "):
            current_file = re.sub(r"^[ab]/", "", raw_line[4:].strip())
            added_line_number = 0
            continue
        if raw_line.startswith("--- ") or raw_line.startswith("@@ "):
            continue
        if not raw_line.startswith("+"):
            continue

        code_line = raw_line[1:]
        added_line_number += 1

        for rule_code, label, pattern in _SECRET_PATTERNS:
            if pattern.search(code_line):
                findings.append({
                    "file": current_file,
                    "line": added_line_number,
                    "rule": rule_code,
                    "message": f"{label} detected on added line.",
                    "severity": "HIGH",
                })
                # Only report the first matching pattern per line to avoid spam
                break

    return findings


# ---------------------------------------------------------------------------
# find_unsafe_calls
# ---------------------------------------------------------------------------

# Unsafe call signatures we look for in the AST
_SIMPLE_UNSAFE = {"eval", "exec"}  # bare function calls

# Attribute calls we consider unsafe unconditionally
_UNSAFE_ATTR = {
    ("pickle", "loads"),
    ("pickle", "load"),
    ("marshal", "loads"),
    ("marshal", "load"),
}


def _is_shell_true(keywords: list) -> bool:
    """Return True if any keyword argument is shell=True."""
    for kw in keywords:
        if kw.arg == "shell" and isinstance(kw.value, ast.Constant):
            if kw.value.value is True:
                return True
    return False


def find_unsafe_calls(diff_text: str) -> List[Dict[str, Any]]:
    """
    Use Python's `ast` module to detect unsafe function calls in added code.

    Detects:
      - eval(...)              → rule "UNSAFE_EVAL"       severity HIGH
      - exec(...)              → rule "UNSAFE_EXEC"       severity HIGH
      - pickle.loads(...)      → rule "UNSAFE_PICKLE"     severity HIGH
      - subprocess calls with shell=True → "SUBPROCESS_SHELL" severity MEDIUM

    Args:
        diff_text: Raw unified diff text.

    Returns:
        List of finding dicts with keys: file, line, rule, message, severity.
    """
    findings: List[Dict[str, Any]] = []

    # Collect added lines per file
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

    for filename, lines in file_added.items():
        if not filename.endswith(".py"):
            continue

        source = "\n".join(lines)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            # --- bare name calls: eval(), exec() ---
            if isinstance(node.func, ast.Name):
                name = node.func.id
                if name in _SIMPLE_UNSAFE:
                    findings.append({
                        "file": filename,
                        "line": node.lineno,
                        "rule": f"UNSAFE_{name.upper()}",
                        "message": (
                            f"Use of `{name}()` is a security risk; "
                            "avoid executing dynamic code."
                        ),
                        "severity": "HIGH",
                    })

            # --- attribute calls: pickle.loads(), subprocess.run(shell=True) ---
            elif isinstance(node.func, ast.Attribute):
                obj  = node.func.value
                meth = node.func.attr

                # Get the object name if it is a simple Name node
                obj_name = obj.id if isinstance(obj, ast.Name) else None

                if obj_name and (obj_name, meth) in _UNSAFE_ATTR:
                    findings.append({
                        "file": filename,
                        "line": node.lineno,
                        "rule": "UNSAFE_PICKLE",
                        "message": (
                            f"`{obj_name}.{meth}()` can execute arbitrary code; "
                            "deserialise only trusted data."
                        ),
                        "severity": "HIGH",
                    })

                # subprocess with shell=True
                if obj_name == "subprocess" and meth in {
                    "run", "call", "check_call", "check_output", "Popen"
                }:
                    if _is_shell_true(node.keywords):
                        findings.append({
                            "file": filename,
                            "line": node.lineno,
                            "rule": "SUBPROCESS_SHELL",
                            "message": (
                                f"`subprocess.{meth}(shell=True)` is a command "
                                "injection risk; use a list of arguments instead."
                            ),
                            "severity": "MEDIUM",
                        })

    return findings
