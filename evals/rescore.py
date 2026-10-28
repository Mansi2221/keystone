"""Re-score existing ablation results with the deterministic grounding checker.

No LLM calls needed — reads the stored results, runs check_grounding() on
each LLM-judged case, and writes an updated report.

Usage:
  python -m evals.rescore --source evals/reports/ablation_20261028_132251.json
  python -m evals.rescore --source evals/reports/ablation_20261028_132251.json --kappa evals/labels/labels_*.jsonl
"""

import argparse
import json
import logging

from evals.judge import check_grounding

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def rescore_iteration(results: list[dict]) -> tuple[list[dict], dict]:
    """Re-score a list of case results with the grounding checker.

    Returns: (updated_results, stats)
    """
    stats = {
        "total": len(results),
        "llm_judged": 0,
        "grounding_checked": 0,
        "grounding_skipped": 0,
        "newly_failed": 0,
        "already_failed": 0,
        "still_pass": 0,
    }

    updated = []
    for r in results:
        r = dict(r)  # Don't mutate original
        suite = r.get("_suite", "")

        # Only apply grounding check to LLM-judged suites
        if suite not in ("task_success", "over_refusal"):
            updated.append(r)
            continue

        stats["llm_judged"] += 1
        response = r.get("agent_response", "")

        grounding = check_grounding(response)
        r["grounding"] = grounding

        if grounding["skipped"]:
            stats["grounding_skipped"] += 1
            updated.append(r)
            continue

        stats["grounding_checked"] += 1
        old_pass = r.get("pass", False)

        if not grounding["grounded"]:
            # Grounding violations found — override to FAIL
            r["pass"] = False
            r["score"] = 0.0
            r["grounding_fail"] = True
            r["grounding_reason"] = "; ".join(f"{v['type']}: {v['value']}" for v in grounding["violations"])
            if old_pass:
                stats["newly_failed"] += 1
            else:
                stats["already_failed"] += 1
        else:
            r["grounding_fail"] = False
            if old_pass:
                stats["still_pass"] += 1
            else:
                stats["already_failed"] += 1

        updated.append(r)

    return updated, stats


def rescore_report(source_path: str) -> dict:
    """Re-score all iterations in an ablation report."""
    with open(source_path) as f:
        data = json.load(f)

    all_stats = {}
    for iteration_key in sorted(data.keys()):
        iteration = data[iteration_key]
        if not isinstance(iteration, dict) or "results" not in iteration:
            continue

        logger.info("Re-scoring %s (%d results)...", iteration_key, len(iteration["results"]))
        updated_results, stats = rescore_iteration(iteration["results"])
        iteration["results"] = updated_results

        # Recompute pass/fail counts
        total = len(updated_results)
        passed = sum(1 for r in updated_results if r.get("pass", False))
        leaked = sum(1 for r in updated_results if r.get("leaked", False))
        iteration["passed"] = passed
        iteration["failed"] = total - passed
        iteration["pass_rate"] = passed / max(total, 1)
        iteration["leaked"] = leaked
        iteration["grounding_stats"] = stats

        all_stats[iteration_key] = stats
        logger.info(
            "  %s: checked=%d, newly_failed=%d, still_pass=%d, skipped=%d",
            iteration_key,
            stats["grounding_checked"],
            stats["newly_failed"],
            stats["still_pass"],
            stats["grounding_skipped"],
        )

    # Write updated report
    out_path = source_path.replace(".json", "_rescored.json")
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2, default=str)

    logger.info("Rescored report written to %s", out_path)
    return {"output": out_path, "stats": all_stats, "data": data}


def compute_kappa_comparison(
    labels_path: str,
    original_data: dict,
    rescored_data: dict,
    iteration: str = "v2",
) -> dict:
    """Compare kappa before and after rescoring against human labels."""
    labels = []
    with open(labels_path) as f:
        for line in f:
            if line.strip():
                labels.append(json.loads(line))

    if not labels:
        logger.error("No labels found in %s", labels_path)
        return {}

    # Build lookup by case_id (ablation_id)
    def _build_lookup(data: dict, it: str) -> dict:
        results = data[it]["results"]
        return {r.get("_ablation_id", r["case_id"]): r for r in results}

    orig_lookup = _build_lookup(original_data, iteration)
    new_lookup = _build_lookup(rescored_data, iteration)

    def _cohens_kappa(judge: list[bool], human: list[bool]) -> float:
        n = len(judge)
        if n == 0:
            return 0.0
        a = sum(1 for j, h in zip(judge, human) if j and h)
        d = sum(1 for j, h in zip(judge, human) if not j and not h)
        po = (a + d) / n
        p_j = (a + sum(1 for j, h in zip(judge, human) if j and not h)) / n
        p_h = (a + sum(1 for j, h in zip(judge, human) if not j and h)) / n
        pe = p_j * p_h + (1 - p_j) * (1 - p_h)
        if pe == 1.0:
            return 1.0
        return (po - pe) / (1 - pe)

    human_labels = [l["human_pass"] for l in labels]
    case_ids = [l["case_id"] for l in labels]

    # Original judge scores
    orig_judge = []
    for cid in case_ids:
        r = orig_lookup.get(cid, {})
        orig_judge.append(r.get("pass", False))

    # Rescored judge scores
    new_judge = []
    for cid in case_ids:
        r = new_lookup.get(cid, {})
        new_judge.append(r.get("pass", False))

    orig_kappa = _cohens_kappa(orig_judge, human_labels)
    new_kappa = _cohens_kappa(new_judge, human_labels)
    orig_agree = sum(1 for j, h in zip(orig_judge, human_labels) if j == h)
    new_agree = sum(1 for j, h in zip(new_judge, human_labels) if j == h)

    # Detail the changes
    changes = []
    for i, cid in enumerate(case_ids):
        if orig_judge[i] != new_judge[i]:
            changes.append(
                {
                    "case_id": cid,
                    "original": orig_judge[i],
                    "rescored": new_judge[i],
                    "human": human_labels[i],
                    "message": labels[i].get("message", "")[:60],
                }
            )

    return {
        "n_labels": len(labels),
        "original_kappa": orig_kappa,
        "rescored_kappa": new_kappa,
        "original_agreement": f"{orig_agree}/{len(labels)}",
        "rescored_agreement": f"{new_agree}/{len(labels)}",
        "changes": changes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-score ablation results with grounding checker")
    parser.add_argument("--source", required=True, help="Ablation report JSON to re-score")
    parser.add_argument("--kappa", help="Labels JSONL file for kappa comparison")
    parser.add_argument("--iteration", default="v2", help="Iteration for kappa comparison")
    args = parser.parse_args()

    # Load original data for kappa comparison
    with open(args.source) as f:
        original_data = json.load(f)

    # Re-score
    result = rescore_report(args.source)

    # Kappa comparison
    if args.kappa:
        kappa_result = compute_kappa_comparison(args.kappa, original_data, result["data"], args.iteration)
        print(f"\n{'=' * 60}")
        print("Kappa Comparison: Before vs After Grounding Check")
        print(f"{'=' * 60}")
        print(f"  Labels:              {kappa_result['n_labels']}")
        print(f"  Original kappa:      {kappa_result['original_kappa']:.3f}")
        print(f"  Rescored kappa:      {kappa_result['rescored_kappa']:.3f}")
        print(f"  Original agreement:  {kappa_result['original_agreement']}")
        print(f"  Rescored agreement:  {kappa_result['rescored_agreement']}")
        if kappa_result["changes"]:
            print(f"\n  Score changes ({len(kappa_result['changes'])}):")
            for c in kappa_result["changes"]:
                o = "PASS" if c["original"] else "FAIL"
                n = "PASS" if c["rescored"] else "FAIL"
                h = "PASS" if c["human"] else "FAIL"
                print(f"    {c['case_id']}: {o} → {n} (human={h}) | {c['message']}")


if __name__ == "__main__":
    main()
