"""Smoke test: verify API key, then run 3 questions x 4 users.

Usage:
    uv run python scripts/smoke_test.py
"""

import sys
import time

# Ensure project root is importable
sys.path.insert(0, ".")

from company.llm import _resolve_provider_model, verify_key

USERS = [
    {
        "label": "Contractor (emp 100)",
        "user_id": 100,
        "employee_id": "MF-0100",
        "role": "contractor",
        "department": "Engineering",
        "groups": [],
    },
    {
        "label": "Manager (emp 10)",
        "user_id": 10,
        "employee_id": "MF-0010",
        "role": "manager",
        "department": "Engineering",
        "groups": ["engineering", "engineering_all"],
    },
    {
        "label": "HR Partner (emp 15)",
        "user_id": 15,
        "employee_id": "MF-0015",
        "role": "hr_partner",
        "department": "HR",
        "groups": ["hr", "hr_all", "hr_full_access"],
    },
    {
        "label": "Executive (emp 1)",
        "user_id": 1,
        "employee_id": "MF-0001",
        "role": "executive",
        "department": "Operations",
        "groups": ["leadership", "board_access", "operations", "operations_all"],
    },
]

QUESTIONS = [
    "How many employees are in the Engineering department?",
    "Show me my salary information.",
    "Search for tickets assigned to me.",
]


def main():
    provider, model = _resolve_provider_model("agent")
    print(f"\n{'=' * 60}")
    print("  Keystone Smoke Test")
    print(f"  Provider: {provider}  Model: {model}")
    print(f"{'=' * 60}\n")

    # Step 1: Verify key
    print("Verifying API key...", end=" ", flush=True)
    ok, msg = verify_key("agent")
    if not ok:
        print(f"FAILED\n  {msg}")
        print("\nSet your API key in .env and try again.")
        sys.exit(1)
    print(f"OK ({msg})")

    # Step 2: Run smoke test
    from agent.graph import run_agent
    from company.principal import Principal

    total = len(USERS) * len(QUESTIONS)
    completed = 0
    results = []
    start = time.time()

    for user in USERS:
        principal = Principal(
            user_id=user["user_id"],
            employee_id=user["employee_id"],
            role=user["role"],
            department=user["department"],
            groups=user["groups"],
        )

        print(f"\n--- {user['label']} ---")

        for question in QUESTIONS:
            completed += 1
            elapsed = time.time() - start
            eta = (elapsed / completed) * (total - completed) if completed > 0 else 0
            print(f"\n  [{completed}/{total}] (ETA {eta:.0f}s) Q: {question}")

            try:
                state = run_agent(question, principal)
                response = state.final_response or state.draft_response or state.error or "(no response)"
                blocked = state.blocked
                tools_used = [tc.tool_name for tc in state.tool_calls]
                policy = "BLOCKED" if blocked else "OK"
            except Exception as e:
                response = f"ERROR: {e}"
                blocked = False
                tools_used = []
                policy = "ERROR"

            # Truncate long responses for display
            display = response[:200] + "..." if len(response) > 200 else response
            print(f"  Policy: {policy}  Tools: {tools_used}")
            print(f"  A: {display}")

            results.append(
                {
                    "user": user["label"],
                    "question": question,
                    "policy": policy,
                    "tools": tools_used,
                    "response_length": len(response),
                    "blocked": blocked,
                }
            )

    # Summary
    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"  Smoke Test Complete — {elapsed:.1f}s total")
    print(f"{'=' * 60}")

    ok_count = sum(1 for r in results if r["policy"] == "OK")
    blocked_count = sum(1 for r in results if r["policy"] == "BLOCKED")
    error_count = sum(1 for r in results if r["policy"] == "ERROR")

    print(f"  OK: {ok_count}  BLOCKED: {blocked_count}  ERROR: {error_count}")
    print()


if __name__ == "__main__":
    main()
