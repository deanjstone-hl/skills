---
name: inbox-process
title: CONTEXT Inbox Processing
description: >
  Process ~/CONTEXT/00.INBOX/: triage quick-capture notes to an issue, a memory or discard
  (owner-approved), and ingest articles into SOURCES/. Use for "process
  inbox", "triage captures", "review captures", "what's in the capture backlog", "ingest",
  "what's in the inbox", or when 00.INBOX/ has unprocessed files. Pass `captures` or
  `articles` for one part.
agent: true
model: sonnet
disable-model-invocation: true
---

> **Effort:** medium — moves and archiving are mechanical; repo inference, duplicate
> detection and reference-page synthesis require judgment. Never skip the Part A approval gate,
> even in auto-mode.

# /inbox-process

Processes `~/CONTEXT/00.INBOX/`. Every file in the inbox is one of three kinds, and each
kind has exactly one owner:

| Kind | How to recognise it | Owner |
|---|---|---|
| **Staged memory** | Frontmatter `type:` is a lowercase memory type (see below) | Filing agent — **never touch** |
| **Capture** | Filename matches `*_capture-NNN_*.md` (or the older `*-capture_NNN-*.md`) | Part A of this skill |
| **Article** | Anything else (excluding `INDEX.md` and `attachments/`) | Part B of this skill |

## Arguments

- none → Part A, then Part B
- `captures` → Part A only
- `articles` → Part B only

## Vault lock

Every git command this skill runs against the live `~/CONTEXT` checkout — the `fetch` and
`worktree add` below, and the `pull` and `worktree remove` in [Merge](#merge) — goes through
the machine-wide vault git lock, per the vault's `CLAUDE.md` (deanjstone/context#209):

```bash
flock -w 30 ~/.argus/vault-git.lock git -C ~/CONTEXT <args>
```

If `flock` times out (exit 1), another writer is mid-operation: wait and retry, or stop and
tell the user. Wrap each live-vault command on its own — never hold the lock across the
run. `memory_remember` takes the same lock itself, so holding it around a Part A promotion
makes that call wait 30s and fail. Work inside `$WT` needs no lock.

## Branch and worktree

Every vault file edit this skill makes — capture frontmatter and archive moves, article
moves, attachments, reference pages — lands through a branch + PR, never a direct commit to
`main`. Work in a dedicated worktree, never in the `~/CONTEXT` checkout itself: that
checkout must stay on `main` because the reconciler and `memory_remember` commit there.

```bash
WT=~/context-worktrees/inbox-process-$(date +%F)
flock -w 30 ~/.argus/vault-git.lock git -C ~/CONTEXT fetch -q
flock -w 30 ~/.argus/vault-git.lock git -C ~/CONTEXT worktree add "$WT" -b chore/inbox-process-$(date +%F) origin/main
```

If the branch already exists from an interrupted run, reuse it
(`flock -w 30 ~/.argus/vault-git.lock git -C ~/CONTEXT worktree add "$WT" chore/inbox-process-<date>`) instead of starting
over. If `~/CONTEXT/00.INBOX/` holds a file that isn't on `origin/main` yet (`git -C
~/CONTEXT status --porcelain 00.INBOX/`), copy it into `$WT/00.INBOX/` first and note it
for removal from the main checkout after the merge.

From here on, **every vault path below is relative to `$WT`**, not `~/CONTEXT`. External
writes are unaffected: GitHub issues are created directly, and `memory_remember` keeps its
own carve-out (it commits to `main` itself).

Commit and push together, every time — never leave a local-only commit. `git -C "$WT"
push -u origin HEAD` on the first push.

---

## Step 0 — Classify

List every file in `00.INBOX/` and sort it into the three kinds above. Read the
frontmatter, never classify from filename alone, except for the capture globs.

**Staged memory.** `memory_remember` writes a new memory straight into `MEMORY/`
([context#316](https://github.com/deanjstone/context/issues/316)), but a memory-typed
file can still be staged in `00.INBOX/`, and the filing agent
(`scripts/filing_agent.py`, daily on homelab) moves it into `MEMORY/`. Skip any file
whose `type` — at the top level, or nested one level under `metadata:`, the same two shapes `reachability_lint.py` accepts — is one of:

- v2 enum ([context#204](https://github.com/deanjstone/context/issues/204)): `fact`,
  `preference`, `pattern`, `decision`, `tension`, `question`, `methodology`, `reference`
- legacy: `user`, `feedback`, `project`

The match is **case-sensitive** ([context#153](https://github.com/deanjstone/context/issues/153)):
a capitalised `Reference` is an OKF page type and is an article. Ingesting a staged memory
is a real loss, not a misfiling: Part B moves and rewrites it, so it never reaches a theme
index, and the 7-day staleness bound that exists to catch that never fires because the
file is gone from the inbox.

**Captures can never be staged memory.** A memory file is named `<type>_<slug>.md`, where
`slugify` replaces every non-alphanumeric character with `_`, so it holds only
alphanumerics and underscores. Both capture globs need hyphens a memory name can never
have: the canonical `*_capture-NNN_*.md` in its `YYYY-MM-DD` date and in `capture-NNN`,
the older `*-capture_NNN-*.md` around `capture_NNN`. Memory captures
(`capture_type: memory`) carry `candidate_type:`, never a lowercase `type:`. Don't widen
the capture globs; if the memory naming rule ever changes, this is the assumption that
breaks.

Report the counts per kind. If a part has no files in scope, say so and skip it.

---

## Part A — Captures (two passes, always)

Captures are written by the quick-capture PWA (`homelab` repo, `services/quick-capture/`).
The daily sessions pass that drafted `auto-capture` memory captures is retired
([context#322](https://github.com/deanjstone/context/issues/322)): memories are now
extracted nightly from sessions by the CONTEXT vault's `scripts/extract_memories.py`, so no
new `auto-capture` file arrives. Ones already in the inbox are handled as below. Only
`vault: context` captures land here — this skill never touches `~/CORTEX/00_INBOX/` (that
vault has its own `sorter`/`inbox-triage` pipeline).

**Propose, stop, then execute.** Do not collapse A3 and A4 into one pass, even in
auto-mode — this convention was set after a session merged them and the user asked for
them kept separate.

### Capture file shape

Filename: `{date}_capture-{seq:03d}_{capture_type}_{repo|general}_{slug}.md`. Underscores
separate the fields; hyphens appear only inside them (`sys-admin`, a multi-word slug).
Since [context#276](https://github.com/deanjstone/context/issues/276) both writers emit
only this shape. Captures named `{date}-capture_{seq:03d}-{capture_type}-{repo|general}-{slug}.md`
are the older shape (`05.ARCHIVE/captures/` keeps them, and a straggler can still arrive):
treat them as captures exactly the same.

```yaml
---
type: Capture
title: "<Title>"
capture_type: idea | task | bug | memory
candidate_type: <v2 memory type>      # memory captures only (both sources)
source: quick-capture | auto-capture   # quick-capture = typed in the PWA; auto-capture = drafted by the retired daily sessions pass (memory only)
vault: context | cortex
repo: <repo-name>        # optional — absent or "general" if not repo-specific
created: YYYY-MM-DDTHH:MM:SS+TZ
status: new | done | discarded-duplicate
---

<free-text body>
```

A capture with no `source:` line predates
[homelab#26](https://github.com/deanjstone/homelab/issues/26) — every PWA capture still in
`00.INBOX/` or `05.ARCHIVE/captures/` from before it. Treat it as `quick-capture`.

**Memory captures** (`capture_type: memory`) always carry a `candidate_type:` from the v2
enum: `fact`, `preference`, `pattern`, `decision`, `tension`, `question`, `methodology`,
`reference`. They are context-vault only: the quick-capture server rejects a memory capture
without `vault: context`, so one never lands in CORTEX. They come from two sources:

- `source: auto-capture` ([context#215](https://github.com/deanjstone/context/issues/215))
  — drafted automatically by the daily sessions pass, with a body already shaped as a
  memory (rule or fact, then **Why:** and **How to apply:**). That pass is retired
  ([context#322](https://github.com/deanjstone/context/issues/322)), so these are a
  backlog that only shrinks.
- `source: quick-capture` ([homelab#26](https://github.com/deanjstone/homelab/issues/26))
  — typed by a person in the PWA. The body is free text, not pre-shaped, so it has to be
  shaped per the `memorise` skill before it is written.

The capture's `source:` is a capture-file field, not a memory tag. It never becomes a
`source:quick-capture` or `source:auto-capture` tag on the memory: `memory_remember`
stamps `source:` itself from its transport and rejects a caller-supplied one
([argus#377](https://github.com/deanjstone/argus/issues/377)). Provenance from the capture
is kept on the archived capture instead (A4 step 2).

### A1 — Scan

Read every capture. Split into three buckets:

- **`status: new`** — needs triage
- **`status: done`** but still in the inbox — triaged before and never archived.
  **Verify before trusting the status**: if it claims a linked issue or output, check it
  (`gh issue view <N>` — actually resolved, not just linked; does the claimed write-up
  exist). If verification fails, revert to `status: new` and re-triage. Otherwise queue for
  archive-only in A4
- **`status: discarded-duplicate`** — archive-only

### A2 — Detect duplicates

Group `status: new` captures by (title, `created`, body). Matching body + timestamp is the
same event captured twice (seen in practice: differing only in the `repo|general` filename
segment) — **but check `vault`/`repo` scope first**: the same idea captured for two
different targets is not a duplicate. Only one member of a true duplicate group gets a real
destination; the rest are proposed as `discarded-duplicate`. Same-topic captures that are
not duplicates get their issues cross-linked in A4.

### A3 — Propose (no execution yet)

For every `status: new` capture not already a duplicate-discard:

1. Read `capture_type`, `repo`, `title` and the body.
2. **Resolve the target repo**, if the destination is a GitHub issue:
   - `repo` present and not `general` → `deanjstone/<repo>`
   - otherwise infer from the body with the `todo` skill's keyword table (its Step 2); if
     still ambiguous, mark "needs repo decision" instead of guessing
3. **Check for a near-duplicate issue** first:
   `gh issue list --repo <repo> --state all --search "<key terms>"` — on a clear match,
   propose "already tracked in #N".
4. **Propose a destination**:
   - `bug` / `task` → new GitHub issue
   - `idea` → new GitHub issue, unless the body is a pure preference/style note with no
     actionable work — then propose a memory
   - `memory` → `memory_remember` with `type` = the draft's `candidate_type` (correct it if
     misclassified — classify by the subject of the Why line, per the `memorise` skill).
     First search for an existing memory on the topic (`memory_search`, and grep
     `~/CONTEXT/MEMORY/`): if one exists, propose an **update** (needs a `reason`) or
     `discarded-duplicate` if it already says this. How hard to lean toward discard
     depends on `source:`:
     - `auto-capture` — discard is a normal outcome for auto-drafted candidates.
     - `quick-capture` (or no `source:`) — a person chose to record this, so default to
       writing it, with the body shaped per the `memorise` skill (rule or fact, then
       **Why:** and **How to apply:**). Propose discard only for a real duplicate.
   - Cross-repo or no owning repo → the `todo` skill's file fallback
     (`~/agent-cli/docs/TODO.md`)
5. **Cite what's known.** Grep `~/CONTEXT/MEMORY/` for related content and note it in
   the proposal.

Present the whole batch in one `AskUserQuestion` (or a numbered list if it doesn't fit the
tool's shape): filename → capture_type → proposed destination → one-line rationale.
**Stop here** until the user approves, even where the routing looks obvious.

### A4 — Execute (only after approval)

For each approved capture, in order:

1. **Execute the destination**:
   - GitHub issue: `gh issue create --repo <repo> --title "<title>" --label <chosen wave, default wave:w1 if <repo> is deanjstone/argus-config, else wave:later> --label mode:<afk|hitl> --body "<body>\n\nMode: <AFK|HITL>\n\n---\nSource: capture <filename>"`
     — the backlog labels and the `Mode:` line exactly as the `todo` skill's Step 3 sets them
   - Memory (new or update): the `memorise` skill's write process — `memory_remember` is
     the only write path, never a hand-edited file. Pass `type` from the approved
     `candidate_type`, and no `source:*` tag (see Capture file shape)
   - File fallback: append to `~/agent-cli/docs/TODO.md` per the `todo` skill's Step 5
   - Discard-as-duplicate: no external write
2. **Update the frontmatter**: `status: done` (or `discarded-duplicate`), plus
   `issue: <url>` if an issue was created, or `memory: <key>` if a memory was written.
   Leave `source:` as it is: the archived capture is where its provenance lives.
3. **Archive, never delete**: `mkdir -p "$WT/05.ARCHIVE/captures/"` and `mv` the file
   there.

Also archive the captures queued in A1 as already `done`/`discarded-duplicate`.
Captures the user deferred stay in the inbox with `status: new`.

Commit and push the archive moves before starting Part B:

```bash
git -C "$WT" add -A 00.INBOX/ 05.ARCHIVE/captures/ && \
git -C "$WT" commit -m "inbox: triage <N> captures" && \
git -C "$WT" push -u origin HEAD
```

Stage only the capture paths — never `git add -A` the whole vault, other writers share it.

---

## Part B — Articles

Every article in the inbox is already agent/AI-dev relevant (routing to the inbox is the
classification step). Part B moves each into the permanent store and synthesises reference
pages. No approval gate, unless a file looks like it belongs in CORTEX — then use
`AskUserQuestion` before moving it.

**Unattended runs:** Part B also runs daily on homelab without a human
(`envs/homelab/scripts/inbox-ingest-run.sh`, [context#217](https://github.com/deanjstone/context/issues/217)),
committing to the long-lived `inbox-ingest` branch behind one rolling PR. Before running
Part B by hand, check for an open `inbox-ingest` PR: an article listed in its
`.inbox-ingest/ledger.tsv` is already ingested there, even while its original is still in
the inbox.

**Large backlogs:** work in batches of about 20 articles — run B1–B5 and commit per batch,
so a stopped run leaves the vault consistent and the remaining files still in the inbox.

### Vault structure

```
~/CONTEXT/
  INDEX.md              ← OKF bundle root; vault nav and type map
  00.INBOX/             ← staging; this is where we read from
  SOURCES/              ← permanent home for all ingested articles (context#317)
    attachments/        ← downloaded images and media, beside the notes
  MEMORY/               ← reference pages land here as reference_<slug>.md
  TOPICS/               ← generated hubs; the ai-reference child hubs list the pages
```

B3 and B4 write reference pages and regenerate the hubs; they are for interactive runs
only. The unattended runner does B1 and B2 and nothing else.

### Frontmatter schema

**Reference page** (`MEMORY/reference_<slug>.md`, 4 KB or less):
```yaml
---
name: reference_<slug>
description: "<One sentence, 150 characters or less. What it is and why it matters.>"
type: reference
topics:
  - <ai-reference child hub>
created: YYYY-MM-DD
modified: YYYY-MM-DD
tags: [<topic>, <subtopic>]
sources: ["[[Source Article Title]]"]
---
```

`topics:` names one `ai-reference` child hub: `agent-memory-systems`, `agentic-patterns`,
`claude-code-ecosystem`, `llm-research-and-infra` or `mcp-and-integrations`. Read
`TOPICS/ai-reference.md` for the current list.

**Source article** (`SOURCES/<filename>.md`): keep existing frontmatter, but
ensure `type: source` is present — prepend it if not.

Tags: topic tags such as `ai-agents`, `memory`, `mcp`, `claude-code`, `llm`,
`local-llm`, `agentic-patterns`, `orchestration`, `harness`, `obsidian`, `tools`, `open-source`.

### B1 — Move to sources

For each article: read it, then `mv` it to `SOURCES/` (`mkdir -p` first if
missing). Everything goes to `SOURCES/` — no routing table.

**A move, never a rewrite.** Use `mv` (or `git mv`) and never re-emit the body with the
Write tool or a heredoc. Every section survives byte for byte — `## BLUF` above all, the
personalised layer a re-emitted body silently loses
([argus-config#319](https://github.com/deanjstone/argus-config/issues/319)) — and so do
line endings. The only edits allowed in the moved file are the `type: source`
frontmatter line and B2's image-URL rewrites, each made with a targeted Edit. Never
write a file into `00.INBOX/`: no processed copy, no ` 1.md` duplicate.

Check every moved file against its original before B2 (copy the original aside first
if it is untracked):

```bash
bash ~/.claude/skills/inbox-process/scripts/source-intact.sh <original> SOURCES/<file>.md
```

Non-zero means the content was damaged: restore the original and redo the move. The
unattended runner runs the same check and refuses the whole run on a failure.

### B2 — Download external image attachments

Scan every moved file for external images (`![...](https://...)` or `<img src="https://...">`).
For each:

1. `curl -L -o SOURCES/attachments/{filename}` — original filename from the URL; on
   collision, prefix with the parent note's slug
2. Replace the external URL in the source with `attachments/{filename}`

Skip tracking pixels (1×1, `pixel`, `beacon`, `open.gif`) and non-image content types.
Move any files in `00.INBOX/attachments/` to `SOURCES/attachments/`.

### B3 — Reference pages (interactive runs only)

For every moved file:

1. Extract key entities, concepts, claims, patterns and tool features
2. Search `MEMORY/reference_*.md` for an existing page to update before creating a new one
3. Create or update `MEMORY/reference_<slug>.md` using the schema above. Done when the
   file is 4 KB or less (`wc -c`): longer detail stays in the source under `SOURCES/`,
   linked from the page's `sources:` field

**Create a page** when a source introduces a concept, pattern, architecture or tool not
already covered; **update** one when it adds new facts to an existing page. Skip a thin
link/tweet list (fetch the full content first with `npx defuddle parse <url> --md`), a full
duplicate of an existing page, and a personal workflow story with no generalisable pattern.

**Page body:**

```markdown
# <Concept or Tool Name>

One-sentence definition. Why it matters. For a tool, add Site/repo, Language and Status
lines.

## <First major aspect>

...

## Related

- [[reference_<other_slug>]] — one-line relationship
```

### B4 — Regenerate the hubs (interactive runs only)

The hubs replace a catalog page. Regenerate them from inside the worktree:

```bash
python3 "$WT/scripts/generate_topic_hubs.py" --apply
```

Done when a dry run (no `--apply`) reports nothing to change.

### B5 — Commit and push

Sources first, then reference pages with the regenerated hubs, then push — per batch:

```bash
git -C "$WT" add 00.INBOX/ SOURCES/ && \
git -C "$WT" commit -m "ingest: add <N> sources to SOURCES"

git -C "$WT" add MEMORY/ TOPICS/ MEMORY.md && \
git -C "$WT" commit -m "ingest: update reference pages — <comma-sep topic list>"

git -C "$WT" push -u origin HEAD
```

---

## Merge

Once the run's last batch is pushed (or the run stops early — merge what is committed):

1. Open the PR: `gh pr create --repo deanjstone/context --base main --head chore/inbox-process-<date>`
   with the Digest below as the body (Summary → Why → Test plan, evidence included).
2. Wait for CI (`gh pr checks <N> --watch`). The Reachability Lint must pass; if it is
   red, investigate before anything else — check whether `main` is red too before
   blaming the branch.
3. Green, no conflicts → `gh pr merge <N> --squash --delete-branch` (pre-authorized for
   your own PR). Conflicts or red CI → stop and tell the user.
4. Sync the vault and clean up:
   ```bash
   flock -w 30 ~/.argus/vault-git.lock git -C ~/CONTEXT pull --ff-only
   flock -w 30 ~/.argus/vault-git.lock git -C ~/CONTEXT worktree remove "$WT"
   ```
   Then remove any untracked inbox originals you copied into `$WT` at the start — they're
   now on `main` in their new location.

---

## Digest

```
## Inbox Processing Complete — YYYY-MM-DD

Inbox at start: N files (captures N · articles N · staged memory N, left for the filing agent)

Captures
  Issues created: N
    - <repo>#<N> — <title>
  Memories written/updated: N
  Discarded as duplicate: N
  Archived to 05.ARCHIVE/captures/: N
  Deferred: N
    - "filename.md" — [reason]

Articles
  Moved to SOURCES/: N
  Attachments downloaded: N
  Reference pages created: N · updated: N
  Skipped/deferred: N
    - "filename.md" — [reason]

00.INBOX/ remaining: N (should equal staged memory + deferred)
```

---

## Rules

- Never touch staged memory — the filing agent owns it
- Never skip the A3 → A4 approval gate, in auto-mode or otherwise
- Never delete inbox files — captures move to `05.ARCHIVE/captures/`, articles to
  `SOURCES/`, and a capture moves only after its frontmatter reflects the real
  disposition
- Read before acting — never classify from filename alone (the capture glob excepted)
- Never move files to JOURNAL, SYSTEM, MEMORY, SESSIONS or REPOS — those have dedicated
  writers
- Reuse the `todo` skill (repo inference, backlog labels, file fallback) and the `memorise`
  skill (memory writes) rather than duplicating them
- Check for an existing near-duplicate issue before creating one
- Use `npx defuddle parse <url> --md`, not WebFetch, for full article content
- Never commit to CONTEXT `main` directly — every vault edit goes through the
  `chore/inbox-process-<date>` worktree branch, a PR, and a squash-merge (`memory_remember`
  is the one carve-out)
- Reference-page commits always come after source commits; push after every commit
- Only ever read/write `~/CONTEXT/` — never `~/CORTEX/00_INBOX/`
