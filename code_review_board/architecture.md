# Architecture — Automated Code Review Board

## Fan-Out / Fan-In Diagram

```mermaid
flowchart TD
    A([Start: submit diff]) --> B[DiffAgent\nparse_diff · summarize_change]
    B -- error --> C[ReviewerManager\ndedupe_findings · rank_by_severity]
    B -- ok --> D[StyleAgent\ncheck_line_length_and_naming\ncheck_docstrings_with_ast]
    B -- ok --> E[SecurityAgent\nscan_for_secrets\nfind_unsafe_calls]
    B -- ok --> F[TestCoverageAgent\nfind_matching_test_files\ncount_new_functions_vs_tests]
    D --> C
    E --> C
    F --> C
    C --> G[FixSuggestionAgent\nget_top_finding · generate_patch]
    G --> H([End: decision + findings])

    style B fill:#4A90D9,color:#fff
    style D fill:#7CB87C,color:#fff
    style E fill:#E07B7B,color:#fff
    style F fill:#D4A74A,color:#fff
    style C fill:#9B59B6,color:#fff
    style G fill:#5DADE2,color:#fff
```

## Shared State Flow

```mermaid
flowchart LR
    CS[(ChangeState)] --> DA[DiffAgent]
    DA -->|parsed_files\ndiff_summary| CS
    CS --> SA[StyleAgent]
    CS --> SEC[SecurityAgent]
    CS --> TCA[TestCoverageAgent]
    SA -->|findings| CS
    SEC -->|findings| CS
    TCA -->|findings| CS
    CS --> RM[ReviewerManager]
    RM -->|decision\ndecision_reason\nranked findings| CS
```

## Decision Rule (ReviewerManager)

```
if state.error         → CANNOT_REVIEW
elif any HIGH finding  → REQUEST_CHANGES
elif MEDIUM count ≥ 2  → REQUEST_CHANGES
else                   → APPROVE
```
