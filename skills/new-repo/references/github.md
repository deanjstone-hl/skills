# Phase 2: GitHub

Wires a local repo to GitHub: the repo itself, CI that runs the local check, a PR template,
labels and trunk readiness. Routine GitHub actions (repo, branches, commits, PRs, issues) are
pre-authorized; org or account settings are not.

## 1. Identify the project and the remote

```bash
cd ~/repos/<name>
git remote get-url origin
```

No remote: create it (private unless the owner says public) and push the scaffold:

```bash
gh repo create <name> --private --source . --remote origin
git push -u origin main
```

Not named: ask with `AskUserQuestion`.

## 2. Detect existing CI

```bash
ls .github/workflows/ 2>/dev/null | head -10
```

Existing workflows: ask whether to add or update. Never overwrite one without asking.

## 3. Find the check

The repo needs one committed local check that workers run before every push and CI runs
on every push to `main`: a `check` script in `package.json`, `scripts/check.sh`,
`scripts/check`, or a Makefile `check` target. The README or `AGENTS.md` must name it
(`scripts/trunk-readiness.sh` reads that as evidence). Read `package.json`, `tsconfig.json`
or `CLAUDE.md` for the stack and build, test and lint commands; ask if unclear. Lint is
oxlint (`pnpm lint`), never ESLint or Biome.

## 4. CI workflow

`.github/workflows/ci.yml`, run on every push to `main` and every pull request. It runs the
check as one command and has no `if:` that skips a squash-merge push (trunk readiness fails
on that).

TypeScript / Node:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'pnpm'
      - run: pnpm install --frozen-lockfile
      - run: pnpm check
```

`pnpm/action-setup` reads the version from `packageManager` in `package.json`. A repo with no
`lint` or `check` script yet gets oxlint and the script first (`pnpm add -D oxlint
oxlint-tsgolint`, `oxlint.config.ts`, as in phase 1). No test suite yet: leave
`# TODO: add test command` in the check rather than a test step that fails.

C# / .NET:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-dotnet@v4
        with:
          dotnet-version: '8.x'
      - run: dotnet restore
      - run: dotnet build --no-restore
      - run: dotnet test --no-build
```

Self-hosted runners: use `runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '"ubuntu-latest"') }}` and guard
hosted-only setup steps with `if: runner.environment == 'github-hosted'`, as
`deanjstone/skills` does in `check.yml`.

## 5. PR template

`.github/pull_request_template.md`:

```markdown
## Summary

<!-- 1-3 bullets: what does this PR do? -->

## Why

<!-- The motivation: why this change, not just what it contains. -->

## Test plan

- [ ] Tested locally, with the output in this description
- [ ] No regressions in existing features

## README

- [ ] README updated, or not needed because: <reason>

## Checklist

- [ ] Commit messages are conventional (`type: subject`)
- [ ] No `.env` or secrets committed

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

No `.github/ISSUE_TEMPLATE/`: issues go through the wayfinder and todo skills, which enforce
their own body structure. Revisit only if the repo goes public with outside contributors.

## 6. Labels

The todo skill files every issue with one `wave:*` and one `mode:*` label. Check the repo is
in scope and the labels exist: `python3 ~/repos/argus-config/hooks/backlog-labels.py repos`
lists the scope, and `ensure` creates the labels. A repo missing from the scope list is an
argus-config change (the scope is defined in `backlog-labels.py`).

## 7. Branch protection

- **Trunk repo** (the standard): small commits straight to `main`, so no protection that
  requires a PR or blocks direct pushes to `main`.
- **`deploy`** is fast-forwarded by the hub and never force-pushed or deleted. Protect it
  against force-push and deletion where the plan allows (public repo or GitHub Pro; private
  repos on the free plan cannot). It does not exist until the first promotion, so do not
  create or push it.
- **A non-trunk repo** uses a dedicated branch + PR; where the plan allows, require the
  `check` status on `main`:

```bash
gh api repos/<owner>/<repo>/branches/main/protection --method PUT \
  --field required_status_checks='{"strict":true,"contexts":["check"]}' \
  --field enforce_admins=false \
  --field required_pull_request_reviews=null \
  --field restrictions=null
```

Say plainly when protection was skipped for the plan.

## 8. README

The README covers setup, commands (naming the check), config and env, and deploy. A change to
any of them updates the README in the same push.

## 9. Trunk readiness

```bash
bash ~/repos/argus-config/scripts/trunk-readiness.sh <owner>/<repo>
```

It checks four points: the README names a committed local check, CI on push to `main` runs
it, every pushing workflow runs the check and retries with a re-sync, and a pushed SHA
verifies. Fix anything it fails. Keep its output for the Resolution. Aquila records the repo
in `trunk_repos` once it passes; do not edit the directive yourself.

## 10. Commit and push

```bash
git add .github/ README.md
git commit -m "ci: add github actions CI and PR template"
git pull --rebase && bash scripts/check.sh   # or the repo's check
git push origin HEAD:main
```

A fallback (non-trunk) repo pushes a branch and opens a PR instead. Then watch CI on the
pushed SHA with a Monitor, not `gh --watch`.

## 11. Report

```
GitHub setup complete for <project>
  CI: .github/workflows/ci.yml (Node/TS | .NET), runs the check on push and PR
  PR template: .github/pull_request_template.md
  Labels: ensured | repo not in scope (argus-config change needed)
  Branch protection: none (trunk) | applied | skipped (plan)
  Trunk readiness: READINESS: ok | fail <point>
```
