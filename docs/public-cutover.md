---
summary: "skills is made public in place, with no private value in the tree: where each value lives in Bitwarden Secrets Manager, what keeps CI safe against fork pull requests, the scrub scan, and the owner's runbook for the flip (scripts/owner-steps/28.sh)"
read_when:
  - "adding an address, an id, an email or a fixture that looks like one to the tree"
  - "a skill needs a private value at run time"
  - "running or resuming the public flip (skills/30)"
  - "a fork pull request, a self-hosted runner or a new workflow trigger on this repository"
---

# skills: a public repository, private values in Bitwarden

Decided by the owner on 15 Nov 2026 10:46 AEDT (skills/27, part of the runner-split map
homelab/463; audit homelab/464): skills goes public so its CI runs on free GitHub-hosted minutes.
Private values live in Bitwarden Secrets Manager (BWS) with placeholders in `.env.example`.

**Changed on 18 Nov 2026, 07:46 AEDT (skills/30): flip in place, no fresh history.** skills/27
planned a fresh-history cutover: rename the repository to `skills-archive`, publish one squashed
commit as a new `skills`, transfer the open issues. The owner chose to flip the same repository
instead, keeping its history, issues, tags, `deploy`, the T3 project and both local clones. That is
safe because the history's only private values are the 26 Tailscale `100.x` addresses in
`skills/syncthing-pair`, added in two commits on 8 Nov: they cannot be routed outside the tailnet,
and the homelab/464 audit already called a history rewrite optional. HEAD is clean and a
full-history `gitleaks git` run on 18 Nov found nothing. Those two commits stay readable in the
public history; the owner accepted that. `scripts/owner-steps/27.sh` and its tests are deleted (see
git history); no `skills-archive` repository exists and no issue is renumbered.

## Where each private value lives

The audit found one kind of private value here: 26 Tailscale addresses in `skills/syncthing-pair`.
There is no Worker, no deploy script and no Cloudflare id in this repository, so nothing else moved.

| BWS secret | Used by | Origin |
|---|---|---|
| `syncthing-tailscale-ip-wsl` | `skills/syncthing-pair`, as `$WSL_IP` | the WSL2 node's tailnet address (`tailscale ip -4`) |
| `syncthing-tailscale-ip-lgn5` | `skills/syncthing-pair`, as `$LGN5_IP` | the Windows host's tailnet address |
| `syncthing-tailscale-ip-homelab` | `skills/syncthing-pair`, as `$HOMELAB_IP` | the homelab server's tailnet address |
| `syncthing-tailscale-ip-dj15` | `skills/syncthing-pair`, as `$DJ15_IP` | the iPhone's tailnet address (SyncTrain and VaultSync share it) |

The skill reads them by key name:

```bash
ts_ip() { bws secret list -o json | jq -r --arg k "syncthing-tailscale-ip-$1" '.[] | select(.key == $k) | .value'; }
```

`bws secret list --output env` is not used: it comments out any key that is not a POSIX variable
name, and these have dashes (Bitwarden, Secrets Manager CLI). `.env.example` lists the key names
with no value; `.env` is gitignored.

The four secrets go in the project that already holds `syncthing-device-homelab`. The flip
script creates them, taking each value from the last commit that still held it, so nobody types an
address. Nothing in CI reads Secrets Manager.

**Why there is no `BWS_ACCESS_TOKEN` Actions secret:** no workflow reads a private value, and the
repository is public. A token a workflow does not need is exposure for nothing, so the flip
does not create one. If a workflow ever needs a value, give it a machine account scoped to one
project, never `personal-machine-secrets`, and add a test to `tests/test_public_safe.py` that names
the step holding it.

## What keeps CI safe on a public repository

GitHub: a fork's pull request starts workflows on the upstream repository; secrets are not passed
to it; and self-hosted runners "should almost never be used for public repositories". So
`tests/test_public_safe.py` pins, for every workflow:

- no job hard-codes a self-hosted runner. While the repo is private, a job may read `vars.CI_RUNS_ON`
  (homelab#475) so the billing guard can move it to a homelab runner, and `release.yml` uses the
  private `host-pnpm` action there. **This invariant was relaxed on purpose.** Before the flip,
  `git revert` the homelab#475 commit: it restores every job to `runs-on: ubuntu-latest` (no
  `CI_RUNS_ON`, no `runner.environment` branch, no action from a private repository) and the stricter
  test. `28.sh` also deletes the `CI_RUNS_ON` variable;
- no `pull_request_target`;
- a workflow a pull request starts (`check.yml`) uses no secret but the read-only `GITHUB_TOKEN`;
- no workflow holds `BWS_ACCESS_TOKEN`.

`release.yml` runs only on a push to `deploy` or a manual dispatch, and holds the write-scoped
`GITHUB_TOKEN` for semantic-release. The flip sets the fork pull-request approval policy to
`all_external_contributors`, so a maintainer approves every first run from a fork.

## The scrub scan

`bash scripts/scrub-scan.sh` runs gitleaks 8 with `.gitleaks.toml`: the default rules plus emails
(placeholders at example.com and similar are allowed), tailnet and LAN addresses, tailnet
hostnames, Australian mobile numbers, Cloudflare ids (32 or 64 hex, UUIDs) and Access team domains.
It scans the tracked and new files, `--head` scans HEAD, a directory argument scans that directory.
It prints rule, file and line, never a value. Test fixtures build any value that looks private at
run time so the scan stays at zero. The flip script runs it on HEAD (`--head`) and stops on a hit. Main CI has no gitleaks, so the scan runs on a worker's host through
`bash scripts/check.sh` (its tests skip without gitleaks) and in the flip script.

Two things it allows on purpose: the SHA-256 content hashes in `skills-lock.json` (the 64-hex rule
is silenced for that one file; an email or address in it is still caught), and one upstream example
address in the verbatim `mcp-builder` reference.

What the scan cannot see, and the owner decides: bare machine names, a Windows account name in a
path, the 7-character Syncthing device-ID prefixes (the full IDs are not in the repo), and the
names of the owner's private repositories and vault paths that many skills cite. The repo's own
private-marker screen (`PRIVATE_MARKERS` in `scripts/skills_lib.py`, `privacyCheck` in
`skills-config.json`) lists those and is left off: turning it on today fails 60 times, one per
cited repo, vault path or orchestrator name.

## The flip (skills/30, owner)

`scripts/owner-steps/28.sh` is one approved command, run from a checkout of `main` at the approved
commit: clean, `HEAD` equal to `origin/main`, and `origin/main` equal to the tip of `main` on
GitHub (it checks all three). `~/repos/skills` may rest detached at `origin/deploy` after a
deploy: `git switch main && git pull --ff-only` first.

```bash
bash scripts/owner-steps/28.sh --dry-run   # reads state, prints every action, changes nothing
bash scripts/owner-steps/28.sh             # exit 3 = stopped before the flip: edit what it names, run it again
```

In order, each step checking the state first so a run that stopped can be run again:

1. Creates `syncthing-tailscale-ip-{wsl,lgn5,homelab,dj15}` in Secrets Manager from the last commit
   of this repo's history that held the addresses, in the project of `syncthing-device-homelab`.
   An existing entry is left alone; no value is printed.
2. Scans the title, body, comments and reviews of **every** issue and pull request, open and
   closed, and every inline review comment, with the scrub rules. Any hit stops the run before the
   flip (exit 3) and names the item, never the value. A list that reaches its 1000-item limit is an
   error, not a pass.
3. Deletes the Actions variable `CI_RUNS_ON` if present (the workflows run on `ubuntu-latest`).
   Other variables are listed and left alone.
4. `gh repo edit deanjstone/skills --visibility public --accept-visibility-change-consequences`.
5. Sets the fork pull-request approval policy to `all_external_contributors`. GitHub refuses to
   read or write the policy while the repository is private ("Fork PR approval is not allowed for
   private repositories"), so a dry run on the private repository cannot show it; this step comes
   after the flip.
6. Verifies: the repository is public, the policy is set, the four keys exist (names only) and
   `CI_RUNS_ON` is gone. A failed check exits 1.

The pre-flight also fails the run (also under `--dry-run`) when the tree at `HEAD` fails the scrub
scan or a self-hosted runner is registered on the repository: do not register one on a public
repository. The script never renames, transfers, archives or deletes anything, never pushes
`deploy`, never runs `promote.sh` and never starts a workflow.

Nothing needs re-pointing afterwards: the repository, its issue numbers, `v1.0.0`, `deploy`, the T3
project and both local clones are unchanged. Approve the next promotion on the ops-hub card as
usual. GitHub notes that flipping to public erases stars and watchers and lets anyone fork. Owner
decision the script leaves open: whether the names in the next section should go too.

## Sources read

- GitHub Docs: [Actions secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)
  and [variables](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-variables)
  (forks get no secrets),
  [repository visibility](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility)
  (private to public: code and Actions logs visible, anyone can fork, push rulesets disabled, stars
  and watchers erased), [secure use of Actions](https://docs.github.com/en/actions/reference/security/secure-use)
  (self-hosted runners, `pull_request_target`) and the
  [Actions permissions REST API](https://docs.github.com/en/rest/actions/permissions) (the fork
  pull-request approval policy).
- Bitwarden: [Secrets Manager CLI](https://bitwarden.com/help/secrets-manager-cli/) (`secret list`,
  `secret create`, `--output`, `BWS_ACCESS_TOKEN`, machine accounts scoped to projects; `get` takes
  an id, so a name is looked up in the list).
