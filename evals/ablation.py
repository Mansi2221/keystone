"""Ablation study runner.

Generates a fixed, stratified ablation set and runs iterations v0-v4,
progressively enabling protection layers.

Usage:
  python -m evals.ablation --generate          # create evals/sets/ablation.jsonl
  python -m evals.ablation --run all           # run v0-v4
  python -m evals.ablation --run v0            # run a single iteration
  python -m evals.ablation --report            # print results table
"""

import argparse
import hashlib
import json
import logging
import random
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ABLATION_SET = Path("evals/sets/ablation.jsonl")
SUITES_DIR = Path("evals/suites")
REPORTS_DIR = Path("evals/reports")
PROGRESS_DIR = REPORTS_DIR / "progress"
IMPROVEMENT_LOG = Path("docs/improvement-log.md")
SEED = 42

# ── Code and data integrity ────────────────────────────────────

# Files whose content affects ablation results.  If any of them change
# mid-run, the results are invalid.
INTEGRITY_FILES = sorted(
    [
        "agent/graph.py",
        "agent/guards.py",
        "agent/prompts.py",
        "company/config.py",
        "company/principal.py",
        "company/rls.py",
        "company/seed.py",
        "mcp_servers/docs/server.py",
        "mcp_servers/hr/server.py",
        "mcp_servers/crm/server.py",
        "mcp_servers/tickets/server.py",
        "mcp_servers/chat/server.py",
        "policy/resource_policies/document.yaml",
        "policy/resource_policies/salary.yaml",
        "policy/resource_policies/deal.yaml",
        "policy/resource_policies/ticket.yaml",
        "policy/resource_policies/chat.yaml",
        "evals/sets/ablation.jsonl",
    ]
)


def _git_commit_hash() -> str:
    """Return the short git commit hash of HEAD."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _data_checksum() -> str:
    """SHA-256 over all INTEGRITY_FILES to detect mid-run changes."""
    h = hashlib.sha256()
    for rel in INTEGRITY_FILES:
        p = Path(rel)
        if p.exists():
            h.update(rel.encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _check_integrity(expected_commit: str, expected_checksum: str) -> None:
    """Raise if code/data changed since the run started."""
    current_commit = _git_commit_hash()
    current_checksum = _data_checksum()
    if current_commit != expected_commit:
        raise RuntimeError(
            f"Git commit changed during ablation: started on {expected_commit}, "
            f"now on {current_commit}.  Results would be invalid — aborting."
        )
    if current_checksum != expected_checksum:
        raise RuntimeError(
            f"Code/data checksum changed during ablation: started with "
            f"{expected_checksum}, now {current_checksum}.  Results would be "
            f"invalid — aborting.  Changed files in: {INTEGRITY_FILES}"
        )


# ── Iteration definitions ───────────────────────────────────────
# Each iteration enables a cumulative set of protections.

ITERATIONS = {
    "positive_control": {
        "note": "all protections off + no permission rules in prompt",
        "policy_checks": False,
        "rls": False,
        "retrieval_prefilter": False,
        "aggregation_guard": False,
        "injection_scanner": False,
        "output_scanner": False,
        "system_prompt_rules": False,
    },
    "v0": {
        "note": "all protections off; system-prompt only",
        "policy_checks": False,
        "rls": False,
        "retrieval_prefilter": False,
        "aggregation_guard": False,
        "injection_scanner": False,
        "output_scanner": False,
    },
    "v1": {
        "note": "+ policy checks",
        "policy_checks": True,
        "rls": False,
        "retrieval_prefilter": False,
        "aggregation_guard": False,
        "injection_scanner": False,
        "output_scanner": False,
    },
    "v2": {
        "note": "+ RLS and pre-filtered retrieval",
        "policy_checks": True,
        "rls": True,
        "retrieval_prefilter": True,
        "aggregation_guard": False,
        "injection_scanner": False,
        "output_scanner": False,
    },
    "v3": {
        "note": "+ aggregation guard and injection scanner",
        "policy_checks": True,
        "rls": True,
        "retrieval_prefilter": True,
        "aggregation_guard": True,
        "injection_scanner": True,
        "output_scanner": False,
    },
    "v4": {
        "note": "+ output scanner (everything on)",
        "policy_checks": True,
        "rls": True,
        "retrieval_prefilter": True,
        "aggregation_guard": True,
        "injection_scanner": True,
        "output_scanner": True,
    },
    "v5": {
        "note": "v4 + grounding checker + value-leak fix",
        "policy_checks": True,
        "rls": True,
        "retrieval_prefilter": True,
        "aggregation_guard": True,
        "injection_scanner": True,
        "output_scanner": True,
    },
}

ITERATION_ORDER = ["v0", "v1", "v2", "v3", "v4", "v5"]

# ── Attack type tags used for leak breakdown ────────────────────

ATTACK_TYPES = [
    "direct",
    "social_engineering",
    "role_impersonation",
    "aggregation",
    "prompt_injection",
    "cross_system",
    "private_access",
    "bulk_extraction",
]


# ================================================================
# Generate the fixed ablation set
# ================================================================


def generate_ablation_set() -> Path:
    """Create a fixed, stratified ablation set from YAML suites."""
    rng = random.Random(SEED)

    # Load suites
    leak_cases = _load_suite_cases("permission_leakage")
    task_cases = _load_suite_cases("task_success")
    or_cases = _load_suite_cases("over_refusal")

    selected: list[dict] = []

    # 150 leak cases, stratified by attack type
    leak_by_type: dict[str, list[dict]] = {}
    for c in leak_cases:
        for tag in c.get("tags", []):
            if tag in ATTACK_TYPES:
                leak_by_type.setdefault(tag, []).append(c)
                break

    per_type = 150 // len(leak_by_type) if leak_by_type else 19
    leak_selected: list[dict] = []
    for atype, cases in leak_by_type.items():
        sample = rng.sample(cases, min(per_type, len(cases)))
        for c in sample:
            c["_suite"] = "permission_leakage"
            c["_scoring"] = "canary_match"
        leak_selected.extend(sample)
    # Top up to 150 from any type
    remaining = [c for c in leak_cases if c not in leak_selected]
    while len(leak_selected) < 150 and remaining:
        c = remaining.pop(rng.randint(0, len(remaining) - 1))
        c["_suite"] = "permission_leakage"
        c["_scoring"] = "canary_match"
        leak_selected.append(c)
    selected.extend(leak_selected[:150])

    # 40 task cases
    task_sample = rng.sample(task_cases, min(40, len(task_cases)))
    for c in task_sample:
        c["_suite"] = "task_success"
        c["_scoring"] = "llm_judge"
    selected.extend(task_sample)

    # 20 over-refusal cases
    or_sample = rng.sample(or_cases, min(20, len(or_cases)))
    for c in or_sample:
        c["_suite"] = "over_refusal"
        c["_scoring"] = "llm_judge"
    selected.extend(or_sample)

    # Renumber with ablation IDs
    for i, c in enumerate(selected, 1):
        c["_ablation_id"] = f"abl-{i:03d}"

    # Write JSONL
    ABLATION_SET.parent.mkdir(parents=True, exist_ok=True)
    with open(ABLATION_SET, "w") as f:
        for c in selected:
            f.write(json.dumps(c, default=str) + "\n")

    # Summary
    suites = {}
    for c in selected:
        s = c["_suite"]
        suites[s] = suites.get(s, 0) + 1
    logger.info("Ablation set: %d cases (%s) -> %s", len(selected), suites, ABLATION_SET)

    # Attack type breakdown
    atk_counts: dict[str, int] = {}
    for c in selected:
        if c["_suite"] == "permission_leakage":
            for tag in c.get("tags", []):
                if tag in ATTACK_TYPES:
                    atk_counts[tag] = atk_counts.get(tag, 0) + 1
                    break
    for atype in ATTACK_TYPES:
        logger.info("  %-20s %d", atype, atk_counts.get(atype, 0))

    return ABLATION_SET


def _load_suite_cases(name: str) -> list[dict]:
    path = SUITES_DIR / f"{name}.yaml"
    with open(path) as f:
        suite = yaml.safe_load(f)
    return suite.get("cases", [])


def load_ablation_set() -> list[dict]:
    """Load the fixed ablation set."""
    if not ABLATION_SET.exists():
        raise FileNotFoundError("Ablation set not found. Run: python -m evals.ablation --generate")
    cases = []
    with open(ABLATION_SET) as f:
        for line in f:
            if line.strip():
                cases.append(json.loads(line))
    return cases


# ================================================================
# Run a single ablation iteration
# ================================================================


def _configure_protections(iteration: str) -> None:
    """Set ablation flags for the given iteration."""
    from company.config import settings

    cfg = ITERATIONS[iteration]

    settings.eval_mode = True
    settings.ablation_policy_checks = cfg["policy_checks"]
    settings.ablation_rls = cfg["rls"]
    settings.ablation_retrieval_prefilter = cfg["retrieval_prefilter"]
    settings.ablation_aggregation_guard = cfg["aggregation_guard"]
    settings.ablation_injection_scanner = cfg["injection_scanner"]
    settings.ablation_output_scanner = cfg["output_scanner"]
    settings.ablation_system_prompt_rules = cfg.get("system_prompt_rules", True)

    # Toggle RLS at the database level
    from company.rls import disable_all_rls, enable_all_rls

    if cfg["rls"]:
        enable_all_rls()
    else:
        disable_all_rls()

    enabled = [k for k, v in cfg.items() if k != "note" and v is True]
    logger.info("Iteration %s: %s", iteration, cfg["note"])
    logger.info("  Enabled: %s", enabled or ["(none)"])


class _CaseTimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise _CaseTimeoutError()


def _load_progress(iteration: str) -> list[dict]:
    """Load completed case results from the progress file."""
    progress_file = PROGRESS_DIR / f"{iteration}.jsonl"
    if not progress_file.exists():
        return []
    results = []
    with open(progress_file) as f:
        for line in f:
            if line.strip():
                results.append(json.loads(line))
    logger.info("Resuming %s: %d cases already completed", iteration, len(results))
    return results


def _append_progress(iteration: str, case_result: dict) -> None:
    """Append a completed case to the progress file."""
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    progress_file = PROGRESS_DIR / f"{iteration}.jsonl"
    with open(progress_file, "a") as f:
        f.write(json.dumps(case_result, default=str) + "\n")


def _clear_progress(iteration: str) -> None:
    """Remove the progress file after a successful iteration."""
    progress_file = PROGRESS_DIR / f"{iteration}.jsonl"
    if progress_file.exists():
        progress_file.unlink()


def run_iteration(
    iteration: str,
    cases: list[dict],
    commit_hash: str = "",
    data_checksum: str = "",
    case_timeout: int = 0,
) -> dict[str, Any]:
    """Run a single ablation iteration and return results.

    Args:
        case_timeout: Per-case timeout in seconds (0 = no limit).
            Timed-out cases are marked as FAIL with timed_out=True.
    """
    from company.llm import get_call_count, reset_call_count
    from evals.runner import _run_case

    _configure_protections(iteration)
    reset_call_count()
    start = time.time()

    # Resume from progress file if available
    prior_results = _load_progress(iteration)
    completed_ids = {r.get("_ablation_id") or r["case_id"] for r in prior_results}
    results = list(prior_results)

    # Install timeout handler if requested
    old_handler = None
    if case_timeout > 0:
        old_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, _timeout_handler)

    try:
        for i, case in enumerate(cases, 1):
            ablation_id = case.get("_ablation_id", "")
            case_id = ablation_id or case.get("id", f"case-{i}")
            if case_id in completed_ids:
                continue  # Already completed in a prior run

            # Integrity check every 50 cases
            if commit_hash and i % 50 == 0:
                _check_integrity(commit_hash, data_checksum)

            scoring = case.get("_scoring", "canary_match")
            case_start = get_call_count()

            if case_timeout > 0:
                signal.alarm(case_timeout)
            try:
                case_result = _run_case(case, scoring)
            except _CaseTimeoutError:
                logger.warning("  [%d/%d] %s TIMEOUT (%ds)", i, len(cases), case_id, case_timeout)
                case_result = {
                    "case_id": case.get("id", "unknown"),
                    "pass": False,
                    "score": 0.0,
                    "timed_out": True,
                    "message": case.get("message", ""),
                    "user_role": case.get("user", {}).get("role", "unknown"),
                    "user_id": case.get("user", {}).get("employee_id", 0),
                    "tags": case.get("tags", []),
                    "agent_response": "[Case timed out]",
                    "agent_tools": [],
                    "tool_call_count": 0,
                    "called_tools": False,
                    "blocked": False,
                }
            finally:
                if case_timeout > 0:
                    signal.alarm(0)

            case_result["llm_calls"] = get_call_count() - case_start
            case_result["_ablation_id"] = ablation_id
            case_result["_suite"] = case.get("_suite", "")
            results.append(case_result)

            # Save progress incrementally
            _append_progress(iteration, case_result)

            status = "PASS" if case_result.get("pass") else ("TIMEOUT" if case_result.get("timed_out") else "FAIL")
            elapsed = time.time() - start
            completed = len(results)
            eta = (elapsed / max(completed - len(prior_results), 1)) * (len(cases) - completed)
            logger.info(
                "  [%d/%d] %s %s (%.0fs elapsed, ETA %.0fs)",
                completed,
                len(cases),
                case_id,
                status,
                elapsed,
                eta,
            )
    finally:
        if old_handler is not None:
            signal.signal(signal.SIGALRM, old_handler)

    # Iteration complete — clean up progress file
    _clear_progress(iteration)

    elapsed = time.time() - start
    total_calls = get_call_count()

    # Compute metrics
    leak_results = [r for r in results if r["_suite"] == "permission_leakage"]
    task_results = [r for r in results if r["_suite"] == "task_success"]
    or_results = [r for r in results if r["_suite"] == "over_refusal"]

    leaked_total = sum(1 for r in leak_results if r.get("leaked", False))
    exposed_total = sum(1 for r in leak_results if r.get("exposed", False))
    task_passed = sum(1 for r in task_results if r.get("pass", False))
    or_passed = sum(1 for r in or_results if r.get("pass", False))

    # Tool-call rate
    called_tools_count = sum(1 for r in results if r.get("called_tools", False))
    tool_call_rate = called_tools_count / max(len(results), 1)

    # Leak breakdown by attack type
    leak_by_attack: dict[str, dict[str, int]] = {}
    for r in leak_results:
        for tag in r.get("tags", []):
            if tag in ATTACK_TYPES:
                entry = leak_by_attack.setdefault(tag, {"total": 0, "leaked": 0, "exposed": 0})
                entry["total"] += 1
                if r.get("leaked", False):
                    entry["leaked"] += 1
                if r.get("exposed", False):
                    entry["exposed"] += 1
                break

    return {
        "iteration": iteration,
        "note": ITERATIONS[iteration]["note"],
        "git_commit": commit_hash,
        "data_checksum": data_checksum,
        "total_cases": len(results),
        "leaks": leaked_total,
        "exposed": exposed_total,
        "leak_total": len(leak_results),
        "leak_rate": leaked_total / max(len(leak_results), 1),
        "exposure_rate": exposed_total / max(len(leak_results), 1),
        "leak_by_attack": leak_by_attack,
        "task_passed": task_passed,
        "task_total": len(task_results),
        "task_rate": task_passed / max(len(task_results), 1),
        "or_passed": or_passed,
        "or_total": len(or_results),
        "or_rate": or_passed / max(len(or_results), 1),
        "tool_call_rate": tool_call_rate,
        "elapsed_seconds": elapsed,
        "total_llm_calls": total_calls,
        "results": results,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ================================================================
# Reporting
# ================================================================


def write_ablation_report(all_iterations: dict[str, dict]) -> Path:
    """Write ablation results to JSON and markdown."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    # JSON
    json_path = REPORTS_DIR / f"ablation_{ts}.json"
    with open(json_path, "w") as f:
        json.dump(all_iterations, f, indent=2, default=str)

    # Markdown
    md_path = REPORTS_DIR / f"ablation_{ts}.md"
    lines = [
        "# Ablation Study Results",
        f"**Generated:** {datetime.utcnow().isoformat()}",
        "",
        "## Summary",
        "",
        "| Iter | Protections | Leaks | Leak Rate | Task Success | Over-Refusal | Time |",
        "|------|-------------|-------|-----------|-------------|-------------|------|",
    ]
    for v in ITERATION_ORDER:
        if v not in all_iterations:
            continue
        r = all_iterations[v]
        lines.append(
            f"| {v} | {r['note']} | {r['leaks']}/{r['leak_total']} | "
            f"{r['leak_rate']:.1%} | {r['task_passed']}/{r['task_total']} ({r['task_rate']:.1%}) | "
            f"{r['or_passed']}/{r['or_total']} ({r['or_rate']:.1%}) | {r['elapsed_seconds']:.0f}s |"
        )

    lines.extend(["", "## Leaks by Attack Type", ""])
    header = "| Attack Type |"
    sep = "|------------|"
    for v in ITERATION_ORDER:
        if v in all_iterations:
            header += f" {v} |"
            sep += "-----|"
    lines.append(header)
    lines.append(sep)

    for atype in ATTACK_TYPES:
        row = f"| {atype} |"
        for v in ITERATION_ORDER:
            if v not in all_iterations:
                continue
            entry = all_iterations[v].get("leak_by_attack", {}).get(atype, {})
            leaked = entry.get("leaked", 0)
            total = entry.get("total", 0)
            row += f" {leaked}/{total} |"
        lines.append(row)

    with open(md_path, "w") as f:
        f.write("\n".join(lines))

    logger.info("Ablation reports: %s, %s", json_path, md_path)
    return md_path


def update_improvement_log_ablation(iteration: str, result: dict) -> None:
    """Append an ablation iteration to the improvement log."""
    if not IMPROVEMENT_LOG.exists():
        IMPROVEMENT_LOG.write_text(
            "# Improvement Log\n\n"
            "| Iteration | Date | Task Success | Leaks | Over-Refusal | Cost/Task | Note |\n"
            "|-----------|------|-------------|-------|-------------|----------|------|\n"
        )

    avg_calls = result["total_llm_calls"] / max(result["total_cases"], 1)
    row = (
        f"| {iteration} | {datetime.utcnow().strftime('%Y-%m-%d')} | "
        f"{result['task_rate']:.1%} | {result['leaks']} | "
        f"{1.0 - result['or_rate']:.1%} | {avg_calls:.1f} calls | "
        f"{result['note']} |\n"
    )

    with open(IMPROVEMENT_LOG, "a") as f:
        f.write(row)


def print_results_table(all_iterations: dict[str, dict]) -> None:
    """Print a compact results table to stdout."""
    print()
    print(f"{'Iter':<4} {'Protections':<45} {'Leaks':>8} {'Task':>12} {'Over-Ref':>12}")
    print("-" * 85)
    for v in ITERATION_ORDER:
        if v not in all_iterations:
            continue
        r = all_iterations[v]
        print(
            f"{v:<4} {r['note']:<45} "
            f"{r['leaks']:>3}/{r['leak_total']:<3} "
            f"{r['task_passed']:>2}/{r['task_total']:<2} ({r['task_rate']:.0%})"
            f"{r['or_passed']:>4}/{r['or_total']:<2} ({r['or_rate']:.0%})"
        )

    print()
    print("Leaks by attack type:")
    header = f"  {'Attack Type':<22}"
    for v in ITERATION_ORDER:
        if v in all_iterations:
            header += f" {v:>6}"
    print(header)
    print("  " + "-" * (22 + 7 * len(all_iterations)))
    for atype in ATTACK_TYPES:
        row = f"  {atype:<22}"
        for v in ITERATION_ORDER:
            if v not in all_iterations:
                continue
            entry = all_iterations[v].get("leak_by_attack", {}).get(atype, {})
            leaked = entry.get("leaked", 0)
            total = entry.get("total", 0)
            row += f" {leaked:>2}/{total:<2} "

        print(row)
    print()


# ================================================================
# Main
# ================================================================


def main() -> None:
    parser = argparse.ArgumentParser(description="Ablation study runner")
    parser.add_argument("--generate", action="store_true", help="Generate the fixed ablation set")
    parser.add_argument("--run", default="", help="Run iteration(s): v0, v1, ..., v5, or 'all'")
    parser.add_argument("--report", default="", help="Print results from a JSON report file")
    parser.add_argument("--case-timeout", type=int, default=0, help="Per-case timeout in seconds (0=unlimited)")
    args = parser.parse_args()

    if args.generate:
        generate_ablation_set()
        return

    if args.report:
        path = Path(args.report)
        with open(path) as f:
            data = json.load(f)
        print_results_table(data)
        return

    if args.run:
        from company.llm import active_profile_info

        info = active_profile_info()

        # Capture code-freeze snapshot
        run_commit = _git_commit_hash()
        run_checksum = _data_checksum()

        logger.info("=" * 60)
        logger.info("Ablation Study")
        logger.info("  Profile:   %s", info["profile"])
        logger.info("  Agent:     %s", info["agent"])
        logger.info("  Judge:     %s", info["judge"])
        logger.info("  Commit:    %s", run_commit)
        logger.info("  Checksum:  %s", run_checksum)
        logger.info("=" * 60)

        cases = load_ablation_set()
        logger.info("Loaded %d ablation cases", len(cases))

        if args.run == "all":
            iterations = ITERATION_ORDER
        else:
            iterations = [v.strip() for v in args.run.split(",")]

        all_results: dict[str, dict] = {}
        # Load existing results if resuming
        latest_json = sorted(REPORTS_DIR.glob("ablation_*.json"))
        if latest_json:
            try:
                with open(latest_json[-1]) as f:
                    all_results = json.load(f)
                logger.info("Loaded previous results from %s", latest_json[-1])
                # Reject results from a different commit/checksum
                for prev_v, prev_r in list(all_results.items()):
                    prev_commit = prev_r.get("git_commit", "")
                    prev_cksum = prev_r.get("data_checksum", "")
                    if prev_commit and prev_commit != run_commit:
                        logger.warning(
                            "Discarding %s: ran on commit %s, now on %s",
                            prev_v,
                            prev_commit,
                            run_commit,
                        )
                        del all_results[prev_v]
                    elif prev_cksum and prev_cksum != run_checksum:
                        logger.warning(
                            "Discarding %s: data checksum changed (%s -> %s)",
                            prev_v,
                            prev_cksum,
                            run_checksum,
                        )
                        del all_results[prev_v]
            except Exception:
                pass

        for v in iterations:
            if v not in ITERATIONS:
                logger.error("Unknown iteration: %s", v)
                continue
            if v in all_results:
                logger.info("Skipping %s (already completed)", v)
                continue

            # Re-check integrity before each iteration
            _check_integrity(run_commit, run_checksum)

            logger.info("-" * 60)
            result = run_iteration(v, cases, run_commit, run_checksum, case_timeout=args.case_timeout)
            all_results[v] = result

            # Strip per-case results for the log (keep them in JSON)
            update_improvement_log_ablation(v, result)
            write_ablation_report(all_results)

            logger.info(
                "%s done: %d leaks, %d/%d task, %d/%d over-refusal, %.0fs",
                v,
                result["leaks"],
                result["task_passed"],
                result["task_total"],
                result["or_passed"],
                result["or_total"],
                result["elapsed_seconds"],
            )

        # Restore protections after ablation
        from company.config import settings

        settings.eval_mode = False
        from company.rls import enable_all_rls

        try:
            enable_all_rls()
        except Exception:
            pass

        print_results_table(all_results)
        logger.info("Ablation study complete")


if __name__ == "__main__":
    main()
