# Worked example: the 2026-10-10 audit

The manual audit this skill encodes (T3 thread "Find and Optimise Heaviest CI Repos"), then
the first script run. Use it to calibrate what a full answer looks like. **Every number
here is history.** Rerun the script for current state.

## What the data showed

**Hosted spend had already been fixed.** Every private repo got
`CI_RUNS_ON=["self-hosted","homelab"]` between 8 Oct 19:26 and 9 Oct 04:04 UTC. Billed
minutes fell from ~800/day (7–8 Oct) to 1 on 9 Oct. Month to date still read 2150 / 2000
weighted min: the account went over the cap before the move. Over the cap is why
`windows-latest` was billing-blocked from 2026-10-08.

The script's per-day billing table for 2–9 Oct:

| Repo | Linux | Windows | Weighted |
|---|---|---|---|
| budget | 857 | 0 | 857 |
| myargus | 405 | 0 | 405 |
| homelab | 234 | 0 | 234 |
| argus-config | 43 | 94 | 231 |
| pkm-vault | 99 | 0 | 99 |

The monthly aggregate had charged minutes to `mcp-memory` and `context`, which never ran
those jobs. That is why the script reads billing per day only.

**The burden then moved to the homelab runners.** Wall minutes since 9 Oct (manual audit):
homelab 1738, argus 964, context 946, budget 752, argus-config 346.

**Queueing: the manual audit measured it wrongly.** It reported max waits of 184 min
(slate-reader), 166 (sys-admin) and 137 (argus) from `run_started_at − created_at`. On a
first attempt those two timestamps are equal. On a re-run, `run_started_at` is the
re-run's start. So those figures were re-run delay. Job-level waits from the script (2–9
Oct, 50 sampled runs per repo) were the real queue:

| Repo | Max job wait | Avg job wait |
|---|---|---|
| atto1 | 176.8 | 15.2 |
| argus-config | 166 | 3.7 |
| homelab | 142.4 | 30 |
| argus | 100.3 | 10.4 |
| budget | 99.7 | 12.3 |

**Busiest trigger:** context's Reachability Lint, with 413 push runs in a week. Every
`memory_remember` commit pushes to context, and the workflow ran on push to every branch
as well as on `pull_request`.

## The fix list it produced

1. context `reachability-lint.yml`: restrict push to `branches: [main]`, add `concurrency`
   with cancel-in-progress, add a `paths:` filter.
2. homelab `test.yml`: ~16.5 exec min per run on both PR and push. Add a `paths:` filter.
3. argus `ci.yml`, argus-config `lint.yml`: add `concurrency` (none of the top 8
   workflows had a `paths:` filter, and these two had no concurrency block either).
4. argus-config `pester` on `windows-latest`: the last hosted spend (94 Windows min = 188
   weighted in a week). Moved to pwsh on homelab: `CI_RUNS_ON` was set on 8 Oct 23:00, and its jobs then ran on `homelab-argus-config`.
5. erto-apps `ci.yml` on `ubuntu-latest` with no `CI_RUNS_ON`: real, but only ~4 min. It
   is listed for completeness, not urgency.

## How the fixes then showed up in a rerun

When the script ran on 10 Oct, fixes 1 and 3 (argus) had already merged. The report marked
them `⚠ file changed 2026-10-09; only N runs since`. The week's load was from the old
files, so the flags no longer applied. In that state the fix is done; the next step is
`--since 2026-10-09` to measure what it bought.
