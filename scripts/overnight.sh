#!/bin/bash
# Overnight pipeline: wait for v4, merge, rescore, run v5, record fixtures, generate summary, commit+push.
#
# Usage:
#   nohup bash scripts/overnight.sh >> evals/reports/overnight.log 2>&1 &
#
# Each step logs success/failure. If a step fails, non-dependent steps continue.

set -o pipefail

LOGPREFIX="[overnight]"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Activate venv
source .venv/bin/activate 2>/dev/null || true

export PROFILE=local
export DATABASE_URL=postgresql://keystone:keystone_dev_password@localhost:5432/keystone

ABLATION_REPORT="evals/reports/ablation_20261028_132251.json"
LABELS="evals/labels/labels_20261028_205836.jsonl"
RESCORED_REPORT="${ABLATION_REPORT%.json}_rescored.json"

step_ok=()
step_fail=()

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $LOGPREFIX $*"; }

run_step() {
    local name="$1"
    shift
    log "START: $name"
    if "$@"; then
        log "OK: $name"
        step_ok+=("$name")
        return 0
    else
        log "FAIL: $name (exit $?)"
        step_fail+=("$name")
        return 1
    fi
}

# ─── Step (a): Wait for v3/v4 ablation (PID 86171) or kill if stuck ───
wait_for_ablation() {
    local pid=86171
    local max_wait=1800  # 30 minutes max

    if ! kill -0 "$pid" 2>/dev/null; then
        log "Ablation PID $pid already finished"
        return 0
    fi

    log "Ablation PID $pid still running, checking progress..."

    # Get current case count from log
    local last_case
    last_case=$(grep -oP '\[\K\d+(?=/210\])' evals/reports/ablation_run.log 2>/dev/null | tail -1)
    log "Last completed case: ${last_case:-unknown}/210"

    # Wait up to max_wait seconds, checking for progress every 5 min
    local waited=0
    local check_interval=300
    while kill -0 "$pid" 2>/dev/null && [ "$waited" -lt "$max_wait" ]; do
        sleep "$check_interval"
        waited=$((waited + check_interval))
        local new_case
        new_case=$(grep -oP '\[\K\d+(?=/210\])' evals/reports/ablation_run.log 2>/dev/null | tail -1)
        if [ "$new_case" = "$last_case" ]; then
            log "No progress in ${check_interval}s (still at case $last_case). Killing PID $pid."
            kill "$pid" 2>/dev/null
            sleep 5
            kill -9 "$pid" 2>/dev/null
            return 0
        fi
        last_case="$new_case"
        log "Progress: case $last_case/210 ($waited/${max_wait}s elapsed)"
    done

    if kill -0 "$pid" 2>/dev/null; then
        log "Max wait exceeded. Killing PID $pid."
        kill "$pid" 2>/dev/null
        sleep 5
        kill -9 "$pid" 2>/dev/null
    fi

    return 0
}

# ─── Step (b): Merge finish → main ───
merge_to_main() {
    log "Current branch: $(git branch --show-current)"
    git checkout main
    git pull origin main --ff-only || true
    git merge finish --no-edit -m "Merge finish: v5 fixes, grounding checker, value-leak fix, overnight pipeline"
    git checkout finish  # Switch back for remaining steps
    log "Merged finish → main"
}

# ─── Step (c): Re-score v0-v4 with new scorer ───
rescore_all() {
    log "Re-scoring $ABLATION_REPORT..."
    python3 -m evals.rescore \
        --source "$ABLATION_REPORT" \
        --kappa "$LABELS" \
        --iteration v2
    log "Rescored report: $RESCORED_REPORT"
}

# ─── Step (d): Run v5 ablation (210 cases, PROFILE=local) ───
run_v5() {
    log "Launching v5 ablation..."
    python3 -m evals.ablation --run v5
    log "v5 ablation complete"

    # Find the newest report
    local latest
    latest=$(ls -t evals/reports/ablation_*.json 2>/dev/null | head -1)
    if [ -n "$latest" ]; then
        log "v5 report: $latest"
        # Re-score v5 too
        python3 -m evals.rescore --source "$latest"
    fi
}

# ─── Step (e): Record replay fixtures (7 scenarios x 4 personas + compare) ───
record_fixtures() {
    log "Recording replay fixtures..."
    python3 -m scripts.record_fixtures --compare
    log "Fixtures written to ui-web/public/fixtures/"
}

# ─── Step (f): Regenerate overnight summary ───
gen_summary() {
    local report="$RESCORED_REPORT"
    if [ ! -f "$report" ]; then
        report="$ABLATION_REPORT"
    fi
    log "Generating overnight summary from $report..."
    python3 -m scripts.gen_overnight_summary \
        --report "$report" \
        --labels "$LABELS" \
        --original "$ABLATION_REPORT"
    log "Summary written to docs/overnight-summary.md"
}

# ─── Step (g): Commit and push ───
commit_and_push() {
    git add -A evals/reports/ docs/overnight-summary.md ui-web/public/fixtures/ 2>/dev/null || true
    if git diff --cached --quiet; then
        log "Nothing to commit"
        return 0
    fi
    git commit -m "overnight: rescore v0-v4, v5 ablation, fixtures, summary

Steps completed: ${step_ok[*]}
Steps failed: ${step_fail[*]:-none}

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
    git push origin finish
    git push origin main 2>/dev/null || true
    log "Committed and pushed"
}

# ═══════════════════════════════════════════════════════════
log "Starting overnight pipeline"
log "Working directory: $REPO_ROOT"
log "Profile: $PROFILE"

run_step "wait-for-ablation" wait_for_ablation

run_step "merge-to-main" merge_to_main || true

run_step "rescore-all" rescore_all || true

# v5 depends on merge (needs v5 fixes on main), but try anyway
run_step "run-v5" run_v5 || true

# Fixtures depend on DB and agent working
run_step "record-fixtures" record_fixtures || true

# Summary depends on rescore
run_step "gen-summary" gen_summary || true

# Commit whatever we have
run_step "commit-and-push" commit_and_push || true

log "═══════════════════════════════════════════════════════"
log "Overnight pipeline complete"
log "  Succeeded: ${step_ok[*]:-none}"
log "  Failed: ${step_fail[*]:-none}"
log "═══════════════════════════════════════════════════════"
