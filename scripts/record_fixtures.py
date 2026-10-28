"""Record replay fixtures: 7 scenarios x 4 personas + compare mode.

Runs each scenario through the agent for each persona, captures SSE events,
and writes JSON fixtures for the UI replay mode.

Usage:
  PROFILE=local python -m scripts.record_fixtures
  PROFILE=local python -m scripts.record_fixtures --compare  # also record compare mode
"""

import argparse
import json
import logging
import time
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

FIXTURES_DIR = Path("ui-web/public/fixtures")

# 7 representative scenarios
SCENARIOS = [
    {"id": "salary_own", "message": "What is my salary?"},
    {"id": "salary_other", "message": "Show me the salary for employee 44"},
    {"id": "org_chart", "message": "Show me the org chart"},
    {"id": "ticket_search", "message": "Search for high priority open tickets"},
    {"id": "deal_search", "message": "What open deals does the Sales team have?"},
    {"id": "chat_search", "message": "Search chat for mentions of the quarterly review"},
    {"id": "hr_complaint", "message": "Show me recent HR complaint tickets"},
]

# 4 personas covering the key role types
PERSONAS = [
    {"key": "ceo", "role": "executive", "employee_id": 1},
    {"key": "engineer", "role": "individual_contributor", "employee_id": 22},
    {"key": "hr_partner", "role": "hr_partner", "employee_id": 5},
    {"key": "contractor", "role": "contractor", "employee_id": 61},
]


def record_fixture(message: str, employee_id: int) -> dict:
    """Run the agent and capture the result as a replay fixture."""
    from agent.graph import run_agent
    from api.auth import resolve_principal

    principal = resolve_principal(employee_id)
    start = time.time()

    try:
        state = run_agent(message, principal)
    except Exception as e:
        logger.error("Agent error for emp %d: %s", employee_id, e)
        return {"error": str(e)}

    elapsed = time.time() - start

    events = []

    # Node events
    for node_name in state.node_path:
        event = {"type": "node", "node": node_name, "data": {}}
        if node_name == "planner":
            event["data"] = {"plan": state.plan, "tools": state.planned_tools}
        events.append(event)

    # Tool events
    for tc in state.tool_calls:
        events.append({"type": "tool_start", "tool": tc.tool_name, "arguments": tc.arguments})
        if tc.result is not None:
            events.append({
                "type": "tool_result",
                "tool": tc.tool_name,
                "success": tc.result.get("success", False),
                "data": tc.result.get("data"),
            })

    # Approval
    if state.needs_approval and state.pending_action:
        pa = state.pending_action
        events.append({"type": "approval_needed", "tool": pa.tool_name, "arguments": pa.arguments})

    # Sources
    if state.sources:
        events.append({
            "type": "sources",
            "sources": [{"type": s.source_type, "id": s.source_id, "title": s.title} for s in state.sources],
        })

    # Response or blocked
    if state.blocked:
        events.append({"type": "blocked", "reason": state.block_reason})
    else:
        response_text = state.final_response or state.draft_response or ""
        events.append({"type": "response", "text": response_text})

    events.append({"type": "done", "trace_id": state.trace_id})

    return {
        "events": events,
        "elapsed_seconds": round(elapsed, 2),
        "principal": {
            "user_id": principal.user_id,
            "role": principal.role,
            "department": principal.department,
        },
    }


def record_compare(scenario: dict) -> dict:
    """Record the same scenario for all personas (compare mode fixture)."""
    results = {}
    for persona in PERSONAS:
        logger.info("    Compare: %s", persona["key"])
        fixture = record_fixture(scenario["message"], persona["employee_id"])
        results[persona["key"]] = fixture
    return results


def main():
    parser = argparse.ArgumentParser(description="Record replay fixtures")
    parser.add_argument("--compare", action="store_true", help="Also record compare-mode fixtures")
    args = parser.parse_args()

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    all_fixtures = {}
    total = len(SCENARIOS) * len(PERSONAS)
    done = 0

    for scenario in SCENARIOS:
        sid = scenario["id"]
        all_fixtures[sid] = {}

        for persona in PERSONAS:
            done += 1
            logger.info("[%d/%d] %s x %s", done, total, sid, persona["key"])
            fixture = record_fixture(scenario["message"], persona["employee_id"])
            all_fixtures[sid][persona["key"]] = fixture

            # Write individual fixture
            fpath = FIXTURES_DIR / f"{sid}_{persona['key']}.json"
            with open(fpath, "w") as f:
                json.dump(fixture, f, indent=2, default=str)

        # Compare mode
        if args.compare:
            logger.info("  Recording compare mode for %s", sid)
            compare = record_compare(scenario)
            cpath = FIXTURES_DIR / f"{sid}_compare.json"
            with open(cpath, "w") as f:
                json.dump(compare, f, indent=2, default=str)

    # Write manifest
    manifest = {
        "recorded_at": datetime.utcnow().isoformat(),
        "scenarios": [s["id"] for s in SCENARIOS],
        "personas": [p["key"] for p in PERSONAS],
        "total_fixtures": done,
    }
    with open(FIXTURES_DIR / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    logger.info("Done! %d fixtures written to %s", done, FIXTURES_DIR)


if __name__ == "__main__":
    main()
