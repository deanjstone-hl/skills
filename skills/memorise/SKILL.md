---
name: memorise
description: >
  Review the conversation and extract durable memory entries. Run at the end of any session
  with significant work, corrections or decisions, on "/memorise", or when corrections or
  patterns emerged during the session.
---

# /memorise

Review the current conversation and extract durable memory entries. Run at the end of any
session with significant work, corrections, or decisions. Also runs automatically as part of
the learning loop when corrections or patterns emerged during a session.

---

## Step 0 — Session-brief

**Before anything else, make sure `~/CONTEXT` is on `main`** (`git -C ~/CONTEXT branch
--show-current`) and level with origin (`git -C ~/CONTEXT status -sb` shows no
`ahead`/`behind`). Since ADR-007 `memory_remember` publishes to `origin/main` from a
scratch worktree whatever is checked out, but a live vault on another branch or diverged
never receives the file — every write comes back `mirror_status: published-not-revealed`. See
[[fact_memory_mirror_commits_to_current_branch]].


Invoke the `session-brief` skill first (`Skill({skill: "session-brief"})`) — not
`/recap`, which is a built-in CLI command with no tool path the assistant can call
(confirmed by an explicit tool error on a prior attempt; see
[[fact_skill_cannot_invoke_local_commands]]). `session-brief` is the callable
replacement and also works in headless/non-interactive runs, where `/recap` is always
skipped. This gives a one-sentence summary of the session that:
- Confirms you're scanning the right conversation

**If a caller already ran `session-brief`** (e.g. `/save-session` runs it as its own
Step 1 before invoking this skill), skip this step and reuse that summary instead —
don't invoke it twice in the same turn.

---

## What to extract

Scan the full conversation for:

| Signal | Memory type | Example |
|---|---|---|
| Correction of something the agent did ("no, don't...", "not like that") | pattern | The rule that prevents the mistake; why |
| Preference, directive or confirmed approach ("yes exactly", "always do X") | preference | What Dean wants; why |
| Tool/system behaviour, gotcha, or current state of a project/system | fact | Edge case in tool Y and the workaround; where X runs |
| Decision between alternatives (architecture, tooling, scope) | decision | Chose X over Y; reason |
| Repeatable multi-step procedure (not a skill) | methodology | Steps to do X |
| Trade-off explicitly still open | tension | X vs Y, unresolved; what would settle it |
| Open question with no position yet | question | What is unknown; what would answer it |
| New resource or external reference found | reference | Where to find X |

Classify by the subject of the **Why:** line: the user → `preference`; the agent's own
mistake → `pattern`; a tool or system → `fact` (context#204).

**Skip:**
- Things already covered (check `~/CONTEXT/MEMORY.md` and the matching hub under `~/CONTEXT/TOPICS/` first)
- Ephemeral task details that won't matter next session
- Things derivable from reading the code or git log
- Anything that doesn't pass the filter: *would this change how I act next time?*

---

## How to write entries

### Step 1 — Read the index, then check Supabase directly

```bash
cat ~/CONTEXT/MEMORY.md
```

Use this for placement (which topic hub a new entry belongs under — read that hub under
`~/CONTEXT/TOPICS/` for the memories already linked) and as a first pass for existing coverage.
But **the index can be stale or missing entries** — file and
store drift in both directions (a Supabase record with no disk mirror/hub link, or the
inverse: a mirror file and hub link with no matching Supabase record — see
[[fact_memory_ghost_entry_mirror_without_supabase]], confirmed 3 times), so a topic
can already be covered by a memory with no corresponding hub link or disk file at
all, or by one the store has never seen. For each topic that looks new or uncertain
from the index alone, confirm against Supabase before deciding:

```
mcp__claude-memory__memory_search({ query: "<topic keywords>" })
```

If a topic surfaces in `memory_search` with no matching hub link, treat this as
a broken index entry — flag it to the user rather than silently re-creating or
ignoring it (it may need the hub regenerated, or the disk mirror hand-written).

**No staging step.** `memory_remember` writes a new memory straight into
`~/CONTEXT/MEMORY/` with its `topics`; the hub link regions under `TOPICS/` are generated
by the vault pipeline, so a memory written in the last few minutes may not be linked yet.
That is not broken. A memory-typed file in `~/CONTEXT/00.INBOX/` is a staged memory in
transit to the filing agent — not orphaned, and one waiting more than 7 days *is* a
fault (`reachability_lint.py` check 6 will already be failing on it).

### Step 2 — Draft candidates

For each candidate entry, decide:
- **New entry** — topic not covered anywhere in the hubs *or* Supabase
- **Update existing** — topic exists but entry is incomplete or stale

### Step 3 — Write without asking

Invoking `/memorise` (directly, or via `/save-session`) **is** the approval. Do not
present candidates for selection, do not use `AskUserQuestion`, and do not ask whether
to create or update an entry — decide from Steps 1–2 and write every candidate that
passes the *would this change how I act next time?* filter.

Since 2026-10-09 every session may also **run this skill on its own judgement** when
something memory-worthy surfaces — a correction, a standing policy the owner states, a
diagnosed gotcha — with no prompt from the user
([[preference_memory_write_requires_approval]]). Pick a sensible checkpoint, batch related
updates into one run, and don't run it for trivia or task details that only matter in
the current conversation.

If there are zero candidates, skip straight to Step 5 and report nothing to save.

### Step 4 — Write entries via the memory MCP tool

Do not write files to disk directly. Call the `memory_remember` MCP tool for each
candidate.

**`memory_remember` is a full overwrite, not a merge** — its own tool description says
so explicitly ("Upserts — calling again with the same key overwrites content and
tags"), see [[fact_memory_remember_full_overwrite]]. For an **update-existing**
candidate, never compose the new `content` from memory alone or from the local mirror
file (which can itself be stale, or absent from the store — see
[[fact_memory_ghost_entry_mirror_without_supabase]]). First pull the current
stored version:

```
mcp__claude-memory__memory_recall({ key: "<existing-key>" })
```

Then write the amended version as a superset of that recalled content (add/revise the
new information, keep what's still true) — a blind rewrite from scratch silently
destroys whatever the recalled content held that the current session didn't touch.

**Input limits — the call is rejected, not truncated:**

- `description` ≤ 150 characters (`MIRROR_DESCRIPTION_MAX_CHARS`). Count before sending.
- Every tag must match `^[a-z0-9_-]+$` — **no `:`**. Never pass a `source:*` tag: the
  server stamps provenance itself from its transport (`source:claude-code` on stdio,
  `source:remote-mcp` on the Worker's `/mcp`) and rejects a caller-supplied one
  ([argus#377](https://github.com/deanjstone/argus/issues/377)). Recalled tags carry a
  `source:*` tag (`source:claude-code`, or `source:unknown` on older rows), so when carrying
  recalled tags forward, **drop every `source:*` tag** or the update fails. The server keeps
  the row's original source on update.

**An update must carry a `reason`.** When the key already exists, `memory_remember`
refuses the call unless `reason` says why the memory is changing; the reason lands in
the mirror commit's body, which is the memory's only history (supersession was declined,
context#205/#214). One sentence, e.g. `reason: "the workaround stopped being needed
after gh 2.80"`. A new memory needs no reason.

**`type` is what gates the disk mirror — always pass it.** The tool's actual signature
is `key`, `content`, `tags`, plus optional `type`, `description`, `topic`, `applies_to`
and `reason` (required on update). Omitting
`type` stores the memory in Supabase *only* — no mirror file, no hub link, no
`mirror_status` in the result. `type` must be one of the eight v2 values —
`fact`/`preference`/`pattern`/`decision`/`tension`/`question`/`methodology`/`reference`
(the table above; the pre-v2 `user`/`feedback`/`project` are rejected since context#213):

```
mcp__claude-memory__memory_remember({
  key: "<type>_<slug>",
  type: "<type>",
  topic: ["<topic-slug>", ...],    // a list of free-form slugs, written to the memory's
                                   // `topics:` frontmatter; each names a hub under TOPICS/
  description: "<one-line summary, ≤150 chars>",   // hard limit — longer is rejected
  tags: ["<type>", ...],                            // each must match ^[a-z0-9_-]+$
  content: "<body — lead with the rule or fact>\n\n**Why:** <the reason — incident, strong preference, constraint>\n**How to apply:** <when this kicks in>"
})
```

Put `<type>` first in `tags` too — the tool docs its first tag as controlling snapshot
section grouping. `description` becomes the mirror file's frontmatter `description:`
and the hub link's hook text. For `topic`, reuse the slugs of existing hubs under
`~/CONTEXT/TOPICS/` that match the candidate; coin a new slug only when no hub fits.

This performs a dual write: a row in Supabase, plus (when `type` is set)
a best-effort mirror to `~/CONTEXT/MEMORY/<type>_<slug>.md` carrying the `topics:` you
passed. The hubs and `MEMORY.md` are generated, so there is no index line to write and no
separate index-update step.

**Verify the Supabase write itself, not just the mirror.** The `memory_remember`
result returns an `id`/`updated_at` — it doesn't echo back the stored content, so
a param typo or truncation (there's a hard 10,000-char `content` limit, silent
`MCP error -32602` on overflow — split long topics across multiple keys with
`[[key]]` cross-links if a candidate is anywhere near that size) can land wrong content
under a "successful" call. Confirm with:

```
mcp__claude-memory__memory_recall({ key: "<key>" })
```

and check the returned content actually matches what was intended before reporting
success.

**Check `mirror_status` in the result when `type` was set.** It is verified
server-side by read-back (fixed 2026-08-06, `argus-context` PR #6 — no longer inferred
from "the call didn't throw"). Four values, four different responses:

- **`written`** — on disk, committed, and pushed to the vault's `main`. Nothing to do.
- **`published-not-revealed`** — pushed to `origin/main` (from a scratch worktree,
  ADR-007), but this machine's `~/CONTEXT` could not fast-forward: it is diverged, on
  another branch, or blocked by a differing local file (the result says which). The
  memory is safe — **do not re-write it or hunt for the file.** Tell the user the live
  checkout needs attention; `vault-sync` heals a fork of redundant commits by itself
  within 15 minutes, and a fork it refuses names the blocking paths in
  `~/.local/state/argus/vault-sync.log`. Before argus#513 this case was reported as
  `written-not-pushed`.
- **`written-not-pushed`** — committed but not pushed (the result says where; added
  in `argus#293`). **Do not hand-write anything** — the file exists and is committed.
  Merge or cherry-pick that commit onto `main`, and tell the user. Better still, avoid
  it: keep `~/CONTEXT` on `main` while memorising (see Step 0 note).
- **`failed`** — this is the only case that warrants hand-writing the mirror file
  yourself, matching the frontmatter format of neighbouring files
  (`name`/`description`/`metadata.type`/`topics`). Hubs are generated; add no index line.

Report the memory as saved in every case (the store row landed either way),
but say which of the latter two happened so the user knows the CONTEXT working tree
drifted.

**Never hand-edit a `~/CONTEXT/MEMORY/*.md` file** as a fix for anything other than a
confirmed `mirror_status` failure from this same call. Always round-trip corrections
through `memory_remember` instead — see
[[fact_memory_ghost_entry_mirror_without_supabase]] (3 confirmed recurrences, most
tied to editing a mirror file directly with `Edit`/`Write`).

The reason is **not** that the edit desyncs Supabase.
[context#153](https://github.com/deanjstone/context/issues/153) settled that the file is
the memory and Supabase is a rebuildable index, so a hand-edit is not a ghost — it is the
memory itself, with a stale index behind it. The rule survives that on three other
grounds ([context#159](https://github.com/deanjstone/context/issues/159)):

- **Validation.** Nothing checks a hand-edited file's frontmatter. `type` is
  case-sensitive and lowercase is reserved for memory, so a capitalised `Reference`
  where `reference` was meant silently means "not a memory at all" — no error anywhere.
- **Provenance.** `memory_remember` stamps the `source:` tag on the write path, from its
  transport ([argus#377](https://github.com/deanjstone/argus/issues/377)), and rejects a
  caller-supplied one — so provenance cannot be hand-added, by an agent or anyone else. A
  hand-edit bypasses that write path, so it carries no provenance at all; the store→files
  reconciler's `source:unknown` covers only rows that reached the store unlabelled.
- **The hub link.** `memory_remember` records the memory's `topics` so the generated hub
  picks it up, and a memory no hub links is a **hard lint failure**
  ([context#154](https://github.com/deanjstone/context/issues/154)).

`memory_remember` is the **sole** sanctioned write path — not preferred-but-optional —
and the same rule binds a human editing in Obsidian and an agent using `Edit`.

### Step 5 — Done

---

## Output to user

After writing, report:
- N new entries added
- N existing entries updated
- List each by name with one-line summary of what was captured

If nothing worth saving was found, say so explicitly rather than inventing entries.
