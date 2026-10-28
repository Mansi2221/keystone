#!/bin/bash
# Overnight pipeline: resume stuck iterations, merge, rescore with user-relative
# leak scoring, run v5, record fixtures, generate summary, commit+push.
#
# Usage:
#   nohup bash scripts/overnight.sh >> evals/reports/overnight.log 2>&1 &
#
# Each step logs success/failure. If a step fails, non-dependent steps continue.
# Iterations that fail twice are marked incomplete in the summary.

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
CASE_TIMEOUT=120

step_ok=()
step_fail=()
incomplete_iterations=()

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
        local rc=$?
        log "FAIL: $name (exit $rc)"
        step_fail+=("$name")
        return $rc
    fi
}

# ─── Step (a): Wait for stuck ablation (PID 86171) or kill if no progress ───
wait_for_ablation() {
    local pid=86171
    local max_wait=1800  # 30 minutes max

    if ! kill -0 "$pid" 2>/dev/null; then
        log "Ablation PID $pid already finished"
        return 0
    fi

    log "Ablation PID $pid still running, checking progress..."
    local last_case
    last_case=$(grep -oP '\[\K\d+(?=/210\])' evals/reports/ablation_run.log 2>/dev/null | tail -1)
    log "Last completed case: ${last_case:-unknown}/210"

    # Wait up to max_wait, checking for progress every 5 min
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

# ─── Step (a2): Resume incomplete iterations with per-case timeout ───
# Runs each of v0–v5 individually. The ablation runner's progress file
# enables resume from the last completed case. If an iteration fails twice,
# mark it incomplete and continue.
resume_iterations() {
    local all_iters="v0 v1 v2 v3 v4 v5"
    for iter in $all_iters; do
        log "Checking iteration $iter..."

        # Try up to 2 times
        local attempt
        local success=false
        for attempt in 1 2; do
            log "  Attempt $attempt for $iter"
            if python3 -m evals.ablation --run "$iter" --case-timeout "$CASE_TIMEOUT"; then
                log "  $iter completed on attempt $attempt"
                success=true
                break
            else
                log "  $iter failed on attempt $attempt (exit $?)"
                if [ "$attempt" -eq 1 ]; then
                    log "  Retrying $iter..."
                    sleep 5
                fi
            fi
        done

        if [ "$success" = "false" ]; then
            log "  $iter INCOMPLETE after 2 attempts"
            incomplete_iterations+=("$iter")
        fi
    done

    if [ ${#incomplete_iterations[@]} -gt 0 ]; then
        log "Incomplete iterations: ${incomplete_iterations[*]}"
    else
        log "All iterations complete"
    fi
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

# ─── Step (c): Re-score all iterations with user-relative leak scoring ───
rescore_all() {
    # Find the latest ablation report (may have been updated by resume_iterations)
    local latest
    latest=$(ls -t evals/reports/ablation_*.json 2>/dev/null | grep -v rescored | head -1)
    if [ -z "$latest" ]; then
        latest="$ABLATION_REPORT"
    fi
    log "Re-scoring $latest with user-relative leak scoring..."
    python3 -m evals.rescore \
        --source "$latest" \
        --kappa "$LABELS" \
        --iteration v2
    RESCORED_REPORT="${latest%.json}_rescored.json"
    log "Rescored report: $RESCORED_REPORT"
}

# ─── Step (d): Record replay fixtures (7 scenarios x 4 personas + compare) ───
record_fixtures() {
    log "Recording replay fixtures..."
    python3 -m scripts.record_fixtures --compare
    log "Fixtures written to ui-web/public/fixtures/"
}

# ─── Step (e): Regenerate overnight summary ───
gen_summary() {
    local report="$RESCORED_REPORT"
    if [ ! -f "$report" ]; then
        report="$ABLATION_REPORT"
    fi

    local incomplete_flag=""
    if [ ${#incomplete_iterations[@]} -gt 0 ]; then
        incomplete_flag="--incomplete $(IFS=,; echo "${incomplete_iterations[*]}")"
    fi

    log "Generating overnight summary from $report..."
    python3 -m scripts.gen_overnight_summary \
        --report "$report" \
        --labels "$LABELS" \
        --original "$ABLATION_REPORT" \
        $incomplete_flag
    log "Summary written to docs/overnight-summary.md"
}

# ─── Step (f): Commit and push ───
commit_and_push() {
    git add -A evals/reports/ docs/overnight-summary.md ui-web/public/fixtures/ 2>/dev/null || true
    if git diff --cached --quiet; then
        log "Nothing to commit"
        return 0
    fi

    local incomplete_msg=""
    if [ ${#incomplete_iterations[@]} -gt 0 ]; then
        incomplete_msg="Incomplete: ${incomplete_iterations[*]}"
    fi

    git commit -m "overnight: rescore v0-v5, fixtures, summary

Steps completed: ${step_ok[*]}
Steps failed: ${step_fail[*]:-none}
${incomplete_msg}

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
    git push origin finish
    git push origin main 2>/dev/null || true
    log "Committed and pushed"
}

# ═══════════════════════════════════════════════════════════
log "Starting overnight pipeline"
log "Working directory: $REPO_ROOT"
log "Profile: $PROFILE"
log "Case timeout: ${CASE_TIMEOUT}s"
log ""
log "Step order:"
log "  (a)  Wait for stuck ablation / kill if no progress"
log "  (a2) Resume all iterations v0-v5 with ${CASE_TIMEOUT}s per-case timeout (retry once on failure)"
log "  (b)  Merge finish → main"
log "  (c)  Re-score all with user-relative leak scoring + grounding checker"
log "  (d)  Record replay fixtures 7×4 + compare"
log "  (e)  Regenerate overnight-summary.md"
log "  (f)  Commit and push"
log ""

run_step "wait-for-ablation" wait_for_ablation

run_step "resume-iterations" resume_iterations || true

run_step "merge-to-main" merge_to_main || true

run_step "rescore-all" rescore_all || true

run_step "record-fixtures" record_fixtures || true

run_step "gen-summary" gen_summary || true

run_step "commit-and-push" commit_and_push || true

log "═══════════════════════════════════════════════════════"
log "Overnight pipeline complete"
log "  Succeeded: ${step_ok[*]:-none}"
log "  Failed: ${step_fail[*]:-none}"
if [ ${#incomplete_iterations[@]} -gt 0 ]; then
    log "  Incomplete iterations: ${incomplete_iterations[*]}"
fi
log "═══════════════════════════════════════════════════════"
