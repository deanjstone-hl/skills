---
name: deploy
description: >
  Deploy a project or argus package the way it really deploys: promotion to the deploy
  branch, CI on merge, a runbook, its own deploy.sh, or a package.json deploy script. Use for
  "deploy <x>", "push <x>", "redeploy <x>", "ship <x>", or putting a package into its runtime
  environment.
---

# Deploy

Find the target's own deploy mechanism, then follow it. This skill never re-implements a
deploy: if the project has no mechanism, it stops and asks.

**Every deploy needs the owner's live approval.** The normal path is the owner approving a
promotion card on the ops hub, which fast-forwards `deploy` and runs the target's
`deploy`-branch workflow; an agent never approves a card. Everything below that runs a command
(`promote.sh`, `deploy.sh`, `wrangler`, `supabase`, rsync plus restart) is **break-glass**: use it
only when the target has no `deploy`-branch workflow yet or the hub cannot promote, and say why
the hub path was not used. In a repo on the deploy-branch model, a
merge to `main` does not deploy: production moves only when a human promotes a `main` SHA to
the `deploy` branch, and rollback is a revert on `main` plus a new promotion. A deploy command
runs only from a thread in default permission mode (a T3 approval-required thread or a
terminal), where the deploy gate shows the exact command at a prompt. Run it, let the prompt
reach the owner, and never answer it yourself. A gate denial (full-access thread, headless run)
or an AFK run stops here: prepare the exact command and tell the owner to run it from an
approval-required thread. A chat "yes" is not approval.

---

## Step 1 — Locate the target

If the user didn't name a target, ask with `AskUserQuestion`.

- **An argus package** (`memory-mcp`, `agent-engine`, …) → `apps/<name>/` in the primary
  checkout `~/repos/argus`.
- **Any other project** → its primary checkout `~/repos/<name>/`, or a package directory
  inside it.

Where the repo has no `origin/deploy` branch, deploys run from the primary checkout, never
from a worktree. A deploy script builds whatever is on disk, uncommitted edits included, so
check it first:

```bash
git -C ~/repos/<repo> fetch --prune
git -C ~/repos/<repo> branch --show-current   # must print main
git -C ~/repos/<repo> status --porcelain      # must print nothing
git -C ~/repos/<repo> pull --ff-only
```

If it is not on `main`, is dirty, or the fast-forward fails, **stop and report it**. Don't
stash, reset, switch branches or deploy from a worktree instead: the stray state is someone's
work in progress, and the owner decides what happens to it.

Where the repo has `origin/deploy` (the deploy-branch model), promotion in Step 3a needs only
the primary checkout on `main` and clean. A **manual path** (`deploy.sh`, `wrangler deploy`,
`supabase`, rsync plus restart) refuses to run unless its checkout's HEAD is `origin/deploy`.
The worktree policy blocks switching a primary checkout off `main`, so run it from a detached
worktree of `deploy`, which carries no one's work in progress:

```bash
git -C ~/repos/<repo> fetch origin deploy
git -C ~/repos/<repo> worktree add --detach ~/.t3/worktrees/<repo>/deploy origin/deploy
# ... Step 3 from that directory, then:
git -C ~/repos/<repo> worktree remove ~/.t3/worktrees/<repo>/deploy
```

---

## Step 2 — Detect the mechanism

```bash
bash ~/.claude/skills/deploy/scripts/detect.sh <target-dir>
```

It is read-only and prints one `<kind>\t<path>` line per mechanism, highest precedence
first, or `none`. Follow the **first** line, using the section below. Lower lines are
fallbacks the project also ships (myargus keeps a `deploy.sh` beside its CI deploy).

| Kind | Meaning | Go to |
|------|---------|-------|
| `ci-on-promote` | A workflow deploys on push to `deploy` (the deploy-branch model) | Step 3a |
| `promote-script` | `scripts/promote.sh`, the promotion mechanism | Step 3a |
| `ci-on-merge` | A workflow deploys on push to `main` (a repo not yet on the model) | Step 3a-merge |
| `runbook` | `docs/deployment.md` (or `DEPLOY.md`) describes the deploy | Step 3b |
| `deploy-script` | `deploy.sh` | Step 3c |
| `package-script` | A `deploy` script in `package.json` | Step 3c, with `pnpm run deploy` |
| `wrangler-config` only | A Worker/Pages config with no deploy owner | Step 3d |
| `none` | Nothing recognisable | Step 3d |

**Known exceptions — the table outranks detection:**

| Package | How it really deploys |
|---------|-----------------------|
| `memory-mcp` | Two deployables. The remote Worker deploys on merge (`memory-mcp-deploy-worker.yml`) until argus joins the deploy-branch model. The local stdio runtime ships as a `memory-mcp-<sha>` GitHub Release on every merge; install it with `systemctl --user start argus-context-fetch-install.service` (otherwise daily at 07:00). `deploy.sh` with no argument only prints usage. |
| `watchtower-collector`, `watchtower-usage-shim` | `deploy.sh`, run **on the host the service runs on**. Anywhere else it stops after writing `.env`. |

---

## Step 3a — CI on promote: promoting is the deploy

Do not run `deploy.sh`, `wrangler` or a build locally, and do not merge a PR expecting it to
ship. Merging to `main` only makes a SHA promotable. List what is merged but not deployed:

```bash
git -C ~/repos/<repo> fetch --prune
git -C ~/repos/<repo> log --oneline origin/deploy..origin/main
```

Nothing listed means `deploy` is current: report that and stop. Otherwise the normal path is
the owner's hub approval of the promotion card; report the SHA and the list above and stop
(only the orchestrator raises the flag). Break-glass only, when the hub cannot promote, promote
a SHA that is already on `main` (any commit, not only a release tag), from the primary checkout:

```bash
scripts/promote.sh --dry-run <sha>   # shows what ships and the push, changes nothing
scripts/promote.sh <sha>             # the deploy: approve at the prompt
```

`promote.sh` fast-forwards `deploy` to the SHA and refuses anything else. It also refuses a
SHA whose commit message carries the skip-CI marker (the release bot's `chore(release)`
commit does): GitHub runs no workflow for a push whose head commit carries it, so nothing
would deploy. The refusal names the nearest earlier commit without the marker; promote that
instead. Never force-push
`deploy`, and never push it by hand when the script exists. When the gate denies the
command, or the run is unattended, post the exact `scripts/promote.sh <sha>` line and the
`origin/deploy..origin/main` list for the owner, and stop.

To watch the deploy the promotion triggered:

```bash
gh run list -R <owner>/<repo> --workflow <workflow-file> --branch deploy --limit 3
gh run watch <run-id> -R <owner>/<repo> --exit-status
```

PRs may get preview deployments from the same workflow (myargus does). Those are not
production. A `main` push whose Deploy job shows `skipped` is correct, not a failure.

Promoting the SHA already on `deploy` is a no-op. To redeploy without a code change, use
`gh workflow run <workflow-file> -R <owner>/<repo> --ref deploy` only if the workflow
declares `workflow_dispatch`; it needs the same approval. Otherwise say there is no manual
trigger and stop. A promotion that ran no workflow (its head commit carried the skip-CI
marker) is replayed the same way, by the owner: homelab's `deploy.yml` takes a `base` input
(`-f base=<last deployed sha>`), the argus deploy workflows redeploy their target.

To undo a bad deploy, revert on `main`, merge the revert, then promote the revert's SHA.

Report the run URL and conclusion. A failed run is a red CI run: read which job failed
before attributing it.

---

## Step 3a-merge — CI on merge: merging is the deploy

A repo whose deploy workflow still runs on push to `main` has not joined the deploy-branch
model. Do not run `deploy.sh`, `wrangler` or a build locally. Tell the user:

- The deploy runs when the change merges to `main`. To ship unmerged work, open or merge
  its PR; that is the deploy, so the merge needs the same live approval.
- PRs may get preview deployments from the same workflow. Those are not production.

To watch a deploy that has been triggered:

```bash
gh run list -R <owner>/<repo> --workflow <workflow-file> --branch main --limit 3
gh run watch <run-id> -R <owner>/<repo> --exit-status
```

To redeploy `main` without a code change, use `gh workflow run <workflow-file> -R <owner>/<repo>`
only if the workflow declares `workflow_dispatch`. Otherwise say there is no manual trigger
and stop.

Report the run URL and conclusion. A failed run is a red CI run: read which job failed
before attributing it.

---

## Step 3b — Runbook: follow it

Read the runbook in full before running anything. It outranks `deploy.sh` because it carries
the steps the script does not: budget's `docs/deployment.md`, for example, requires pending
database migrations to be applied **before** `deploy.sh`, and the script never runs them.

- Do its **pre-deploy** steps first (pending migrations, prerequisites, a green `main`), in
  order. Check what is pending with the runbook's own probe; do not guess.
- When it says to run `deploy.sh`, go to Step 3c for that step.
- Then run its **verify** steps and report each result.

A step that writes to a production database, or is marked one-off, is a live action: confirm
it with the user before running it, quoting the exact command.

---

## Step 3c — deploy.sh or a package deploy script

Break-glass where the repo has a `deploy`-branch workflow or the hub promotes it. State why the
hub path was not used before running it.

Read the script's header comment first. It names the secrets it needs and any host it must
run on.

**Secrets:**

- **BWS** (the script sources `~/.bws_token` or needs `BWS_ACCESS_TOKEN`): load it with
  `set -a; source ~/.bws_token; set +a`. Never pass the file's contents as a value.
- **Personal vault** (the script calls `bw`): it unlocks non-interactively.
  ```bash
  source ~/repos/argus-config/envs/wsl2/bashrc.d/bitwarden.sh
  export BW_SESSION="$(bitwarden-session)"
  ```
  Never run `bw-unlock` from a tool call and never ask the user to unlock. If
  `bitwarden-session` fails because `~/.bw_master` is missing, stop and tell the user.
- **None** (wrangler OAuth, or no secrets): skip this.

Then run it from its own directory. In a repo with `origin/deploy` that is the detached
`deploy` worktree from Step 1, and the script refuses anywhere else; the gate asks for live
approval of the exact command:

```bash
cd <target-dir>
bash deploy.sh          # or: pnpm run deploy
```

Stream the output. On a non-zero exit, report the failing step and error line.

---

## Step 3d — No mechanism: stop and ask

Report what detection found and stop. Do not write a deploy from scratch, run
`wrangler deploy` against a bare config, or rsync files by hand. Ask the user with
`AskUserQuestion` whether to deploy by a method they name, or file an issue in the project's
repo for it to get a `deploy.sh`, a deploy workflow or a runbook.

---

## Step 4 — Verify

Prefer the project's own verification: a runbook's verify section, a script's built-in
check (myargus `deploy.sh verify <target>`), or the workflow's health-check job.

For a target that runs as a systemd user service:

```bash
systemctl --user status <service-name> --no-pager | head -20
journalctl --user -u <service-name> -n 50 --no-pager   # when it is not active
```

- agent-engine: `curl -sf http://localhost:3747/health`
- memory-mcp: `~/.argus/argus-context-mcp-server/.deployed-version` names the new release,
  and `systemctl --user show argus-context-fetch-install.service -p Result` is `success`.

---

## Step 5 — Report

- Target and the mechanism followed (from Step 2); for a promotion, the SHA promoted
- Pre-deploy steps run (runbook only)
- Deploy result: the run URL and conclusion, or the script's exit status
- Verification result
