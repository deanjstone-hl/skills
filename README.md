# skills

Agent skills (`SKILL.md`) for coding agents, maintained by Dean Stone.

Status: seeded. Every skill is a pinned import from upstream (none authored yet); the pstack skills are adapted to Claude Code and T3 on top of the verbatim base. Release plumbing is in place; no version has been cut.

## What lives here

- **Imported skills**, copied from upstream at a pinned commit, then edited only when needed.
- **Authored skills** (none yet), written here.

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
bash scripts/check.sh                          # the local check: tests, then skills, lock, licences, private markers
                                               # (same as `pnpm run check`; CI and the Release test job run it)

# import verbatim at a pinned commit (HEAD is resolved to a SHA)
python3 scripts/import_skill.py <owner/repo> <path-to-skill> --license MIT \
    [--license-path LICENSE] [--license-scope <subdir>] [--name <local-name>] [--ref <sha>] [--status unadapted]

# after editing an imported skill
python3 scripts/refresh_lock.py <skill>
```

## How imports stay updatable

1. An import is committed **verbatim** first, so the pinned upstream commit is an exact merge base.
2. Edits go in later commits. `refresh_lock.py` then records `edited: true` and the new `localHash`; the upstream hash and commit stay.
3. `check_skills.py` fails if an unedited import differs from its upstream hash, or an edited one differs from its recorded local hash.
4. Taking an upstream update (not built yet) will be a three-way merge: base = upstream file at the pinned commit, ours = the file here, theirs = new upstream. Renames are recorded with `upstreamName`.

`status: unadapted` in the lock means the skill still names another harness's paths or tools and is not ready to use as shipped. `check_skills.py` warns about these.

## Development

Trunk-based once the repo is on the trunk list: small commits straight to `main` with `Refs #N`; before each push run `git pull --rebase` and `bash scripts/check.sh`. Until then, pull requests. Tests first for script changes.

## Releases and the `deploy` branch

- A merge to `main` runs the check and releases nothing.
- `deploy` is only ever fast-forwarded to a commit already on `main`, on the owner's approval of a promotion. It is never force-pushed or deleted.
- A push to `deploy` runs `.github/workflows/release.yml`: job `Test before release (unit tests, skill check)`, then `Release`. semantic-release tags `vX.Y.Z` and publishes a GitHub Release from the commit types since the last tag (`feat` is minor, `fix` and `perf` are patch, a breaking change is major). A promotion of only `chore`, `docs`, `ci`, `test` or `refactor` commits releases nothing.
- Nothing is installed on any machine yet: how machines consume a release is undecided (deanjstone/argus-config#1225).

## Licence

MIT for the original content in this repo. Imported skills keep their upstream licences: see each skill's `SOURCE` note and `licenses/`.
