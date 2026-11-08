---
name: git-maintenance
description: >
  Clean up stale branches, prune remote-tracking refs and run git housekeeping across repos.
  Use for "clean branches", "git cleanup", "prune branches", "housekeeping", "prune refs",
  "/git-maintenance", or tidying a git repository.
---

# Git Maintenance

Runs branch cleanup, remote pruning, and gc in a repo. Always confirms before deleting
anything.

**T3 Code owns every worktree under `~/.t3/worktrees/`** (`/home/deanj/.t3/worktrees` on
WSL2, `/home/srvr/.t3/worktrees` on homelab) and every branch a live T3 thread uses. Its own
storage cleanup removes them — `storageCleanup` in `~/.t3/userdata/settings.json`
(`worktreeOnMerge`, `worktreeOnDelete`, `worktreeAfterDays`). This skill never removes one
of those worktrees and never deletes one of those branches, even when it is clean and
merged, and even if the user says "delete all". T3 threads, settled ones included, stay
bound to their worktree path; removing it breaks the thread with "workspace folder no
longer exists" (argus-config#501).

Every worktree removal and branch deletion goes through `scripts/worktree-guard.sh` in
this skill's directory — never a bare `git worktree remove` or `git branch -d/-D`. The
guard enforces the T3 exclusion and records each removed SHA to
`~/.local/state/git-maintenance/<date>.tsv` (persistent, not `/tmp`) for recovery.

**Deploy copies (`~/repos/*`) are different.** The worktree-policy hook blocks every agent
ref change there. Find merged branches and stale tags with
`python3 ~/repos/argus-config/scripts/prune-merged-branches.py --list --plan-out <file>`
(read-only), and present the list and its plan id to the owner. Only once the owner
approves that plan id, run
`python3 ~/repos/argus-config/scripts/prune-merged-branches.py --apply <file> --plan-id <id>`
in exactly that form: an `ask` rule in settings.json prompts the owner for it in every
mode, and the hook blocks any other form (argus-config#715).

```bash
GUARD=~/.claude/skills/git-maintenance/scripts/worktree-guard.sh
```

---

## Step 1 — Identify the target repo(s)

Default to the current working directory. If the user names a project, resolve it:

```bash
# Confirm we're in a git repo
git rev-parse --show-toplevel 2>/dev/null || echo "NOT A GIT REPO"
```

If the user says "all projects" or "all repos", collect:

```bash
find ~/repos -maxdepth 2 -name ".git" -type d | \
  sed 's|/.git||' | sort
```

Run maintenance on each in sequence.

---

## Step 2 — Status snapshot

Show the current branch state before touching anything:

```bash
# Local branches sorted by last commit
git branch -v --sort=-committerdate | head -20

# Remote-tracking refs
git branch -r | head -20

# Stash list
git stash list 2>/dev/null | head -5
```

---

## Step 3 — Classify local branches

Every local branch other than the default and the current one falls into exactly one
bucket. **GitHub's PR state is the authority on "merged", not git ancestry**: a
squash-merged branch is never an ancestor of main, so `git branch --merged` alone reports
it as unmerged. Use git ancestry only as a fast positive — never as proof of "unmerged".

```bash
DEFAULT=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||')
DEFAULT=${DEFAULT:-main}
CURRENT=$(git branch --show-current)
OWNER=$(gh api 'repos/{owner}/{repo}' --jq .owner.login)

git for-each-ref --format='%(refname:short)' refs/heads/ |
  grep -vxE "$DEFAULT|main|master|develop|$CURRENT" |
  while read -r BRANCH; do
    PRS=$(gh api "repos/{owner}/{repo}/pulls?head=$OWNER:$BRANCH&state=all" \
      --jq '[.[] | {state, merged: (.merged_at != null)}]') || { echo "error     $BRANCH"; continue; }
    if [ "$(jq 'any(.state == "open")' <<<"$PRS")" = true ]; then
      echo "open-pr   $BRANCH"
    elif [ "$(jq 'any(.merged)' <<<"$PRS")" = true ] ||
         git merge-base --is-ancestor "$BRANCH" "origin/$DEFAULT" 2>/dev/null; then
      echo "merged    $BRANCH"
    else
      echo "unmerged  $BRANCH"
    fi
  done
```

The PR lookup is REST, not `gh pr list`, so a many-branch repo does not spend GraphQL
quota.

- **open-pr** — never deleted, whatever its age.
- **merged** — a deletion candidate. Squash-merged branches land here via the
  `--state merged` PR lookup; they need `git branch -D` because git itself cannot see
  the merge.
- **unmerged** — a deletion candidate only if it passes the citation gate in Step 4.
- **error** — the PR lookup failed. Keep the branch and report it; re-run once `gh`
  works.

If `gh` is unauthenticated or offline, stop: without PR state, a squash-merged branch
and an abandoned one are indistinguishable, and the citation gate cannot run.

---

## Step 3b — Classify worktrees

```bash
bash "$GUARD" list
```

Each linked worktree prints as `<bucket>\t<path>\t<branch>`:

- **t3-owned** — the path resolves (symlinks followed) under `~/.t3/worktrees/`. Keep it,
  and keep its branch. Report it in Step 9; never offer it for removal.
- **removable** — a removal candidate only if its branch is in the `merged` bucket from
  Step 3. The guard still refuses a dirty one.

A branch checked out in any worktree cannot be deleted until that worktree is gone, so a
merged branch in a **t3-owned** worktree stays — that is correct, not a leftover.

---

## Step 4 — Citation gate (every unmerged branch)

An unmerged branch with no PR can still be a deliberate citation target — a research
or spike branch named in an open issue as "full findings on branch X". Deleting it
orphans the citation. Run this gate on **every** branch in the `unmerged` bucket before
it can be offered for deletion:

1. Derive the branch's topic slug (the part after the first `/`; `OWNER` is from
   Step 3):

   ```bash
   SLUG=${BRANCH#*/}
   ```

2. Search open issues **and** PRs across all of the owner's repos for the full branch
   name as an exact phrase (`--include-prs` returns issues as well as PRs):

   ```bash
   gh search issues --owner "$OWNER" "\"$BRANCH\"" --state open --include-prs \
     --json url --jq '.[].url'
   ```

3. Repeat for the slug, if it differs from the branch name:

   ```bash
   [ "$SLUG" != "$BRANCH" ] && gh search issues --owner "$OWNER" "\"$SLUG\"" \
     --state open --include-prs --json url --jq '.[].url'
   ```

4. Decide:
   - **Any URL printed** → the branch is **cited**: keep it, and flag it in the report
     with every citing URL. Never delete it, even if the user says "delete all".
   - **No URL from either search** → the branch is uncited and may be offered for
     deletion in Step 5.
   - **Either search failed** (non-zero exit, rate limit, network) → treat the branch as
     **cited**. A failed search is not evidence of no citation. The search API allows
     30 requests a minute: on a rate-limit error, wait for the reset
     (`gh api rate_limit --jq .resources.search.reset`) and re-run the search rather
     than skipping it.

`--state` accepts only `open` or `closed`. Closed issues do not protect a branch.

This gate is about citations only. Removing a non-T3 worktree does not need it, since
the branch ref survives — but that does not make worktree removal always safe: a
worktree under `~/.t3/worktrees/` is never removed at all (Step 3b).

---

## Step 5 — Confirm before deleting

List every branch with its bucket, the cited ones with their URLs, then ask about each
deletable group separately:

```
AskUserQuestion: "Delete these merged local branches?"
Options:
  - "Yes — delete all listed"
  - "No — skip branch cleanup"
```

```
AskUserQuestion: "Delete these unmerged branches? None is cited by an open issue or PR."
Options:
  - "Yes — delete all listed"
  - "No — keep them"
```

Ask separately about removable worktrees (Step 3b) whose branch is merged:

```
AskUserQuestion: "Remove these merged worktrees? T3-owned worktrees are not listed and are kept."
Options:
  - "Yes — remove all listed"
  - "No — keep them"
```

Remove approved worktrees first, then delete approved branches, naming each one
explicitly:

```bash
bash "$GUARD" remove "$WORKTREE_PATH"...
bash "$GUARD" delete-branch "$BRANCH"...
```

The guard prints `kept (owned by T3)`, `kept (T3 branch)` or `kept (dirty)` for anything
it refuses and exits 1; report those, don't work around them. It exits 2 and deletes
nothing when the T3 state DB (`~/.t3/userdata/statev2.sqlite`) exists but cannot be
read — stop branch deletion for that run rather than falling back to `git branch -D`.

Never pipe a bucket straight into `xargs` — a cited or open-PR branch must not be
reachable by the delete command.

For remote merged branches, ask separately:

```
AskUserQuestion: "Prune these merged remote-tracking branches too?"
Options:
  - "Yes — prune remote refs"
  - "No — leave remote refs"
```

If yes:

```bash
git remote prune origin
```

---

## Step 6 — Prune stale remote-tracking refs

Even if no merged branches were found, always prune stale remote refs:

```bash
git fetch --prune --quiet
```

This removes remote-tracking branches where the remote branch no longer exists.
Report how many refs were pruned.

---

## Step 7 — git gc

Run garbage collection to pack loose objects and expire reflog entries:

```bash
git gc --auto --quiet
```

`--auto` only runs gc when the repo has accumulated enough loose objects to warrant it —
safe to run unconditionally.

---

## Step 8 — Large file check (optional)

If the user mentioned "clean up space" or "large files", identify big objects:

```bash
git rev-list --objects --all | \
  git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | \
  awk '/^blob/ {print substr($0,6)}' | \
  sort --numeric-sort --key=2 --reverse | \
  head -10 | \
  awk '{printf "%s\t%s\n", $2/1024/1024 " MB", $3}'
```

Report objects > 1 MB. Do NOT delete them automatically — flag for manual review.

---

## Step 9 — Report

Summary per repo:

```
Repo: ~/repos/<name>
  Branches deleted (local): N
  Branches kept — cited: N (each with its citing URLs)
  Branches kept — open PR: N
  Worktrees removed: N
  Worktrees kept — owned by T3: N (each path; T3's storageCleanup owns them)
  Branches kept — T3 thread or worktree: N
  Remote refs pruned: N
  gc: ran / skipped (already clean)
  Large objects: N files > 1MB (listed above)
  Recovery log: ~/.local/state/git-maintenance/<date>.tsv
```

If nothing needed cleaning: "Repo is already tidy — no stale branches, refs pruned."
