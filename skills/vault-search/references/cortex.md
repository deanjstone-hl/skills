# CORTEX vault

The **life PKM vault** at `~/CORTEX/`: personal knowledge, saved articles, journal, work notes,
contacts. It holds no agent memory, session transcripts or repo snapshots (that is CONTEXT).

## Vault map

| Directory | Contains | Search by default? |
|---|---|---|
| `REFERENCE/sources/` | Ingested web articles, clippings, blog posts | Yes |
| `REFERENCE/knowledge/` | LLM-synthesised concept pages (high-signal) | Yes |
| `REFERENCE/software/` | LLM-maintained tool/framework pages | Yes |
| `REFERENCE/articles/` | Shorter clippings and one-offs | Yes |
| `REFERENCE/internet-logs/` | AI briefings and curated digests | Yes |
| `PROJECTS/` | Coding projects and playgrounds | If asked |
| `LIFE/` | Contacts, finances, health, recipes, objects | If asked |
| `JOURNAL/` | Daily notes (do not modify) | If asked |
| `WORK/` | Work notes and meetings | If asked |
| `LIBRARY/` | Books, authors, stories | If asked |
| `SYSTEM/` | Templates, config, agents, skills | If asked |

Default scope is `REFERENCE/` only. Widen only when the user asks or the query clearly
implies another section.

**Not here:** past session notes, agent memory files (`feedback_`, `project_`, `reference_`
entries), agent/AI-dev reference and tool evaluations (`reference_*` memories under the
`ai-reference` hub), and Claude/AI source articles are all CONTEXT.

## Frontmatter schema

Extract frontmatter instead of reading whole files; it is enough to judge most queries.

Clippings (`REFERENCE/sources/`, `REFERENCE/articles/`):
```yaml
title: "Article title"
source: "https://..."
description: "Truncated excerpt (~200 chars), the primary relevance signal"
published: 2026-04-18
tags: [clippings]   # always just "clippings", useless for filtering
```

Knowledge and software pages (`REFERENCE/knowledge/`, `REFERENCE/software/`):
```yaml
type: wiki/knowledge   # or wiki/software
hall_type: facts       # or: advice
tags: [agents, memory, ai-architecture]   # semantic tags, the primary relevance signal
sources: ["[[Linked Source]]"]            # secondary signal
```

## Search parameters

- `vault_root`: `~/CORTEX/`
- `search_dirs`:
  - `~/CORTEX/REFERENCE/` (filename, top-level)
  - `~/CORTEX/REFERENCE/sources/` (fulltext)
  - `~/CORTEX/REFERENCE/knowledge/` (fulltext)
  - `~/CORTEX/REFERENCE/software/` (fulltext)
- `frontmatter_hint`: "clippings: title + description fields; knowledge/software pages: tags + sources fields; filename match is a strong positive signal"
- `result_format`: "vault-relative path (e.g. REFERENCE/sources/My Article.md), title, type ([source]/[knowledge]/[software]/[article]), one-line relevance reason"

Narrow one-off lookups skip the three-phase flow and stay direct `grep`:

```bash
grep -ril "<query>" ~/CORTEX/LIFE/Contacts/ 2>/dev/null          # contacts
grep -ril "<query>" ~/CORTEX/PROJECTS/ 2>/dev/null               # projects
grep -ril "<query>" ~/CORTEX/JOURNAL/ 2>/dev/null | head -10     # journal, read-only
grep -ril "<query>" ~/CORTEX/WORK/ 2>/dev/null                   # work
grep -ril "^tags:.*<tag>" ~/CORTEX/REFERENCE/ 2>/dev/null        # tag search
grep -ril " #<tag>" ~/CORTEX/REFERENCE/ 2>/dev/null              # inline tags
grep -rl "\[\[<Note Title>\]\]" ~/CORTEX/ 2>/dev/null            # backlinks
```

Backlinks work because CORTEX notes cite sources in `sources:` frontmatter
(`sources: ["[[Headroom MCP]]"]`), not inline wikilinks. Use it before editing or deleting a
note ("what references this").

## After results

1. Present a ranked list: path, title, type, one-line summary.
2. Read a note with `Read` on its full `~/CORTEX/...` path.
3. To use content in a repo, link or cite the note by vault path. Never copy CORTEX syntheses
   into a repo's `docs/`; copies drift from the vault original (argus#418).
4. To open in Obsidian (Windows), the file is already in the live vault: give the vault-relative path.
5. Save results as a new note only when the user asks, at `~/CORTEX/REFERENCE/knowledge/<title>.md`:

```yaml
---
type: wiki/knowledge
hall_type: facts
tags: [<relevant-tags>]
sources: []
---

# <Title>

<Synthesised content from search results>
```

Obsidian-side skills (`obsidian-cli`, `vault-audit`, `inbox-triage`, `tag-garden`) run in
CORTEX's own Claude session (`@tex`) when Obsidian is open on Windows, not from here.
