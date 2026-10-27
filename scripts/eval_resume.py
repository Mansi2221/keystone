"""Resume-capable full eval runner.

Runs all 797 cases across all suites, saving progress per case to JSONL.
An interrupted run continues from where it stopped.

Usage:
  python scripts/eval_resume.py                    # start or resume
  python scripts/eval_resume.py --reset            # clear progress and restart
  python scripts/eval_resume.py --status            # show progress

Progress file: evals/reports/full_eval_progress.jsonl
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, ".")

import yaml

from company.llm import active_profile_info, get_call_count, reset_call_count

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SUITES_DIR = Path("evals/suites")
REPORTS_DIR = Path("evals/reports")
PROGRESS_FILE = REPORTS_DIR / "full_eval_progress.jsonl"
IMPROVEMENT_LOG = Path("docs/improvement-log.md")


def load_all_cases() -> list[dict]:
    """Load all cases from all suites with metadata."""
    all_cases = []
    for path in sorted(SUITES_DIR.glob("*.yaml")):
        with open(path) as f:
            suite = yaml.safe_load(f)
        suite_name = suite["name"]
        scoring = suite.get("scoring", "deterministic")
        for case in suite.get("cases", []):
            case["_suite"] = suite_name
            case["_scoring"] = scoring
            case["_case_key"] = f"{suite_name}:{case.get('id', 'unknown')}"
            all_cases.append(case)
    return all_cases


def load_completed() -> set[str]:
    """Load the set of completed case keys from the progress file."""
    completed = set()
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        completed.add(record["_case_key"])
                    except (json.JSONDecodeError, KeyError):
                        continue
    return completed


def run_full_eval() -> None:
    """Run all cases, resuming from progress file."""
    info = active_profile_info()
    logger.info("=" * 60)
    logger.info("Full Eval Runner (resume-capable)")
    logger.info("  Profile: %s", info["profile"])
    logger.info("  Agent:   %s", info["agent"])
    logger.info("  Judge:   %s", info["judge"])
    logger.info("  Progress: %s", PROGRESS_FILE)
    logger.info("=" * 60)

    all_cases = load_all_cases()
    completed = load_completed()
    remaining = [c for c in all_cases if c["_case_key"] not in completed]

    logger.info("Total cases: %d, completed: %d, remaining: %d",
                len(all_cases), len(completed), len(remaining))

    if not remaining:
        logger.info("All cases already completed. Use --reset to start over.")
        _print_summary()
        return

    from evals.runner import _run_case

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    reset_call_count()
    start_time = time.time()

    with open(PROGRESS_FILE, "a") as progress_f:
        for i, case in enumerate(remaining, 1):
            case_start_calls = get_call_count()
            case_start_time = time.time()

            scoring = case["_scoring"]
            result = _run_case(case, scoring)
            result["_case_key"] = case["_case_key"]
            result["_suite"] = case["_suite"]
            result["llm_calls"] = get_call_count() - case_start_calls
            result["elapsed"] = time.time() - case_start_time

            # Write result immediately (flush for durability)
            progress_f.write(json.dumps(result, default=str) + "\n")
            progress_f.flush()

            total_done = len(completed) + i
            elapsed = time.time() - start_time
            rate = elapsed / i
            eta = rate * (len(remaining) - i)
            status = "PASS" if result.get("pass") else "FAIL"

            logger.info(
                "  [%d/%d total, %d/%d this run] %s %s (%.1fs, ETA %.0fs)",
                total_done, len(all_cases), i, len(remaining),
                result["case_id"], status, result["elapsed"], eta,
            )

    logger.info("Full eval complete!")
    _print_summary()


def _print_summary() -> None:
    """Print a summary from the progress file."""
    if not PROGRESS_FILE.exists():
        logger.info("No progress file found.")
        return

    results: list[dict] = []
    with open(PROGRESS_FILE) as f:
        for line in f:
            if line.strip():
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    by_suite: dict[str, dict] = {}
    for r in results:
        suite = r.get("_suite", "unknown")
        entry = by_suite.setdefault(suite, {"total": 0, "passed": 0, "leaked": 0, "calls": 0})
        entry["total"] += 1
        if r.get("pass"):
            entry["passed"] += 1
        if r.get("leaked"):
            entry["leaked"] += 1
        entry["calls"] += r.get("llm_calls", 0)

    print(f"\n{'Suite':<25} {'Cases':>6} {'Passed':>7} {'Rate':>7} {'Leaks':>6} {'Calls':>6}")
    print("-" * 60)
    total_cases = 0
    total_passed = 0
    total_leaked = 0
    total_calls = 0
    for suite, s in sorted(by_suite.items()):
        rate = s["passed"] / max(s["total"], 1)
        print(f"{suite:<25} {s['total']:>6} {s['passed']:>7} {rate:>6.1%} {s['leaked']:>6} {s['calls']:>6}")
        total_cases += s["total"]
        total_passed += s["passed"]
        total_leaked += s["leaked"]
        total_calls += s["calls"]
    print("-" * 60)
    rate = total_passed / max(total_cases, 1)
    print(f"{'TOTAL':<25} {total_cases:>6} {total_passed:>7} {rate:>6.1%} {total_leaked:>6} {total_calls:>6}")
    print()


def show_status() -> None:
    """Show current progress."""
    all_cases = load_all_cases()
    completed = load_completed()

    by_suite: dict[str, dict] = {}
    for c in all_cases:
        suite = c["_suite"]
        entry = by_suite.setdefault(suite, {"total": 0, "done": 0})
        entry["total"] += 1
        if c["_case_key"] in completed:
            entry["done"] += 1

    print(f"\n{'Suite':<25} {'Done':>6} {'Total':>6} {'Progress':>10}")
    print("-" * 50)
    for suite, s in sorted(by_suite.items()):
        pct = s["done"] / max(s["total"], 1)
        bar = "█" * int(pct * 20) + "░" * (20 - int(pct * 20))
        print(f"{suite:<25} {s['done']:>6} {s['total']:>6}  {bar} {pct:.0%}")

    total_done = sum(s["done"] for s in by_suite.values())
    total = sum(s["total"] for s in by_suite.values())
    print(f"\nOverall: {total_done}/{total} ({total_done/max(total,1):.1%})")

    if PROGRESS_FILE.exists():
        _print_summary()


def main() -> None:
    parser = argparse.ArgumentParser(description="Resume-capable full eval runner")
    parser.add_argument("--reset", action="store_true", help="Clear progress and restart")
    parser.add_argument("--status", action="store_true", help="Show current progress")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.reset:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
            logger.info("Progress cleared: %s", PROGRESS_FILE)
        return

    run_full_eval()


if __name__ == "__main__":
    main()
