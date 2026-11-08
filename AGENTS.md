# skills

A public repo of agent skills: pinned imports from upstream plus authored skills. Read `README.md` for layout and commands.

## Rules

- **Imports go in verbatim first.** Use `scripts/import_skill.py`; commit the import before any edit, so the pinned commit stays an exact merge base. Edit in later commits, then run `scripts/refresh_lock.py <skill>`.
- **Take upstream changes with `scripts/update_skill.py`**, never by re-importing over an edited skill: the merge keeps local edits and moves the pin. Run `update_skill.py status` to see what moved. A conflict stays pending until `resolve`.
- **Never hand-edit `skills-lock.json` hashes.** `refresh_lock.py` writes them. A rename is the one manual lock edit: move the key and set `upstreamName`.
- **Check before every push:** `bash scripts/check.sh` must pass (unit tests, then `check_skills.py`). CI and the Release test job run the same command.
- **Nothing private.** No personal paths, hostnames or tool names from the owner's own set-up (the `PRIVATE_MARKERS` list in `scripts/skills_lib.py` enforces some). This repo is public.
- **Keep SKILL.md under about 8 KB**; move detail into files the skill loads on demand. The check warns above 8 KB.
- **Licences:** an import needs its upstream licence text in `licenses/`; do not import a skill whose repo has no licence.
- Tests first for changes to `scripts/`.
