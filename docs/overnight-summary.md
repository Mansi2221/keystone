# Overnight Summary

**Generated:** 2026-10-28 22:07 UTC
**Iterations:** v0, v1, v2
**Cases per iteration:** 210

## Ablation Results

| Iteration | Task Success | Over-Refusal | Leaks (canary) | Leaks (value) | Grounding Fails | LLM Calls/Case |
|-----------|-------------|-------------|----------------|---------------|-----------------|----------------|
| v0 | 28/40 | 15/20 | 60 | 1307 | 6 | 3.2 |
| v1 | 29/40 | 15/20 | 31 | 1109 | 6 | 2.7 |
| v2 | 29/40 | 17/20 | 31 | 1109 | 6 | 2.6 |

### Leak Breakdown by Type

| Type | v0 | v1 | v2 |
|------|---|---|---|
| message | 2 | 2 | 2 |
| review_value | 724 | 670 | 670 |
| salary | 55 | 0 | 0 |
| salary_value | 583 | 439 | 439 |
| ticket | 21 | 13 | 13 |
| unknown | 13 | 13 | 13 |

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
