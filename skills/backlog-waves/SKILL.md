---
name: backlog-waves
description: >
  Answer what to work on next from the rolling-wave Argus Ecosystem Backlog (wave:* and
  mode:* labels) and keep wave labels true; also list what is open across the repos. Use for
  "what should I work on next", "what's takeable", "which wave are we on", "what's blocking
  the current wave", "is the backlog still accurate", "cut the next wave", placing an issue
  in a wave, "what's open?", "show me the backlog", "what's open in <project>?", "find
  issues about X", or "any urgent issues?".
---

# Backlog Waves

The Argus Ecosystem Backlog is run as a sequence of **scope-boxed, numbered rolling waves**
([argus ADR-011](https://github.com/deanjstone/argus/blob/main/docs/decisions/adr-011-rolling-wave-backlog.md)).
Near-term work is planned in detail and far-term work coarsely, and each wave is refined as it
approaches. This skill answers "what is takeable right now", keeps the `wave:*` labels
honest, and proposes the next wave once the old Next has been promoted. It is permanent: the method has no end state.

It answers ordering questions first; plain inventory ("what's open", "what's open in budget", "find issues about X", "any urgent issues") is the [`inventory` mode](#mode-inventory) below.

**This skill navigates. It does not execute.** It reports and proposes, then stops — you pick,
then invoke `/implement`, `/wayfinder`, or work the issue directly. It never claims an issue,
never starts an agent, and never moves or closes an issue without explicit approval.

## The method

| Wave label | Meaning |
|---|---|
| `wave:w<n>` — lowest with open issues | **Current.** Being worked, in dependency order. |
| `wave:w<n>` — second lowest with open issues | **Next.** Planned and gated, not started. |
| `wave:later` | Everything else, deliberately unordered. A session may file straight into `wave:w1`, `wave:w2` or `wave:later`, with a one-line reason in the issue body, and the orchestrator validates each new filing on its tick and changes the wave where it disagrees (argus-config#1197). With no reason to choose, new issues in every repo except argus-config are filed here and the daily label sweep places each new one in W1, W2 or Later once (argus-config#629). argus-config issues default to `wave:w1` because they affect the whole ecosystem (argus-config#716). |
| `wave:held` | Parked on owner hold (all of budget and obsidian-cadence since 2026-10-14). **Never takeable**: never Current or Next, never proposed by `cut-next`, never picked by the AFK loop. Only the owner moves an issue out of it. |

The helper shows these as `W1`, `Later`, `Held`. Closed history, including the
retired `old-W*` chart, stays on the frozen `projects/2` board and is not read.

- At most two waves are detailed at any time: Current and Next.
- Each wave has a **name**, kept in `waves.json` beside this file. Waves have no size cap
  (dropped 2026-10-16), and no goal, exit criteria or closing review (dropped 2026-10-07).
- A wave advances on its own: when Current's last issue closes, Next becomes Current. Then
  `cut-next` proposes a new Next.
- Gates are GitHub's **native issue dependencies** (`blockedBy`/`blocking`), which work across
  repos.

## Constants

| | |
|---|---|
| Wave labels | `wave:w1`, `wave:w2`, `wave:w3`, `wave:later`, `wave:held` — exactly one per open issue |
| Mode labels | `mode:afk`, `mode:hitl` — exactly one per open issue, set by the `todo` skill at filing. `mode:both` is retired and deleted (argus-config#595, #604): a stray one reads as no mode |
| Type labels | `type:bug`, `type:feat`, `type:docs`, `type:chore`, `type:refactor`, `type:test`, `type:ci`, `type:perf`, `type:build`, `type:security`, `type:revert` — exactly one per issue, set by the `todo` skill at filing; waived on `wayfinder:map`, grilling, research and prototype tickets, required on `wayfinder:task`. Not an ordering field: wave stays the only one. A missing one is a sweep warning |
| Scope | The 23 repos `hooks/backlog-labels.py repos` prints: non-archived, non-fork `deanjstone` repos minus certificate-generator, erto-apps and template-repo-with-claude, plus obsidian-cadence. Issues only, never PRs |
| Wave metadata | `waves.json` — per wave: `name`; plus `defaults.stale_later_days` (90) |
| Source of truth | the labels. Taxonomy and data moves: `hooks/backlog-labels.py` in argus-config |

Labels were added to every in-scope repo and backfilled from project board
`deanjstone/projects/2` on 2026-10-14 (argus-config#566). The board was closed at the cutover
(argus-config#574) and is never read or written; it keeps the closed-issue history.

Grouping inside a wave uses native sub-issues (the issue's parent).

`carryover-signal.sh` gates on the same native dependencies and reads the same labels, so the
SessionStart signal and this skill agree about what is blocked.

## Reading the backlog

Always go through the helper:

```bash
python3 ~/.claude/skills/backlog-waves/scripts/board.py <dump|open|next|drift|cut-next>
```

It reads every open in-scope issue through `hooks/backlog-labels.py rows` (one GraphQL issue
search, a few points a page) and emits short rows. Every mode is read-only; the only writes this
skill describes are the `assign` commands below, done by hand after approval.

For an ad-hoc look, GitHub's label search works too:
`gh search issues --owner deanjstone --state open --label wave:w1 --label mode:afk`.

---

## Mode: `next` (default)

```bash
python3 ~/.claude/skills/backlog-waves/scripts/board.py next
```

Takeable = the **Current** wave (lowest-numbered `W<n>` with an open issue, compared
numerically, so `W10` follows `W9`), minus anything with an open native blocker. `Later`
and `Held` never count as Current. Next, `Later` and `Held` are reported as
hidden counts only — that hiding is the method's point, not a limitation to work around.

Each takeable row ends `[mode: AFK|HITL|unset]`, from the issue's `mode:*` label. An
orchestrated session (the AFK backlog loop, or a T3 thread an orchestrator launched) reads it
as the `todo` skill defines it:

| Mode | Orchestrated session |
|---|---|
| `AFK` | Takes it. |
| `HITL` | Skips it unless the owner is present. |
| `unset` | Treat as `HITL`. No `mode:*` label, or more than one. |

Present the helper's output largely as-is. Two things to say in your own words:

- **If the wave is stalled** — open issues, none takeable — name the gating issues and say the
  wave cannot advance until they close.
- **Never quietly look past the Current wave.** If the user wants Next or `Later`, that is their
  decision to state; surface the hidden counts and let them ask.

Stop there. Do not offer to start work unless the user asks.

---

## Mode: `drift`

Reconciles the labels against reality and against ADR-011's rules.

```bash
python3 ~/.claude/skills/backlog-waves/scripts/board.py drift
```

| Class | Meaning |
|---|---|
| Open, no `wave:*` label | Missed intake. The daily label sweep sets `wave:w1` in argus-config and `wave:later` elsewhere. |
| Conflicting wave labels | More than one `wave:*` label. Readers take the least takeable until it is settled. Keep one. |
| No single `mode:*` label | Missing or doubled mode. Set one; never guess it. |
| Stale in `Later` | Open `Later` items not updated for 90+ days. Close as stale with a comment, or keep explicitly. |
| Held | Counted only. Not checked, not proposed. |

The helper reads every open issue in scope, so there is no separate "absent from the board"
check any more.

**Propose, then apply.** Present the discrepancies with a suggested placement for each, get
approval with `AskUserQuestion`, then apply via `assign`. Placing an issue is a sequencing
judgment; a wrong one hides real work.

---

## Mode: `cut-next`

Proposes a new Next wave and the `Later` prune. It makes no writes of any kind — it reads the
labels once and prints.

```bash
python3 ~/.claude/skills/backlog-waves/scripts/board.py cut-next
```

Run it when there is no Next wave: Current's last issue closed, so the old Next was promoted.
While a Next wave exists it says so and cuts nothing, since at most two waves are detailed.
The output has two steps:

1. **Cut a new Next** — the new wave's number and every non-stale `Later` candidate,
   oldest-updated first.
2. **Prune `Later`** — items untouched for 90+ days: close as stale with a comment, or keep.

Then, and only then:

1. Walk each step with the user via `AskUserQuestion` and collect explicit decisions.
2. Add the new Next wave to `waves.json` (name), on a branch + PR in argus-config. If it
   is `W4` or higher, add its label to `labels/labels.yml` (the `wave:` family), run
   `python3 scripts/compose_labels.py` and commit the generated files in the same PR; after
   promotion the owner runs `python3 hooks/backlog-labels.py sync --confirm`.
3. Apply the approved moves via `assign`; close pruned issues with a comment saying why.

---

## Mode: `inventory`

What is open, not what to do next. Read-only `gh` calls, no judgment beyond grouping. Run
them in a Haiku `Explore` subagent so raw `gh` JSON stays out of the main session, and show
its formatted answer as-is. Pick the sub-mode from the request: no repo or keyword is
**summary**, a named project is **repo drill-down**, a keyword is **search**, "urgent" is
summary with the urgent filter. Ambiguous means summary.

Repo registry (spoken name to repo):

| Project | Repo |
|---|---|
| argus / agent-cli / agent-engine / mcp-memory | `deanjstone/argus` |
| argus-config / claude config / skills | `deanjstone/argus-config` |
| atto1 / EV tracker | `deanjstone/atto1` |
| budget / budgetbuddy / Up Bank | `deanjstone/budget` |
| erto / AQF cert | `audaxworks/erto-apps` |
| homelab / dell | `deanjstone/homelab` |
| ios-scripts / scriptable | `deanjstone/scriptable-private` |
| myargus / stockade / knowledge / reader | `deanjstone/myargus` |
| sys-admin / sysadmin / dev stack | `deanjstone/sys-admin` |

`deanjstone/mcp-memory` and `deanjstone/ccbot` are archived and hold no open issues; they are
not iterated. The registry above is a convenience, and `board.py dump` covers the full
in-scope set.

**Summary** (one `gh` call per repo, then urgent items):

```bash
for repo in deanjstone/argus deanjstone/argus-config deanjstone/atto1 deanjstone/budget audaxworks/erto-apps deanjstone/homelab deanjstone/scriptable-private deanjstone/myargus deanjstone/sys-admin; do
  count=$(gh issue list --repo "$repo" --state open --json number -q 'length' 2>/dev/null)
  [ "${count:-0}" -gt 0 ] && echo "$count $repo"
done | sort -rn
gh search issues --owner deanjstone --state open "\[!\]" \
  --json repository,number,title \
  -q '.[] | "\(.repository.name)/\(.number) \(.title)"' 2>/dev/null
```

Present as open counts per repo, then the urgent `[!]` items.

**Repo drill-down:**

```bash
gh issue list --repo "$TARGET_REPO" --state open --limit 100 \
  --json number,title,createdAt -q '.[] | "#\(.number)  \(.title)"'
```

Group by theme above 10 issues, list flat at 10 or fewer, and end with
`https://github.com/$TARGET_REPO/issues`.

**Search:**

```bash
gh search issues --owner deanjstone --state open "<keyword>" \
  --json repository,number,title -q '.[] | "\(.repository.name)/\(.number)  \(.title)"'
```

Group by repo and show the repo URL per group.

Rules: always show issue numbers (the handle for follow-up); never invent counts or titles;
skip a repo that errors (archived, private, no access) silently; `~/agent-cli/docs/TODO.md`
is a cross-cutting scratchpad and never appears in a backlog view.

---

## Mode: `assign`

Set the wave on one or more issues: add the new `wave:*` label and remove the old one in the
same call, so the issue never carries two.

```bash
gh issue edit <n> -R deanjstone/<repo> --add-label wave:w2 --remove-label wave:later
```

That is the whole write: labels are the only record of the wave.

---

## Out of scope

- **Resolving a decision issue.** Issues in a wave that decide whether other work exists at all
  are human decisions worked through `/wayfinder`; any mass close that follows is deliberate,
  not done by this skill.
- **Claiming, dispatching, or implementing.** See the opening note.
- **Changing the method.** The rules above come from ADR-011. Changing them is a new ADR, not
  an edit here.
