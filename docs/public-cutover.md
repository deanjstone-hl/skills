---
summary: "skills is a public repository with no private value in the tree: where each value lives in Bitwarden Secrets Manager, what keeps CI safe against fork pull requests, the scrub scan, and the owner's runbook for the fresh-history cutover (scripts/owner-steps/27.sh)"
read_when:
  - "adding an address, an id, an email or a fixture that looks like one to the tree"
  - "a skill needs a private value at run time"
  - "running or resuming the public cutover (skills/27, skills/28)"
  - "a fork pull request, a self-hosted runner or a new workflow trigger on this repository"
---

# skills: a public repository, private values in Bitwarden

Decided by the owner on 15 Nov 2026 10:46 AEDT (skills/27, part of the runner-split map
homelab/463; audit homelab/464): skills goes public so its CI runs on free GitHub-hosted minutes.
Private values live in Bitwarden Secrets Manager (BWS) with placeholders in `.env.example`, and the
history is cleaned by starting again: the current repository is renamed `skills-archive` and kept
private, and a new public `skills` starts from one commit of the scrubbed tree.

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

The four secrets go in the project that already holds `syncthing-device-homelab`. The cutover
script creates them, taking each value from the last commit that still held it, so nobody types an
address. Nothing in CI reads Secrets Manager.

**Why there is no `BWS_ACCESS_TOKEN` Actions secret:** no workflow reads a private value, and the
repository is public. A token a workflow does not need is exposure for nothing, so the cutover
does not create one. If a workflow ever needs a value, give it a machine account scoped to one
project, never `personal-machine-secrets`, and add a test to `tests/test_public_safe.py` that names
the step holding it.

## What keeps CI safe on a public repository

GitHub: a fork's pull request starts workflows on the upstream repository; secrets are not passed
to it; and self-hosted runners "should almost never be used for public repositories". So
`tests/test_public_safe.py` pins, for every workflow:

- every job is `runs-on: ubuntu-latest` (no `self-hosted`, no `CI_RUNS_ON` or other variable that
  could pick a runner, no `runner.environment` branch, no action from a private repository);
- no `pull_request_target`;
- a workflow a pull request starts (`check.yml`) uses no secret but the read-only `GITHUB_TOKEN`;
- no workflow holds `BWS_ACCESS_TOKEN`.

`release.yml` runs only on a push to `deploy` or a manual dispatch, and holds the write-scoped
`GITHUB_TOKEN` for semantic-release. The cutover sets the fork pull-request approval policy to
`all_external_contributors`, so a maintainer approves every first run from a fork.

## The scrub scan

`bash scripts/scrub-scan.sh` runs gitleaks 8 with `.gitleaks.toml`: the default rules plus emails
(placeholders at example.com and similar are allowed), tailnet and LAN addresses, tailnet
hostnames, Australian mobile numbers, Cloudflare ids (32 or 64 hex, UUIDs) and Access team domains.
It scans the tracked and new files, `--head` scans HEAD, a directory argument scans that directory.
It prints rule, file and line, never a value. Test fixtures build any value that looks private at
run time so the scan stays at zero. The cutover script runs it on the tree it would publish and
stops on a hit. Main CI has no gitleaks, so the scan runs on a worker's host through
`bash scripts/check.sh` (its tests skip without gitleaks) and in the cutover script.

Two things it allows on purpose: the SHA-256 content hashes in `skills-lock.json` (the 64-hex rule
is silenced for that one file; an email or address in it is still caught), and one upstream example
address in the verbatim `mcp-builder` reference.

What the scan cannot see, and the owner decides: bare machine names, a Windows account name in a
path, the 7-character Syncthing device-ID prefixes (the full IDs are not in the repo), and the
names of the owner's private repositories and vault paths that many skills cite. The repo's own
private-marker screen (`PRIVATE_MARKERS` in `scripts/skills_lib.py`, `privacyCheck` in
`skills-config.json`) lists those and is left off: turning it on today fails 60 times, one per
cited repo, vault path or orchestrator name.

## The cutover (skills/28, owner)

`scripts/owner-steps/27.sh` is written and has only been run with `--dry-run`. It is one approved
command from a checkout of `main` at the merged commit. Why this order: GitHub cannot transfer an
issue from a private repository to a public one, so the new repository starts **private**, the
open issues are transferred, their text is checked, and only then does it go public.

```bash
bash scripts/owner-steps/27.sh --dry-run   # reads state, prints every action, changes nothing
bash scripts/owner-steps/27.sh             # exit 3 = stopped before public: edit the issues it names, run it again
```

It renames the repository to `skills-archive` (private), creates the four BWS secrets it can
derive, creates the private new `skills` from one squashed commit and pushes `main`, clones the
labels, sets the Actions secrets named in `SKILLS_ACTIONS_SECRETS` (none today), does not recreate
`CI_RUNS_ON`, transfers the open issues except `SKILLS_KEEP_ISSUES` (default `27 28`), scans them,
makes the repository public, sets the fork approval policy, verifies, and prints the wiring. It is
idempotent: a run that stopped can be run again. It never pushes `deploy`, never runs `promote.sh`,
and never starts a workflow. Transferred issues get new numbers, oldest first; the script prints
`archive#N -> skills#M`.

After it: re-clone `~/repos/skills` on both hosts and repoint the T3 project; the first promotion
(the ops-hub Approve) creates `deploy` in the new repository. The first commit is a `chore`, so
that promotion cuts no version until a `feat` or `fix` lands. A reference to `deanjstone/skills#N`
anywhere else now means the new repository's #N. Owner decisions the script leaves open: whether
to archive `skills-archive` (`gh repo archive`).

## Sources read

- GitHub Docs: [renaming a repository](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository)
  (redirects for web and git; "do not reuse the original name of the renamed repository", or the
  redirects stop, which step 3 does on purpose; no redirect for an action),
  [creating a repository](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)
  (name rules; do not pre-populate a repository you will push to),
  [transferring an issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/administering-issues/transferring-an-issue-to-another-repository)
  (open issues only, same owner, a private repository's issue cannot move to a public one; labels
  survive only if the target has them), [Actions secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)
  and [variables](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-variables)
  (`gh secret set` reads stdin; forks get no secrets; neither carries over a new repository),
  [repository visibility](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility)
  (private to public: code and Actions logs visible, anyone can fork, push rulesets disabled, stars
  and watchers erased), [secure use of Actions](https://docs.github.com/en/actions/reference/security/secure-use)
  (self-hosted runners, `pull_request_target`) and the
  [Actions permissions REST API](https://docs.github.com/en/rest/actions/permissions) (the fork
  pull-request approval policy).
- Bitwarden: [Secrets Manager CLI](https://bitwarden.com/help/secrets-manager-cli/) (`secret list`,
  `secret create`, `--output`, `BWS_ACCESS_TOKEN`, machine accounts scoped to projects; `get` takes
  an id, so a name is looked up in the list).
