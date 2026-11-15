"""
tools/fix_suggestion_tools.py
=============================
Tools for the (bonus) Fix-Suggestion Agent.

Produces a concrete patch for the single highest-severity finding.
All logic is deterministic — no LLM calls.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from code_review_board.state.change_state import Finding, Severity


# Severity ordering (lower = worse)
_SEVERITY_ORDER = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}


# ---------------------------------------------------------------------------
# get_top_finding
# ---------------------------------------------------------------------------

def get_top_finding(findings: List[Finding]) -> Optional[Finding]:
    """
    Return the single highest-severity finding from the list.

    If multiple findings share the top severity, the first one (by file and
    line number) is returned.  Returns None if the list is empty.

    Args:
        findings: Ranked list of Finding objects.

    Returns:
        The worst Finding, or None.
    """
    if not findings:
        return None

    return min(
        findings,
        key=lambda f: (
            _SEVERITY_ORDER[f.severity],
            f.file,
            f.line,
        ),
    )


# ---------------------------------------------------------------------------
# generate_patch
# ---------------------------------------------------------------------------

# Rule → patch template
_PATCH_TEMPLATES: Dict[str, str] = {
    "SECRET_API_KEY": (
        "# FIX: Never hardcode API keys.\n"
        "# Replace the hardcoded value with an environment variable:\n"
        "import os\n"
        "API_KEY = os.environ.get('API_KEY')  # set this in .env or CI secrets\n"
    ),
    "SECRET_PASSWORD": (
        "# FIX: Never hardcode passwords.\n"
        "import os\n"
        "PASSWORD = os.environ.get('PASSWORD')\n"
    ),
    "SECRET_TOKEN": (
        "# FIX: Never hardcode tokens.\n"
        "import os\n"
        "TOKEN = os.environ.get('TOKEN')\n"
    ),
    "SECRET_AWS_KEY": (
        "# FIX: Never hardcode AWS credentials.\n"
        "# Use IAM roles or ~/.aws/credentials instead.\n"
        "import os\n"
        "AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')\n"
    ),
    "SECRET_GENERIC_HIGH_ENTROPY": (
        "# FIX: Move this secret to an environment variable.\n"
        "import os\n"
        "SECRET = os.environ.get('SECRET')\n"
    ),
    "UNSAFE_EVAL": (
        "# FIX: Avoid eval(). Use ast.literal_eval() for safe expression parsing,\n"
        "# or refactor to remove dynamic code execution entirely.\n"
        "import ast\n"
        "value = ast.literal_eval(user_input)  # safe alternative\n"
    ),
    "UNSAFE_EXEC": (
        "# FIX: Avoid exec(). Refactor to call functions directly.\n"
        "# If dynamic dispatch is needed, use a dict mapping name → function.\n"
    ),
    "UNSAFE_PICKLE": (
        "# FIX: Avoid pickle.loads() with untrusted data.\n"
        "# Use json.loads() for data interchange, or validate the source.\n"
        "import json\n"
        "data = json.loads(raw_bytes)  # safe alternative for JSON payloads\n"
    ),
    "SUBPROCESS_SHELL": (
        "# FIX: Avoid shell=True; pass a list of arguments instead.\n"
        "import subprocess\n"
        "result = subprocess.run(['cmd', 'arg1', 'arg2'], capture_output=True)\n"
    ),
    "BAD_FUNC_NAME": (
        "# FIX: Rename the function to snake_case.\n"
        "# Example: 'MyFunction' → 'my_function'\n"
    ),
    "LINE_TOO_LONG": (
        "# FIX: Break the long line into multiple shorter lines.\n"
        "# Use parentheses for implicit line continuation:\n"
        "result = (\n"
        "    some_long_expression\n"
        "    + another_expression\n"
        ")\n"
    ),
    "MISSING_DOCSTRING": (
        '# FIX: Add a docstring as the first statement of the function.\n'
        'def your_function(args):\n'
        '    """One-line summary.\n\n'
        '    Args:\n'
        '        args: Description.\n\n'
        '    Returns:\n'
        '        Description.\n'
        '    """\n'
        '    ...\n'
    ),
    "MISSING_TEST_FILE": (
        "# FIX: Create a test file for the changed module.\n"
        "# Example skeleton (save as tests/test_<module>.py):\n"
        "import pytest\n"
        "from your_module import your_function\n\n"
        "def test_your_function():\n"
        "    assert your_function() == expected_result\n"
    ),
    "UNTESTED_FUNCTION": (
        "# FIX: Add a test for the new function.\n"
        "# Example:\n"
        "def test_new_function():\n"
        "    result = new_function(sample_input)\n"
        "    assert result == expected_output\n"
    ),
}

_DEFAULT_PATCH = (
    "# FIX: Review the finding manually and apply the appropriate fix.\n"
    "# No automated patch template is available for rule: {rule}\n"
)


def generate_patch(finding: Finding) -> Dict[str, Any]:
    """
    Generate a concrete, human-readable fix suggestion for a single finding.

    The patch is a text snippet (not a git diff) that shows what the corrected
    code should look like.  Templates exist for every rule defined in this
    system.

    Args:
        finding: The Finding object to fix (typically the top-severity one).

    Returns:
        A dict with keys:
            finding_id  – UUID of the original finding
            rule        – the rule code
            file        – the affected file
            line        – the affected line
            patch_text  – the suggested replacement / fix snippet
    """
    template = _PATCH_TEMPLATES.get(
        finding.rule,
        _DEFAULT_PATCH.format(rule=finding.rule),
    )

    return {
        "finding_id": finding.id,
        "rule": finding.rule,
        "file": finding.file,
        "line": finding.line,
        "patch_text": template,
    }
