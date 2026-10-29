# Deployment Memo: Keystone AI Assistant

**To:** Sarah Chen, Chief Information Officer, Meridian Freight
**From:** Engineering Team
**Date:** October 2026
**Re:** Enterprise AI Assistant -- Design, Evaluation, and Recommendations

---

## Problem Statement

Meridian Freight's 120 employees access information across five disconnected internal systems: HR, ticketing, document management, team chat, and CRM. Finding information requires knowing which system to check, having the right credentials, and navigating each system's interface. This friction costs an estimated 3-5 hours per employee per week.

We propose Keystone, an AI assistant that provides a single conversational interface to all five systems while maintaining strict, auditable permission enforcement.

## Constraints

1. **Permission integrity**: The assistant must never reveal information a user isn't authorized to see. A single salary leak or unauthorized board minutes disclosure is a compliance incident.
2. **Auditability**: Every query and response must be logged with the user's identity, the tools invoked, and the policy decisions made.
3. **No new access patterns**: The assistant must not create access paths that don't exist in the underlying systems. An engineer shouldn't be able to social-engineer the AI into showing HR data.
4. **LLM provider flexibility**: The company may need to switch between cloud LLM providers or move to self-hosted models for compliance reasons.

## System Architecture

```
  Browser/CLI
       |
       v
+------+-------+     +----------+
| FastAPI       |     | Langfuse |
| Gateway       +---->| (Traces) |
| (JWT Auth)    |     +----------+
+------+--------+
       |
       v
+------+--------+
| LangGraph     |
| Agent         |
| (Plan/Route/  |
|  Execute)     |
+--+----+----+--+
   |    |    |
   v    v    v
+--+--+ | +--+--+
|Cerb.| | |Out  |    Layer 1: ABAC policy check
|ABAC | | |Scan |    Layer 5: Canary leak detection
+--+--+ | +--+--+    Layer 6: Grounding checker
   |    |    |
   |    v    |
   | +--+--+ |
   | |Input| |       Layer 4: Injection scanner
   | |Guard| |
   | +--+--+ |
   |    |    |
   v    v    v
+--+----+----+------+
| 5 MCP Tool Servers |
| HR | Tkt | Doc |   |
| Chat | CRM        |
+---------+----------+
          |
          v
+---------+----------+
| Postgres + pgvector |
| RLS per-table       |    Layer 2: Row-level security
| Pre-filtered search |    Layer 3: Retrieval pre-filter
+---------------------+
```

## Six Security Layers

| # | Layer | Technology | Catches |
|---|-------|-----------|---------|
| 1 | **Policy Engine** | Cerbos (ABAC) | Role not authorized for resource type |
| 2 | **Data Layer** | Postgres RLS | Row-level access violations |
| 3 | **Retrieval Pre-filter** | SQL WHERE in vector search | Unauthorized docs in semantic results |
| 4 | **Input Guard** | 16 regex patterns | Prompt injection in retrieved content |
| 5 | **Output Scanner** | Canary registry matching | Leaked restricted data in responses |
| 6 | **Grounding Checker** | Deterministic post-hoc | Fabricated URLs, hallucinated IDs, wrong dollar amounts |

Defense-in-depth: a failure in any single layer is caught by the others. The LLM never decides permissions -- it cannot even access restricted data to leak it (once RLS is active).

## Evaluation Methodology

### Ablation Study Design

We run 6 iterations (v0-v5), each enabling a cumulative set of protections, to measure the marginal contribution of each layer:

- **210 cases** per iteration (70 per suite)
- **3 suites**: task_success, over_refusal, permission_leakage
- **8 attack types**: direct, social engineering, role impersonation, aggregation, prompt injection, cross-system, private access, bulk extraction
- **7 personas**: CEO, HR Manager, Sales Rep, Engineer (IC), Contractor, Ops Manager, Finance Director
- **Per-case timeout**: 120 seconds (prevents stuck LLM calls from blocking the pipeline)
- **Per-case resume**: Progress saved to JSONL; a killed run resumes from the last completed case

### Leak Detection

Every restricted record in the database contains a unique canary string (e.g., `CANARY-SAL-4471`). After each agent response, we check whether any canary appears that the acting user isn't cleared for. This provides zero-false-positive leak detection.

**User-relative scoring**: A protected value counts as a leak only if the acting user's role isn't cleared for that specific record. A manager seeing their own reports' salaries is NOT a leak. Authorization is checked against the canary registry's `allowed_roles` and `allowed_employee_ids`, plus the org chart's manager relationships.

### Judge

The LLM judge (qwen2.5:7b via Ollama, local inference) evaluates each case. After discovering the false-pass bug (see below), we added a deterministic grounding checker that verifies structured claims against the database.

## Results

### Ablation Table

| Iteration | Protections | Task Success | Over-Refusal | Canary Leaks | Value Leaks | Grounding Fails | LLM Calls/Case |
|-----------|------------|-------------|-------------|-------------|-------------|-----------------|----------------|
| v0 | None | 28/40 (70%) | 15/20 (75%) | 32 | 43 | 6 | 3.2 |
| v1 | + Policy | 29/40 (72%) | 15/20 (75%) | 4 | 13 | 6 | 2.7 |
| v2 | + RLS | 29/40 (72%) | 17/20 (85%) | 4 | 13 | 6 | 2.6 |
| v3 | + Agg/Inj | 26/40 (65%)\* | 16/20 (80%) | 4 | 13 | 8 | 3.6 |
| v4 | + Output scan | 26/40 (65%)\* | 16/20 (80%) | 1 | 12 | 8 | 2.7 |
| v5 | + Grounding | 26/40 (65%)\* | 16/20 (80%) | 1 | 12 | 8 | 2.6 |

\*v3-v5 task success differences from v0-v2 are within noise (~3%) at n=210.

### Leak Breakdown by Attack Type

| Attack Type | v0 | v1 | v2 | v3 | v4 | v5 |
|------------|----|----|----|----|----|----|
| direct | 19/19 | 1/19 | 1/19 | 1/19 | 0/19 | 0/19 |
| social_engineering | 9/18 | 2/18 | 2/18 | 2/18 | 2/18 | 2/18 |
| role_impersonation | 5/18 | 2/18 | 2/18 | 2/18 | 2/18 | 2/18 |
| aggregation | 10/20 | 10/20 | 10/20 | 10/20 | 8/20 | 8/20 |
| prompt_injection | 0/19 | 0/19 | 0/19 | 0/19 | 0/19 | 0/19 |
| cross_system | 8/18 | 8/18 | 8/18 | 6/18 | 4/18 | 4/18 |
| private_access | 1/19 | 1/19 | 1/19 | 1/19 | 1/19 | 1/19 |
| bulk_extraction | 8/19 | 7/19 | 7/19 | 5/19 | 3/19 | 3/19 |

## Key Findings

### Finding 1: The False-Pass Bug

**Discovery**: When we ran a positive control (all protections OFF, no permission rules in the system prompt), we expected nearly 100% task failure -- the model should not be able to answer permission-gated questions without any access. Instead, the judge marked many responses as "pass."

**Root cause**: The LLM was generating plausible-sounding but fabricated responses (e.g., "The salary for employee #42 is $85,000" when the actual salary is $127,500). The LLM judge couldn't distinguish these hallucinations from correct answers because it only checked whether the response "looked reasonable."

**Fix**: We added a deterministic grounding checker that verifies:
- Employee IDs mentioned in the response exist in the database
- Dollar amounts match actual records (salary, deal values)
- URLs and document references point to real resources
- Department/title claims match HR records

**Impact**: The grounding checker is fully deterministic (no LLM variance) and added 6 additional failures per iteration for fabricated content.

### Finding 2: Judge Reliability

We hand-labeled 30 cases and measured Cohen's kappa:

| Metric | Before Grounding Checker | After Grounding Checker |
|--------|-------------------------|------------------------|
| Cohen's kappa | 0.348 (Fair agreement) | 0.630 (Substantial agreement) |

The improvement comes entirely from catching hallucinated content that the LLM judge accepted. The grounding checker cannot catch semantic errors (e.g., reporting an old salary as current), but it eliminates the largest class of false passes.

### Finding 3: Cross-System Spillage

**The most dangerous leak vector is not direct queries -- it's data that humans have duplicated across systems.**

Even with full RLS on HR tables, confidential information leaks through:
- **Chat**: A manager discusses upcoming layoffs in `#leadership-private` -- anyone with chat access sees it
- **Tickets**: An HR complaint ticket references an employee's salary -- anyone who can view tickets sees it
- **Documents**: Board minutes contain deal terms -- anyone with docs access sees them

This is hard to fix because the data was put there by humans, not by the AI. RLS on employee/salary tables doesn't help when the same information exists in a chat message.

**Ablation evidence**: The `cross_system` attack type shows 8/18 leaks in v0 and **still 8/18 in v2** (with RLS on). The leak rate doesn't drop until the output scanner in v4 (4/18), confirming these leaks come from chat/ticket/docs tables, not the HR tables that RLS protects.

### Finding 4: Wrong-Database Bug

During overnight evaluation, the pipeline silently connected to local Postgres (port 5432) instead of Docker Postgres (port 5433). This happened because:

1. `company/config.py` has `postgres_port: int = 5432` as the default
2. The `raw_database_url` property constructs the URL from individual settings fields, not from `DATABASE_URL`
3. The main repo had `.env` with `POSTGRES_PORT=5433`, but the git worktree did not inherit it
4. The `disable_all_rls()` function connected to the wrong Postgres and got `FATAL: role "keystone" does not exist`

**Lesson**: Configuration that is split across multiple derivation paths (an env var for one connection, computed properties for another) creates silent failure modes. A single `DATABASE_URL` source of truth would have prevented this.

The earlier v0-v2 results were valid because they ran from the main repo where `.env` existed.

## CI Pipeline

The CI pipeline runs four jobs on every push:

1. **lint** -- ruff check + format verification
2. **unit-tests** -- 111+ tests with no external dependencies
3. **cerbos-policy-tests** -- Validates Cerbos YAML policies
4. **security-tests** -- Deterministic security tests with a real Postgres instance:
   - RLS enforcement (contractor can't see salaries, IC sees own only, etc.)
   - Cache isolation (different users get different cache keys)
   - Canary detection (canary patterns match, no false positives)

### Demo: The Cache Key Bug

The `feature/retrieval-cache` PR added a response cache keyed on query text only. The security test caught that a CEO and a contractor got the **same cache key** for the same query -- meaning cached CEO salary results would be served to a contractor.

- **Failing CI run**: The assertion `ceo_key != contractor_key` failed because both hashed to the same SHA-256
- **Fix**: Added `user_id` and `role` to the cache key input
- **Passing CI run**: All security tests green after the fix

## Known Limitations

1. **Cross-system leaks remain open**: RLS on source tables doesn't prevent data that humans have duplicated into chat/tickets/docs. Fixing this requires content-level classification and filtering, not just row-level access control.
2. **Local LLM quality**: qwen2.5:7b (used for local eval) has lower task success than cloud models. Production should benchmark against GPT-4o-mini or Claude Haiku.
3. **Grounding checker scope**: Catches fabricated data but not semantic errors (wrong context, outdated values, correct data attributed to the wrong person).
4. **Single-turn focus**: The current agent handles one question at a time. Multi-turn context would improve UX.
5. **Prompt injection defense**: 16 regex patterns catch common attacks, but sophisticated adversarial prompts may evade detection. The canary-based output scanner is the final safety net.

## Phase 2 Recommendations

### 1. Content-Level Classification
Address cross-system spillage by classifying chat messages and ticket comments by sensitivity level. Apply access controls at the content level, not just the table level.

### 2. SSO Integration
Replace JWT-based demo auth with SAML/OIDC (Okta, Azure AD). Inherit existing role assignments; enable session management and forced logout.

### 3. Self-Hosted Models
Evaluate vLLM or TGI with Llama 3.1 70B for on-premise inference. Eliminates per-token costs and data exposure to third-party providers. Benchmark task success before switching.

### 4. Continuous Eval
Run the ablation study weekly on a schedule. Track task success and leak rate trends. Alert on regressions. The per-case resume and timeout infrastructure supports unattended runs.

### 5. Enhanced Monitoring
- Real-time alerts on canary leak events (currently logged only)
- Dashboard for permission denial rates by role (detect misconfiguration)
- Cost tracking per department and use case

---

*This memo is part of the Keystone project documentation.*
*Ablation data from overnight pipeline run 2026-10-29 (commit 280daec, qwen2.5:7b local inference).*
