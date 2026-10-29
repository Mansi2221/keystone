"""Convert a failed agent trace into a new eval case.

Usage: python -m evals.trace_to_eval --trace-id <id> --suite permission_leakage
"""

import argparse
import json
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

SUITES_DIR = Path("evals/suites")


def trace_to_case(
    trace_id: str,
    suite: str,
    user_message: str,
    user_role: str,
    user_id: int,
    agent_response: str,
    failure_reason: str,
) -> dict:
    """Convert a trace into an eval case."""
    suite_path = SUITES_DIR / f"{suite}.yaml"
    with open(suite_path) as f:
        suite_data = yaml.safe_load(f)

    # Generate next case ID
    existing_ids = [c["id"] for c in suite_data.get("cases", [])]
    prefix = {"permission_leakage": "pl", "task_success": "ts", "tool_correctness": "tc", "over_refusal": "or"}.get(suite, "xx")
    max_num = max((int(cid.split("-")[1]) for cid in existing_ids if cid.startswith(prefix)), default=0)
    new_id = f"{prefix}-{max_num + 1:03d}"

    case = {
        "id": new_id,
        "user": {"role": user_role, "employee_id": user_id},
        "message": user_message,
        "tags": ["from_trace", trace_id],
        "note": f"Auto-generated from trace {trace_id}: {failure_reason}",
    }

    if suite == "permission_leakage":
        case["expected_behavior"] = "deny"
        case["canary_must_not_appear"] = True
    elif suite == "task_success":
        case["expected_answer"] = "[FILL IN expected answer]"
        case["expected_tools"] = []
    elif suite == "over_refusal":
        case["expected_behavior"] = "allow"
        case["must_succeed"] = True

    # Append to suite
    suite_data.setdefault("cases", []).append(case)
    with open(suite_path, "w") as f:
        yaml.dump(suite_data, f, default_flow_style=False, sort_keys=False)

    logger.info("Added case %s to suite %s", new_id, suite)
    return case


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert failed trace to eval case")
    parser.add_argument("--trace-id", required=True)
    parser.add_argument("--suite", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--response", default="")
    parser.add_argument("--reason", default="Failed trace")
    args = parser.parse_args()

    case = trace_to_case(
        trace_id=args.trace_id,
        suite=args.suite,
        user_message=args.message,
        user_role=args.role,
        user_id=args.user_id,
        agent_response=args.response,
        failure_reason=args.reason,
    )
    print(json.dumps(case, indent=2))


if __name__ == "__main__":
    main()
