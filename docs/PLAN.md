# Keystone Build Plan

## Phase 1: The Fictional Company "Meridian Freight" — DONE
- [x] Project scaffolding (pyproject.toml, docker-compose, Makefile, .env.example)
- [x] Database schemas for HR, Ticketing, Documents, Chat, CRM
- [x] Org chart generator (120 people, 7 roles, 5 departments)
- [x] Data generators for all 5 systems with Faker + fixed seed
- [x] Canary registry: unique canary per restricted record
- [x] LLM-generated documents and messages with disk caching
- [x] Deliberate mess: duplicates, inconsistencies, prompt injections (16)
- [x] Seed script: `make seed` builds everything from scratch
- [x] Tests: 69 tests — row counts, org chart integrity, canary completeness — ALL PASSING

## Phase 2: MCP Servers and Data-Layer Security — DONE
- [x] MCP server per system (hr, tickets, docs, chat, crm) with tool registries
- [x] Principal propagation (user_id, role, groups) on every tool call
- [x] Postgres RLS on 11 tables with 20+ policies (salary, reviews, tickets, docs, chat, deals, leave)
- [x] Vector retrieval pre-filtering by access groups in SQL before similarity ranking
- [x] Integration tests for RLS: salary visibility, board minutes, deals, private chat, contractor lockout
- [x] Shared tool registry with write tool detection for approval flow

## Phase 3: Policy Engine and Identity
- [ ] Cerbos policies for full permission matrix
- [ ] Cerbos policy tests covering every rule including denials
- [ ] FastAPI gateway with JWT auth
- [ ] Dev login endpoint with seeded demo users
- [ ] Identity resolution from HR system
- [ ] Principal attachment and propagation

## Phase 4: The Agent
- [ ] LangGraph graph: planner, tool router, executor, self-check, approval, responder
- [ ] Cerbos check before every tool call
- [ ] LangGraph interrupt for write actions
- [ ] Self-check node for grounding and citations
- [ ] Input guard for prompt injection detection
- [ ] Output scanner for canary/sensitive pattern leaks
- [ ] Audit log table
- [ ] Langfuse tracing
- [ ] Aggregation leak and cross-system inference handling

## Phase 5: Evaluation Harness
- [ ] 5 eval suites (task success, permission leakage, tool correctness, over-refusal, cost/latency)
- [ ] Eval case generation scripts
- [ ] LLM judge with calibration
- [ ] Eval runner (`make eval`, `make eval-fast`)
- [ ] Improvement log automation

## Phase 6: CI
- [ ] GitHub Actions workflow
- [ ] Lint, typecheck, test, policy test, eval-fast gates
- [ ] Leak detection gate
- [ ] Task success regression gate
- [ ] PR comment with eval summary

## Phase 7: UI and Packaging
- [ ] Streamlit chat with user switcher
- [ ] Approval panel for write actions
- [ ] Audit log view and Langfuse trace links
- [ ] Side-by-side demo mode
- [ ] README.md with architecture diagram
- [ ] docs/architecture.md
- [ ] docs/deployment-memo.md
