"""Hand-labeling CLI and inter-rater agreement (Cohen's kappa).

Usage:
  # Label 50 task outputs from the latest ablation run:
  python -m evals.label --source evals/reports/ablation_XXXX.json --iteration v4 --count 50

  # Compute Cohen's kappa between your labels and the LLM judge:
  python -m evals.label --kappa evals/labels/labels_XXXX.jsonl
"""

import argparse
import json
import logging
import random
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

LABELS_DIR = Path("evals/labels")


def _cohens_kappa(judge: list[bool], human: list[bool]) -> float:
    """Compute Cohen's kappa for two binary raters."""
    assert len(judge) == len(human)
    n = len(judge)
    if n == 0:
        return 0.0

    # Contingency table
    a = sum(1 for j, h in zip(judge, human) if j and h)       # both pass
    b = sum(1 for j, h in zip(judge, human) if j and not h)   # judge pass, human fail
    c = sum(1 for j, h in zip(judge, human) if not j and h)   # judge fail, human pass
    d = sum(1 for j, h in zip(judge, human) if not j and not h)  # both fail

    po = (a + d) / n  # observed agreement
    p_judge_pass = (a + b) / n
    p_human_pass = (a + c) / n
    pe = p_judge_pass * p_human_pass + (1 - p_judge_pass) * (1 - p_human_pass)

    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def label_session(source_path: str, iteration: str, count: int) -> Path:
    """Interactive labeling session: present cases, collect pass/fail labels."""
    with open(source_path) as f:
        data = json.load(f)

    if iteration not in data:
        logger.error("Iteration '%s' not found in %s", iteration, source_path)
        logger.error("Available: %s", list(data.keys()))
        sys.exit(1)

    results = data[iteration].get("results", [])
    # Only show task_success and over_refusal cases (LLM-judged)
    judgeable = [r for r in results if r.get("_suite") in ("task_success", "over_refusal")]
    if not judgeable:
        logger.error("No LLM-judged cases found in %s/%s", source_path, iteration)
        sys.exit(1)

    rng = random.Random(42)
    sample = rng.sample(judgeable, min(count, len(judgeable)))

    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = LABELS_DIR / f"labels_{ts}.jsonl"

    labels: list[dict] = []
    print()
    print("=" * 70)
    print(f"  LABELING SESSION: {len(sample)} cases from {iteration}")
    print("  Enter: p = pass, f = fail, s = skip, q = quit")
    print("=" * 70)

    for i, r in enumerate(sample, 1):
        print(f"\n--- Case {i}/{len(sample)}: {r.get('_ablation_id', r['case_id'])} ---")
        print(f"  Suite:    {r.get('_suite', 'unknown')}")
        print(f"  Role:     {r['user_role']}")
        print(f"  Message:  {r['message']}")
        if r.get("expected_answer"):
            print(f"  Expected: {r['expected_answer']}")
        print(f"  Response: {r.get('agent_response', '(no response)')[:500]}")
        print(f"  LLM judge: {'PASS' if r.get('pass') else 'FAIL'} "
              f"(score={r.get('score', '?')}, reason={r.get('reasoning', 'n/a')[:80]})")

        while True:
            try:
                choice = input("  Your label [p/f/s/q]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "q"

            if choice in ("p", "f", "s", "q"):
                break
            print("  Invalid input. Use p (pass), f (fail), s (skip), q (quit).")

        if choice == "q":
            print("Quitting labeling session.")
            break
        if choice == "s":
            continue

        human_pass = choice == "p"
        labels.append({
            "case_id": r.get("_ablation_id", r["case_id"]),
            "suite": r.get("_suite", ""),
            "message": r["message"],
            "judge_pass": r.get("pass", False),
            "judge_score": r.get("score", 0.0),
            "human_pass": human_pass,
            "iteration": iteration,
        })

    # Save labels
    with open(out_path, "w") as f:
        for label in labels:
            f.write(json.dumps(label) + "\n")

    print(f"\nSaved {len(labels)} labels to {out_path}")

    # Compute quick kappa
    if labels:
        judge_labels = [l["judge_pass"] for l in labels]
        human_labels = [l["human_pass"] for l in labels]
        kappa = _cohens_kappa(judge_labels, human_labels)
        agree = sum(1 for j, h in zip(judge_labels, human_labels) if j == h)
        print(f"\nQuick stats:")
        print(f"  Labeled:    {len(labels)}")
        print(f"  Agreement:  {agree}/{len(labels)} ({agree/len(labels):.1%})")
        print(f"  Cohen's κ:  {kappa:.3f}")
        _interpret_kappa(kappa)

    return out_path


def compute_kappa(labels_path: str) -> None:
    """Compute Cohen's kappa from a saved labels file."""
    labels = []
    with open(labels_path) as f:
        for line in f:
            if line.strip():
                labels.append(json.loads(line))

    if not labels:
        logger.error("No labels found in %s", labels_path)
        return

    judge_labels = [l["judge_pass"] for l in labels]
    human_labels = [l["human_pass"] for l in labels]

    kappa = _cohens_kappa(judge_labels, human_labels)
    agree = sum(1 for j, h in zip(judge_labels, human_labels) if j == h)

    # Contingency table
    tp = sum(1 for j, h in zip(judge_labels, human_labels) if j and h)
    fp = sum(1 for j, h in zip(judge_labels, human_labels) if j and not h)
    fn = sum(1 for j, h in zip(judge_labels, human_labels) if not j and h)
    tn = sum(1 for j, h in zip(judge_labels, human_labels) if not j and not h)

    print(f"\n{'=' * 50}")
    print(f"Cohen's Kappa Analysis: {labels_path}")
    print(f"{'=' * 50}")
    print(f"  Total labeled:  {len(labels)}")
    print(f"  Agreement:      {agree}/{len(labels)} ({agree/len(labels):.1%})")
    print(f"  Cohen's κ:      {kappa:.3f}")
    print()
    print(f"  Contingency table:")
    print(f"  {'':>20} Human PASS  Human FAIL")
    print(f"  {'Judge PASS':>20}    {tp:>4}        {fp:>4}")
    print(f"  {'Judge FAIL':>20}    {fn:>4}        {tn:>4}")
    print()

    _interpret_kappa(kappa)

    # Disagreements
    disagreements = [l for l in labels if l["judge_pass"] != l["human_pass"]]
    if disagreements:
        print(f"\nDisagreements ({len(disagreements)}):")
        for d in disagreements[:10]:
            j = "PASS" if d["judge_pass"] else "FAIL"
            h = "PASS" if d["human_pass"] else "FAIL"
            print(f"  {d['case_id']}: judge={j}, human={h} | {d['message'][:60]}")


def _interpret_kappa(kappa: float) -> None:
    if kappa < 0:
        interp = "Less than chance agreement"
    elif kappa < 0.21:
        interp = "Slight agreement"
    elif kappa < 0.41:
        interp = "Fair agreement"
    elif kappa < 0.61:
        interp = "Moderate agreement"
    elif kappa < 0.81:
        interp = "Substantial agreement"
    else:
        interp = "Almost perfect agreement"
    print(f"  Interpretation: {interp} (Landis & Koch)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hand-labeling CLI and Cohen's kappa")
    parser.add_argument("--source", help="Ablation report JSON to label from")
    parser.add_argument("--iteration", default="v4", help="Which iteration to label (default: v4)")
    parser.add_argument("--count", type=int, default=50, help="Number of cases to label")
    parser.add_argument("--kappa", help="Compute kappa from a saved labels JSONL file")
    args = parser.parse_args()

    if args.kappa:
        compute_kappa(args.kappa)
    elif args.source:
        label_session(args.source, args.iteration, args.count)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
