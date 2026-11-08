# summary.jq — every number ci-review reports, computed from the cache.
# Inputs (all --slurpfile, so each is [value]): meta repos billing vars
# runners queued runs jobs workflows. Output: one summary object.

def minutes_between(start; finish): ((finish | fromdateiso8601) - (start | fromdateiso8601)) / 60;
def round1: (. * 10 | round) / 10;
def os_of: if test("windows"; "i") then "windows" elif test("macos"; "i") then "macos" else "linux" end;
def multiplier: {"linux": 1, "windows": 2, "macos": 10}[.];
def file_of: split("/") | last;

# Where a runs-on value lands once CI_RUNS_ON (or its fallback) is applied.
def runner_class:
  if test("self-hosted") then "self-hosted"
  elif test("windows"; "i") then "windows"
  elif test("macos"; "i") then "macos"
  elif test("ubuntu"; "i") then "linux"
  else "unresolved" end;

$meta[0] as $meta
| ($repos[0] | map({(.name): (.visibility | ascii_downcase)}) | add // {}) as $visibility
| $vars[0] as $vars

# --- hosted billing (per-day items only) ------------------------------------
| ($billing[0]
    | map(select(.product == "actions" and .unitType == "Minutes")
          | (.sku | os_of) as $os
          | {date: .date[0:10], repo: .repositoryName, os: $os, minutes: .quantity,
             weighted: (.quantity * ($os | multiplier)),
             visibility: ($visibility[.repositoryName] // "unknown")})) as $minutes
| ($minutes | map(select(.visibility != "public"))) as $billable
| ($billable | map(select(.date >= $meta.since))
    | group_by(.repo)
    | map({repo: .[0].repo, visibility: .[0].visibility,
           linux: (map(select(.os == "linux").minutes) | add // 0),
           windows: (map(select(.os == "windows").minutes) | add // 0),
           macos: (map(select(.os == "macos").minutes) | add // 0),
           weighted: (map(.weighted) | add // 0)})
    | sort_by(-.weighted)) as $hosted
| ($billable | map(select(.date >= $meta.since)) | group_by(.date)
    | map({date: .[0].date, weighted: (map(.weighted) | add)})) as $daily
| ($billable | map(select(.date >= $meta.month_start)) | map(.weighted) | add // 0) as $month_weighted
| ($minutes | map(select(.visibility == "public" and .date >= $meta.since))
    | group_by(.repo) | map({repo: .[0].repo, minutes: (map(.minutes) | add)})) as $public_free

# --- self-hosted load ---------------------------------------------------------
# A run's run_started_at equals created_at on its first attempt, so the run
# object cannot show queueing at all; and on a re-run it is the re-run's start,
# so created->started there is re-run delay, not queue. Real waiting is per
# job: created_at -> started_at, from the sampled jobs.
| ($runs[0] | map(
    . + {wall: (if .run_started_at then minutes_between(.run_started_at; .updated_at) else 0 end)})) as $timed_runs
| ($timed_runs | map({(.id | tostring): (.path | file_of)}) | add // {}) as $run_file
| ($jobs[0] | map(select(.started_at and .completed_at and .conclusion != "skipped")
    | . + {exec: minutes_between(.started_at; .completed_at),
           wait: minutes_between(.created_at; .started_at),
           file: ($run_file[.run_id | tostring] // "?"),
           hosted: ((.runner_name // "") | startswith("GitHub Actions"))})) as $timed_jobs
| ($timed_jobs | group_by(.repo) | map({(.[0].repo): {
      sampled_runs: (map(.run_id) | unique | length),
      exec_min: (map(.exec) | add | round1),
      avg_job_wait_min: (map(.wait) | add / length | round1),
      max_job_wait_min: (map(.wait) | max | round1),
      hosted_jobs: (map(select(.hosted)) | length),
      runners: (map(.runner_name // "?") | group_by(.) | map({(.[0]): length}) | add)}})
    | add // {}) as $job_stats
# Mean summed job time per sampled run, per workflow file: what "heavy" means.
| ($timed_jobs | group_by([.repo, .file]) | map({("\(.[0].repo)/\(.[0].file)"):
      (group_by(.run_id) | map(map(.exec) | add) | add / length)}) | add // {}) as $exec_per_run
| ($timed_runs | group_by(.repo) | map(
    {repo: .[0].repo,
     runs: length,
     reruns: (map(select(.run_attempt > 1)) | length),
     wall_min: (map(.wall) | add | round1),
     queued_now: ($queued[0][.[0].repo] // 0)}
    + ($job_stats[.[0].repo] // {}))
    | sort_by(-.wall_min)) as $load

# --- per workflow + event -----------------------------------------------------
| ($timed_runs | group_by([.repo, .path, .event]) | map(
    {repo: .[0].repo, workflow: .[0].name, file: (.[0].path | file_of), event: .[0].event,
     runs: length, wall_min: (map(.wall) | add | round1)})
    | sort_by(-.runs)) as $by_event

# --- hygiene: each workflow file, its load, and what to change ---------------
| ($workflows[0] | map(
    . as $wf
    | ($timed_runs | map(select(.repo == $wf.repo and (.path | file_of) == $wf.file))) as $wf_runs
    | ($visibility[$wf.repo] // "unknown") as $vis
    | ($wf.runs_on | unique | map(
        . as $value
        | (if test("vars\\.CI_RUNS_ON") then
             ($vars[$wf.repo].value // ((capture("\\|\\|\\s*'(?<fallback>[^']*)'").fallback) // ""))
           else $value end) as $resolved
        | {runs_on: $value, resolved: $resolved, class: ($resolved | runner_class)})) as $placements
    | ($wf_runs | length) as $count
    | (if $count > 0 then ($wf_runs | map(.wall) | add) else 0 end) as $wall
    | ($exec_per_run["\($wf.repo)/\($wf.file)"]) as $exec
    | {repo: $wf.repo, file: $wf.file, visibility: $vis,
       changed_at: $wf.changed_at,
       runs: $count, wall_min: ($wall | round1),
       runs_since_change: (if $wf.changed_at then ($wf_runs | map(select(.created_at > $wf.changed_at)) | length) else null end),
       avg_wall_min: (if $count > 0 then ($wall / $count | round1) else 0 end),
       avg_exec_min: (if $exec then ($exec | round1) else null end),
       events: ($wf_runs | group_by(.event) | map({(.[0].event): length}) | add // {}),
       placements: $placements,
       flags: ([
         (select($wf.push and ($wf.push_restricted | not))
           | if $wf.pull_request then "push-all-branches+pr-duplicates" else "push-all-branches" end),
         (select(($wf.concurrency | not) and ($wf.file | test("release|deploy|publish") | not)) | "no-concurrency"),
         # Release/deploy runs must finish once started: queueing them is right.
         (select($wf.concurrency and ($wf.cancel | not) and ($wf.file | test("release|deploy|publish") | not))
           | "no-cancel-in-progress"),
         # A group holds one pending run: keyed on github.ref, a second merge queued behind a
         # busy runner cancels the first merge's pending run, so that commit is never tested.
         (select($wf.ref_keyed and $wf.push and ($wf.file | test("release|deploy|publish") | not))
           | "ref-keyed-concurrency"),
         (select(($wf.paths | not) and ($wf.push or $wf.pull_request)) | "no-paths-filter"),
         (select((($exec // (if $count > 0 then $wall / $count else 0 end))) > 10) | "heavy"),
         ($placements[] | select($vis != "public" and (.class | IN("linux", "windows", "macos")))
           | "hosted-\(.class)"),
         ($placements[] | select($vis == "public" and .class == "self-hosted") | "public-on-self-hosted"),
         ($placements[] | select(.class == "unresolved") | "runs-on-unresolved")
       ] | unique),
       # A group marked `# ci-review: supersede-intended` documents that superseding main
       # runs is the point (e.g. a whole-tree lint): reported here, never as a fix.
       accepted: ([
         (select($wf.supersede_intended and $wf.push and ($wf.file | test("release|deploy|publish") | not))
           | "ref-keyed-concurrency")
       ])})) as $hygiene

| {meta: $meta,
   hosted: {
     plan_cap_min: 2000,
     month_to_date_weighted: ($month_weighted | round1),
     window_weighted: ($hosted | map(.weighted) | add // 0 | round1),
     daily: ($daily | map(.weighted |= round1)),
     repos: ($hosted | map(.linux |= round1 | .windows |= round1 | .macos |= round1 | .weighted |= round1)),
     public_excluded: $public_free},
   placement: {
     ci_runs_on: ($vars | to_entries | map(select(.value != null)
       | {repo: .key, value: .value.value, updated_at: .value.updated_at}) | sort_by(.updated_at)),
     hosted_jobs: ($hygiene | map(select(.flags | any(startswith("hosted-"))))
       | map({repo, file, runs, wall_min,
              placements: (.placements | map(select(.class | IN("linux", "windows", "macos"))))})),
     runners: ($runners[0] | to_entries | map(.key as $repo | .value[] | . + {repo: $repo}))},
   load: $load,
   queue: ($load | map(select(.max_job_wait_min != null)) | sort_by(-.max_job_wait_min)),
   by_event: $by_event,
   fixes: ($hygiene | map(select(.flags | length > 0)) | sort_by(-.wall_min)),
   accepted: ($hygiene | map(select(.accepted | length > 0)) | sort_by(-.wall_min)),
   hygiene: $hygiene}
