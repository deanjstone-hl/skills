---
name: archive-project
description: >
  Archive an active project: write an archived-status CLAUDE.md with successor info, commit,
  optionally push and archive on GitHub, move to ~/repos/archive/. Use for "archive <project>", "retire <project>", "move <project> to archive",
  or decommissioning a project.
disable-model-invocation: true
---

# Archive Project

Decommissions an active project with a full paper trail: CLAUDE.md, git commit, optional
GitHub archive and directory move.

## Steps

### 1. Resolve the project

If the user named the project in the invocation, use that name directly.

Otherwise, list active projects and ask:

```bash
ls ~/repos/ | grep -v '^archive$'
```

Use `AskUserQuestion` to confirm which project to archive.

### 2. Gather context

Ask two questions in a single `AskUserQuestion` call:

- **Reason:** Superseded / Abandoned / Completed / Other
- **Successor:** Name of successor project or repo (e.g. `~/repos/argus/apps/memory-mcp`), or "None"

### 3. Determine CLAUDE.md action

Check whether a `CLAUDE.md` already exists in the project root:

```bash
ls ~/repos/<name>/CLAUDE.md
```

- **Exists** — read it. If it already has a `## Status` section with `ARCHIVED`, warn the user
  and ask whether to proceed with an overwrite via `AskUserQuestion`.
- **Does not exist** — create it from scratch.
- **Is a symlink** — remove the symlink first (`rm`), then create a real file.

### 4. Write the CLAUDE.md Status block

For a **new** CLAUDE.md:

```markdown
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

**ARCHIVED <YYYY-MM-DD>.** <reason sentence>. <If successor: "Superseded by `<successor>`." | If abandoned: "No successor." | If completed: "Work complete; not actively maintained.">

<retain any existing content below this point, or omit this line if creating from scratch>
```

For an **existing** CLAUDE.md — prepend or insert the `## Status` block immediately after the
opening `# CLAUDE.md` heading (or as the first section if the heading is absent). Do not
rewrite the rest of the file.

Use today's date (`date +%Y-%m-%d`) for the archive date.

### 5. Commit

Check for a git repo:

```bash
git -C ~/repos/<name> rev-parse --git-dir 2>/dev/null
```

If one exists:

```bash
git -C ~/repos/<name> add CLAUDE.md
git -C ~/repos/<name> commit -m "add archived status to CLAUDE.md"
```

If no git repo, skip silently.

### 6. Handle the remote

```bash
git -C ~/repos/<name> remote get-url origin 2>/dev/null
```

**No remote** → skip steps 6a–6c.

**Remote exists** — run these checks before asking anything:

**6a. Successor remote collision** — if a successor was named, check whether its repo shares
the same remote URL:

```bash
# derive successor dir — handle both ~/repos/<x> and ~/repos/argus/packages/<x> forms
git -C <successor-path> remote get-url origin 2>/dev/null
```

If the URLs match, skip push silently and tell the user why.

**6b. GitHub already archived** — check with:

```bash
gh repo view --json isArchived -q '.isArchived' 2>/dev/null
```

Run this from inside `~/repos/<name>/` (gh infers the repo from git remote).
If `true`, skip push silently and tell the user.

**6c. Ask about push + GitHub archive** — if neither 6a nor 6b blocked, use `AskUserQuestion`
with two questions:

- Push to remote? (Yes / No)
- Archive the GitHub repo (make it read-only)? (Yes / No)

If push → `git -C ~/repos/<name> push`

**Before archiving: close out any tracking issue with its resolution comment first.** GitHub
locks *all* issues on an archived repo read-only — you cannot comment on or close an issue
(including the one tracking this very archival) once `gh repo archive` has run. If a GitHub
issue is driving this archival (e.g. a `/todo`-filed decommission ticket), post its resolution
comment and close it **before** this step, not after. Hit exactly this ordering bug archiving
`argus-wiki` (2026-08-09) — had to `gh api -X PATCH repos/<owner>/<repo> -f archived=false` to
unarchive, close the issues properly, then re-archive.

If archive on GitHub → confirm once more (destructive, irreversible) then:

```bash
gh repo archive --yes   # run from ~/repos/<name>/
```

### 7. Move to archive

Use `AskUserQuestion`:

> Move `~/repos/<name>/` to `~/repos/archive/<name>/`?

Options: **Yes, move it** / **No, leave it in place**

If yes:

```bash
mv ~/repos/<name> ~/repos/archive/<name>
```

### 8. Report

Summarise what was done:

- CLAUDE.md written / updated
- Commit SHA (if committed)
- Push result (pushed / skipped + reason)
- GitHub archive result (archived / skipped + reason)
- Directory moved (yes / no)
