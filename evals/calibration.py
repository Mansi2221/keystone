"""LLM Judge Calibration.

A labeling CLI to hand-label 100 task outputs and a calibration script
that measures agreement between the LLM judge and human labels.
"""

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from evals.judge import judge_task_success

logger = logging.getLogger(__name__)

LABELS_DIR = Path("evals/calibration")
LABELS_FILE = LABELS_DIR / "human_labels.json"


def label_cli() -> None:
    """Interactive CLI for hand-labeling agent outputs."""
    LABELS_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing labels
    labels: list[dict] = []
    if LABELS_FILE.exists():
        labels = json.loads(LABELS_FILE.read_text())

    print(f"Existing labels: {len(labels)}")
    print("Enter outputs to label (Ctrl+C to stop):")

    try:
        while len(labels) < 100:
            print(f"\n--- Label {len(labels) + 1}/100 ---")
            question = input("Question: ").strip()
            if not question:
                break
            expected = input("Expected answer: ").strip()
            response = input("Agent response: ").strip()
            role = input("User role: ").strip() or "individual_contributor"

            while True:
                verdict = input("Pass? (y/n): ").strip().lower()
                if verdict in ("y", "n"):
                    break
            score_str = input("Score (0.0-1.0): ").strip()
            try:
                score = float(score_str)
            except ValueError:
                score = 1.0 if verdict == "y" else 0.0

            labels.append(
                {
                    "question": question,
                    "expected": expected,
                    "response": response,
                    "role": role,
                    "human_pass": verdict == "y",
                    "human_score": score,
                }
            )

            LABELS_FILE.write_text(json.dumps(labels, indent=2))
            print(f"Saved ({len(labels)} total)")

    except KeyboardInterrupt:
        print(f"\nStopped. {len(labels)} labels saved.")


def calibrate() -> dict[str, Any]:
    """Run the LLM judge on human-labeled data and compute agreement metrics.

    Returns Cohen's kappa, precision, recall, and disagreement cases.
    """
    if not LABELS_FILE.exists():
        raise FileNotFoundError(f"No labels found at {LABELS_FILE}. Run 'python -m evals.calibration label' first.")

    labels = json.loads(LABELS_FILE.read_text())
    logger.info("Calibrating on %d labeled examples", len(labels))

    human_pass = []
    judge_pass = []
    disagreements = []

    for i, label in enumerate(labels):
        result = judge_task_success(
            user_message=label["question"],
            agent_response=label["response"],
            expected_answer=label["expected"],
            role=label["role"],
        )

        h = label["human_pass"]
        j = result["pass"]
        human_pass.append(h)
        judge_pass.append(j)

        if h != j:
            disagreements.append(
                {
                    "index": i,
                    "question": label["question"][:80],
                    "human": h,
                    "judge": j,
                    "judge_reasoning": result.get("reasoning", ""),
                }
            )

    # Compute metrics
    n = len(human_pass)
    tp = sum(1 for h, j in zip(human_pass, judge_pass) if h and j)
    fp = sum(1 for h, j in zip(human_pass, judge_pass) if not h and j)
    fn = sum(1 for h, j in zip(human_pass, judge_pass) if h and not j)
    tn = sum(1 for h, j in zip(human_pass, judge_pass) if not h and not j)

    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)

    # Cohen's kappa
    po = (tp + tn) / max(n, 1)  # observed agreement
    pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / max(n * n, 1)
    kappa = (po - pe) / max(1 - pe, 1e-10)

    metrics = {
        "n": n,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "cohens_kappa": round(kappa, 3),
        "observed_agreement": round(po, 3),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "disagreements": disagreements,
    }

    # Write calibration report
    report_path = LABELS_DIR / "calibration_report.json"
    with open(report_path, "w") as f:
        json.dump(metrics, f, indent=2)

    logger.info(
        "Calibration: kappa=%.3f, precision=%.3f, recall=%.3f, %d disagreements",
        kappa,
        precision,
        recall,
        len(disagreements),
    )

    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM Judge Calibration")
    parser.add_argument("action", choices=["label", "calibrate"], help="Action to perform")
    args = parser.parse_args()

    if args.action == "label":
        label_cli()
    elif args.action == "calibrate":
        metrics = calibrate()
        print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
