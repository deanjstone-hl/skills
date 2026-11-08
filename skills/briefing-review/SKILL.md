---
name: briefing-review
description: Triage the daily AI briefings (read from the briefings API) over a date range into one prioritised extraction note in SOURCES/, opened as a PR in deanjstone/context.
disable-model-invocation: true
---

# /briefing-review

Read every daily briefing in a date range, keep only the items that clear the triage bar, and write one prioritised extraction note so nobody has to reread the briefings. On demand only: there is no schedule.

Arguments (optional): `[FROM] [TO]` as `YYYY-MM-DD`. `FROM` alone means `FROM` to today. No arguments means the 14 days ending today.

## Step 1: Discover briefings

Briefings live on the homelab briefings API (the ops hub), not in the vault. It keeps 14 days, so a range reaching further back returns only the last 14. List what exists, passing the arguments through and omitting any you were not given. This reads the notice-board device token inside the call and prints nothing secret:

```bash
bash -s -- <FROM> <TO> <<'EOF'
FROM="${1:-$(date -d '14 days ago' +%F)}"; TO="${2:-$(date +%F)}"
source ~/.argus/hooks/briefings-api.sh
listing=$(briefings_api GET /briefings) || exit 1
python3 -I -c '
import json, sys
frm, to = sys.argv[1:3]
for date in sorted(item["date"] for item in json.load(sys.stdin)["briefings"]):
    if frm <= date <= to:
        print(date)
' "$FROM" "$TO" <<<"$listing"
EOF
```

Report the count and the date range covered. With zero dates, say so and stop. A failure naming the device token or the hub is an owner problem (the token file is written by `scripts/notice-board-client-token.sh` in argus-config): report it and stop.

Done when: you have the sorted date list.

## Step 2: Read every briefing

Fetch each date with `briefings_api GET /briefings/<date>` (same `source` line as above). The response holds `news` (markdown), `ops` (rows of `section`, `title`, `url`, `detail`) and `memories`. Triage reads `news`. Read all of them before triaging, since you can only detect recurrence after you have seen the whole set. Parallel reads are fine. The news uses the headings from `hooks/daily-briefing-analyze.sh` in argus-config:

| Heading | How to use it |
|---|---|
| `## 🎯 BLUF - Most relevant` | Already filtered against the stack. Treat each bullet as a candidate |
| `## 📈 Trend Consolidation` | Recurrence the briefing agent already saw across days. Strong candidates |
| `## 🤖 Claude Code & Anthropic` | Version notes, model updates, security advisories |
| `## 🚀 Agentic AI Highlights` | Scan for anything the BLUF missed |
| `## 🧰 T3 Code` | Versions, and changes to act on or watch |
| `## 💻 Coding Agent Ecosystem`, `## 📱 Tech & Devices (XDA)` | Only in briefings before 2026-10-22; the trimmed news no longer has them. Scan for anything the BLUF missed; XDA is low yield |
| `## 🛠️ Tools & Repos` | Bullets (a table before 2026-10-22). `Signal`: `GH-starred` is the strongest, then `GH-trending`/`HN`, then `GH-new`. `Fit`: Complements / Replaces / Pattern / No fit, each followed by the in-scope repo it applies to (`Complements — homelab`). Briefings before 2026-10-15 name this column `Argus Fit` and rate against Argus only |

While reading, track for each item:

- **Recurrence**: every date it appears. This is the strongest signal.
- **Stack hits**: any match against the stack-relevance list below.

### Stack-relevance list

An item touching any of these counts as immediately relevant:

- **Argus**: agent-cli, agent-engine, memory-mcp (memory.myargus.cc), notice-board, vault-agent, watchtower, email-worker/email-mcp, x-mcp, wiki
- **Harness**: Claude Code, argus-config (skills, hooks, settings), T3 Code, agent-intern (Codex, Gemini, Copilot and the other bridged CLIs), the 5-hour quota window
- **Vaults**: CONTEXT (agent memory, briefings), CORTEX (Obsidian PKM), Syncthing sync
- **Projects**: myargus.cc, design-system, budget, atto1, erto-apps, slate-reader
- **Stack**: TypeScript, Vite, Tailwind CSS, Supabase, Cloudflare Workers/Pages, Node.js, pnpm
- **Infra**: WSL2, homelab, Tailscale, systemd user units, Bitwarden

## Step 3: Triage

Include an item if any of these holds:

- It is a security issue with a concrete attack path into the stack: MCP surfaces, credential scope, prompt injection through agent inputs, or supply chain in a dependency we use.
- It recurs in 2 or more briefings.
- It carries a `High` priority label, or it is a `GH-starred` row whose `Fit` (or `Argus Fit`, in older briefings) is anything other than `No fit`.
- It is directly actionable against a named item on the stack-relevance list.

Drop an item if any of these holds:

- It is ecosystem news with no action path (funding, acquisitions, org changes).
- Acting on it needs something we lack, such as a paid-only API.
- It appears once and has no stack hit.
- The stack already does it. Record it as "already have this" only when that is useful to know.

Done when: every candidate from Step 2 is placed in a tier or dropped for a stated reason.

## Step 4: Write the extraction note

Work in a scratch worktree of the CONTEXT repo, branched from `origin/main`. The live `~/CONTEXT` checkout stays on its own branch, because the memory-reconcile timer and Syncthing write there.

```bash
cd ~/CONTEXT && git fetch
git worktree add -b chore/briefing-extractions-<FROM>-to-<TO> /tmp/context-briefing-<FROM>-<TO> origin/main
```

Write `SOURCES/Briefing Extractions <FROM> to <TO>.md` inside the worktree (`mkdir -p SOURCES` first if missing; `SOURCES/` has no size cap). If a note covering an overlapping range already exists there, extend it: merge the new items in and remove duplicates rather than writing a second note.

```markdown
---
created: YYYY-MM-DD
modified: YYYY-MM-DD
type: Extraction
title: Briefing Extractions <FROM> to <TO>
description: "Prioritised items from N daily AI briefings, <FROM> to <TO>."
covers: <FROM> to <TO>
tags:
  - briefing
  - extraction
  - agentic-ai
---

# Briefing Extractions <FROM> to <TO>

Synthesised from N briefings (<FROM> to <TO>). Every item cleared the triage bar: a security path into the stack, recurrence across briefings, or direct action against a current project.

## 🔴 Act Now: Security

### {Item} ({Oct 2, Oct 5})

{What it is, how it reaches the stack, what to check.}

- Action: {specific step}
- Source: [{title}]({url})

## 🟠 Do This Week

## 🟡 Do This Month

## 🔵 Monitor

### {Item} ({date})

{Why it is on the radar, and what would promote it.}

- Source: [{title}]({url})

## 📋 One-Off Signals

| Item | Date | Note |
|------|------|------|
```

Placement:

- **🔴 Act Now**: every security item with a concrete attack path, however few briefings mention it. Never soften a real threat into a lower tier.
- **🟠 Do This Week**: `High` labels, items that unblock a named project, and items seen in 3 or more briefings.
- **🟡 Do This Month**: actionable but not time-sensitive, including items seen in 2 briefings.
- **🔵 Monitor**: stack-adjacent items with no action yet, or items blocked on a future milestone.
- **📋 One-Off Signals**: Claude Code version notes, platform changelog items, sentiment.

Every item heading carries its briefing dates. Every item has a `Source:` link copied from the briefing. Each `Action:` must be specific enough to act on without opening the briefing. A recurring item states its count ("6 of 10 briefings"). Leave a tier heading empty with `None this period.` rather than filling it with items that did not clear triage. Briefings are inputs only: never post to or edit the API.

Done when: every item from Step 3 is in the note with dates, a source and, outside Monitor, an action.

## Step 5: Open the PR

```bash
cd /tmp/context-briefing-<FROM>-<TO>
git add "SOURCES/Briefing Extractions <FROM> to <TO>.md"
git commit -m "add briefing extractions <FROM> to <TO>"
git push -u origin HEAD
gh pr create --repo deanjstone/context --base main \
  --title "add briefing extractions <FROM> to <TO>" --body "<summary>"
```

The body follows the PR template (Summary, Why, Test plan) and includes the tier counts from Step 6. Leave the PR for the user to review and merge. Then remove the scratch worktree with `git -C ~/CONTEXT worktree remove /tmp/context-briefing-<FROM>-<TO>`.

## Step 6: Report

```
## Briefing Review: <FROM> to <TO>

Briefings read: N (from the briefings API)
Items: 🔴 N · 🟠 N · 🟡 N · 🔵 N · 📋 N
Recurring (2+ briefings): {names}
PR: {url}
```
