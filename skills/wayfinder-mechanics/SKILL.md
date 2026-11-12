---
name: wayfinder-mechanics
description: >
  Read-only reference for how a wayfinder map is charted and kept on GitHub: map sections,
  ticket types and labels, sub-issues, blocked-by gating, Decisions-so-far, intake,
  closeout. Use for how-to questions: "how do I chart a wayfinder map", "wire these as
  sub-issues", "what labels does a wayfinder ticket need", "how do I mark this ticket
  blocked", "why did sub_issue_id 422".
---

# Wayfinder mechanics

**This skill documents. It does not execute.** It tells you how a map is structured
and wired, then stops. It never creates, labels, assigns, wires, comments on or closes
an issue, and never touches the backlog labels. That work belongs to `/wayfinder`, which the user or an
agent invokes. This skill stays read-only so it can answer questions without acting.

Every command that writes is quoted only inside a fenced block tagged `reference`.
Those blocks are there so you can check what `/wayfinder` will run, or so the user can
copy them. They are not steps for you to run from this skill. If this skill ever gains
an action, fold it into `/wayfinder` instead.

`envs/wsl2/skills/wayfinder/SKILL.md` is the method: why a map exists, the fog of war,
and the one-ticket-per-session rule. This page holds the mechanics people keep
re-deriving. The two should agree. Where they don't, the wayfinder skill wins, so fix
this page.

## Where each fact comes from

| Tag | Source |
|---|---|
| [WF] | `envs/wsl2/skills/wayfinder/SKILL.md` |
| [GH-TRK] | `envs/wsl2/skills/setup-matt-pocock-skills/issue-tracker-github.md`, "Wayfinding operations" |
| [DOCS-SUB] | GitHub REST docs, [sub-issues](https://docs.github.com/en/rest/issues/sub-issues), checked 2026-10-08 |
| [DOCS-DEP] | GitHub REST docs, [issue dependencies](https://docs.github.com/en/rest/issues/issue-dependencies), checked 2026-10-08 |
| [MAP-366] | A real map, read through REST on 2026-10-08: [Map: Single harness-neutral AGENTS.md via compose + slim](https://github.com/deanjstone/argus-config/issues/366) and its nine children |
| [GH-CLI] | `--help` output of gh's `issue create` and `issue edit` subcommands, gh 2.101.0 |
| [MEM:…] | A `~/CONTEXT/MEMORY/` entry, named in full |

## 1. The map issue

The map is a single issue labelled `wayfinder:map`. It is the canonical artifact [WF].
It is an **index, not a store**: each decision lives in its ticket, and the map gives a
gist and a link [WF]. Open tickets are **not** listed in the body. They are found by
querying the map's open sub-issues [WF].

The body has these five sections, in this order [WF]. [MAP-366] uses exactly these
`##` headings:

| Section | What goes in it |
|---|---|
| `## Destination` | One or two lines saying what reaching the end looks like: a spec, a decision, or a change made in place. Name it first, because it fixes the scope. |
| `## Notes` | The domain, the skills every session should consult, and standing preferences. An override of "plan, don't do" also goes here. |
| `## Decisions so far` | One line per **closed** ticket: `- [<ticket title>](<url>): <one-line gist>`. Empty at charting. |
| `## Not yet specified` | In-scope fog you can't phrase sharply enough to ticket yet. A patch leaves this section when it becomes a ticket. |
| `## Out of scope` | Work ruled beyond the destination. Give each entry one line: the gist, why, and a link to the closed ticket. It never graduates into a ticket. |

**Fog or ticket?** Make a ticket when you can state the question precisely now, even if
it's blocked. Leave it in **Not yet specified** when you can't phrase it yet [WF].

## 2. Tickets: types and labels

Each ticket is a child issue of the map, sized to one ~100K-token session. Its body is
a single `## Question` section [WF]. Real tickets follow this; see [MAP-366] → #369.

| Label | Mode | Use when |
|---|---|---|
| `wayfinder:grilling` | HITL | An open decision. This is the default. Resolve it with the `grilling` and `domain-modeling` skills. |
| `wayfinder:research` | AFK | A decision is waiting on a fact from outside the working directory. Resolve it with a subagent that calls the `research` skill. |
| `wayfinder:prototype` | HITL | The question is "how should it look or behave?" Make a cheap artifact to react to, using the `prototype` skill. |
| `wayfinder:task` | HITL or AFK | Manual work must happen before a decision can be made. It earns its place by unblocking a decision, not by delivering the destination. |

Sources: [WF], "Ticket Types". [MAP-366] mixes `research` and `grilling` children.

Derive each child's type from the question it actually asks, not from a blanket
instruction in the map body. If you can't state the deliverable, the ticket is a
decision [MEM:methodology_wayfinder_ticket_types, update 2026-09-13].

A ticket is **claimed** by assigning it to the dev driving the map. That is the first
write, made before any work. An open ticket with no assignee is unclaimed [WF, GH-TRK].

## 3. Per-repo label check

The `wayfinder:*` labels are defined per repo and are not guaranteed to exist [WF].
Before applying any of them for the first time in a repo, read the label list:

```bash
gh label list -R <owner>/<repo> --search wayfinder --json name,color,description
```

The full set is `wayfinder:map`, `wayfinder:grilling`, `wayfinder:research`,
`wayfinder:prototype` and `wayfinder:task`. Copy the colours and descriptions from a
repo that already has them. In argus-config on 2026-10-08:

| Label | Colour | Description |
|---|---|---|
| `wayfinder:map` | `5319E7` | Wayfinder map issue |
| `wayfinder:grilling` | `1D76DB` | Wayfinder grilling ticket |
| `wayfinder:research` | `0E8A16` | Wayfinder research ticket |
| `wayfinder:prototype` | `FBCA04` | Wayfinder prototype ticket |
| `wayfinder:task` | `D93F0B` | Wayfinder task ticket |

`/wayfinder` creates a missing label like this:

```bash reference
gh label create "wayfinder:grilling" -R <owner>/<repo> --color 1D76DB --description "Wayfinder grilling ticket"
```

## 4. Wiring: sub-issues for map → ticket

A ticket is a **native GitHub sub-issue** of the map [WF, GH-TRK]. A `#N` mention in
prose is not a link. The native list is what renders the map's scope in GitHub's UI.
Tickets spawned while resolving another ticket get wired straight away, in the same
action [MEM:pattern_wayfinder_subissue_wiring_gap].

Facts the API docs state [DOCS-SUB]:

- `POST /repos/{owner}/{repo}/issues/{issue_number}/sub_issues`, where
  `{issue_number}` is the map.
- `sub_issue_id` is an **integer** and required. It is the child's **database `id`**:
  `gh api repos/<o>/<r>/issues/<n> --jq .id`. It is not the `#number` and not the
  `node_id`.
- "The sub-issue must belong to the same repository owner as the parent issue." So
  cross-repo works only under the same owner.
- `replace_parent` (boolean) moves a child that already has a parent.

**The integer gotcha.** `-f sub_issue_id=$ID` sends a string, and the API answers 422
`is not of type integer`. `-F` coerced correctly here 6/6 times, but the same `-F` form
returned 404 on the dependency endpoint (§5). The one form seen to work on **both**
endpoints is a JSON body read from stdin by `gh api --input`
[MEM:fact_gh_api_subissue_dependency_integer_type, amended 2026-09-13]. Real ids are
around 5.6 billion, larger than a 32-bit integer (#366 is `5640260823`) [MAP-366].

```bash reference
CHILD_ID=$(gh api repos/<o>/<r>/issues/<child> --jq .id)
echo "{\"sub_issue_id\":$CHILD_ID}" | gh api -X POST repos/<o>/<r>/issues/<map>/sub_issues --input -
```

gh 2.101.0 can also link at creation with `--parent <number|url>` on create, and
afterwards with `--parent` on edit [GH-CLI]. A homelab charting run confirmed the
create-time flag [MEM:fact_github_gotchas, the `--parent` entry]. The REST form
above is still the one to use for linking an issue that already exists across repos.

```bash reference
gh issue create -R <o>/<r> --title "<question as a title>" --label wayfinder:grilling --parent <map-number> --body-file <file>
```

## 5. Gates: native blocked-by dependencies

Blocking uses GitHub's **native issue dependencies**, never a `blocked_by: #N` body
line [WF, GH-TRK]. The native form works **across repos**. A bare `#N` in a body always
resolves against the issue's own repo, so the body convention cannot express a
cross-repo gate [MEM:fact_github_native_issue_dependencies]. Native gates also render
as a banner in GitHub's own UI.

Facts the API docs state [DOCS-DEP]:

- `POST /repos/{owner}/{repo}/issues/{issue_number}/dependencies/blocked_by`, where
  `{issue_number}` is the **blocked** ticket.
- `issue_id` is an **integer** and required: "The id of the issue that blocks the
  current issue". It is the blocker's database `id`.
- `GET …/dependencies/blocked_by` and `GET …/dependencies/blocking` read the edges.
  `DELETE …/dependencies/blocked_by/{issue_id}` removes one.

Wire edges in a **second pass**, once every ticket exists, because issues need ids
before they can reference each other [WF].

```bash reference
BLOCKER_ID=$(gh api repos/<o>/<r>/issues/<blocker> --jq .id)
echo "{\"issue_id\":$BLOCKER_ID}" | gh api -X POST repos/<o>/<r>/issues/<blocked>/dependencies/blocked_by --input -
```

`-F issue_id=` is what [GH-TRK] shows. It returned 404 twice in a row on this endpoint
while the JSON body succeeded on the same ids
[MEM:fact_gh_api_subissue_dependency_integer_type]. Use the JSON body. gh 2.101.0 also
lists an edit flag that adds a blocked-by relation by number or URL [GH-CLI]. It is not
yet confirmed in practice here, so prefer the REST form.

**Reading the gate.** An issue's `issue_dependencies_summary` has `blocked_by`, which
counts **open** blockers only, and `total_blocked_by`, which counts all of them. On
[MAP-366], #369 shows `blocked_by: 0, total_blocked_by: 2` because both blockers are
closed. A closed blocker still appears in the `GET` list, so the test is whether every
blocker is closed, not whether the list is empty. The SessionStart frontier count in
`hooks/carryover-signal.sh` (`is_blocked`) treats an issue as blocked if **either** the
native edge or the body line says so.

## 6. Reading a map

All of these are read-only REST calls. Running them is in scope for this skill.

```bash
# the map: labels, progress, and its own gate summary
gh api repos/<o>/<r>/issues/<map> \
  --jq '{labels:[.labels[].name], sub_issues_summary, issue_dependencies_summary}'

# its children: state, type label, open/total blockers, assignee (= claim)
gh api repos/<o>/<r>/issues/<map>/sub_issues --paginate \
  --jq '.[] | "\(.number) \(.state) \([.labels[].name]|join(",")) blocked=\(.issue_dependencies_summary.blocked_by)/\(.issue_dependencies_summary.total_blocked_by) assignee=\(.assignee.login // "-") \(.title)"'

# one ticket's blockers, cross-repo aware
gh api repos/<o>/<r>/issues/<n>/dependencies/blocked_by \
  --jq '.[] | "\(.repository.full_name)#\(.number) \(.state)"'

# confirm a child's parent after wiring; don't trust the POST's exit status
gh api repos/<o>/<r>/issues/<n> --jq .parent_issue_url

# find maps across the account (REST search)
gh api 'search/issues?q=user:<owner>+label:"wayfinder:map"+state:open' \
  --jq '.items[] | "\(.repository_url|split("/")[-1])#\(.number) \(.title)"'
```

**The frontier** is the open children with no open blocker and no assignee. The first
one in map order wins [WF, GH-TRK].

**Wiring audit.** Compare the numbers from `…/sub_issues` against every issue number
mentioned in the map body. A number that appears only in prose is a wiring gap
[MEM:pattern_wayfinder_subissue_wiring_gap].

## 7. Backlog intake

Every new map **and** every child ticket is labelled at creation with the filing wave (your choice of `wave:w1`, `wave:w2` or
`wave:later`, with a one-line reason in the body: the map, blocker or incident it serves; with no reason to choose the default
stands, `wave:later`, or `wave:w1` in `deanjstone/argus-config`, argus-config#716, and the orchestrator validates the choice on its tick, argus-config#1197) plus
exactly one `mode:*` label (`mode:afk` or `mode:hitl`) matching its `Mode:`
line, plus exactly one `type:*` label on every `wayfinder:task` (the commit type of the build:
`type:feat`, `type:bug`, `type:docs`, `type:chore` and the rest; argus-config#1294). `type:` is
waived on `wayfinder:map`, `wayfinder:grilling`, `wayfinder:research` and `wayfinder:prototype`
tickets, which have no change type. Until every filing path sets it, a missing `type:` on a task
is a sweep warning. That rule comes from the global `TODO Convention` → *Backlog triage*: the backlog's wave
and mode live in labels on issues (argus-config#566). Child tickets belong in the backlog too.
Their absence has been drift, not convention
[MEM:preference_board_tracks_all_repos, correction (c) 2026-08-17]. `/todo` does this in one
step. `/wayfinder`'s own ticket creation does not, which is how map argus#242 and its children
never reached the backlog [same memory, 2026-08-14].

A map is identified by `wayfinder:map`; there is no separate category. The daily label sweep
gives any open issue with no wave label its filing wave (`wave:w1` in argus-config, `wave:later` elsewhere), but it never guesses a mode, so set the
mode at creation.

`mode:both` is retired and deleted (argus-config#595, #604). A ticket whose agent work has one owner checkpoint
is two tickets: an AFK ticket for the work, and a HITL ticket for the checkpoint, gated on the
AFK one with a native blocked-by edge (§5). Both are sub-issues of the map.

**A cleared map turns AFK** (owner, 8 Nov 2026 18:05 AEDT). When a map has no fog (its `## Not yet specified`
section is empty) and its dev spec has been generated (`/to-spec`), swap the map to `mode:afk`: the label
and the `Mode:` line together, whatever mode it was filed with. Link the spec from the map body.

```bash reference
gh issue edit <n> -R deanjstone/<repo> --add-label wave:later --add-label mode:afk   # your chosen wave; default wave:w1 in argus-config
# a wayfinder:task also gets one type: label, e.g. --add-label type:feat
```

## 8. Resolving a ticket and keeping the map readable

Each resolution makes three writes, in this order [WF, GH-TRK]:

1. A **Resolution comment** on the ticket. [MAP-366]'s children open with
   `**Resolution**`. `## Resolution` is the other form in use
   [MEM:methodology_wayfinder_ticket_types].
2. **Close** the ticket.
3. **Append one line** to the map's `## Decisions so far`:
   `- [<ticket title>](<url>): <gist>`. This is the step most often skipped. It is
   what makes a map readable months later. [MAP-366]'s Decisions so far has nine such
   lines, one per closed child.

Post the comment and close as **separate** calls. A combined close-with-comment exits 0
but drops the comment when the issue is already closed (a merged PR's `Closes #N` gets
there first) or when GraphQL returns a 504. Afterwards, read back
`"\(.state) comments=\(.comments)"` [MEM:fact_gh_issue_close_comment_dropped_when_closed].

```bash reference
gh issue comment <n> -R <o>/<r> --body-file resolution.md
gh issue close <n> -R <o>/<r>
gh issue edit <map> -R <o>/<r> --body-file map-body.md   # Decisions-so-far appended
```

When a resolution admits unfinished work ("requires X which isn't available here"),
file a follow-up and wire it before closing. Otherwise the work goes invisible
[MEM:pattern_wayfinder_task_map_orphan_check].

## 9. Refer by name, not bare id

In everything a human reads — narration, the Decisions-so-far list, the map's own
closing comment — refer to a map or ticket by its **title**, with the link inside the
name. `#42, #43, #44` is illegible [WF, "Refer by name"]. Ids still ride inside the
link. They just never stand in for the name.

## 10. Plan, don't do — and closeout

- **Default:** each ticket resolves a decision. The map is done when nothing is left
  to decide. When you feel the pull to just build, you have usually reached the edge
  of the map [WF].
- **Override:** an effort may carry execution into the map by saying so in its
  `## Notes` [WF]. A `wayfinder:task` map, where every child is a build ticket, is the
  form the TODO convention prescribes for clear-scope work longer than a session.
- **Map closeout:** once the way is clear, write a Resolution comment on the map
  itself, then hand off to `/to-spec`, not `/implement`. `/to-spec` collapses the
  linked decisions into a buildable spec. Skip that collapse only when the effort
  turned out small [WF]. [MAP-366]'s closing comment shows this: it states the way is
  clear and names the follow-on map by title.
- **Concurrency:** other sessions may be working unblocked tickets of the same map at
  the same time. Re-read the map body immediately before rewriting it [WF].

## 11. The plans mirror

Every map is mirrored to `myargus.cc/plans/wayfinder-<repo>-<map#>` [WF, "Mirror to plans"], argus-config#884. It is a **read-only view**: GitHub stays canonical, and ticking a step on the plan page comments on nothing and closes nothing.

`wayfinder/scripts/mirror-map.sh <owner/repo> <map#>` does it. It reads the map and its sub-issues (§6), builds the plan, and hands it to the `impl-plan` skill's `publish.sh` (agent-engine `POST /plans`).

| Map element | Plan step |
|---|---|
| `## Destination` | pre-done step "Destination" |
| open, assigned (claimed) | checkable step, `Claimed` |
| open, unassigned, no open blocker (frontier) | checkable step, `Frontier` |
| open with an open blocker | checkable step, `Blocked` |
| closed ticket | pre-done step; note is the `## Decisions so far` gist, else the close date |

Facts that shape it:

- **Slug.** `wayfinder-<repo>-<map#>`, the repo folded to `a-z0-9` and hyphens. The same slug republishes in place and keeps ticked steps.
- **Sanitiser.** The plans page keeps only a small HTML set and no images or embeds [MEM:fact_myargus_plans_page_limits], so step content is `<p>`, `<strong>` and `<a>`, with titles escaped.
- **Blocked** counts open blockers only (§5): a ticket whose blockers are all closed is frontier.
- **Fallback.** The script prints publish.sh's one line. `fallback <reason>: <detail>` (`no-token`, `unreachable`, `unauthorized`, ...) exits 0, so the closeout reports it and continues.
- **Republish points.** After charting, and after each ticket's closeout (§8).

## Out of scope

- **Doing any of it.** Charting, claiming, wiring, resolving and closing are
  `/wayfinder` (invoked by the user or an agent) or `/todo`. This skill stops at telling you how.
- **Board ordering.** Which wave something belongs in is `backlog-waves`.
- **The method's rules.** Change those in `wayfinder/SKILL.md`, then bring this page
  back into line.
