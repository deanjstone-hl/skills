# Phase 3: Ops

Takes a scaffolded repo with CI to production-ready: secrets, Supabase, a deploy script and
the `deploy`-branch workflows. Assumes `~/repos/<name>/` has a git repo, source files and
`.env.example`; if not, run phase 1.

## The rule that shapes this phase

Production is anything that changes shared state or the outside world. A deploy repo deploys
**only from the `deploy` branch**, fast-forwarded to a SHA already on `main` by the owner's
Approve on the ops-hub promotion card. A `main` merge or push never deploys, and an agent runs
no deploy.

So this phase **writes** the deploy scripts and workflows. It does not run them, push `deploy`,
or run `promote.sh`. Live steps below (creating a Supabase project, applying a migration,
writing a secret) are manual paths: prepare the exact command, tell the owner, and run it
only after the owner's live approval of that exact command. AFK work prepares and notifies. A
bundle of owner steps goes in one reviewed `scripts/owner-steps/<issue>.sh`.

## 1. Choose components

Ask with `AskUserQuestion` (multi-select), and run only the selected ones:

- Supabase project
- Bitwarden secrets + `.env` template
- Deploy script and `deploy`-branch deploy workflow
- Release workflow

## 2. Supabase project

Creating a project is a live, production-writing call.

1. Ask the org and region with `AskUserQuestion` (the usual: `deanjstone` org,
   `ap-southeast-2` Sydney).
2. With the owner's live approval of the call, run `mcp__supabase__create_project` with the
   project name equal to the directory name. Poll `mcp__supabase__get_project` every 10 s, up
   to 2 minutes, until `ACTIVE_HEALTHY`.
3. Read `mcp__supabase__get_project_url` and `mcp__supabase__get_publishable_keys`. Write the
   values to `.env.local` (gitignored) and the names only to `.env.example`:
   `SUPABASE_URL`, `SUPABASE_ANON_KEY` (Node) or `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`
   (Vite).
4. An initial schema is a migration: prepare it, and apply with
   `mcp__supabase__apply_migration` only on the owner's approval.

## 3. Secrets

Run the **secrets-setup** skill with the project name and any Supabase credentials just
obtained, so it names the Bitwarden items correctly. Writing a new secret-store item is its
own confirmation.

## 4. Deploy script and workflow

Ask the deploy target with `AskUserQuestion`: runtime on a host (`~/.argus/<name>/`),
Cloudflare Workers (use the `cf` CLI unless the repo has a Wrangler config), Vercel, or custom.

Write the script at the repo root (`deploy.sh`, or `install-<host>.sh` for a host install),
`chmod +x`, and make it idempotent. Host-runtime template:

```bash
#!/usr/bin/env bash
set -euo pipefail

PACKAGE_NAME="<name>"
DEPLOY_DIR="${HOME}/.argus/${PACKAGE_NAME}"

pnpm install --frozen-lockfile
pnpm build

rsync -av --delete dist/ "${DEPLOY_DIR}/dist/"
cp package.json "${DEPLOY_DIR}/"
(cd "${DEPLOY_DIR}" && pnpm install --prod --frozen-lockfile)

node "${DEPLOY_DIR}/dist/index.js" --version
```

Cloudflare Workers: the script calls the `cf` CLI deploy (or `wrangler deploy` when a Wrangler
config exists). Vercel: `vercel --prod`.

The workflow `.github/workflows/deploy.yml` runs that script **on the `deploy` push**, on the
host's runner, never on `main`:

```yaml
name: Deploy

on:
  push:
    branches: [deploy]
  # A rollback dispatches a prior tag from the hub card.
  workflow_dispatch:

jobs:
  deploy:
    runs-on: [self-hosted, <host>]
    steps:
      - uses: actions/checkout@v4
      - run: bash deploy.sh
```

A hosted target (Cloudflare, Vercel) keeps `runs-on: ubuntu-latest` and passes its token from
a repo secret (`gh secret set <NAME> --repo <owner>/<name>` is a secret write: the owner
approves it, and the value never appears in the transcript).

## 5. Release workflow

Versions are cut only on promotion, one tag per deployable unit. `.github/workflows/release.yml`:

- Trigger `push: branches: [deploy]` plus a manual `workflow_dispatch` for a failed run. Never
  `workflow_run`: GitHub reports the default branch as the run's branch and semantic-release
  silently dry-runs.
- Job `Test before release (<what it ran>)`, then job `Release` with `needs:` it. Both run
  only when `github.ref == 'refs/heads/deploy'`.
- Nothing releasable (only `chore`, `docs`, `ci`, `test`, `refactor` commits): no test, no
  version. Otherwise the test reuses `main`'s green full CI run of the exact promoted SHA, fails
  on any red `main` run, and runs the full gate only if there is none.
- semantic-release analyses, tags and publishes the GitHub Release. It commits nothing back,
  because `deploy` is fast-forwarded from `main` and a commit made there would fork the
  branches. `.releaserc.json` sets the `branches`.

Reference implementations to copy from: `deanjstone/skills` (`.github/workflows/release.yml`,
`.releaserc.json`, `scripts/ci/release-with-retry.sh`) and `atto1`'s `release.yml`.

## 6. Register the repo

- Add the repo to the deploy-repo list in the instruction files (`common/` in `argus-config`:
  a PR, and a deploy-gate change goes through the same promotion).
- Ask the owner to register it with the ops hub; the first promotion creates `deploy`. Do not
  create or push `deploy` yourself.

## 7. Commit and push

Stage only the new files (never `.env.local`):

```bash
git add .env.example deploy.sh .github/ README.md
git commit -m "chore: wire production ops (secrets, deploy, release)"
git pull --rebase && bash scripts/check.sh   # or the repo's check
git push origin HEAD:main
```

Watch CI on the pushed SHA with a Monitor.

## 8. Report

```
Ops wired for <project>
  Supabase: <ref>.supabase.co | skipped | prepared, awaiting owner approval
  Secrets: items listed | skipped
  Deploy: deploy.sh + deploy.yml on push to deploy | skipped
  Release: release.yml (Test before release, Release) | skipped
  Registered: deploy-repo list PR <url> | pending
```

List every manual step left for the owner (Supabase create, migration, secret writes, hub
registration, first promotion).
