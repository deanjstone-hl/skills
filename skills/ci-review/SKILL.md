---
name: ci-review
description: >
  Audit GitHub Actions load across deanjstone repos: hosted minutes vs the Free-plan cap,
  homelab runner load and queueing, workflow hygiene; ranked table and fix list. Use for "ci
  review", "which repos burn the most CI", "optimise CI", "actions minutes", "runner queue",
  "why is CI slow/queued", "/ci-review".
disable-model-invocation: true
---

# CI review

Account-wide: collect real run, job and billing data → rank the heaviest repos → punch list
of fixes ranked by payoff. The script does the gathering and the arithmetic; this file is
how to read its output and turn it into fixes.

Read-only unless the user asks for fixes to be applied.

## Run it

```bash
SKILL=~/.claude/skills/ci-review
bash "$SKILL/scripts/ci-review.sh"                       # last 7 days, markdown report
bash "$SKILL/scripts/ci-review.sh" --since 2026-10-09    # window from a date (e.g. a fix landing)
bash "$SKILL/scripts/ci-review.sh" --top 10 --json       # longer lists / machine-readable
bash "$SKILL/scripts/ci-review.sh" --report-only <cache> # re-render a past run, no API calls
```

A run takes ~4 minutes (one jobs call per sampled run, 8 in parallel). Every raw response
lands in the cache dir it prints on stderr: that dir is the evidence, so quote it rather
than re-querying. `--jobs-runs N` (default 50) sets how many recent runs per repo are
sampled for job-level data. It needs `gh`, `jq` and GNU `date`: run it from WSL2 or
homelab, never Windows PowerShell.

Exit `2` means a GitHub call failed. The script aborts rather than guessing, because "the
variable is unset" and "the variable could not be read" are different findings. Report the
error; do not hand-patch the numbers.

## Reading the report

Report sections in this order: hosted spend first (it is money, and the cap is hard), then
self-hosted load. Each list shows at most `--top` rows and counts the rest.

| Section | Source | Gotcha the script already handles |
|---|---|---|
| Hosted spend | `/users/<owner>/settings/billing/usage?year&month&day`, one call per day | The **monthly** form misattributes `repositoryName`, charging minutes to repos that never ran a job. Per-day only. Windows ×2, macOS ×10. Public repos are free, so they are excluded and listed separately. The cap is 2,000 weighted min/month, and going over it blocks hosted jobs. |
| Self-hosted load | `actions/runs?created=>=DATE&status=completed` | Run wall time (`updated_at − run_started_at`) includes jobs queued *inside* the run, so read **Exec min** (summed job time) for real runner occupancy. |
| Queue waits | `actions/runs/<id>/jobs`, job `created_at → started_at` | A run's `run_started_at` equals `created_at` on attempt 1, and on a re-run it is the re-run's start. **Run timestamps cannot show queueing.** Any "queue" computed from them is re-run delay. Re-runs are counted separately. |
| Busiest triggers | runs grouped by workflow + event | Exposes the costly trigger (e.g. every `memory_remember` commit pushing to context). |
| Runner placement | `CI_RUNS_ON` repo variable + every `runs-on:` line | `runs-on: ${{ fromJSON(vars.CI_RUNS_ON \|\| '"ubuntu-latest"') }}` falls back to **hosted** when the variable is unset. A hardcoded `windows-latest`/`macos-*` job ignores the variable entirely. |
| Fix candidates | workflow files, scanned line by line | Flags describe the file **as it is now**. A `⚠ file changed` line means the window's load came mostly from an older version. Rerun with `--since <that date>` before claiming the fix is still needed. |

All self-hosted runners (`homelab`, `homelab-2`, `homelab-<repo>`) run on **one machine**.
Once spend is near zero, the burden is contention: one busy repo's queue is every repo's
queue. Low-volume repos showing long waits are the symptom, not the cause.

## From report to fix list

Write the punch list as one numbered list ranked by payoff, at most 5 items. Each item
names the repo, the file and the exact change. Payoff order:

1. **Hosted spend in a private repo**: `hosted-linux` → set `CI_RUNS_ON` or hardcode
   `runs-on: [self-hosted, homelab]`. `hosted-windows`/`hosted-macos` → no homelab
   fallback exists for Windows/macOS-only steps, so gate the job behind a `paths:` filter
   (e.g. `**/*.ps1` for Pester), or move it to `pwsh` on homelab as argus-config's `pester`
   job did.
2. **Trigger volume** (highest wall/exec minutes first): `push-all-branches` (restrict to
   `branches: [main]`, the PR run already covers branch pushes), then `no-paths-filter`
   (skip docs-only changes), then `no-concurrency`. `ref-keyed-concurrency` is a
   correctness fix, not a load one: list it whatever its payoff rank.
3. **Heavy workflows** (`heavy` = over 10 summed exec min per run): split, cache, or gate
   the slow job. Read its jobs in the cache first to name the slow one.
4. **`public-on-self-hosted`**: move it to hosted runners. Hosted is free for public repos,
   and fork PRs on a self-hosted runner execute untrusted code on homelab.

House style for the changes, so fixes match what the account already runs (CI tiering per
memory `decision_ci_workflow_strategy`; workflow shape per the `github-setup` skill):

```yaml
on:
  push:
    branches: [main]          # PR runs already cover branch pushes
  pull_request:
    paths-ignore: ['**.md', 'docs/**']

concurrency:
  # One group per PR, one per main commit. Never ${{ github.ref }}: a group holds one
  # pending run, so on main the next merge would cancel this commit's queued run.
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.sha }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

jobs:
  build:
    runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '"ubuntu-latest"') }}
```

`ref-keyed-concurrency` flags a push workflow whose group is keyed on `github.ref` alone
(memory `fact_github_concurrency_group_cancels_pending`; argus#612 and argus-config#503
fixed it after #603/#497 shipped it). Leave it only where superseding main is the point,
such as context's whole-tree Reachability Lint: say why in a comment, and mark the group
with `# ci-review: supersede-intended` on its `group:` line or the line directly above.
A marked group is reported under **Accepted exceptions**, not as a fix candidate; the
marker covers that one group only.

Leave `release`/`deploy`/`publish` workflows queued (`cancel-in-progress: false`): the
script never flags them for it, because a cancelled deploy is half a deploy.

A `paths:` filter on a workflow whose check is **required** by branch protection leaves
docs-only PRs waiting on that check forever. Before adding one, run
`gh api repos/<o>/<r>/branches/main/protection` (a 404 means no protection, as on Free-plan
private repos). If the check is required, keep the workflow triggering and skip the
expensive steps with a changed-files check (e.g. `dorny/paths-filter`), or drop the
requirement.

## Applying fixes (only when asked)

The default is the report and the punch list, nothing else. When the user asks to apply
fixes:

- One branch (`chore/ci-<change>`) and one PR per target repo, opened from a fresh worktree
  of that repo. Never a direct commit. Register each PR with `link_pull_request`.
- Setting a repo variable (`gh variable set CI_RUNS_ON -R <o>/<r> --body '["self-hosted","homelab"]'`)
  edits live repo config: confirm it with the literal command first.
- Each PR body carries the report rows that justify it (runs, minutes, flags) as evidence.
- After merge, rerun with `--since <merge date>` and report the before/after numbers. That
  rerun is the verification. The merge alone proves nothing.

A worked example (the 2026-10-10 audit, with the numbers and the fixes that followed) is in
[`worked-example.md`](worked-example.md). Read it to calibrate what a full answer looks
like. Its numbers are history, not current state.

## Not this skill

- One PR's red CI: `pr-triage` (reads that PR's job logs).
- Writing CI for a repo that has none: `github-setup`.
