#!/bin/bash
# Launch v5 ablation: all fixes + grounding scorer, 210 cases, PROFILE=local
# Usage: bash scripts/launch_v5.sh
# Run from project root (main branch, after merging finish)

set -euo pipefail

echo "=== Pre-flight checks ==="

# Verify we're on main
BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "main" ]; then
    echo "ERROR: Must be on main branch (currently on $BRANCH)"
    exit 1
fi

# Verify grounding checker exists
if ! python3 -c "from evals.judge import check_grounding" 2>/dev/null; then
    echo "ERROR: check_grounding not importable — did you merge finish?"
    exit 1
fi

# Verify DB is up
if ! PGPASSWORD=keystone_dev_password psql -h localhost -U keystone -d keystone -c "SELECT 1" >/dev/null 2>&1; then
    echo "ERROR: Database not reachable"
    exit 1
fi

# Verify Ollama is up
if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "ERROR: Ollama not reachable"
    exit 1
fi

COMMIT=$(git rev-parse --short HEAD)
echo "  Branch: $BRANCH"
echo "  Commit: $COMMIT"
echo "  Profile: local (Ollama qwen2.5:7b)"

echo ""
echo "=== Re-scoring v0-v2 with grounding checker ==="
PROFILE=local python3 -m evals.rescore \
    --source evals/reports/ablation_20261028_132251.json

echo ""
echo "=== Launching v5 ablation (nohup) ==="
export PROFILE=local
export DATABASE_URL=postgresql://keystone:keystone_dev_password@localhost:5432/keystone

nohup python3 -m evals.ablation --run v5 \
    >> evals/reports/ablation_v5.log 2>&1 &

V5_PID=$!
echo "v5 ablation started as PID $V5_PID"
echo "  Log: evals/reports/ablation_v5.log"
echo "  Monitor: tail -f evals/reports/ablation_v5.log"
echo ""
echo "When done, run:"
echo "  python3 -m evals.rescore --source <v5_report>.json --kappa evals/labels/labels_*.jsonl"
