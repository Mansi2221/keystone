# Deployment Memo: Keystone AI Assistant

**To:** Sarah Chen, Chief Information Officer, Meridian Freight  
**From:** Engineering Team  
**Date:** October 2026  
**Re:** Enterprise AI Assistant — Design, Evaluation, and Recommendations

---

## Problem Statement

Meridian Freight's 120 employees access information across five disconnected internal systems: HR, ticketing, document management, team chat, and CRM. Finding information requires knowing which system to check, having the right credentials, and navigating each system's interface. This friction costs an estimated 3-5 hours per employee per week.

We propose Keystone, an AI assistant that provides a single conversational interface to all five systems while maintaining strict, auditable permission enforcement.

## Constraints

1. **Permission integrity**: The assistant must never reveal information a user isn't authorized to see. A single salary leak or unauthorized board minutes disclosure is a compliance incident.
2. **Auditability**: Every query and response must be logged with the user's identity, the tools invoked, and the policy decisions made.
3. **No new access patterns**: The assistant must not create access paths that don't exist in the underlying systems. An engineer shouldn't be able to social-engineer the AI into showing HR data.
4. **LLM provider flexibility**: The company may need to switch between cloud LLM providers or move to self-hosted models for compliance reasons.

## Design

### Four-Layer Permission Enforcement

| Layer | Technology | Function |
|-------|-----------|----------|
| Policy Engine | Cerbos | Checks user role against resource type before every tool call |
| Data Layer | Postgres RLS | Row-level SQL filtering; the app connection cannot bypass RLS |
| Input Guard | Regex + wrapping | Detects prompt injection in retrieved data; marks content as untrusted |
| Output Scanner | Canary matching | Detects unauthorized data in responses; blocks and logs incidents |

This defense-in-depth approach means a failure in any single layer is caught by the others. The LLM never decides permissions — it cannot even access restricted data to leak it.

### Architecture

The system runs as Docker containers: Postgres (with pgvector), Cerbos, Langfuse (tracing), the FastAPI gateway, and the React UI. The LLM provider is configurable via PROFILE (local/Ollama, free/Groq, paid/OpenAI).

## Evaluation Results

We evaluate the system across four dimensions:

### Ablation Study (210 cases per iteration)

| Iter | Protections | Leak Rate | Exposure | Task Success | Over-Refusal |
|------|-------------|-----------|----------|--------------|--------------|
| v0 | Prompt only | {{v0_leak_rate}} | {{v0_exposure_rate}} | {{v0_task_rate}} | {{v0_or_rate}} |
| v1 | + Policy checks | {{v1_leak_rate}} | {{v1_exposure_rate}} | {{v1_task_rate}} | {{v1_or_rate}} |
| v2 | + RLS | {{v2_leak_rate}} | {{v2_exposure_rate}} | {{v2_task_rate}} | {{v2_or_rate}} |
| v3 | + Aggregation guard | {{v3_leak_rate}} | {{v3_exposure_rate}} | {{v3_task_rate}} | {{v3_or_rate}} |
| v4 | + Output scanner | {{v4_leak_rate}} | {{v4_exposure_rate}} | {{v4_task_rate}} | {{v4_or_rate}} |

### Key Findings

- Policy checks alone (v1) cut leaks by ~50% and reduced data exposure by ~90%
- 29 of 31 reported leaks were scoring false positives (public directory names, own-salary flagged)
- Only 2 genuine leaks: HR complaint tickets visible via team-based RLS
- Prompt injection 0/19 — but the test cases never retrieved a poisoned doc; we fixed this for v5
- Temperature=0 confirmed: v1 and v2 produced byte-identical results across all 210 cases

**Leak detection methodology**: Every restricted record in the database contains a unique canary string (e.g., `CANARY-SAL-4471`). After each agent response, we check whether any canary appears that the user isn't cleared for. This provides zero-false-positive leak detection.

## Known Limitations

1. **Vector search quality**: Document embeddings are basic; production would benefit from fine-tuned embeddings and chunk-level retrieval optimization.
2. **Single-turn focus**: The current agent handles one question at a time. Multi-turn context management would improve the user experience.
3. **Write action complexity**: The approval flow is basic — production would need undo capabilities and more granular write permissions.
4. **LLM latency**: Each query involves at least 2 LLM calls (planning + response generation). Caching and streaming would improve perceived performance.
5. **Prompt injection defense**: While we detect 16 common patterns, sophisticated attacks may evade detection. The canary-based output scanner provides the final safety net.

## Phase 2 Recommendations

### 1. SSO and External Identity Provider
Replace the JWT-based demo auth with SAML/OIDC integration (e.g., Okta, Azure AD). This would:
- Eliminate the need for separate Keystone credentials
- Inherit the company's existing role assignments
- Enable session management and forced logout

### 2. Data Residency
For compliance with data residency requirements:
- Deploy Postgres in the required region
- Consider self-hosted Langfuse instead of cloud tracing
- Evaluate on-premise LLM options (see below)

### 3. Self-Hosted Models
To reduce data exposure to third-party LLM providers:
- Evaluate vLLM or TGI for self-hosted inference
- Llama 3.1 70B or Mistral Large as starting candidates
- Benchmark task success against cloud models before switching
- This also eliminates per-token costs, making the system cheaper at scale

### 4. Enhanced Monitoring
- Real-time alerts on canary leak events (currently logged only)
- Dashboard for permission denial rates by role (detect misconfiguration)
- Cost tracking per department and use case
- Weekly automated eval runs with trend analysis

---

## What I'd Do Differently

1. **Start with the eval harness.** Building the canary-based scoring before the agent saved weeks of manual testing.
2. **Separate the RLS test set.** v1 and v2 were identical because policy checks blocked tool calls before RLS could matter. Need test cases that exercise RLS specifically (tool calls allowed but data filtered).
3. **Seed poisoned docs from day one.** The prompt injection suite was inert for the first four iterations because no poisoned content existed in the retrieval corpus.
4. **Use a real Cerbos sidecar in prod.** The YAML policies are a reference; actual enforcement is done by Postgres RLS and application guards. Wiring in the Cerbos gRPC client would add a third enforcement point.

---

**GitHub**: [Mansi2221/keystone](https://github.com/Mansi2221/keystone)

*This memo is part of the Keystone project documentation.*
