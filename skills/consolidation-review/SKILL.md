---
name: consolidation-review
title: Consolidation Review
description: >
  Review the open memory-consolidation PR in deanjstone/context: accept, reject or skip each
  finding, apply decisions through the engine, merge the cycle. Use for "review
  consolidation", "consolidation review", "review the consolidation PR",
  "/consolidation-review", or when session start shows open findings or a ⚠️/🔴 review-due
  warning.
---

# Consolidation Review

The homelab cycle (`envs/homelab/scripts/memory-consolidation-run.sh`) proposes findings
daily on one long-lived branch and PR. This skill is the decision half: it runs in the
session you already have open, so it needs no token and no GitHub App (context#221).

Critical findings are not reviewed here. The cycle files each one as a GitHub issue and
records it in `.consolidation/criticals.json`.

## Rules

- Never switch branches in `~/CONTEXT`. It is Syncthing-shared. Work in a temporary
  worktree only.
- Never hand-edit a memory file, or an entry's `before`, `after` or `applied` block. The
  engine is the only thing that applies or reverts an edit.
- Change only `state` (and optionally `note`) in the manifest.
- The merge is a **merge commit** and the branch is **never deleted**. This is the
  standing exception to squash-always; it needs no per-merge confirmation. Merge only
  with green checks and no conflicts.

## Step 1 — Worktree

```bash
VAULT_REPO="$HOME/CONTEXT"
WT="$(mktemp -d)/consolidation-review"
git -C "$VAULT_REPO" fetch --quiet origin
git -C "$VAULT_REPO" worktree add --quiet --detach "$WT" origin/memory-consolidation
cd "$WT" && git switch --quiet -C memory-consolidation-review origin/memory-consolidation

# Accepted promotions edit argus-config's compose source parts, so the engine needs a
# checkout to write into. Same branch the homelab cycle publishes promotions on.
# Stays detached: Step 4 pushes HEAD by refspec, so no local branch is ever created in
# the primary checkout's ref namespace, and Step 6 has none to delete.
CONFIG_REPO="$HOME/repos/argus-config"
CFG_WT="$HOME/.t3/worktrees/argus-config/memory-consolidation-promotions-review"
git -C "$CONFIG_REPO" fetch --quiet origin
CFG_BASE=origin/memory-consolidation-promotions
git -C "$CONFIG_REPO" rev-parse --quiet --verify "$CFG_BASE" >/dev/null || CFG_BASE=origin/main
git -C "$CONFIG_REPO" worktree add --quiet --detach "$CFG_WT" "$CFG_BASE"
gh pr list -R deanjstone/context --head memory-consolidation --state open --json number,createdAt
```

No open PR means there is nothing to review. Say so, clean up (Step 6) and stop.

## Step 2 — List open findings

```bash
python3 - <<'PY'
import json
for e in json.load(open(".consolidation/manifest.json")):
    if e.get("state") in ("proposed", "needs-judgment"):
        print(json.dumps({k: e.get(k) for k in ("id", "action", "state", "file", "into", "section", "reason", "note", "after")}))
PY
```

Zero open findings: go to Step 5.

## Step 3 — Ask

For each open finding, show the user a two-line summary before asking: the action and
file, then the reason trimmed to one sentence. For `promote`, quote the `after` text,
because that is the rule being proposed. For `needs-judgment`, quote the `note`, which
says why the engine held it.

Ask with `AskUserQuestion`, up to four findings per call, one question each. Options,
recommendation first with "(Recommended)" when you have a grounded one:

- **Accept** — the engine applies it on the next step.
- **Reject** — never re-proposed while the file's content is unchanged.
- **Skip** — stays open for a later review.

Before recommending, open the file the finding names and check the claim. A finding is a
model's judgment from an earlier day; the file may have changed since.

An accepted `promote` edits the compose source part for its section (`common/` or
`envs/<env>/overlay/`) in the argus-config worktree and reruns `compose.sh`. The engine
holds it as `needs-judgment` instead when the section has no part, or the text carries an
issue ref, ISO date or "rediscovered" (argus-config's structure check rejects those).

## Step 4 — Apply

Set the states, then run the engine with no new findings so it only applies decisions:

```bash
python3 - "$DECISIONS_JSON" <<'PY'
import json, sys
decisions = json.loads(sys.argv[1])          # {"<id>": "accepted" | "rejected"}
path = ".consolidation/manifest.json"
m = json.load(open(path))
for e in m:
    if e["id"] in decisions:
        e["state"] = decisions[e["id"]]
open(path, "w").write(json.dumps(m, indent=2, ensure_ascii=False) + "\n")
PY
echo '{"findings": []}' > /tmp/consolidation-review-empty.json
python3 scripts/consolidation_engine.py --root . --findings /tmp/consolidation-review-empty.json \
  --instructions-root "$CFG_WT"
python3 scripts/reachability_lint.py
```

The engine rewrites the manifest in its own key order; that is expected. If the lint
fails, stop and report the output. Do not push.

```bash
git add -A
git commit -m "consolidation: review decisions $(date +%F)"
git push origin HEAD:memory-consolidation
```

If a promotion was applied, publish it from the argus-config worktree on the branch the
homelab cycle uses, then open a PR if none is open (that repo merges by squash as usual):

```bash
if [ -n "$(git -C "$CFG_WT" status --porcelain)" ]; then
  git -C "$CFG_WT" add -A
  git -C "$CFG_WT" commit -m "promote consolidation findings $(date +%F)"
  git -C "$CFG_WT" push origin HEAD:memory-consolidation-promotions
  gh pr list -R deanjstone/argus-config --head memory-consolidation-promotions --state open --json number \
    | grep -q number || gh pr create -R deanjstone/argus-config --head memory-consolidation-promotions \
      --title "Memory consolidation — instruction promotions" --body "Promotions accepted in /consolidation-review."
fi
```

A rejected push to `memory-consolidation` means the homelab cycle pushed meanwhile. Clean up, start again from
Step 1, and re-ask only the findings that are still open. Never force-push this branch.

## Step 5 — Merge when nothing is open

Re-read the manifest. If any finding is still `proposed` or `needs-judgment`, report the
count and stop without merging.

Otherwise wait for checks to finish, re-read them, then merge:

```bash
gh pr checks <n> -R deanjstone/context            # poll until nothing is pending
gh pr view <n> -R deanjstone/context --json mergeable,mergeStateStatus
gh pr merge <n> -R deanjstone/context --merge      # merge commit, branch kept
```

The next cycle resets the manifest; nothing else to do.

## Step 6 — Clean up

Run each block as its own Bash call, so a failure or a hook block in one cannot stop
the other.

```bash
cd ~ && git -C "$VAULT_REPO" worktree remove --force "$WT"
git -C "$VAULT_REPO" branch -D memory-consolidation-review 2>/dev/null
```

```bash
git -C "$CONFIG_REPO" worktree remove --force "$CFG_WT"
```

Never run `git branch` against `$CONFIG_REPO`: it is a primary checkout and the
worktree-policy hook blocks the whole call. The argus-config worktree is detached, so
there is no branch to delete.

## Report

Lead with the outcome in one line: how many accepted, rejected and skipped, and whether
the cycle merged. Then list anything held as `needs-judgment` with its note.
