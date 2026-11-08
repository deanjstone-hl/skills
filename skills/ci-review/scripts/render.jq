# render.jq — markdown report from summary.jq's output. $top caps every list;
# the cut rows stay in the summary (--json) and are counted, never dropped silently.

def capped(rows): rows[:$top];
def more(rows): if (rows | length) > $top then "\n_+\((rows | length) - $top) more — rerun with `--top N` or `--json`._" else "" end;
def table(header; rows; row):
  if (rows | length) == 0 then "_none_"
  else ([header, (header | gsub("[^|]"; "-"))] + (capped(rows) | map(row))) | join("\n") end
  + more(rows);
def fix_text:
  {"push-all-branches": "restrict `push:` to `branches: [main]`",
   "push-all-branches+pr-duplicates": "restrict `push:` to `branches: [main]` (every PR push currently runs twice: push + pull_request)",
   "no-concurrency": "add top-level `concurrency:` (group `${{ github.workflow }}-${{ github.event.pull_request.number || github.sha }}`, `cancel-in-progress: ${{ github.event_name == 'pull_request' }}`)",
   "ref-keyed-concurrency": "re-key `concurrency.group` on `${{ github.event.pull_request.number || github.sha }}`: keyed on `github.ref`, a queued main run is cancelled by the next merge and that commit is never tested (fine only if superseding main is intended, e.g. a whole-tree lint — say so in a comment and mark the group `# ci-review: supersede-intended`)",
   "no-cancel-in-progress": "set `cancel-in-progress: true` on the existing `concurrency:`",
   "no-paths-filter": "add `paths:`/`paths-ignore:` so docs-only changes skip it",
   "heavy": "heavy run — split, cache, or gate the slow job behind a paths filter",
   "hosted-linux": "set repo variable `CI_RUNS_ON=[\"self-hosted\",\"homelab\"]` or hardcode `runs-on: [self-hosted, homelab]`",
   "hosted-windows": "hosted Windows (2x minutes) — move to pwsh on homelab, or gate with a `paths:` filter",
   "hosted-macos": "hosted macOS (10x minutes) — gate with a `paths:` filter or drop",
   "public-on-self-hosted": "public repo on homelab: hosted runners are free here, and fork PRs run code on homelab",
   "runs-on-unresolved": "runs-on could not be resolved (matrix/expression) — check by hand"}[.] // .;

.meta as $m
| [
  "# CI review — \($m.owner), since \($m.since)",
  "",
  "Generated \($m.generated_at). Hosted minutes from per-day billing; Windows weighted 2x, macOS 10x; public repos excluded.",
  "",
  "## 1. Hosted spend (private repos)",
  "",
  "Month to date: **\(.hosted.month_to_date_weighted) / \(.hosted.plan_cap_min)** weighted min. Window: \(.hosted.window_weighted).",
  "",
  "Daily: " + (if (.hosted.daily | length) == 0 then "_no billed minutes_" else (.hosted.daily | map("\(.date[5:]) \(.weighted)") | join(" · ")) end),
  "",
  table("| Repo | Linux | Windows | macOS | Weighted |"; .hosted.repos;
        "| \(.repo) | \(.linux) | \(.windows) | \(.macos) | \(.weighted) |"),
  "",
  "## 2. Self-hosted load",
  "",
  table("| Repo | Runs | Re-runs | Wall min | Exec min (sampled runs) | Queued now |"; .load;
        "| \(.repo) | \(.runs) | \(.reruns) | \(.wall_min) | \(if .exec_min then "\(.exec_min) (\(.sampled_runs))" else "—" end) | \(.queued_now) |"),
  "",
  "Wall min includes time jobs sat queued inside the run. Exec min is summed job time over the sampled runs only (latest `--jobs-runs` per repo).",
  "",
  "### Worst queue waits (job created → started, sampled runs)",
  "",
  table("| Repo | Max wait min | Avg wait min | Sampled runs |"; .queue;
        "| \(.repo) | \(.max_job_wait_min) | \(.avg_job_wait_min) | \(.sampled_runs) |"),
  "",
  "### Busiest workflow triggers",
  "",
  table("| Repo | Workflow | Event | Runs | Wall min |"; .by_event;
        "| \(.repo) | \(.workflow) | \(.event) | \(.runs) | \(.wall_min) |"),
  "",
  "## 3. Runner placement",
  "",
  table("| Repo | CI_RUNS_ON | Updated |"; (.placement.ci_runs_on | reverse);
        "| \(.repo) | `\(.value)` | \(.updated_at) |"),
  "",
  "Jobs still resolving to GitHub-hosted runners (private repos):",
  "",
  table("| Repo | Workflow | runs-on | Runs | Wall min |"; .placement.hosted_jobs;
        "| \(.repo) | \(.file) | \(.placements | map("`\(.runs_on)` → \(.class)") | join(", ")) | \(.runs) | \(.wall_min) |"),
  "",
  "Runners: \(.placement.runners | length) registered, \(.placement.runners | map(select(.status == "online")) | length) online"
    + (.placement.runners | map(select(.status != "online")) | if length > 0 then ". **Offline:** " + (map("\(.repo)/\(.name)") | join(", ")) else "" end) + ".",
  "",
  "## 4. Fix candidates (ranked by wall minutes in window)",
  "",
  (if (.fixes | length) == 0 then "_none_" else
    (capped(.fixes) | to_entries | map(
      "\(.key + 1). **\(.value.repo) `\(.value.file)`** — \(.value.runs) runs, \(.value.wall_min) wall min"
      + (if .value.avg_exec_min then ", \(.value.avg_exec_min) exec min/run (summed across jobs)" else "" end)
      + (if (.value.events | length) > 0 then " (" + (.value.events | to_entries | map("\(.key) \(.value)") | join(", ")) + ")" else "" end)
      + (if .value.changed_at and .value.changed_at > $m.since then "\n   - ⚠ file changed \(.value.changed_at[0:10]); only \(.value.runs_since_change) runs since — flags describe the current file" else "" end)
      + "\n" + (.value.flags | map("   - " + fix_text) | join("\n"))) | join("\n"))
    + more(.fixes) end),
  "",
  "## 5. Accepted exceptions",
  "",
  "Marked `# ci-review: supersede-intended` on the concurrency `group:` line or the line above: superseding queued main runs is intended, so these are not fix candidates.",
  "",
  (if (.accepted | length) == 0 then "_none_" else
    (capped(.accepted) | map("- \(.repo) `\(.file)` — \(.accepted | join(", "))") | join("\n"))
    + more(.accepted) end)
] | join("\n")
