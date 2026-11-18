# skills

A public repo of agent skills (made public in place, history kept): pinned imports from upstream plus authored skills. Read `README.md` for layout and commands.

## Rules

- **Imports go in verbatim first.** Use `scripts/import_skill.py`; commit the import before any edit, so the pinned commit stays an exact merge base. Edit in later commits, then run `scripts/refresh_lock.py <skill>`.
- **Take upstream changes with `scripts/update_skill.py`**, never by re-importing over an edited skill: the merge keeps local edits and moves the pin. Run `update_skill.py status` to see what moved. A conflict stays pending until `resolve`.
- **Never hand-edit `skills-lock.json` hashes.** `refresh_lock.py` writes them. A rename is the one manual lock edit: move the key and set `upstreamName`.
- **Check before every push:** `bash scripts/check.sh` must pass (unit tests, then `check_skills.py`). CI and the Release test job run the same command.
- **Authored skills have no lock entry and no `SOURCE` file.** Adding either to an authored skill makes the check treat it as an import and fail it.
- **Nothing private goes in the tree: the repo is public.** No address, hostname, email, Cloudflare id or other value that identifies the owner's hosts or accounts. A skill that needs one reads it at run time from Bitwarden Secrets Manager by key name (see `skills/syncthing-pair`), and the key name goes in `.env.example`. `bash scripts/scrub-scan.sh` must print `pass (0 findings)` before a push. Test fixtures build such values at run time. `docs/public-cutover.md` has the rules.
- **CI runs on `vars.CI_RUNS_ON` (default `ubuntu-latest`).** Never a hard-coded `self-hosted`, `pull_request_target` or a secret in a workflow a pull request starts: `tests/test_public_safe.py` fails on each. The strict hosted-only rule was relaxed on purpose while the repo is private (homelab#475); `git revert` that commit before going public.
- **The private-marker check is off here, not removed.** `skills-config.json` sets `privacyCheck: false` because the skills cite the owner's private repos and vault paths on purpose. The screen (`PRIVATE_MARKERS` in `scripts/skills_lib.py`) stays: switch it on with `check_skills.py --privacy`. Never commit secrets either way.
- **Keep SKILL.md under about 8 KB**; move detail into files the skill loads on demand. The check warns above 8 KB.
- **Licences:** an import needs its upstream licence text in `licenses/`; do not import a skill whose repo has no licence.
- Tests first for changes to `scripts/`.
