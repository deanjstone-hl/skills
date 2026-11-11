# skills

Agent skills (`SKILL.md`) for coding agents, maintained by Dean Stone.

Status: seeded, private. 89 skills: 59 pinned imports from upstream (15 edited: the pstack set adapted to Claude Code and T3, `pr`, `spec-review`, and the owner's private versions of `wayfinder`, `diagnosing-bugs`, `wizard`, `handoff` and `i-have-adhd` merged onto upstream) and 30 authored here, including the skills the owner's orchestrator, memory and host set-up depend on. Eight overlapping skills are folded into six: `claude-handoff` into `handoff`, `context-search` and `cortex-search` into `vault-search`, `github-setup` and `project-init-extended` into `new-project` (now `new-repo`), `grill-with-docs` into `grilling`, `issues` into `backlog-waves`, `ssh-perms-check` into `health-check`; the retired names are not in this repo, and `tests/test_retired_references.py` fails on any skill text that still names one. Nothing installs from this repo yet. Release plumbing is in place; no version has been cut.

## What lives here

- **Imported skills**, copied from upstream at a pinned commit, then edited only when needed.
- **Authored skills**, written here: no lock entry and no `SOURCE` note. They get the same front matter and size checks, and no hash checks.

Each imported skill has an entry in `skills-lock.json` (upstream repo, path, commit, content hashes, licence, whether it is edited) and a `SOURCE` note inside its directory. The upstream licence text sits in `licenses/`.

## Layout

```
skills/<name>/        one skill: SKILL.md plus its files, and SOURCE
skills-lock.json      upstream, pinned commit and hashes for every import
licenses/             upstream licence texts
scripts/              check.sh, import_skill.py, refresh_lock.py, check_skills.py, skills_lib.py, ci/release-with-retry.sh
tests/                unittest tests for the scripts
```

## Commands

Python 3 and PyYAML; `gh` for imports.

```bash
bash scripts/check.sh                          # the local check: tests, then skills, lock and licences
                                               # (same as `pnpm run check`; CI and the Release test job run it)

# import verbatim at a pinned commit (HEAD is resolved to a SHA)
python3 scripts/import_skill.py <owner/repo> <path-to-skill> --license MIT \
    [--license-path LICENSE] [--license-scope <subdir>] [--name <local-name>] [--ref <sha>] [--status unadapted]

# after editing an imported skill (--adapted also clears the `unadapted` flag)
python3 scripts/refresh_lock.py [--adapted] <skill>

# take upstream changes into an imported skill, keeping local edits
python3 scripts/update_skill.py status [<skill> ...]                 # compare each pin with upstream HEAD, no writes
python3 scripts/update_skill.py update <skill> [--ref SHA] [--path NEW_UPSTREAM_PATH]
python3 scripts/update_skill.py resolve <skill>                      # after fixing a conflicted update
```

## How imports stay updatable

1. An import is committed **verbatim** first, so the pinned upstream commit is an exact merge base.
2. Edits go in later commits. `refresh_lock.py` then records `edited: true` and the new `localHash`; the upstream hash and commit stay.
3. `check_skills.py` fails if an unedited import differs from its upstream hash, or an edited one differs from its recorded local hash.
4. `update_skill.py update` is a three-way merge per file: base is the upstream skill at the pinned commit (checked against `upstreamHash` first, and refused if it no longer matches), ours is the directory here, theirs is the skill at the new upstream commit (HEAD unless `--ref`). A clean merge advances `ref` and the hashes. A conflict writes `<<<<<<< local` / `>>>>>>> upstream` markers, sets `status: merge-conflict` with a `pending` block, and leaves the pin where it was. Fix the files and run `resolve`. `check_skills.py` fails while a conflict is pending or markers remain. If upstream moved the skill, pass `--path`. A local rename is recorded with `upstreamName`.

`status: unadapted` in the lock means the skill still names another harness's paths or tools and is not ready to use as shipped. `check_skills.py` warns about these.

## Settings and CI

- **`skills-config.json`**: `privacyCheck` controls the private-marker screen (the `PRIVATE_MARKERS` list in `scripts/skills_lib.py`: personal paths, hostnames, internal repo names). It is **off here** because the repo is private; the code stays for repos that publish skills. Force it for one run with `python3 scripts/check_skills.py --privacy` (or `--no-privacy`); with no config file it defaults to on.
- **Runners**: both workflows use `runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '"ubuntu-latest"') }}`, like the other repos. With no `CI_RUNS_ON` repo variable they run on GitHub-hosted runners. To move to the homelab JIT runners: enrol `deanjstone/skills` in the dispatcher (an owner step on the homelab, see homelab `docs/runbooks/jit-dispatcher.md`), check the dispatcher token reaches the repo, then set `CI_RUNS_ON` to `["self-hosted","homelab"]`. Set the variable only after enrolment: until then those jobs would queue with nobody serving them.

## Development

Trunk-based once the repo is on the trunk list: small commits straight to `main` with `Refs #N`; before each push run `git pull --rebase` and `bash scripts/check.sh`. Until then, pull requests. Tests first for script changes.

## Releases and the `deploy` branch

- A merge to `main` runs the check and releases nothing.
- `deploy` is only ever fast-forwarded to a commit already on `main`, on the owner's approval of a promotion. It is never force-pushed or deleted.
- A push to `deploy` runs `.github/workflows/release.yml`: job `Test before release (unit tests, skill check)`, then `Release`. semantic-release tags a version and publishes a GitHub Release from the commit types since the last tag (`feat` is minor, `fix` and `perf` are patch, a breaking change is major). **Releases are alphas for now** (owner decision, 8 Nov 2026): `.releaserc.json` marks `deploy` as an `alpha` prerelease branch, so versions read `v1.0.0-alpha.1`, `v1.0.0-alpha.2` and so on, published as GitHub prereleases, until the prerelease flag is removed on purpose. `main` is listed in the config only because semantic-release needs one non-prerelease branch; the workflow never runs on it. A promotion of only `chore`, `docs`, `ci`, `test` or `refactor` commits releases nothing.
- The `deploy` branch does not exist yet. The ops hub creates it on the first promotion.
- Nothing is installed on any machine yet: how machines consume a release is undecided (deanjstone/argus-config#1225).
- Rollback: the ops hub's Roll back card dispatches the deploy workflows (every workflow on a push to `deploy` except `release*.yml`) at a release tag. This repo has none, so there is nothing to dispatch yet. `tests/test_deploy_rollback.py` fails if one is added without ops-hub's rollback wiring: a `workflow_dispatch` trigger, a job `if:` that allows `refs/tags/v*`, `DEPLOY_ROLLBACK_TAG` set from the tag, and a `scripts/require-deploy-checkout.sh` that accepts it (deanjstone/argus#1179).

## Licence

MIT for the original content in this repo. Imported skills keep their upstream licences: see each skill's `SOURCE` note and `licenses/`.
