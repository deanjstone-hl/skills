---
name: todo
description: >
  Track deferred work as a GitHub issue. Use for "add a TODO", "TODO:", "log a TODO", "track
  this", "note this for later", or any deferral. Also use proactively when an item is
  deferred mid-task ("we'll come back to", "fix later", "review later", "do this next
  session").
---

# TODO Skill

Creates a GitHub issue as the canonical record. Only writes to `~/agent-cli/docs/TODO.md`
for cross-cutting items that have no clear repo.

---

## Step 1 — Parse the request

Extract from the user's message:

| Field | How to derive |
|---|---|
| **Title** | Short imperative phrase (≤ 8 words). Infer from the user's wording. |
| **Detail** | Expanded context: what needs doing and why. Include file paths or specifics if mentioned. |
| **Urgent** | True if the user says "urgent", "critical", "blocking", "ASAP", or uses `[!]`. |
| **Mode** | Exactly one of `HITL` or `AFK` — see the table below. Always set; never left blank. |

If the title or detail are genuinely unclear, ask with `AskUserQuestion` — one call, both fields.

### Choosing the mode

The mode tells an orchestrated session (the AFK backlog loop, or a T3 thread an orchestrator
launched) whether it can work the issue with nobody watching.

| Mode | Choose it when | An orchestrated session |
|---|---|---|
| **HITL** | The work itself needs the owner: a design or product decision nobody has made yet, a live-system action that needs confirmation (deploying, enabling a service, editing shared remote config, a destructive or non-standard git action), a credential or secret-store write, or physical access to a device. | Skips it unless the owner is present. |
| **AFK** | An agent can take it from start to merged PR under standing authorization: repo-only changes, a decided design, tests that prove it, a standard squash-merge. | Takes it. |

Pick on the **hardest step**, not the typical one: a single live-system confirmation makes the
issue HITL, never AFK.

**There is no Both mode** — it was retired on 2026-10-14 (argus-config#595) and its label
deleted (#604). When an agent can
do most of the work but one named step needs the owner, file **two** issues:

1. An **AFK** issue for the agent work, up to the checkpoint.
2. A **HITL** issue for the checkpoint itself, natively blocked by the AFK issue (see
   Step 3). Its title names the concrete step ("Deploy X to homelab", "Pick the schema for
   Y"), never "review".

Each gets its own labels and `Mode:` line. Never file a new `mode:both` issue.

This is not the `ready-for-agent` triage label. That label says an issue is fully specified;
the mode says who must be present. An issue can be AFK and not yet specified, or fully
specified and HITL.

---

## Step 2 — Infer the target GitHub repo

Determine which repo this TODO belongs to.

**Keyword → repo mapping:**

| Keywords / signals | Repo |
|---|---|
| budget, budgetbuddy, Up Bank, FIRE, transaction | `deanjstone/budget` |
| reader, read.myargus, knowledge, myargus, shell app, stockade | `deanjstone/myargus` |
| atto1, EV tracker | `deanjstone/atto1` |
| ios-scripts, scriptable | `deanjstone/scriptable-private` |
| erto, AQF cert | `audaxworks/erto-apps` |
| mcp-memory, memory mcp | `deanjstone/argus` |
| homelab, dell | `deanjstone/homelab` |
| argus-config, claude config, skills, hooks, settings | `deanjstone/argus-config` |
| sys-admin, dev stack, sysadmin | `deanjstone/sys-admin` |
| argus, agent-cli, agent-engine, orchestration | `deanjstone/argus` |
| No clear signal | current project's repo: `gh repo view --json nameWithOwner -q .nameWithOwner` |

If inference is ambiguous, use `AskUserQuestion`:

```
Question: "Which repo should this issue go in?"
Options: [matched candidates or common repos] + "agent-cli (cross-cutting)"
```

If the item is genuinely cross-cutting (spans multiple repos, or is orchestration meta-work
with no single owner), set `$TARGET_REPO` to `""` — use the file fallback (Step 5).

Store the resolved repo as `$TARGET_REPO`.

---

## Step 3 — Create GitHub issue

Set `$WAVE_LABEL` first. Choose it: `wave:w1`, `wave:w2` or `wave:later`, and put the reason in one line of the body (the map, blocker or incident it serves; argus-config#1197). With no reason to choose, the default stands: `wave:w1` when `$TARGET_REPO` is `deanjstone/argus-config` (its work affects the whole ecosystem, argus-config#716), `wave:later` for every other repo. The orchestrator validates the choice on its tick.

Set `$TYPE_LABEL` too: the kind of change, from the title's commit type (`fix` is `type:bug`; otherwise `type:feat`, `type:docs`, `type:chore`, `type:refactor`, `type:test`, `type:ci`, `type:perf`, `type:build`, `type:security` or `type:revert`). Exactly one; pick the nearest, never leave it off (argus-config#1294).

```bash
gh issue create \
  --repo "$TARGET_REPO" \
  --title "<Title>" \
  --label "$WAVE_LABEL" \
  --label mode:<afk|hitl> \
  --label "$TYPE_LABEL" \
  --body "<Detail and context>

Mode: <HITL|AFK>"
```

**The labels are the backlog** (argus-config#566): the filing wave (chosen, with a reason line; default `wave:w1` in argus-config, `wave:later` elsewhere), the one `mode:*`
label matching Step 1 (`AFK` → `mode:afk`, `HITL` → `mode:hitl`), and the one `type:*` label (`$TYPE_LABEL`). Moving the issue into W1
or W2 is not this skill's job: the daily label sweep judges each new issue once. `Urgent`
(Step 1) is conveyed in the body, not by filing straight into a numbered wave.

If `gh` reports a label as not found, the repo predates the label set or is out of scope.
Do not create it by hand: `python3 ~/.claude/hooks/backlog-labels.py sync --repo "$TARGET_REPO"` prints the plan (a dry run), and the owner approves `--confirm`. File the issue without the missing label meanwhile.
Out-of-scope repos (certificate-generator, erto-apps) get no backlog labels; file without them.

The body ends with a one-line `Mode:` that matches the `mode:*` label: `Mode: AFK` or
`Mode: HITL`.

For an owner checkpoint (Step 1), create the AFK issue first, then the HITL checkpoint issue,
and gate the checkpoint on the AFK issue with a native dependency (works across repos):

```bash
AFK_ID=$(gh api repos/<o>/<afk-repo>/issues/<afk-n> --jq .id)
echo "{\"issue_id\":$AFK_ID}" | gh api -X POST repos/<o>/<r>/issues/<checkpoint-n>/dependencies/blocked_by --input -
```

`issue_id` is the numeric `.id`, not the issue number (`wayfinder-mechanics` §5).

Capture the returned issue URL as `$ISSUE_URL`.

If the `gh` call fails, note the error and proceed to the file fallback (Step 5).

---

## Step 4 — Report and stop (normal path)

```
Created issue: **<Title>** · $ISSUE_URL
[Labelled <wave:w1|wave:w2|wave:later>, mode:<mode>, type:<type>]
```

No file write needed. Done.

---

## Closeout

When a `/todo`-created issue is later closed, close it with a written **Resolution**
comment (what was decided/done, not just a bare close or a PR's auto-close reference) —
the same convention wayfinder tickets already use. One closure vocabulary across both
forms means a session scanning closed issues never has to guess which kind of "done"
it's looking at.

---

## Step 5 — File fallback (cross-cutting items only)

Only reached when `$TARGET_REPO` is empty or the GH call failed.

Write to `~/agent-cli/docs/TODO.md`:

```bash
ls ~/agent-cli/docs/TODO.md 2>/dev/null || echo "MISSING"
```

If missing, create it:

```markdown
# TODO — agent-cli

Cross-cutting and orchestration-level items only. All project-specific work is tracked as GitHub issues in the relevant repo.
```

### Format

Standard item:

```markdown
- [ ] **<Title>** — <detail and context> Mode: <HITL|AFK> (added <YYYY-MM-DD>)
```

Urgent item:

```markdown
- [ ] `[!]` **<Title>** — <detail and context> Mode: <HITL|AFK> (added <YYYY-MM-DD>)
```

Append under the correct section heading (stable area names, never date-keyed). Use Edit — do not rewrite the file.

Report:

```
Added to ~/agent-cli/docs/TODO.md → <Section>: **<Title>**
```

---

## Rules

- **GitHub issue is always the primary record.** File write is only for cross-cutting or GH-unreachable items.
- **One skill invocation = one TODO item.** If the user lists multiple, create all issues in one pass.
- **Proactive use:** when any work is explicitly deferred mid-task, create the issue immediately without waiting for the user to invoke `/todo`.
- **Never create docs/TODO.md in project dirs.** The only TODO.md files that exist are `~/agent-cli/docs/TODO.md` and `~/agent-cli/docs/TODO-archive.md`.
- **Size gate, not this skill.** If the deferred work is unclear in scope, or clearly more than ~1 session, it's not a `/todo` issue — it's a wayfinder map (grilling if the scope is unclear, task-type if it's just large). Only invoke this skill for work that's both clear and small.
- **You choose the wave at filing** (`wave:w1`, `wave:w2` or `wave:later`, with a one-line reason in the body); the defaults are `wave:w1` in argus-config and `wave:later` everywhere else — see Step 3.
- **Every issue carries exactly one `type:`** — the commit-type label (`type:bug`, `type:feat`, `type:docs`, `type:chore`, …) in `$TYPE_LABEL`, set at filing (Step 3); a missing one is a sweep warning.
- **Every issue carries exactly one mode** — the `mode:*` label plus the `Mode:` body line, set at filing (Steps 1 and 3). Unlike the wave, the mode is decided here: the filer knows best what the work needs. The owner may correct it later, swapping the label and the line together.
