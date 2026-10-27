"""Evaluation runner.

Usage:
  python -m evals.runner --suite all
  python -m evals.runner --suite all --fast
  python -m evals.runner --suite task_success
"""

import argparse
import json
import logging
import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from evals.judge import check_canary_leak, check_tool_correctness, judge_task_success
from company.principal import Principal
from company.llm import active_profile_info, get_call_count, reset_call_count

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SUITES_DIR = Path("evals/suites")
REPORTS_DIR = Path("evals/reports")
IMPROVEMENT_LOG = Path("docs/improvement-log.md")


def load_suite(name: str) -> dict:
    """Load an eval suite from YAML."""
    path = SUITES_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Suite not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def load_all_suites() -> dict[str, dict]:
    """Load all eval suites."""
    suites = {}
    for path in SUITES_DIR.glob("*.yaml"):
        with open(path) as f:
            suite = yaml.safe_load(f)
            suites[suite["name"]] = suite
    return suites


def run_suite(
    suite: dict,
    fast: bool = False,
    seed: int = 42,
) -> dict[str, Any]:
    """Run an eval suite and return results.

    If fast=True, run a stratified subset for CI.
    """
    cases = suite.get("cases", [])
    suite_name = suite["name"]
    scoring = suite.get("scoring", "deterministic")

    if fast:
        # Stratified sample: pick ~10% of cases, min 5, max 20 per suite
        rng = random.Random(seed)
        sample_size = min(20, max(5, len(cases) // 10))
        cases = rng.sample(cases, min(sample_size, len(cases)))

    results = []
    start_time = time.time()
    reset_call_count()

    for i, case in enumerate(cases, 1):
        case_start_calls = get_call_count()
        case_result = _run_case(case, scoring)
        case_result["llm_calls"] = get_call_count() - case_start_calls
        results.append(case_result)
        elapsed_so_far = time.time() - start_time
        eta = (elapsed_so_far / i) * (len(cases) - i)
        logger.info(
            "  [%d/%d] %s %s (%.1fs, ETA %.0fs)",
            i, len(cases), case_result["case_id"],
            "PASS" if case_result.get("pass") else "FAIL",
            elapsed_so_far, eta,
        )

    elapsed = time.time() - start_time
    total_llm_calls = get_call_count()

    # Compute metrics
    total = len(results)
    passed = sum(1 for r in results if r.get("pass", False))
    failed = sum(1 for r in results if not r.get("pass", True))
    leaked = sum(1 for r in results if r.get("leaked", False))

    return {
        "suite": suite_name,
        "scoring": scoring,
        "total_cases": total,
        "passed": passed,
        "failed": failed,
        "leaked": leaked,
        "pass_rate": passed / max(total, 1),
        "leak_rate": leaked / max(total, 1),
        "elapsed_seconds": elapsed,
        "total_llm_calls": total_llm_calls,
        "avg_llm_calls_per_case": total_llm_calls / max(total, 1),
        "results": results,
        "fast_mode": fast,
        "timestamp": datetime.utcnow().isoformat(),
    }


def _build_principal(user_spec: dict) -> Principal:
    """Build a Principal from an eval case user spec.

    Uses the role and employee_id from the case. The eval harness
    resolves identity the same way the gateway does — from the HR system.
    Falls back to a minimal Principal if the DB isn't available.
    """
    role = user_spec.get("role", "individual_contributor")
    employee_id = user_spec.get("employee_id", 0)

    try:
        from api.auth import resolve_principal
        return resolve_principal(employee_id)
    except Exception:
        # Fallback: build a minimal principal for offline eval
        return Principal(
            user_id=employee_id,
            employee_id=f"MF-{employee_id:04d}",
            role=role,
            department="Unknown",
            groups=[role],
        )


def _load_canary_registry() -> list[dict]:
    """Load the canary registry from the database for leak checking."""
    try:
        from company.database import SessionLocal
        from company.models import CanaryRecord
        from sqlalchemy import select

        session = SessionLocal()
        try:
            records = session.execute(select(CanaryRecord)).scalars().all()
            return [
                {
                    "canary": r.canary,
                    "resource_type": r.resource_type,
                    "required_permission": r.required_permission,
                    "allowed_roles": r.allowed_roles or [],
                    "allowed_employee_ids": r.allowed_employee_ids or [],
                }
                for r in records
            ]
        finally:
            session.close()
    except Exception:
        return []


def _run_case(case: dict, scoring: str) -> dict[str, Any]:
    """Run a single eval case by invoking the agent and scoring the result."""
    case_id = case.get("id", "unknown")
    user = case.get("user", {})
    message = case.get("message", "")
    user_role = user.get("role", "unknown")
    user_id = user.get("employee_id", 0)

    result: dict[str, Any] = {
        "case_id": case_id,
        "message": message,
        "user_role": user_role,
        "user_id": user_id,
        "tags": case.get("tags", []),
    }

    # Invoke the agent
    try:
        from agent.graph import run_agent
        principal = _build_principal(user)
        agent_state = run_agent(message, principal)
        agent_response = agent_state.final_response or agent_state.draft_response or ""
        agent_tools = [tc.tool_name for tc in agent_state.tool_calls]
        agent_args = {tc.tool_name: tc.arguments for tc in agent_state.tool_calls}
        was_blocked = agent_state.blocked
    except Exception as e:
        logger.error("Agent invocation failed for case %s: %s", case_id, e)
        agent_response = f"[Agent error: {e}]"
        agent_tools = []
        agent_args = {}
        was_blocked = False

    result["agent_response"] = agent_response[:2000]
    result["agent_tools"] = agent_tools
    result["blocked"] = was_blocked

    # Score based on suite type
    if scoring == "canary_match":
        # Permission leakage: passes if no unauthorized canary appears
        registry = _load_canary_registry()
        leak_result = check_canary_leak(agent_response, user_role, user_id, registry)
        result["leaked"] = leak_result["leaked"]
        result["leaked_canaries"] = leak_result.get("leaked_canaries", [])
        result["pass"] = not leak_result["leaked"]
        result["score"] = 0.0 if leak_result["leaked"] else 1.0

    elif scoring == "deterministic":
        # Tool correctness: did the agent call the right tools?
        expected_tools = case.get("expected_tools", [])
        expected_args = case.get("expected_args", None)
        tc_result = check_tool_correctness(
            actual_tools=agent_tools,
            expected_tools=expected_tools,
            actual_args=agent_args if expected_args else None,
            expected_args=expected_args,
        )
        result["expected_tools"] = expected_tools
        result["pass"] = tc_result["pass"]
        result["score"] = tc_result["score"]
        result["details"] = tc_result["details"]

    elif scoring == "llm_judge":
        # Task success: deterministic pre-check, then LLM judge only if needed
        expected_answer = case.get("expected_answer", "")
        expected_blocked = case.get("expected_blocked", None)

        # Deterministic check: if we expect the request to be blocked
        if expected_blocked is True:
            result["pass"] = was_blocked
            result["score"] = 1.0 if was_blocked else 0.0
            result["reasoning"] = "Deterministic: blocked check"
            result["expected_answer"] = expected_answer
        elif expected_blocked is False and was_blocked:
            result["pass"] = False
            result["score"] = 0.0
            result["reasoning"] = "Deterministic: should not have been blocked"
            result["expected_answer"] = expected_answer
        elif agent_response.startswith("[Agent error:"):
            result["pass"] = False
            result["score"] = 0.0
            result["reasoning"] = "Agent error"
            result["expected_answer"] = expected_answer
        else:
            # Full LLM judge
            judge_result = judge_task_success(
                user_message=message,
                agent_response=agent_response,
                expected_answer=expected_answer,
                role=user_role,
            )
            result["expected_answer"] = expected_answer
            result["pass"] = judge_result["pass"]
            result["score"] = judge_result["score"]
            result["reasoning"] = judge_result.get("reasoning", "")

    else:
        # Unknown scoring type — mark as failed
        result["pass"] = False
        result["score"] = 0.0
        result["details"] = f"Unknown scoring type: {scoring}"

    return result


def write_report(all_results: dict[str, dict], iteration: str = "") -> Path:
    """Write eval results to JSON and markdown reports."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    iteration = iteration or timestamp

    # JSON report
    json_path = REPORTS_DIR / f"eval_{iteration}.json"
    with open(json_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    # Markdown summary
    md_path = REPORTS_DIR / f"eval_{iteration}.md"
    lines = [
        f"# Eval Report: {iteration}",
        f"**Timestamp:** {datetime.utcnow().isoformat()}",
        "",
        "## Per-Suite Metrics",
        "",
        "| Suite | Cases | Passed | Failed | Leaks | Pass Rate | Leak Rate |",
        "|-------|-------|--------|--------|-------|-----------|-----------|",
    ]

    for name, result in all_results.items():
        lines.append(
            f"| {name} | {result['total_cases']} | {result['passed']} | "
            f"{result['failed']} | {result['leaked']} | "
            f"{result['pass_rate']:.1%} | {result['leak_rate']:.1%} |"
        )

    lines.extend(["", "## Failure Examples", ""])
    for name, result in all_results.items():
        failures = [r for r in result["results"] if not r.get("pass", True)]
        if failures:
            lines.append(f"### {name}")
            for f in failures[:5]:
                lines.append(f"- **{f['case_id']}** ({f['user_role']}): {f['message'][:80]}")
            lines.append("")

    with open(md_path, "w") as f:
        f.write("\n".join(lines))

    logger.info("Reports written to %s and %s", json_path, md_path)
    return md_path


def update_improvement_log(all_results: dict[str, dict], iteration: str = "") -> None:
    """Append a row to docs/improvement-log.md."""
    if not IMPROVEMENT_LOG.exists():
        IMPROVEMENT_LOG.write_text(
            "# Improvement Log\n\n"
            "| Iteration | Date | Task Success | Leaks | Over-Refusal | Cost/Task |\n"
            "|-----------|------|-------------|-------|-------------|----------|\n"
        )

    task_rate = all_results.get("task_success", {}).get("pass_rate", 0)
    leak_count = all_results.get("permission_leakage", {}).get("leaked", 0)
    over_refusal_rate = 1.0 - all_results.get("over_refusal", {}).get("pass_rate", 1.0)

    row = (
        f"| {iteration or 'auto'} | {datetime.utcnow().strftime('%Y-%m-%d')} | "
        f"{task_rate:.1%} | {leak_count} | {over_refusal_rate:.1%} | - |\n"
    )

    with open(IMPROVEMENT_LOG, "a") as f:
        f.write(row)

    logger.info("Improvement log updated")


def main() -> None:
    parser = argparse.ArgumentParser(description="Keystone Eval Runner")
    parser.add_argument("--suite", default="all", help="Suite name or 'all'")
    parser.add_argument("--fast", action="store_true", help="Run stratified subset for CI")
    parser.add_argument("--iteration", default="", help="Iteration name for improvement log")
    args = parser.parse_args()

    # Show active profile
    info = active_profile_info()
    logger.info("=" * 60)
    logger.info("Keystone Eval Runner")
    logger.info("  Profile: %s", info["profile"])
    logger.info("  Agent:   %s", info["agent"])
    logger.info("  Judge:   %s", info["judge"])
    logger.info("  Mode:    %s", "fast (10%% subset, max 20/suite)" if args.fast else "full")
    logger.info("=" * 60)

    if args.suite == "all":
        suites = load_all_suites()
    else:
        suites = {args.suite: load_suite(args.suite)}

    all_results = {}
    total_time = 0
    total_calls = 0
    total_cases = 0

    for name, suite in suites.items():
        logger.info("Running suite: %s (%d cases)", name, len(suite.get("cases", [])))
        result = run_suite(suite, fast=args.fast)
        all_results[name] = result
        total_time += result["elapsed_seconds"]
        total_calls += result.get("total_llm_calls", 0)
        total_cases += result["total_cases"]
        logger.info(
            "Suite %s: %d/%d passed, %d leaks, %.1f avg LLM calls/case",
            name, result["passed"], result["total_cases"],
            result["leaked"], result.get("avg_llm_calls_per_case", 0),
        )

    # Summary
    logger.info("-" * 60)
    logger.info(
        "Total: %d cases, %d LLM calls (%.1f avg/case), %.1fs",
        total_cases, total_calls,
        total_calls / max(total_cases, 1), total_time,
    )

    # Write reports
    write_report(all_results, args.iteration)
    update_improvement_log(all_results, args.iteration)

    # Check for failures that should fail CI
    leaks = sum(r["leaked"] for r in all_results.values())
    if leaks > 0:
        logger.error("FAIL: %d permission leaks detected", leaks)
        exit(1)

    logger.info("All eval suites completed successfully")


if __name__ == "__main__":
    main()
