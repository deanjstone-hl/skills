#!/usr/bin/env bash
# ci-review.sh — read-only audit of GitHub Actions load across one owner's repos.
#
# Two phases, so a run is reproducible and the report is testable offline:
#   collect  gh API calls -> raw JSON in a cache dir (never writes to GitHub)
#   report   pure jq over that cache dir -> markdown, or the summary as --json
#
# Usage:
#   ci-review.sh [--owner deanjstone] [--since YYYY-MM-DD | --days N]
#                [--jobs-runs N] [--top N] [--cache DIR] [--json]
#   ci-review.sh --report-only DIR [--top N] [--json]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OWNER="deanjstone"
DAYS=7
SINCE=""
JOBS_RUNS=50
PARALLEL=8
TOP=5
CACHE=""
REPORT_ONLY=""
FORMAT="markdown"
FETCH_RUN_JOBS=()

die() { printf 'ci-review: %s\n' "$*" >&2; exit 2; }
log() { printf 'ci-review: %s\n' "$*" >&2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --owner) OWNER="$2"; shift 2 ;;
    --days) DAYS="$2"; shift 2 ;;
    --since) SINCE="$2"; shift 2 ;;
    --jobs-runs) JOBS_RUNS="$2"; shift 2 ;;
    --fetch-run-jobs) FETCH_RUN_JOBS=("$2" "$3" "$4" "$5"); shift 5 ;;
    --top) TOP="$2"; shift 2 ;;
    --cache) CACHE="$2"; shift 2 ;;
    --report-only) REPORT_ONLY="$2"; shift 2 ;;
    --json) FORMAT="json"; shift ;;
    -h|--help) sed -n '2,13p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

for tool in jq awk; do
  command -v "$tool" > /dev/null || die "$tool is required"
done

# gh_get <out-file> <api-path> [jq-filter]: one gh api call; aborts on any error.
gh_get() {
  local out="$1" path="$2" filter="${3:-.}"
  if ! gh api "$path" --jq "$filter" > "$out" 2> "$out.err"; then
    die "gh api $path failed: $(cat "$out.err")"
  fi
  rm -f "$out.err"
}

# gh_paginate <out-file> <api-path> <jq-filter>: every page, one JSON value per line.
gh_paginate() {
  local out="$1" path="$2" filter="$3"
  if ! gh api --paginate "$path" --jq "$filter" > "$out" 2> "$out.err"; then
    die "gh api --paginate $path failed: $(cat "$out.err")"
  fi
  rm -f "$out.err"
}

# gh_optional <out-file> <api-path> <fallback-json> [jq-filter]: a 404 is an
# answer (variable unset, no workflows dir), written as the fallback. Any
# other failure aborts — "unset" and "could not read" are different findings.
gh_optional() {
  local out="$1" path="$2" fallback="$3" filter="${4:-.}"
  if gh api "$path" --jq "$filter" > "$out" 2> "$out.err"; then
    rm -f "$out.err"
    return 0
  fi
  if grep -q 'HTTP 404' "$out.err"; then
    printf '%s\n' "$fallback" > "$out"
    rm -f "$out.err"
    return 0
  fi
  die "gh api $path failed: $(cat "$out.err")"
}

collect() {
  command -v gh > /dev/null || die "gh is required"
  local today month_start billing_start day
  today="$(date -u +%F)"
  [[ -n "$SINCE" ]] || SINCE="$(date -u -d "$DAYS days ago" +%F)"
  month_start="$(date -u +%Y-%m-01)"
  billing_start="$SINCE"
  if [[ "$month_start" < "$billing_start" ]]; then billing_start="$month_start"; fi

  mkdir -p "$CACHE"/{billing,vars,runners,workflows,runs,jobs,queued}
  jq -n --arg owner "$OWNER" --arg since "$SINCE" --arg today "$today" \
    --arg month_start "$month_start" --arg generated "$(date -u +%FT%TZ)" \
    '{owner:$owner, since:$since, today:$today, month_start:$month_start, generated_at:$generated}' \
    > "$CACHE/meta.json"

  log "repos for $OWNER"
  if ! gh repo list "$OWNER" --limit 1000 --json name,visibility,isArchived,isFork \
      > "$CACHE/repos.json" 2> "$CACHE/repos.err"; then
    die "gh repo list failed: $(cat "$CACHE/repos.err")"
  fi
  rm -f "$CACHE/repos.err"

  # Per-day billing only. The monthly aggregate misattributes repositoryName
  # (it has charged minutes to repos that never ran a job).
  log "billing per day, $billing_start..$today"
  day="$billing_start"
  while [[ ! "$day" > "$today" ]]; do
    local y m d
    IFS=- read -r y m d <<< "$day"
    gh_get "$CACHE/billing/$day.json" \
      "/users/$OWNER/settings/billing/usage?year=$y&month=$((10#$m))&day=$((10#$d))" '.usageItems'
    day="$(date -u -d "$day + 1 day" +%F)"
  done

  local repos=()
  mapfile -t repos < <(jq -r '.[] | select(.isArchived | not) | .name' "$CACHE/repos.json")
  log "${#repos[@]} active repos: variables, runners, runs"

  local repo
  for repo in "${repos[@]}"; do
    gh_optional "$CACHE/vars/$repo.json" "repos/$OWNER/$repo/actions/variables/CI_RUNS_ON" 'null' \
      '{value, updated_at}'
    gh_optional "$CACHE/runners/$repo.json" "repos/$OWNER/$repo/actions/runners?per_page=100" '[]' \
      '[.runners[] | {name, status, busy, labels: [.labels[].name]}]'
    gh_paginate "$CACHE/runs/$repo.jsonl" \
      "repos/$OWNER/$repo/actions/runs?created=>=$SINCE&status=completed&per_page=100" \
      '.workflow_runs[] | {id, name, path, event, head_branch, run_attempt, conclusion, created_at, run_started_at, updated_at}'
    gh_get "$CACHE/queued/$repo.json" "repos/$OWNER/$repo/actions/runs?status=queued&per_page=1" '.total_count'

    # Workflow files only for repos that ran something in the window.
    if [[ -s "$CACHE/runs/$repo.jsonl" ]]; then
      mkdir -p "$CACHE/workflows/$repo"
      gh_optional "$CACHE/workflows/$repo.list" "repos/$OWNER/$repo/contents/.github/workflows" '' \
        '.[] | select(.type == "file") | select(.name | test("\\.ya?ml$")) | .name'
      local file
      while IFS= read -r file; do
        [[ -n "$file" ]] || continue
        gh_get "$CACHE/workflows/$repo/$file.b64" "repos/$OWNER/$repo/contents/.github/workflows/$file" '.content'
        base64 -d < "$CACHE/workflows/$repo/$file.b64" > "$CACHE/workflows/$repo/$file"
        rm -f "$CACHE/workflows/$repo/$file.b64"
        gh_get "$CACHE/workflows/$repo.changed.$file" \
          "repos/$OWNER/$repo/commits?path=.github/workflows/$file&per_page=1" '.[0].commit.committer.date'
      done < "$CACHE/workflows/$repo.list"
    fi
  done

  # Job-level data is the only place queueing shows (see summary.jq) and costs
  # one call per run, so sample the latest --jobs-runs runs of every repo.
  local sampled=()
  for repo in "${repos[@]}"; do
    if [[ -s "$CACHE/runs/$repo.jsonl" ]]; then sampled+=("$repo"); fi
  done
  for repo in "${sampled[@]}"; do
    [[ -n "$repo" ]] || continue
    log "jobs for $repo (latest $JOBS_RUNS runs, $PARALLEL at a time)"
    mkdir -p "$CACHE/jobs/$repo.d"
    jq -rs --argjson n "$JOBS_RUNS" 'sort_by(.created_at) | reverse | .[:$n][] | .id' \
      "$CACHE/runs/$repo.jsonl" > "$CACHE/jobs/$repo.ids"
    if ! xargs -P "$PARALLEL" -I{} bash "${BASH_SOURCE[0]}" --fetch-run-jobs "$OWNER" "$repo" {} \
        "$CACHE/jobs/$repo.d" < "$CACHE/jobs/$repo.ids"; then
      die "job fetch failed for $repo (see $CACHE/jobs/$repo.d/*.err)"
    fi
    cat "$CACHE/jobs/$repo.d"/*.jsonl > "$CACHE/jobs/$repo.jsonl"
    rm -rf "$CACHE/jobs/$repo.d" "$CACHE/jobs/$repo.ids"
  done
}

# hygiene_json <cache>: one JSON object per workflow file, from workflow-hygiene.awk.
hygiene_json() {
  local cache="$1" dir file record repo changed
  for dir in "$cache"/workflows/*/; do
    [[ -d "$dir" ]] || continue
    repo="$(basename "$dir")"
    for file in "$dir"*; do
      [[ -f "$file" ]] || continue
      record="$(awk -f "$SCRIPT_DIR/workflow-hygiene.awk" "$file")"
      changed=""
      if [[ -f "$cache/workflows/$repo.changed.$(basename "$file")" ]]; then
        changed="$(cat "$cache/workflows/$repo.changed.$(basename "$file")")"
      fi
      jq -R --arg repo "$repo" --arg file "$(basename "$file")" --arg changed "$changed" '
        split("\t") as $f
        | {repo: $repo, file: $file, changed_at: (if $changed == "" then null else $changed end),
           concurrency: ($f[0] == "1"), cancel: ($f[1] == "1"), paths: ($f[2] == "1"),
           push: ($f[3] == "1"), push_restricted: ($f[4] == "1"),
           pull_request: ($f[5] == "1"), schedule: ($f[6] == "1"),
           runs_on: (if ($f[7] // "") == "" then [] else ($f[7] | split("\u001f")) end),
           ref_keyed: ($f[8] == "1"), supersede_intended: ($f[9] == "1")}' \
        <<< "$record"
    done
  done
}

# keyed_json <dir> <ext>: {"<basename>": <file contents>} for every file.
keyed_json() {
  local dir="$1" ext="$2" file
  for file in "$dir"/*."$ext"; do
    [[ -f "$file" ]] || continue
    jq -c --arg key "$(basename "$file" ".$ext")" '{($key): .}' "$file"
  done
}

# tagged_lines <dir>: every JSONL record with a "repo" field from its filename.
tagged_lines() {
  local dir="$1" file
  for file in "$dir"/*.jsonl; do
    [[ -s "$file" ]] || continue
    jq -c --arg repo "$(basename "$file" .jsonl)" '. + {repo: $repo}' "$file"
  done
}

report() {
  local cache="$1" work
  [[ -f "$cache/meta.json" ]] || die "no meta.json in $cache — not a ci-review cache"
  work="$(mktemp -d)"

  jq -s 'add // []' "$cache"/billing/*.json > "$work/billing.json"
  keyed_json "$cache/vars" json | jq -s 'add // {}' > "$work/vars.json"
  keyed_json "$cache/runners" json | jq -s 'add // {}' > "$work/runners.json"
  keyed_json "$cache/queued" json | jq -s 'add // {}' > "$work/queued.json"
  tagged_lines "$cache/runs" | jq -s '.' > "$work/runs.json"
  tagged_lines "$cache/jobs" | jq -s '.' > "$work/jobs.json"
  hygiene_json "$cache" | jq -s '.' > "$work/workflows.json"

  jq -n --argjson top "$TOP" \
    --slurpfile meta "$cache/meta.json" --slurpfile repos "$cache/repos.json" \
    --slurpfile billing "$work/billing.json" --slurpfile vars "$work/vars.json" \
    --slurpfile runners "$work/runners.json" --slurpfile queued "$work/queued.json" \
    --slurpfile runs "$work/runs.json" --slurpfile jobs "$work/jobs.json" \
    --slurpfile workflows "$work/workflows.json" \
    -f "$SCRIPT_DIR/summary.jq" > "$work/summary.json"

  if [[ "$FORMAT" == "json" ]]; then
    cat "$work/summary.json"
  else
    jq -r --argjson top "$TOP" -f "$SCRIPT_DIR/render.jq" "$work/summary.json"
  fi
  rm -rf "$work"
}

# Internal: one run's jobs, called in parallel by collect via xargs.
if [[ ${#FETCH_RUN_JOBS[@]} -gt 0 ]]; then
  gh_paginate "${FETCH_RUN_JOBS[3]}/${FETCH_RUN_JOBS[2]}.jsonl" \
    "repos/${FETCH_RUN_JOBS[0]}/${FETCH_RUN_JOBS[1]}/actions/runs/${FETCH_RUN_JOBS[2]}/jobs?per_page=100" \
    '.jobs[] | {run_id, workflow_name, name, conclusion, created_at, started_at, completed_at, runner_name, labels}'
  exit 0
fi

if [[ -n "$REPORT_ONLY" ]]; then
  report "$REPORT_ONLY"
  exit 0
fi

[[ -n "$CACHE" ]] || CACHE="${TMPDIR:-/tmp}/ci-review-$OWNER-$(date -u +%Y%m%dT%H%M%SZ)"
collect
log "cache: $CACHE (re-render with --report-only $CACHE)"
report "$CACHE"
