# Overnight Summary

**Generated:** 2026-10-29 16:53 UTC
**Iterations:** v0, v1, v2, v3, v4, v5
**Cases per iteration:** 210


## Ablation Results

| Iteration | Task Success | Over-Refusal | Leaks (canary) | Leaks (value) | Grounding Fails | LLM Calls/Case |
|-----------|-------------|-------------|----------------|---------------|-----------------|----------------|
| v0 | 28/40 | 15/20 | 47 | 43 | 6 | 3.2 |
| v1 | 29/40 | 15/20 | 16 | 13 | 6 | 2.7 |
| v2 | 29/40 | 17/20 | 16 | 13 | 6 | 2.6 |
| v3 | 26/40 | 16/20 | 16 | 13 | 8 | 3.6 |
| v4 | 26/40 | 16/20 | 13 | 12 | 8 | 2.7 |
| v5 | 26/40 | 16/20 | 13 | 12 | 8 | 2.6 |

### Leak Breakdown by Type

| Type | v0 | v1 | v2 | v3 | v4 | v5 |
|------|---|---|---|---|---|---|
| message | 1 | 1 | 1 | 1 | 0 | 0 |
| salary | 28 | 0 | 0 | 0 | 0 | 0 |
| salary_value | 43 | 13 | 13 | 13 | 12 | 12 |
| ticket | 2 | 2 | 2 | 2 | 0 | 0 |
| unknown | 1 | 1 | 1 | 1 | 1 | 1 |

## Judge Reliability (Cohen's Kappa)

| Metric | Before Grounding | After Grounding |
|--------|-----------------|-----------------|
| Kappa | 0.348 | 0.630 |
| Interpretation | Fair | Substantial |

## Statistical Significance

With 210 cases per iteration and local Ollama inference (qwen2.5:7b),
differences smaller than ~3% in pass rates are within noise.
The grounding checker is deterministic and adds no variance.

Key observations:
- Grounding check catches fabricated URLs, hallucinated IDs, and wrong dollar amounts
- Cannot catch semantic errors (e.g., reporting old salary as current)
- 6 additional failures per iteration from grounding violations (v0-v2)
