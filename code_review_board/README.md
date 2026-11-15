# Automated Code Review Board

> **CSE476 — Agentic AI and Intelligent Automation**  
> A multi-agent system built with **Semantic Kernel (Python)** that reviews code changes (unified diffs) and produces a consolidated review with a merge recommendation.

---

## Agent Roster

| Agent | Role | Tools |
|-------|------|-------|
| **DiffAgent** | Gate — parse & validate the diff | `parse_diff`, `summarize_change` |
| **StyleAgent** | Fan-out #1 — style checks | `check_line_length_and_naming`, `check_docstrings_with_ast` |
| **SecurityAgent** | Fan-out #2 — security scan | `scan_for_secrets`, `find_unsafe_calls` |
| **TestCoverageAgent** | Fan-out #3 — test coverage | `find_matching_test_files`, `count_new_functions_vs_tests` |
| **ReviewerManager** | Fan-in — merge & decide | `dedupe_findings`, `rank_by_severity` |
| **FixSuggestionAgent** | Bonus — produce a patch | `get_top_finding`, `generate_patch` |

---

## Architecture — Fan-Out / Fan-In

```
     [DiffAgent]  ← validates the diff (GATE)
          │
    ┌─────┼─────┐
    ▼     ▼     ▼
[Style] [Security] [TestCoverage]  ← run in PARALLEL (asyncio.gather)
    └─────┼─────┘
          ▼
   [ReviewerManager]  ← deduplicates, ranks, decides
          │
   [FixSuggestionAgent]  ← (bonus) patches the top finding
```

**Why fan-out / fan-in fits this problem:**  
Style, security, and coverage checks are entirely independent — they read the same diff but write to separate parts of the shared state. Running them in parallel halves the wall-clock time and mirrors how a real code-review committee works (each reviewer specialises in one dimension).

---

## Shared Memory — `ChangeState`

| Field | Type | Written by |
|-------|------|-----------|
| `diff_raw` | `str` | Caller (input) |
| `parsed_files` | `list[DiffFile]` | DiffAgent |
| `diff_summary` | `str` | DiffAgent |
| `findings` | `list[Finding]` | StyleAgent, SecurityAgent, TestCoverageAgent; replaced by ReviewerManager |
| `decision` | `str` | ReviewerManager |
| `decision_reason` | `str` | ReviewerManager |
| `error` | `str \| None` | DiffAgent |
| `agent_errors` | `dict` | Any fan-out agent that crashes |

Every `Finding` carries: `id`, `agent`, `file`, `line`, `rule`, `message`, `severity`.

---

## Failure Handling

**Empty / malformed diff:**  
The DiffAgent sets `state.error` and returns immediately.  
The ReviewerManager sees the error flag and returns `CANNOT_REVIEW` without touching findings.

**Fan-out agent crash:**  
Each of the three fan-out agents wraps its body in `try/except` and writes the exception string to `state.agent_errors[agent_name]`.  
The pipeline continues; the ReviewerManager adds a note to `decision_reason` naming the failed sections.

---

## Running the Project

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run all tests (offline mode — no API key needed)
pytest code_review_board/tests/ -v

# 3. Run the demo notebook
jupyter notebook demo.ipynb

# 4. (Optional) live mode — copy .env.example to .env and add your key
cp .env.example .env
# edit .env: set LLM_MODE=live and OPENAI_API_KEY=sk-...
```

---

## Run Log

Every agent action is appended as one JSON line to `logs/run_log.jsonl`:

```json
{"timestamp": "...", "run_id": "...", "agent": "SecurityAgent",
 "tool": "scan_for_secrets", "input_summary": "diff length=512 chars",
 "output_summary": "2 finding(s)"}
```

The file is opened in **append mode only** — it is never truncated.
