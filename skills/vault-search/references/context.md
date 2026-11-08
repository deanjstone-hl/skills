# CONTEXT vault

The **agent-first vault** at `~/CONTEXT/`: agent memory, session history, repo snapshots. It
holds no personal knowledge, saved articles or life content (that is CORTEX).

## Vault map

| Directory | Contains | Search by default? |
|---|---|---|
| `00.INBOX/` | User-curated articles pending ingest | No, staging only |
| `MEMORY/` | Persistent memory files, one per memory, each with `topics:` frontmatter | Yes |
| `TOPICS/` | Topic hubs: prose plus a generated link region to the memories on that topic | Yes |
| `SESSIONS/` | Session notes (`type: session`), one per session, date-prefixed | Yes |
| `ARCHIVE/` | Superseded notes; `ARCHIVE/reference/` and `ARCHIVE/wiki/` hold the full text of reference pages too long for one memory | Only when a memory's `Full page:` line points there |
| `SOURCES/` | Raw agent/AI-dev article clippings (200+ files), images in `SOURCES/attachments/` | If asked |

**Before searching:** `~/CONTEXT/MEMORY.md` (the vault root index, always loaded at session
start) and the topic hub it points to may already answer the question. Search only to go
deeper: memory bodies or session notes. AI/agent reference pages are `reference_*` memories
under the `ai-reference` hub. `MEMORY.md` lives at the vault root, not in `MEMORY/`, so
`autoMemoryDirectory` resolves it (context#55); it is not part of the `MEMORY/` set.

**Not here:** personal life articles, contacts, journal, work notes, and non-AI clippings
(cars, finance, tools) are CORTEX (`~/CORTEX/REFERENCE/` for the clippings).

## Memory file frontmatter

Every `MEMORY/*.md` file:

```yaml
---
name: pattern_xyz           # slug matching the filename
description: one-line summary, the primary relevance signal
type: fact|preference|pattern|decision|tension|question|methodology|reference
topics: [slug, ...]         # the hubs under TOPICS/ that link this memory
---
```

Read `description` before opening a body.

## Session notes (`SESSIONS/`)

Filenames are mostly `YYYY-MM-DD-<session-slug>.md`; a few older ones are
`Session - <title> - YYYY-MM-DD.md`. Frontmatter carries `type: session` and `date:`. Body:
`# <Session Title> — YYYY-MM-DD`, `## What happened`, `## Carry forward`. Filter on the
filename date and slug before reading the body. Raw transcripts are not in the vault: the
`.jsonl` session files are the source, and old ones are in git history (context#319).

## Search parameters

- `vault_root`: `~/CONTEXT/`
- `search_dirs`:
  - `~/CONTEXT/MEMORY/` (both)
  - `~/CONTEXT/TOPICS/` (filename; hubs list memories by topic)
  - `~/CONTEXT/SESSIONS/` (both)
- `frontmatter_hint`: "memory files: description field is primary signal; session notes: date + title in the first 8 lines"
- `result_format`: "path relative to ~/CONTEXT/, type ([memory]/[session]), date, one-line relevance reason"

## After results

1. Present the ranked list: path, type, date, relevance reason.
2. Read a memory with `Read ~/CONTEXT/MEMORY/<filename>`, a session with `Read ~/CONTEXT/SESSIONS/<filename>`.
3. When a reference memory ends with `Full page: \`ARCHIVE/...\``, read that file for the detail.
4. Session notes are historical records: read them, and leave edits to the session synthesiser.
