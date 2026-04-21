# FRIDAY Agent Efficiency Check

This report evaluates whether orchestrated specialist routing improves output efficiency compared to using one broad agent for everything.

## Baseline vs Orchestrated Model

- Baseline: single broad execution agent (`Friday Dev Cycle`) with 6 tools (`read, search, edit, execute, todo, web`) for most tasks.
- Orchestrated: `Friday Orchestrator` routes to 5 focused specialists with reduced tool scope per task.

## Tool-Surface Comparison

| Agent | Tool Count | Notes |
| --- | ---: | --- |
| Friday Dev Cycle | 6 | Broad capability, higher context/tool overhead |
| Friday Hook Guardian | 5 | Focused on hooks and quality gates |
| Friday PR Reviewer | 4 | Read/review only workflow |
| Friday Graph Intelligence | 5 | Graph tuning and diagnostics |
| Friday CLI UX Designer | 5 | CLI interaction/UX focus |
| Friday Orchestrator | 4 | Routing + synthesis only |

Estimated per-task tool reduction (when correctly routed):

- PR review path: 6 -> 4 (`-33%` tool surface)
- Orchestrator + PR Reviewer flow: 6 -> 4 effective execution set for task-critical work
- Hooks path remains 5 but with role isolation and reduced off-scope actions

## Routing Precision Matrix (Keyword-driven)

| Intent | Specialist | Expected Benefit |
| --- | --- | --- |
| `full dev cycle`, `implement and verify`, `ship` | Friday Dev Cycle | Fewer routing mistakes, end-to-end execution |
| `pre-commit`, `hooks`, `quality gates` | Friday Hook Guardian | Faster hook diagnosis and reproducibility |
| `PR`, `review`, `risk`, `release notes` | Friday PR Reviewer | Higher signal review outputs |
| `graph`, `cluster`, `similarity`, `mermaid` | Friday Graph Intelligence | Better cluster quality tuning |
| `UI`, `UX`, `dashboard`, `commands` | Friday CLI UX Designer | Better CLI usability iterations |

## Efficiency Outcome

- Delegation model improves **focus efficiency** by reducing unnecessary tool/action space per task.
- Multi-step requests benefit from deterministic specialist sequencing.
- Best gains appear in review-only and diagnostics-heavy tasks where editing/execute breadth is not required.

## Practical Verification Steps

1. Run the same prompt through broad agent vs orchestrator route and compare:
   - Time to first actionable output
   - Number of unnecessary edits/commands
   - Number of follow-up clarifications required
2. Track over 5-10 tasks and compute average reduction.

## Recommendation

Use `Friday Orchestrator` as default for mixed or ambiguous requests, and call specialists directly when intent is clear and narrow.
