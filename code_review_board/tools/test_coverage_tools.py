"""
tools/test_coverage_tools.py
============================
Deterministic tools for the Test-Coverage Agent.

Checks whether changed source files have companion test files and whether
newly defined functions have corresponding test functions.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List


# Regex: matches a function definition in added lines
_DEF_RE      = re.compile(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_TEST_DEF_RE = re.compile(r"^\s*def\s+(test_[A-Za-z_][A-Za-z0-9_]*)\s*\(")


# ---------------------------------------------------------------------------
# find_matching_test_files
# ---------------------------------------------------------------------------

def find_matching_test_files(
    parsed_files: List[Dict[str, Any]],
    repo_root: str = ".",
) -> List[Dict[str, Any]]:
    """
    For each changed Python source file, check whether a companion test file
    exists either on disk OR in the same diff (i.e., being added together).

    Convention: for a changed file `src/utils.py` the expected test file is
    `tests/test_utils.py` (just the basename, in a `tests/` sibling folder).

    Args:
        parsed_files: Output of parse_diff() — list of dicts with key "file".
        repo_root:    Absolute (or relative) path to the repository root.
                      Defaults to current working directory.

    Returns:
        List of finding dicts for files that have NO companion test file.
        Each dict has: file, line (0 = not applicable), rule, message, severity.
    """
    findings: List[Dict[str, Any]] = []

    # Build a set of all test-file basenames present in the diff itself
    # so that a diff which adds both src/foo.py and tests/test_foo.py
    # is correctly recognised as covered.
    test_files_in_diff: set[str] = {
        os.path.basename(f["file"])
        for f in parsed_files
        if os.path.basename(f["file"]).startswith("test_") and f["file"].endswith(".py")
    }

    for file_info in parsed_files:
        filename: str = file_info["file"]

        # Only check Python source files that are not already test files
        if not filename.endswith(".py"):
            continue
        basename = os.path.basename(filename)
        if basename.startswith("test_"):
            continue

        # Derive expected test-file name
        stem = os.path.splitext(basename)[0]          # e.g. "utils"
        test_filename = f"test_{stem}.py"             # e.g. "test_utils.py"
        test_path = os.path.join(repo_root, "tests", test_filename)

        # Check on disk OR in the diff itself
        covered = os.path.exists(test_path) or (test_filename in test_files_in_diff)

        if not covered:
            findings.append({
                "file": filename,
                "line": 0,
                "rule": "MISSING_TEST_FILE",
                "message": (
                    f"No test file found for '{filename}'. "
                    f"Expected: tests/{test_filename}"
                ),
                # MEDIUM severity for missing test file so that critical security
                # vulnerabilities (secrets, remote code execution) take top priority in ranking.
                "severity": "MEDIUM",
            })

    return findings


# ---------------------------------------------------------------------------
# count_new_functions_vs_tests
# ---------------------------------------------------------------------------

def count_new_functions_vs_tests(diff_text: str) -> List[Dict[str, Any]]:
    """
    Compare the number of new functions added to the number of new test
    functions added in the same diff.

    Strategy:
      - For each source file (not a test file), count new `def` declarations.
      - If a companion test file is present in the SAME diff, also count its
        new `test_` functions.  If the source file is entirely covered by a
        companion test file in the diff, skip it (MISSING_TEST_FILE handles
        the case where NO test file exists at all).
      - Only emit UNTESTED_FUNCTION findings when the source file has a
        companion test file in the diff but that test file does not have
        enough test functions to cover the new source functions.

    Rule: "UNTESTED_FUNCTION" at LOW severity.

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

    # Identify test files in the diff and count their test functions
    # Map: test_stem → count_of_test_functions
    # e.g. "test_calculator.py" → 2
    test_function_counts: Dict[str, int] = {}
    for filename, lines in file_added.items():
        if not filename.endswith(".py"):
            continue
        bname = os.path.basename(filename)
        if not bname.startswith("test_"):
            continue
        count = sum(1 for line in lines if _TEST_DEF_RE.match(line))
        test_function_counts[bname] = count

    for filename, lines in file_added.items():
        if not filename.endswith(".py"):
            continue
        basename = os.path.basename(filename)
        if basename.startswith("test_"):
            continue

        stem = os.path.splitext(basename)[0]
        test_filename = f"test_{stem}.py"

        # Count new non-test functions in this source file
        new_funcs: List[tuple[str, int]] = []
        for lineno, code_line in enumerate(lines, start=1):
            m = _DEF_RE.match(code_line)
            if m:
                name = m.group(1)
                if not name.startswith("test_"):
                    new_funcs.append((name, lineno))

        if not new_funcs:
            continue

        # Check how many test functions cover this file in the diff
        tests_in_diff = test_function_counts.get(test_filename, None)

        if tests_in_diff is None:
            # When no test file is present in the diff, also flag the newly added
            # functions as untested functions at MEDIUM severity so that adding
            # multiple untested functions triggers a REQUEST_CHANGES decision.
            for func_name, lineno in new_funcs:
                findings.append({
                    "file": filename,
                    "line": lineno,
                    "rule": "UNTESTED_FUNCTION",
                    "message": (
                        f"New function '{func_name}' has no corresponding "
                        "test function in this diff."
                    ),
                    "severity": "MEDIUM",
                })
            continue

        # Test file exists in diff — flag uncovered functions
        uncovered_count = max(0, len(new_funcs) - tests_in_diff)
        for func_name, lineno in new_funcs[:uncovered_count]:
            findings.append({
                "file": filename,
                "line": lineno,
                "rule": "UNTESTED_FUNCTION",
                "message": (
                    f"New function '{func_name}' has no corresponding "
                    "test function in this diff."
                ),
                "severity": "LOW",
            })

    return findings
