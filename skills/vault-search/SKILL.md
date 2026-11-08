---
name: vault-search
description: >
  Deep search of a markdown vault: CONTEXT (agent memory bodies, past session notes, AI/agent
  reference) or CORTEX (the life PKM: saved articles, knowledge pages, software references,
  journal, contacts, work notes). Use for "search CONTEXT", "what did we do in the session
  where", "find the session about", "trace a past decision", "search CORTEX", "what did I
  save about", "pull from CORTEX". Quick memory lookups: read ~/CONTEXT/MEMORY.md and the
  matching hub in ~/CONTEXT/TOPICS/ first.
argument-hint: "<context|cortex> <query>"
disable-model-invocation: true
---

# Vault Search

Three-phase filesystem search over one vault, run in a Haiku `Explore` subagent so results
stay out of the main context. Both vaults are Syncthing-synced local paths; never use the
`/mnt/c/` Windows mount from WSL2. The `obsidian` CLI is Windows-only, so use `grep`/`find`.

## 1. Pick the vault

| Vault | Path | Holds | Reference |
|---|---|---|---|
| CONTEXT | `~/CONTEXT/` | Agent memory, session notes, AI/agent reference | `references/context.md` |
| CORTEX | `~/CORTEX/` | Life PKM: articles, knowledge, journal, contacts, work | `references/cortex.md` |

The first word of the request ("context", "cortex") picks it. With none: agent history,
memories, past decisions and tool evaluations are CONTEXT; saved articles, life and
reading content are CORTEX. If it is still unclear, search CONTEXT and say so.

Read the chosen reference file now. It supplies the five parameters below, the vault map,
the frontmatter schema and the after-results steps. A hit that belongs to the other vault
is named, not searched: say which vault holds it and offer to run that one.

## 2. Parameters (from the reference file)

- `vault_root`: absolute path to the vault
- `search_dirs`: directories to search, each tagged `filename` (find only), `fulltext` (grep
  only) or `both`
- `query`: the user's keywords
- `frontmatter_hint`: which frontmatter fields carry the relevance signal
- `result_format`: fields to return per result line

## 3. Three-phase strategy

**Phase 1, candidates** (filenames only, cheap):
```bash
# each search_dir tagged filename or both:
find <search_dir> -name "*.md" -iname "*<keyword>*" 2>/dev/null
# each search_dir tagged fulltext or both:
grep -ril "<query>" <search_dir> 2>/dev/null | head -30
```
Deduplicate. With 0 results, retry with broader terms or synonyms.

**Phase 2, frontmatter filter** (about 10 to 20 tokens a file):
```bash
for f in <candidates>; do
  echo "=== $f ==="
  awk '/^---/{c++; if(c==2) exit} c==1 && !/^---/ {print}' "$f"
  echo ""
done
```
Score with `frontmatter_hint`; drop files with no relevance signal. Read no bodies yet.

**Phase 3, bodies** (top 3 to 5 only): `head -60 "<file>"`, or `cat` for short files.

## 4. Delegate

```javascript
Agent({
  description: "Vault search: <query>",
  subagent_type: "Explore",
  model: "haiku",
  prompt: `
Search the vault at <vault_root> for content relevant to: "<query>"

Search directories (mode in parens): <search_dirs as "path (mode)" list>

## Phase 1: Get candidates
Run the find/grep commands per directory mode, in parallel. Deduplicate.

## Phase 2: Filter
Extract frontmatter/headers only (not full bodies). Score relevance using: <frontmatter_hint>.
Drop candidates with no signal.

## Phase 3: Body read (top 3-5 only)
head -60 on the top-ranked candidates only.

## Output
Return a ranked list (best match first, max 20) with these fields per result: <result_format>
  `
})
```

Return the subagent's ranked list to the user unchanged, then follow the "After results"
section of the reference file.
