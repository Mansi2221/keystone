# Keystone

**A permission-aware enterprise AI agent deployed into a fictional company, with a full evaluation harness and CI gate.**

Keystone demonstrates that an LLM-powered agent can be made safe and auditable by enforcing permissions in code -- at the policy layer before each tool call, and again at the data layer -- never relying on the model to decide access.

## Architecture

```
                         +------------------+
                         |   Streamlit UI   |
                         +--------+---------+
                                  |
                         +--------v---------+
                         |  FastAPI Gateway  |  JWT auth, audit log
                         +--------+---------+
                                  |
                    +-------------v--------------+
                    |   LangGraph Agent           |
                    |  Planner -> Router -> Exec  |
                    +--+--------+--------+-------+
                       |        |        |
               +-------v--+ +--v-----+ +v-----------+
               | Cerbos   | | Input  | | Output     |
               | Policy   | | Guard  | | Scanner    |
               | (ABAC)   | | (Inj.) | | (Canaries) |
               +-------+--+ +--------+ +-----+------+
                       |                      |
                +------v----------------------v------+
                |         5 MCP Tool Servers         |
                |  HR  | Tickets | Docs | Chat | CRM |
                +------+----+----+------+------+-----+
                             |
                    +--------v---------+
                    | Postgres + RLS   |
                    | pgvector search  |
                    +------------------+
```

## Six Layers of Permission Enforcement

| Layer | What it does | How |
|-------|-------------|-----|
| **1. Policy Engine (ABAC)** | Checks if the user's role is allowed to call this tool on this resource | Cerbos YAML policies, checked before every tool invocation |
| **2. Data Layer (RLS)** | Filters database rows by the user's identity | Postgres RLS policies; `SET LOCAL app.user_id/role/groups` per transaction |
| **3. Retrieval Pre-filter** | Prevents vector search from returning unauthorized documents | Access group filtering in the SQL WHERE clause, before results are returned |
| **4. Input Guard** | Detects prompt injection in retrieved content | 16 regex patterns; wraps content as `<untrusted_data>` |
| **5. Output Scanner** | Catches any leaked restricted data in the response | Canary string matching against the registry; blocks and logs leaks |
| **6. Grounding Checker** | Catches fabricated URLs, hallucinated IDs, wrong dollar amounts | Deterministic post-hoc check on structured claims in the response |

## The Company: Meridian Freight

A fictional 120-person logistics company with 5 departments (Sales, Operations, Finance, HR, Engineering) and 7 roles. Five internal systems are fully seeded:

- **HR**: Employees, salaries (canary-tagged), reviews, leave, terminations (including pending)
- **Ticketing**: 2,000 IT/ops tickets with security incidents and HR complaints
- **Document Store**: 300 documents with pgvector -- policies, contracts, wikis, board minutes (confidential acquisition)
- **Team Chat**: 5,000 messages across public/private channels and DMs (layoff discussion)
- **CRM**: 80 customers, 150 deals (visible only to owner + sales leadership)

**Deliberate challenges**: 20 duplicate docs, 15 stale versions, 16 hidden prompt injections, inconsistent name formats.

## Ablation Study

We run an ablation study across 6 iterations, progressively enabling security layers, to measure what each protection actually does:

| Iteration | Protections | Task Success | Over-Refusal | Leak Cases | Leak Rate |
|-----------|------------|-------------|-------------|------------|-----------|
| v0 | None (system prompt only) | 28/40 (70%) | 15/20 (75%) | 47/150 | 31% |
| v1 | + Cerbos policy checks | 29/40 (72%) | 15/20 (75%) | 16/150 | 11% |
| v2 | + RLS + retrieval pre-filter | 29/40 (72%) | 17/20 (85%) | 16/150 | 11% |
| v3 | + Aggregation guard + injection scanner | 26/40 (65%)\* | 16/20 (80%) | 16/150 | 11% |
| v4 | + Output scanner (canary matching) | 26/40 (65%)\* | 16/20 (80%) | 13/150 | 9% |
| v5 | + Grounding checker + value-leak fix | 26/40 (65%)\* | 16/20 (80%) | 13/150 | 9% |

\*v3-v5 task success differences from v0-v2 are within noise (~3%) at n=210 with local inference.

**210 cases** per iteration. 8 attack types: direct, social engineering, role impersonation, aggregation, prompt injection, cross-system, private access, bulk extraction.

## Key Findings

### 1. The False-Pass Bug (Positive Control)

When we ran a **positive control** (all protections OFF, no permission rules in the system prompt), the judge still marked many responses as "pass." The LLM was generating plausible-sounding responses without real data, and the judge couldn't tell the difference. This revealed that **the judge needed a grounding check** -- verifying that responses contain real data from the actual database, not hallucinated content. Without this, our pass rates were inflated.

### 2. Judge Reliability: Kappa 0.348 -> 0.630

We labeled 30 cases by hand and measured inter-rater agreement (Cohen's kappa) between the human labels and the LLM judge:

| | Before Grounding Checker | After Grounding Checker |
|---|---|---|
| Cohen's kappa | 0.348 (Fair) | 0.630 (Substantial) |
| n | 30 human labels | 30 human labels |

The grounding checker catches fabricated URLs, hallucinated employee IDs, and wrong dollar amounts. It cannot catch semantic errors (e.g., reporting an old salary as current).

### 3. Cross-System Spillage

Chat messages, ticket comments, and documents **leak data across departmental boundaries** even with RLS on employee/salary tables. Cross-system leaks: 8/18 cases in v0 (no protection) and **still 8/18 in v2** (with RLS on) -- the leak rate doesn't drop because these leaks come from chat/ticket/docs tables, not the HR tables that RLS protects. The output scanner (v4) reduces it to 4/18 by catching canary strings, but value-based leaks in chat text remain.

### 4. Wrong-Database Bug

The overnight evaluation pipeline in the `finish` worktree silently connected to local Postgres on port 5432 instead of Docker Postgres on port 5433. The cause: the `raw_database_url` property in `company/config.py` is built from individual settings fields (`postgres_host`, `postgres_port`), not from the `DATABASE_URL` environment variable. The main repo had a `.env` file with `POSTGRES_PORT=5433`, but the worktree did not inherit it. Earlier results (v0-v2) were valid because they ran from the main repo directory where the `.env` existed. The bug was caught when the worktree pipeline failed with `FATAL: role "keystone" does not exist` -- the local Postgres has no such role.

## Quickstart

```bash
# 1. Clone and configure
git clone https://github.com/Mansi2221/keystone.git
cd keystone
cp .env.example .env
# Edit .env -- at minimum, set POSTGRES_PORT=5433

# 2. Start services (Postgres + Cerbos)
docker compose up -d postgres cerbos

# 3. Install dependencies
uv sync --extra dev

# 4. Seed the database
PROFILE=local python -m company.seed

# 5. Run evaluations
PROFILE=local python -m evals.ablation --run all --case-timeout 120

# 6. Launch the demo UI
make demo
```

**Important**: The `POSTGRES_PORT` environment variable (default 5433) must match the Docker Compose port mapping. If running from a git worktree, copy `.env` from the main repo or export `POSTGRES_PORT=5433` explicitly.

## Development

```bash
# Install dependencies
uv sync --extra dev

# Run tests
make test              # All tests
make test-unit         # Unit only (no DB required)
make test-integration  # Requires Postgres

# Lint and format
make lint
make format

# Run the ablation study
PROFILE=local python -m evals.ablation --run v0 --case-timeout 120
```

## CI Pipeline

The CI pipeline runs on every push and PR:

1. **lint**: ruff check + ruff format
2. **unit-tests**: 111+ tests (no external services needed)
3. **cerbos-policy-tests**: Validates all Cerbos YAML policies
4. **security-tests**: Deterministic security tests with a real Postgres -- RLS enforcement, cache isolation, canary detection

The `feature/retrieval-cache` PR demonstrates the CI catching a real bug: the response cache keyed on query text only, so a contractor could receive cached results from a CEO's salary query. The security test detected identical cache keys for different users and failed CI. The fix added `user_id` and `role` to the cache key.

## Project Structure

```
keystone/
  company/        # Data generators, seed scripts, canary registry, config
  mcp_servers/    # HR, Tickets, Docs, Chat, CRM -- one MCP server each
  agent/          # LangGraph graph, prompts, guards, state
  policy/         # Cerbos policies and policy tests
  api/            # FastAPI gateway, JWT auth, audit log
  evals/          # Ablation runner, LLM judge, rescore, labeling
  ui-web/         # React + Vite + TypeScript frontend with replay mode
  scripts/        # Overnight pipeline, fixture recording, summary generation
  docs/           # Architecture, deployment memo, improvement log
  tests/          # 111+ unit, integration, and security tests
```

## Key Design Decisions

- **Permissions are never in prompts.** The model never sees permission rules. Permissions are enforced in code before and after the model runs.
- **Pre-filter, not post-filter.** Vector retrieval includes access group filtering in the SQL WHERE clause, not after results are returned.
- **Canary-based leak detection.** Every restricted record contains a unique canary string. The output scanner checks every response against the canary registry -- any unauthorized canary in output is an exact, deterministic leak detection.
- **Principal from gateway only.** The MCP servers never accept a principal from the model. The gateway resolves identity from the JWT and passes it unchanged.
- **User-relative leak scoring.** A protected value counts as a leak only if the acting user's role isn't cleared for that specific record. A manager seeing their own reports' salaries is NOT a leak.

## License

This is a portfolio project for educational purposes.
