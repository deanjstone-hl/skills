---
name: save-session
description: >
  Save memories and compute a session name.
  Trigger on: "/save-session", "save session", "checkpoint", "name this session",
  or any variant asking to checkpoint the session's work before continuing.
---

# /save-session

Checkpoint the session — memories and session name. Session notes are written by the
nightly session synthesiser from the `.jsonl`, not by this skill (context#332).

Note: neither `/clear` nor `/rename` can be invoked by the assistant — both are
client-side-only commands with no tool path (see
[[fact_skill_cannot_invoke_local_commands]]). This skill computes and reports
what to run; you apply them yourself. `/recap` is the same kind of client-side-only
command — confirmed by an explicit tool error the one time this skill tried to call it
directly — which is why Step 1 uses `session-brief` instead (see below).

---

## Step 1 — Get the session recap via session-brief

Invoke the `session-brief` skill (`Skill({skill: "session-brief"})`), not `/recap` —
`/recap` is a built-in CLI command with no tool path the assistant can call; a prior
attempt to invoke it here failed with an explicit error (see
[[fact_skill_cannot_invoke_local_commands]]). `session-brief` was built as a
callable replacement and also works in headless/non-interactive runs, where native
`/recap` is always skipped.

Take its one-sentence summary and reuse it for both Step 2 (the label) and Step 3
(`/memorise` needs it too, and must not invoke `session-brief` a second time).

---

## Step 2 — Compute the session name

**Derive the prefix** from the git repo name, not the working directory — worktree
checkouts (e.g. `argus-config-wt`) live in dirs whose name doesn't match the repo:

1. **`pwd` is `~/.argus/workspace/`**: prefix is always `AGENT`, regardless of git
   state. Check this first, before the git-repo test below — the workspace is
   deliberately kept a non-git scratch dir (see [[decision_argus_workspace_not_git_repo]]),
   so it would otherwise fall through to the generic environment-prefix branch and get
   labeled `WSL`/`LGN5`/`SRVR` like any other non-repo directory, losing the fact that
   it's the orchestrator workspace specifically.
2. **Inside a git repo/worktree**: run `git remote get-url origin`, take the basename
   with `.git` stripped (fallback: basename of `git rev-parse --show-toplevel` if there's
   no remote), uppercase it.
3. **Not in a git repo and not the workspace**: fall back to the environment prefix:

| Environment | Prefix |
|---|---|
| WSL | `WSL` |
| Windows | `LGN5` |
| Homelab | `SRVR` |

**Derive the label**: if the user passed one as an argument (e.g. `/save-session
build-5-skills`), use it directly — do not summarise. Otherwise derive it from the
Step 1 session-brief summary in 3–5 words, `kebab-case`.

**Compose**: `<PREFIX>_<label>`

Examples:
- repo `argus` + "build 5 skills" → `ARGUS_build-5-skills`
- worktree `argus-config-wt` (repo `argus-config`) + "fix skills" → `ARGUS-CONFIG_fix-skills`
- `/home/deanj` (not a repo) + "daily review" → `WSL_daily-review`
- `/home/srvr/repos/argus` (repo `argus`) + "deploy code-relay" → `ARGUS_deploy-code-relay`
- `~/.argus/workspace/` (non-git orchestrator workspace) + "triage inbox" → `AGENT_triage-inbox`

---

## Step 3 — Run /memorise

**Always invoke it — this step is mandatory, not conditional on whether the session
"felt significant."** `memorise` is a real Skill-tool-invocable skill, unlike `/clear`,
`/rename`, and `/recap` in the note at the top of this file — do not treat its
slash-styled name as another one of those. Call it explicitly:

```
Skill({skill: "memorise"})
```

but tell it to **skip its own Step 0** — the session-brief summary already ran in Step 1,
reuse it instead of invoking `session-brief` again. `memorise` itself:
- Scans the conversation for durable memory entries, checks the Supabase memory store
  (not just the local `MEMORY/` mirror — the two can drift in either
  direction, see [[fact_memory_ghost_entry_mirror_without_supabase]]) for existing
  entries on the same topic, then writes every candidate without a selection prompt
  (memorise's own Step 3 — invoking it is the approval) via the
  `memory_remember` MCP tool with `type` set (dual-writes to Supabase and mirrors to
  `~/CONTEXT/MEMORY/`, verifying both the Supabase content and the `mirror_status`
  in the result)

It is normal for `memorise` to conclude "nothing to save" — that's `memorise` applying
its own filter *after* being invoked, not a reason to skip invoking it.

---

## Output to user

Report as **two separate messages**, not one bundled block — the session name is an
action item (the user has to actually type it), and gets lost when it trails a
multi-line status block.

**Always send both messages**, every run, regardless of whether Step 3 found anything
to save — the rename line is Step 2's output, not Step 3's, so "nothing to memorise"
never removes it.

**First message** — the checkpoint status:

```
Memories: <N new / N updated — list by name> (or "nothing to save")
```

**Second message** — standalone, **always wrapped in its own fenced code block**
(triple backticks, no language tag), containing only the rename command and nothing
else — no leading label like "Session name:", no trailing note, no prose before or
after the fence in that message:

```
/rename <PREFIX_label>
```

Never emit the rename line as plain inline text outside a fence — a bare line reads
identically to prose in chat and isn't reliably copy-pasteable; the fence is what makes
it a single clean block the user can click-to-copy.
