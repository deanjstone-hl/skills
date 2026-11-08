---
name: adr
description: >
  Write, promote or decline an Architecture Decision Record (next number, template,
  DECISIONS.md index, branch + PR). Use for "write an ADR", "add an ADR", "record ADR",
  "document a decision", "propose an ADR", "promote ADR-NNN", "decline ADR-NNN", "/adr".
---

# ADR Skill

Creates a well-formed ADR from the standard template, wires it into the DECISIONS.md index,
and lands it via branch + PR — never direct to main.

---

## Step 1 — Locate the project

The target project is the current working directory unless the user names another repo.

Confirm `docs/decisions/` and `docs/DECISIONS.md` exist:

```bash
ls docs/decisions/ 2>/dev/null || echo "MISSING"
ls docs/DECISIONS.md 2>/dev/null || echo "MISSING"
```

If either is missing, create them now:

```bash
mkdir -p docs/decisions
```

For `docs/DECISIONS.md` — create a minimal index stub:

```markdown
# Architecture Decision Records

| ADR | Title | Status |
|-----|-------|--------|
```

---

## Step 2 — Determine the next ADR number

Read `docs/DECISIONS.md` and find the highest `ADR-NNN` in the table.
New ADR = `NNN + 1`, zero-padded to three digits (e.g. `006`).

If no ADRs exist yet, start at `001`.

---

## Step 3 — Gather the decision details

If the user's invocation states a clear decision topic, infer the title from it.
Otherwise ask with `AskUserQuestion`:

- **Title** — short descriptive phrase (e.g. "Use Cloudflare Pages for hosting")
- **Status** — `draft`, `proposed`, or `accepted` (default `accepted` unless the user says
  otherwise). Use `proposed` for a still-being-argued proposal that isn't a locked decision
  yet — the KiroCrew `request-for-change/` equivalent, folded into `docs/decisions/` instead
  of a separate directory.

Do not ask for Context/Decision/Consequences yet — fill those in Step 5.

If the user is asking to **promote or decline an existing `proposed` ADR** rather than create
a new one, skip to "Promoting or declining a proposed ADR" below instead of continuing here.

---

## Step 4 — Create the branch

Branch name: `docs/adr-NNN-<kebab-case-title>` (all lowercase, hyphens only).

```bash
git checkout -b docs/adr-NNN-<kebab-title>
```

Example: `docs/adr-006-use-cloudflare-pages`

---

## Step 5 — Write the ADR file

File path: `docs/decisions/adr-NNN-<kebab-title>.md`

Template:

```markdown
---
title: ADR-NNN — <Title>
status: <draft|proposed|accepted>
date: <YYYY-MM-DD>
summary: "ADR-NNN: <the decision, in one line>"
read_when:
  - <a situation in which an agent should open this ADR>
---

# ADR-NNN: <Title>

## Context

<Why this decision was needed. What problem or tension prompted it. Include relevant
constraints, prior decisions that led here, and options considered if there were obvious
alternatives.>

## Decision

<State the decision directly. What was chosen and why.>

## Consequences

<What changes as a result. Trade-offs accepted. Any follow-up work this creates.>
```

`summary:` and `read_when:` feed the repo's docs index (Repo Structure Standard, "Docs
index"). Keep them even in a repo without a `scripts/docs-list.ts`: some repos' CI fails an ADR
that lacks either.

Use today's date:

```bash
date +%Y-%m-%d
```

Fill Context / Decision / Consequences from the user's request if it contains enough
detail. If not, ask with `AskUserQuestion` (one call, all three clearly labelled).
Never leave a section blank or as a placeholder.

---

## Step 6 — Update the DECISIONS.md index

Append a row to the table in `docs/DECISIONS.md`:

```markdown
| [ADR-NNN](decisions/adr-NNN-<kebab-title>.md) | <Title> | <status> |
```

Keep rows sorted by ADR number ascending.

---

## Step 7 — Commit and push

```bash
git add docs/decisions/adr-NNN-<kebab-title>.md docs/DECISIONS.md
git commit -m "docs: add ADR-NNN — <Title>"
git push -u origin docs/adr-NNN-<kebab-title>
```

---

## Step 8 — Open a PR

```bash
gh pr create \
  --title "docs: ADR-NNN — <Title>" \
  --body "$(cat <<'EOF'
Adds ADR-NNN to docs/decisions/. Status: <status>.
EOF
)" \
  --base main
```

Return the PR URL to the user.

---

## Step 9 — Report

- ADR file: `docs/decisions/adr-NNN-<kebab-title>.md`
- Index updated: `docs/DECISIONS.md`
- Branch: `docs/adr-NNN-<kebab-title>`
- PR: `<url>`

---

## Promoting or declining a proposed ADR

A `status: proposed` ADR is still being argued — it isn't a locked decision. Once it's
resolved, flip its status **in place**: no new file, no new ADR number.

1. **Identify the ADR.** Confirm its current `docs/decisions/adr-NNN-<kebab-title>.md` has
   `status: proposed` in frontmatter. If it doesn't, stop and tell the user — this flow only
   applies to `proposed` ADRs.
2. **Ask the outcome** with `AskUserQuestion` if not already stated: promote to `accepted`, or
   mark `declined`.
3. **Branch:** `docs/adr-NNN-<kebab-title>-promote` (or `-decline`).
4. **Update the ADR file:** change `status: proposed` to `status: accepted` or
   `status: declined` in the frontmatter. Leave Context/Decision/Consequences untouched unless
   the user wants the Consequences section updated to reflect the outcome — ask if unclear.
5. **Update `docs/DECISIONS.md`:** change that ADR's status column to match.
6. **Commit, push, open a PR:**
   ```bash
   git add docs/decisions/adr-NNN-<kebab-title>.md docs/DECISIONS.md
   git commit -m "docs: promote ADR-NNN to accepted"   # or "decline ADR-NNN"
   git push -u origin docs/adr-NNN-<kebab-title>-promote
   gh pr create --title "docs: promote ADR-NNN — <Title>" --base main --body "..."
   ```
7. **Report** the new status and PR URL. Do not create a new ADR file or bump the ADR number
   for either outcome — the ADR keeps its original number regardless of promote/decline.

---

## Rules

- **Never commit directly to main.** Always branch + PR.
- **Never leave placeholders.** All three sections must be substantive prose.
- **File name is strict:** `adr-NNN-kebab-case-title.md` — three-digit, lowercase, hyphens only, no em dashes.
- **Frontmatter is required:** `title`, `status`, `date` — no exceptions.
- **Status values:** `draft`, `proposed`, `accepted`, `superseded`, or `declined` only.
- **Promotion/decline never creates a new file or ADR number** — it flips the existing ADR's status in place (frontmatter + index).
