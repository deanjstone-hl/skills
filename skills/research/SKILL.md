---
name: research
description: >
  Investigate a question against high-trust primary sources and write findings to a Markdown
  file, each claim cited. Use to research a topic, gather docs or API facts, delegate
  reading to a background agent, resolve a wayfinder `research` ticket, or inventory a repo
  ("read these files in full and report every X").
---

Spin up a background agent to do the research, so the main session keeps working while it reads.

Use the `Agent` tool (`subagent_type: general-purpose`, `run_in_background: true` unless the result is needed before continuing) and brief it with:

1. The exact question, not a vague topic.
2. Investigate against **primary sources** — official docs, source code, specs, first-party APIs — not a secondary write-up of them. Follow every claim back to the source that owns it.
3. Write the findings to a single Markdown file, citing each claim's source.
4. Save it where the repo already keeps such notes; match the existing convention, and if there is none, put it somewhere sensible and say where.

## Resolving a wayfinder `research` ticket

Brief the agent with the ticket's exact question. It should:

- Work on a throwaway `research/<name>` branch. If the calling session's own working directory isn't a git repo (so `isolation: "worktree"` can't create one), have the agent `cd` into the real repo itself and run `git worktree add /tmp/wf-research-<name> -b research/<name> origin/main`, then clean the worktree up when done.
- Post the findings as a comment on the ticket with a link to the file/branch.
- Never close the ticket or edit the map — resolving the ticket (closing it, recording the answer in Decisions-so-far) is the calling session's job, not the research agent's.

## Repo inventory

When the question is "what does this repo actually contain or do about X" — an inventory, not a web lookup — skip the file and get the answer back inline. Build the file list yourself first with a targeted `Glob`/`Grep` (cheap, and it keeps the subagent from re-deriving scope), then brief one subagent with this template. Use `subagent_type: Explore` (read-only); the template overrides its default of reading excerpts.

```text
Repo: <absolute path> — <one line on what the repo is>.
Question: <the exact inventory wanted, e.g. "every mechanism this repo uses to deploy its config">.

Read each of these files in full with the Read tool — not excerpts, not grep hits:
1. <path>
2. <path>
...
If a listed file points at another file that is part of the answer, read that too and name it.

Report the full relevant content, not a summary: quote commands, paths and values exactly.
Group the output by <environment | mechanism | file>. Note any listed file that is missing or empty.
Under <N> words total.

Do not: edit, commit or run anything that writes; touch live systems, settings or memory; read outside <repo path>.
```

Reuse the same brief for follow-up questions on the same repo by swapping only the question and file list.
