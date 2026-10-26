# Architecture

## Components

### 1. FastAPI Gateway (`api/`)
The single entry point for all requests. Handles JWT authentication, resolves the user's identity from the HR system, and attaches the Principal to every downstream call.

- **Auth flow**: JWT token → decode → employee DB ID → HR lookup → Principal (user_id, role, groups, report_ids)
- **Audit**: Every tool call creates an audit log entry with timestamp, user, tool, arguments, policy decision, and result status
- **No superuser**: The gateway never has elevated permissions. It passes the user's identity unchanged.

### 2. LangGraph Agent (`agent/`)
A 7-node directed graph:

1. **Planner**: Determines which tools to use based on the user's question
2. **Tool Router**: Creates structured ToolCall objects with arguments
3. **Tool Executor**: Runs tools with policy checks, injection scanning, and untrusted data wrapping
4. **Approval**: Interrupts for human approval on write actions
5. **Responder**: Generates the response from tool results
6. **Self-Check**: Verifies grounding and citations
7. **Output Scanner**: Final canary leak check before delivery

### 3. MCP Servers (`mcp_servers/`)
One server per internal system, each exposing read and write tools. Every tool takes a Principal as its first argument (set by the gateway, not the model).

- **HR**: search_employees, get_employee, get_salary, get_reviews, get_leave, get_org_chart
- **Tickets**: search, get, list_comments, update_status (write), add_comment (write)
- **Docs**: search, get, semantic_search (with pre-filtered vector queries)
- **Chat**: list_channels, get_messages, search, post_message (write)
- **CRM**: list_customers, search_deals, get_deal, update_deal_stage (write)

### 4. Postgres with RLS
Row-level security on 11 tables. Each transaction sets `app.user_id`, `app.role`, `app.groups`, and `app.report_ids` via `SET LOCAL`. The application DB role (`keystone_app`) cannot bypass RLS.

### 5. Cerbos Policy Engine (`policy/`)
YAML-based resource policies for 7 resource types. Policy tests cover all allow and deny rules.

### 6. Evaluation Harness (`evals/`)
4 suites with deterministic and LLM-judged scoring, plus a calibration framework.

## Request Flow

```
User → Streamlit UI → FastAPI Gateway
  → JWT decode → HR identity lookup → Principal created
  → Agent.planner() → picks tools
  → Agent.tool_executor() → for each tool:
      → Cerbos policy check (deny → structured refusal)
      → MCP tool invocation with Principal
      → RLS-filtered SQL query
      → Input guard scans result for injections
      → Wraps result as <untrusted_data>
  → Agent.responder() → generates response from tool results
  → Agent.self_check() → verifies grounding
  → Agent.output_scanner() → checks for canary leaks
      → If leak found: block response, log event
      → If clean: deliver response
  → Audit log entry written
```

## Design Decisions and Trade-offs

### Pre-filter vs Post-filter Retrieval
**Decision**: Pre-filter. The vector similarity query includes `WHERE access_groups && :user_groups` before ranking.

**Why**: Post-filtering leaks information. If the model sees "5 results returned, 2 filtered out," it learns that restricted content exists and is relevant. Pre-filtering means unauthorized documents never enter the model's context.

**Trade-off**: The similarity ranking only considers accessible documents, which may miss the globally most-similar document if it's restricted. This is the correct behavior — the user should not know about restricted content.

### Why Permissions Are Not in Prompts
**Decision**: The model never sees permission rules in its system prompt beyond "respect permissions."

**Why**: LLMs can be manipulated through prompt injection, jailbreaking, and social engineering. If the permission matrix is in the prompt, it can be overridden. By enforcing permissions in code (Cerbos + RLS), the model literally cannot access restricted data even if it tries.

### Canary-based Leak Detection
**Decision**: Plant unique canary strings in every restricted record. Scan every output for canaries.

**Why**: Regex-based content detection is fragile — the model can paraphrase or restructure restricted content. But canary strings are exact: if `CANARY-SAL-4471` appears in output for an unauthorized user, that's a deterministic, zero-false-positive leak detection. This makes eval scoring reliable.

**Trade-off**: Canaries are synthetic and wouldn't exist in production data. In production, you'd combine canary testing (in staging) with semantic similarity detection against restricted content.

### Aggregation Leak Protection
**Decision**: Block salary aggregation for teams smaller than 5 members.

**Why**: If a manager has 3 reports and asks for "average salary," the average narrows down individual salaries significantly. The threshold of 5 follows k-anonymity principles.

### Untrusted Data Wrapping
**Decision**: All retrieved content is wrapped in `<untrusted_data>` tags before reaching the model.

**Why**: Makes the boundary between system instructions and external data explicit. The model is instructed to never follow instructions found within untrusted data tags. This provides defense in depth against prompt injection even if individual payloads bypass pattern detection.
