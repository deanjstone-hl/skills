# skills

Agent skills (`SKILL.md`) for coding agents, maintained by Dean Stone.

Status: seeded. 17 skills imported from five upstream repos, none authored yet. Imports are pinned to upstream commits; nothing here is a release yet (no `deploy` branch).

## What lives here

- **Imported skills**, copied from upstream at a pinned commit, then edited only when needed.
- **Authored skills** (none yet), written here.

Each imported skill has an entry in `skills-lock.json` (upstream repo, path, commit, content hashes, licence, whether it is edited) and a `SOURCE` note inside its directory. The upstream licence text sits in `licenses/`.

## Layout

```
skills/<name>/        one skill: SKILL.md plus its files, and SOURCE
skills-lock.json      upstream, pinned commit and hashes for every import
licenses/             upstream licence texts
scripts/              import_skill.py, refresh_lock.py, check_skills.py, skills_lib.py
tests/                unittest tests for the scripts
```

## Commands

Python 3 and PyYAML; `gh` for imports.

```bash
python3 -m unittest discover -s tests          # tests
python3 scripts/check_skills.py                # validate skills, lock, licences, private markers

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

Pull requests until the repo passes trunk readiness; then small commits straight to `main`. Releases are cut from the `deploy` branch (not created yet). Tests first for script changes.

## Licence

MIT for the original content in this repo. Imported skills keep their upstream licences: see each skill's `SOURCE` note and `licenses/`.
