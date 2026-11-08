---
name: t3-thread
title: T3 Thread
description: >
  Start a new T3 Code thread in a project with a first-turn prompt, typically to hand off
  a GitHub issue. Use for "trigger a T3 thread in homelab to pick up #117", "start a T3
  thread for this issue", "hand this off to T3", "/t3-thread". Targets this environment's
  T3 server unless another is named.
---

# T3 Thread

T3 Code runs on homelab as a user service and on WSL2 as the desktop app's backend. Its
CLI has no "start a thread" command, so
`envs/homelab/scripts/t3-open-thread.sh` talks to the server the way its web client does,
on orchestration protocol 2: mint a 5-minute admin session, read the shell snapshot from
`/api/orchestration/shell`, call the `orchestration.launchThread` RPC over the `/ws`
WebSocket (one command creates the thread and starts its first turn), and revoke the
session. The token only ever sits in a mode-600 temp file.

The new thread runs in **full-access** mode with no one watching. Whatever it must obey
(git procedure, what not to touch, when to stop and ask) has to be in the prompt. So does any context from this session the work depends on.

## Where to run it

**Default: the environment the skill is triggered from.** The thread lands in that
machine's T3, against that machine's checkout. Only target another machine when the owner
names it.

- **Locally (WSL2 or homelab):** `~/repos/argus-config/envs/homelab/scripts/t3-open-thread.sh`.
  The script finds the local server either way: homelab's service install records its
  binary in `~/.t3/runtime/service-state.json`, and the WSL2 desktop backend has no service
  state, so the script uses the executable of the server pid in
  `~/.t3/userdata/server-runtime.json`.
- **Owner named the other T3 environment, from inside a T3 thread:** use the `t3-peer`
  MCP tools instead (`peer_thread_launch`, plus `peer_thread_list`/`read`/`send`/`interrupt`
  to follow it up). They reach the other machine's T3 over ssh, and they set the project and
  worktree the same way. See argus `apps/t3-peer-mcp/README.md`.
- **Owner named homelab from elsewhere, without the peer tools:** run the same path over
  `ssh homelab`, and pipe the prompt to stdin (`--prompt-file -`).
- **Windows:** no bash runner. Ask the owner which machine's T3 to use.

In the commands below, `T3_HOME` is `~/.t3` on the target machine. Project roots are that
machine's paths (`/home/deanj/repos/<repo>` on WSL2, `/home/srvr/repos/<repo>` on homelab).

## Steps

### 1. Resolve the project

The target is the T3 project whose workspace root is the repo checkout on the target
machine. Confirm it is registered and live (read-only query):

```bash
python3 - <<'PY'
import os, sqlite3
c = sqlite3.connect("file:" + os.path.expanduser("~/.t3/userdata/statev2.sqlite") + "?mode=ro", uri=True)
for r in c.execute("select title, workspace_root from projection_projects where deleted_at is null order by title"):
    print(*r, sep="\t")
PY
```

Not listed? Ask the owner before adding it. Adding changes T3's live state:
`"$T3" project add <path>`, with `$T3` resolved as in step 5.

### 2. Title and dedup prefix

- **Picking up an issue:** use the title `<repo>#<N> — <short summary>` and
  `--dedup-prefix "<repo>#<N>"`. That allows one live thread per issue: a second run
  reports the existing one instead of creating a duplicate. Archiving or settling the
  thread in T3 frees the prefix (T3 also auto-settles idle threads).
- **Anything else:** use a short, descriptive title. Add a dedup prefix only if repeat runs
  are possible.

### 3. Write the prompt

For an issue pickup, start from this and adapt it. Read the issue first so the summary is
accurate:

```
Pick up deanjstone/<repo>#<N> (wave:<w>): <one-sentence problem statement>.

Read the issue in full first (`gh issue view <N>`). Follow the global git procedure: fetch,
branch (`fix/`, `feat/`, `chore/` or another conventional prefix), conventional commits, commit+push per logical step, PR with test evidence, squash-merge
when CI is green. <Task-specific guardrails, e.g. "audit each installer for idempotency
before wiring it in; document exclusions with the reason">. Assign yourself when you start
(`gh issue edit <N> -R deanjstone/<repo> --add-assignee @me`: open and assigned reads as in
progress). Close the issue with a Resolution comment. If a design choice
in the issue's open questions needs me, ask via AskUserQuestion rather than guessing.
```

Never put secrets, tokens or `.env` contents in a prompt. They persist in T3's database.

### 4. Open the thread

```bash
~/repos/argus-config/envs/homelab/scripts/t3-open-thread.sh \
  --project <workspace-root> \
  --title "<repo>#<N> — <summary>" \
  --dedup-prefix "<repo>#<N>" \
  --prompt-file - <<'EOF'
<prompt>
EOF
```

Optional flags:

- `--model '<json>'` overrides the model. The default copies the most recently used
  thread's `modelSelection`.
- `--label` names the temporary session.
- `--worktree-branch <branch> --base-ref <ref> [--from-origin]` launches the thread into
  a new worktree on `<branch>`, cut from `<ref>`, instead of the project's main checkout
  (the default). Use it when several threads in the same project run in parallel, so they
  don't share one checkout. `--from-origin` starts from `origin/<ref>` after a fetch;
  without it the local `<ref>` is used, local commits included. Give both
  `--worktree-branch` and `--base-ref`, or neither: a half-specified set exits 64 before
  anything is created. Needs `jq` on the target machine.

| Exit | Meaning | Do |
| --- | --- | --- |
| 0 | stdout `created<TAB><title><TAB><thread-id>` | Verify (step 5) |
| 10 | stdout `open<TAB><title>`: a live thread with that prefix exists | Tell the owner. Don't create another |
| 1 | stderr reason, nothing created | Report the reason (server down, project missing, …) |
| 2 | stderr `T3 rejected the thread (<reason>)` | The launch was sent, so the thread may have landed. Check step 5, and tell the owner |
| 64 | usage or empty prompt | Fix the call |

### 5. Verify: don't trust exit 0

Check that the thread exists and its first run is running, and that the session was revoked:

```bash
python3 - <thread-id> <<'PY'
import os, sqlite3, sys
c = sqlite3.connect("file:" + os.path.expanduser("~/.t3/userdata/statev2.sqlite") + "?mode=ro", uri=True)
t = c.execute("select title, archived_at from orchestration_v2_projection_threads where thread_id=?", (sys.argv[1],)).fetchone()
runs = c.execute("select status from orchestration_v2_projection_runs where thread_id=?", (sys.argv[1],)).fetchall()
print("thread:", t, "runs:", runs)
PY
# service install (homelab) records its version; the desktop backend (WSL2) does not
if [ -f ~/.t3/runtime/service-state.json ]; then
  T3="$HOME/.t3/runtime/versions/$(python3 -c 'import json,os;print(json.load(open(os.path.expanduser("~/.t3/runtime/service-state.json")))["activeVersion"])')/t3"
else
  T3=$(readlink "/proc/$(python3 -c 'import json,os;print(json.load(open(os.path.expanduser("~/.t3/userdata/server-runtime.json")))["pid"])')/exe")
fi
"$T3" auth session list | grep -c "<label>"   # expect 0; the default label is t3-open-thread
```

A run in status `running` (or `completed`) means the agent picked it up.

### 6. Report

Tell the owner the thread title, machine, project, model, and run status. Also say what the prompt
told it to do, in one line.
