# skills

Agent skills (`SKILL.md`) for coding agents, maintained by Dean Stone.

Status: seeded. 89 skills: 59 pinned imports from upstream (15 edited: the pstack set adapted to Claude Code and T3, `pr`, `spec-review`, and the owner's private versions of `wayfinder`, `diagnosing-bugs`, `wizard`, `handoff` and `i-have-adhd` merged onto upstream) and 30 authored here, including the skills the owner's orchestrator, memory and host set-up depend on. Eight overlapping skills are folded into six: `claude-handoff` into `handoff`, `context-search` and `cortex-search` into `vault-search`, `github-setup` and `project-init-extended` into `new-project` (now `new-repo`), `grill-with-docs` into `grilling`, `issues` into `backlog-waves`, `ssh-perms-check` into `health-check`; the retired names are not in this repo, and `tests/test_retired_references.py` fails on any skill text that still names one. Nothing installs from this repo yet. Release plumbing is in place; the version history is the repository's own (`v1.0.0` and the issues stay where they are).

**Public, in place.** The repo goes public as the same repository (skills/30), not through a new one: its history, issues, tags, `deploy`, T3 project and local clones all stay. The owner runs one command, `bash scripts/owner-steps/28.sh` (`--dry-run` first), which stores the addresses a skill needs in Bitwarden Secrets Manager, scans every issue and pull request, deletes the `CI_RUNS_ON` variable, flips the visibility and sets the fork approval policy. No private value is in the tree: addresses a skill needs are read at run time from Secrets Manager by key name, `.env.example` lists the names with no value, and `bash scripts/scrub-scan.sh` (gitleaks plus personal-data rules) must report no finding. See `docs/public-cutover.md`.

## What lives here

- **Imported skills**, copied from upstream at a pinned commit, then edited only when needed.
- **Authored skills**, written here: no lock entry and no `SOURCE` note. They get the same front matter and size checks, and no hash checks.

Each imported skill has an entry in `skills-lock.json` (upstream repo, path, commit, content hashes, licence, whether it is edited) and a `SOURCE` note inside its directory. The upstream licence text sits in `licenses/`.

## Layout

```
skills/<name>/        one skill: SKILL.md plus its files, and SOURCE
skills-lock.json      upstream, pinned commit and hashes for every import
licenses/             upstream licence texts
docs/                 public-cutover.md: where private values live, CI safety, the scrub scan, the public-flip runbook
.env.example          Secrets Manager key names for private values, no values (`.env` is gitignored)
.gitleaks.toml        the scrub rules behind scripts/scrub-scan.sh
scripts/              check.sh, import_skill.py, refresh_lock.py, check_skills.py, skills_lib.py, release-needed.sh, scrub-scan.sh, owner-steps/28.sh (the in-place public flip, owner-run), ci/ (release-with-retry.sh, release-proof.sh, release-scripts-check.sh, release-scripts.lock: vendored from argus-config, synced and never edited here; the check fails CI on a hand-edited copy)
tests/                unittest tests for the scripts
```

## Commands

Python 3 and PyYAML; `gh` for imports; `gitleaks` and `jq` for the scrub scan (the scan and the owner-step tests skip without them).

```bash
bash scripts/check.sh                          # the local check: tests, then skills, lock and licences
                                               # (same as `pnpm run check`; CI and the Release test job run it)
bash scripts/scrub-scan.sh                     # gitleaks + personal-data rules over the tree: must print `pass (0 findings)`

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

- **`skills-config.json`**: `privacyCheck` controls the private-marker screen (the `PRIVATE_MARKERS` list in `scripts/skills_lib.py`: personal paths, hostnames, internal repo names). It is **off here**: the skills cite the owner's private repos and vault paths on purpose, and the screen would fail 60 times. The value gate is `scripts/scrub-scan.sh`. Force the marker screen for one run with `python3 scripts/check_skills.py --privacy` (or `--no-privacy`); with no config file it defaults to on.
- **Runners**: both workflows run every job on `vars.CI_RUNS_ON`, default `ubuntu-latest`, so the billing guard can move them to a homelab runner once the repo is enrolled in the JIT dispatcher (homelab#475). The repo is private, so the public-safe invariant (hosted runners only, no `CI_RUNS_ON`) was relaxed on purpose; `tests/test_public_safe.py` still fails on a hard-coded `self-hosted` runner, `pull_request_target`, or a secret beyond the read-only `GITHUB_TOKEN` in `check.yml`. If the repo goes public, `git revert` the homelab#475 commit to restore the strict invariant and keep it out of the dispatcher.
- **README guard**: [`readme-guard.yml`](.github/workflows/readme-guard.yml) (logic in [`.github/scripts/readme-guard.sh`](.github/scripts/readme-guard.sh), vendored from [argus-config/1147](https://github.com/deanjstone/argus-config/issues/1147)) runs on every push to `main`, always on `ubuntu-latest` (no `CI_RUNS_ON`: it is seconds of work and needs no homelab path). It fails a push that changes `package.json` scripts or `bin`, a workflow, a deploy or install script, an env template or a CLI entry point without touching a README, unless a commit message carries `README: not needed because <reason>`. Change the script in argus-config and re-copy it; do not edit it here.

## Development

Trunk-based: small commits straight to `main` with `Refs #N`; before each push run `git pull --rebase` and `bash scripts/check.sh`. Tests first for script changes. `scripts/check.sh` takes the host-wide heavy lock ([argus-config/1506](https://github.com/deanjstone/argus-config/issues/1506)): it re-runs itself through `scripts/heavy-lock.sh`, so only one full check runs at a time on a host, whichever thread or CI job starts it, and it also waits while memory `some avg60` is 10 or more. A queued run prints `waiting for the host lock` and starts when the holder ends; it exits 75 without running once `HEAVY_LOCK_TIMEOUT` (3600 s) passes. `scripts/heavy-lock.sh` and `scripts/heavy-lock.lock` are vendored byte-for-byte from argus-config (its `scripts/sync-heavy-lock.sh` rewrites both; never edit them here), and `tests/test_heavy_lock.py` fails on a copy that no longer matches its lock.

## Releases and the `deploy` branch

- A merge to `main` runs the check and releases nothing.
- `deploy` is only ever fast-forwarded to a commit already on `main`, on the owner's approval of a promotion. It is never force-pushed or deleted.
- A push to `deploy` runs `.github/workflows/release.yml`: job `Test before release (unit tests, skill check)`, then `Release` (`needs:` it). The test job starts with `scripts/release-needed.sh`, which looks at the commits since the last `v*` tag: with no `feat`, `fix`, `perf`, `revert` or breaking change, the run ends green with no test and no version. Otherwise it runs `bash scripts/check.sh` on the promoted SHA, then semantic-release tags a version and publishes a GitHub Release (`feat` is minor, `fix` and `perf` are patch, a breaking change is major). `deploy` is the only release branch in `.releaserc.json`, so versions are plain `vX.Y.Z`; the first promotion with a releasable commit is `v1.0.0`. The workflow's concurrency group is `release`.
- The github plugin's `successComment`, `failComment` and `releasedLabels` are off: commit subjects cite `#N` refs that can point at issues in other repos, and the plugin's success step turns the Release job red after the tag is cut when it cannot resolve them.
- The `deploy` branch does not exist yet. The ops hub creates it on the first promotion.
- Nothing is installed on any machine yet: how machines consume a release is undecided (deanjstone/argus-config#1225).
- Rollback: the ops hub's Roll back card dispatches the deploy workflows (every workflow on a push to `deploy` except `release*.yml`) at a release tag. This repo has none, so there is nothing to dispatch yet. `tests/test_deploy_rollback.py` fails if one is added without ops-hub's rollback wiring: a `workflow_dispatch` trigger, a job `if:` that allows `refs/tags/v*`, `DEPLOY_ROLLBACK_TAG` set from the tag, and a `scripts/require-deploy-checkout.sh` that accepts it (deanjstone/argus#1179).

## Licence

MIT for the original content in this repo. Imported skills keep their upstream licences: see each skill's `SOURCE` note and `licenses/`.
