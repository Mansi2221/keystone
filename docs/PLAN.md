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

## Phase 3: Policy Engine and Identity — DONE
- [x] Cerbos YAML policies for salary, reviews, terminations, tickets, documents, chat, deals
- [x] Cerbos policy tests: salary (8 cases), documents (6 cases), deals (7 cases)
- [x] FastAPI gateway with JWT auth, dev login, audit logging
- [x] 13 seeded demo users covering all 7 roles
- [x] Identity resolution from HR system with recursive report tree
- [x] Principal propagation to all tool calls via dependency injection

## Phase 4: The Agent — DONE
- [x] LangGraph graph: planner, tool_router, tool_executor, approval, responder, self_check, output_scanner
- [x] Policy-checked tool execution with RLS enforcement
- [x] LangGraph interrupt for write actions with approval node
- [x] Self-check node verifies grounding and citations
- [x] Input guard: 16 injection patterns, wrap untrusted data
- [x] Output scanner: canary detection against registry, leak blocking
- [x] Audit log integration via API gateway
- [x] Aggregation leak detection (small team threshold)
- [x] LLM-driven tool argument generation (no empty-dict stubs)
- [x] 96 unit tests all passing

## Phase 5: Evaluation Harness — DONE
- [x] 4 eval suites: task_success (21 cases), permission_leakage (28 cases), tool_correctness (10 cases), over_refusal (15 cases)
- [x] LLM judge with fallback keyword scoring
- [x] Canary-based leak detection against registry
- [x] Tool correctness scorer (tools + arguments)
- [x] Calibration CLI: hand-label 100, measure Cohen's kappa, precision, recall
- [x] Eval runner: `make eval` (all), `make eval-fast` (stratified 20% subset)
- [x] Trace-to-eval converter: turn failed traces into new eval cases
- [x] Auto-append improvement log after each eval run
- [x] Real agent invocation in eval runner (no hardcoded pass=True)
- [x] 120 unit tests all passing

## Phase 6: CI — DONE
- [x] GitHub Actions workflow on every PR and push to main
- [x] Jobs: lint-and-typecheck, unit-tests, cerbos-policy-tests, integration-tests-and-eval
- [x] Leak detection gate: fails build on any permission leak
- [x] Task success regression gate: fails if >3 point drop vs baseline
- [x] PR comment with eval summary markdown
- [x] Artifact uploads for test results and eval reports

## Phase 7: UI and Packaging — DONE
- [x] Streamlit chat with user switcher (12 demo users across all roles)
- [x] Approval panel for pending write actions
- [x] Audit log view with trace IDs
- [x] Side-by-side demo mode: same question as contractor, manager, executive
- [x] README.md with Mermaid architecture diagram, enforcement layers, quickstart
- [x] docs/architecture.md: components, request flow, design decisions, trade-offs
- [x] docs/deployment-memo.md: 2-page CIO memo with problem, design, results, recommendations
- [x] docs/improvement-log.md with auto-append from eval runner
- [x] 120 unit tests all passing across all 7 phases
