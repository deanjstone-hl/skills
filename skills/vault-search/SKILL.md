---
name: vault-search
description: >
  Internal helper: filesystem search over a markdown vault (filename, full-text, frontmatter
  filters, top-match bodies) in a Haiku Explore subagent, keeping results out of main
  context. Called by context-search and cortex-search; end-user requests go to those two.
---

# Vault Search (shared engine)

A parameterized three-phase search pattern used by vault-specific skills
(`context-search`, `cortex-search`). The calling skill supplies:

- `vault_root` — absolute path to the vault (e.g. `~/CONTEXT/`, `~/CORTEX/`)
- `search_dirs` — list of directories to search, each tagged `filename` (find only),
  `fulltext` (grep only), or `both`
- `query` — the user's search query / keywords
- `frontmatter_hint` — one or two lines describing which frontmatter fields carry the
  relevance signal (e.g. "description field" or "tags + sources fields") — passed straight
  from the calling skill's own frontmatter-schema section
- `result_format` — what fields to include per result line (path, type, date, title, etc.)

## Three-phase strategy

**Phase 1 — Candidate list** (filenames only, cheap):
```bash
# For each search_dir tagged filename or both:
find <search_dir> -name "*.md" -iname "*<keyword>*" 2>/dev/null

# For each search_dir tagged fulltext or both:
grep -ril "<query>" <search_dir> 2>/dev/null | head -30
```
Deduplicate. If 0 results, retry with broader terms or synonyms.

**Phase 2 — Frontmatter/header filter** (cheap, ~10–20 tokens/file):
```bash
for f in <candidates>; do
  echo "=== $f ==="
  awk '/^---/{c++; if(c==2) exit} c==1 && !/^---/ {print}' "$f"
  echo ""
done
```
Score using `frontmatter_hint`. Discard files with no relevance signal. Do not read
full bodies yet.

**Phase 3 — Body read** (top 3–5 matches only):
```bash
head -60 "<file>"   # or cat for short files
```

## Delegation

```javascript
Agent({
  description: "Vault search: <query>",
  subagent_type: "Explore",
  model: "haiku",
  prompt: `
Search the vault at <vault_root> for content relevant to: "<query>"

Search directories (mode in parens): <search_dirs as "path (mode)" list>

## Phase 1: Get candidates
Run the appropriate find/grep commands per directory mode, in parallel. Deduplicate.

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

## Output

Return the subagent's ranked list unchanged to the calling skill/user.
