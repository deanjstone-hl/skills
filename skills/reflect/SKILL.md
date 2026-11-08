---
name: reflect
description: Spawn three parallel review subagents over the active transcript, surface learnings, and route each to a concrete edit on an existing skill. Use when the user says reflect.
disable-model-invocation: true
---

# Reflect

Mine the current conversation for durable learnings, then route them into skill edits.

Invoke when the user says "reflect" or "/reflect". Skip when the conversation is trivial, off-topic, or already covered by an existing skill the parent followed correctly. One-offs are not learnings.

## 1. Locate the active transcript

Before fanning out, find this conversation's transcript. Claude Code writes one JSONL file per session under `~/.claude/projects/<encoded-cwd>/`, where `<encoded-cwd>` is the session's working directory with every `/` and `.` replaced by `-` (`/home/me/.work/app` becomes `-home-me--work-app`). Subagent transcripts sit beside it in `<session-id>/subagents/`. Look only in this one directory. Do not glob across `~/.claude/projects/*/`: that crosses workspace boundaries and reads private chats from unrelated projects.

```bash
ls -t ~/.claude/projects/<encoded-cwd>/*.jsonl | head -10
```

For each candidate, read the first record whose `type` is `user` and whose `message.content` is text. Take the file that contains the conversation's opening user prompt. If none matches, or the harness keeps no transcript, pass a tight digest of the session instead.

## 2. Spawn three reviewers in parallel

One message, three `Agent` calls with `subagent_type: general-purpose`. Use the general-purpose type, not `Explore`: reviewers need the MCP tools (deferred ones are loaded with `ToolSearch`) to look up the tickets, chat threads and traces the transcript references, and `Explore` strips them. They must not edit files; the prompt templates say so.

Set `model` from the table. If the repo's instructions name a model for this skill, use that instead. If the harness rejects a value, use the closest valid one and say so. To run a reviewer on another provider, T3 Code's `delegate_task` takes the same prompt.

| Lens | Default `model` | Prompt template |
|---|---|---|
| Judgment | `opus` | `references/judgment-reviewer.md` |
| Tooling | `sonnet` | `references/tooling-reviewer.md` |
| Divergent | `opus` | `references/divergent-reviewer.md` |

Pass each template verbatim, substituting the transcript path or digest where marked. Reviewers return findings as the `Agent` call's result.

## 3. Synthesize

One `Agent` call, `subagent_type: general-purpose`, `model: opus`. It spot-verifies citations through MCP, so it needs the general-purpose type. Pass `references/synthesizer.md` verbatim, with each reviewer's full output inlined where marked. It returns an Accepted / Rejected / Backlog list.

## 4. Structural enforcement check

Move any Accepted item that a lint rule, script, metadata flag, or runtime check would enforce more reliably to Backlog. The `correct` skill covers this: try architecture, then types, then a lint, then a test, and docs last.

## 5. Apply

Present the synthesizer's full Accepted / Rejected / Backlog output and wait for explicit approval before applying any Accepted edit. The user picks the subset and may redirect routings. Skill changes affect every future agent in the org. Do not auto-apply.

File each Backlog item to the project's issue tracker without waiting. Only the Accepted list waits for approval.

Never edit a skill under `~/.claude/plugins/cache/`: updates overwrite it. Before approval, show its destination, `.claude/skills/<skill>/` (this project) or `~/.claude/skills/<skill>/` (every project). After approval, copy the skill folder there and edit the copy. If the skill is a symlink into a source repo, edit the source and say so. Never open a PR or push.

Follow each approved row's Routing exactly:

- Trivial existing-skill edit (a one-line bullet, a tightened sentence, a stale fact corrected): the parent does it directly.
- Substantive existing-skill edit (a new section, a new pattern table, more than ~10 lines): hand to a skill-authoring skill if one is installed (for example `skill-creator`) and run its draft / test / iterate loop; otherwise make the edit directly and keep `SKILL.md` short.
- `tune description: <skill path>` (the skill exists but didn't trigger when it should have): rewrite the description to name the trigger, with the skill-authoring skill if installed.
- `new skill: <kebab-name>`: create it with the skill-authoring skill if installed. Do not invent the shape ad hoc.

If your environment ships a SKILL.md validator, run it on every touched skill before declaring done.

## 6. Summarize for the user

Short list, no preamble:

- Edits applied: `<skill path>`. What changed, one line each.
- New skills created: `<skill path>`. One line each (rare).
- Backlog filed to the issue tracker: `<issue title>` (`<tags>`). One line each.
- Dropped: one line per rejected finding + reason from the synthesizer.
