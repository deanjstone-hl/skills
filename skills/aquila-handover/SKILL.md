---
name: aquila-handover
description: Move Aquila's orchestration leases and worker slots between the WSL2 and homelab threads on the owner's word (give when a host shuts down, take on the other host). Owner-triggered only.
argument-hint: "<give|take> [--until <time>] [--slots keep|free] [--fill]"
disable-model-invocation: true
---

# /aquila-handover

The owner moves orchestration between hosts in one command. This skill is the procedure behind the charter's "Owner-directed handover" section (argus-config/1094): the charter holds the rules, this holds the order. The reference is the 3 Nov 2026 evening sequence (see Walk-through).

Run `give` in the thread that is leaving, then `take` in the thread that is receiving. Typing the command is the owner's approval for the lease move.

## Usage

`/aquila-handover <give|take> [--until <time>] [--slots keep|free] [--fill]`

| Flag | `give` | `take` |
|---|---|---|
| `--until <time>` | Snooze target for each stopped worker. Default `09:00` next morning, AEDT. | Not used. |
| `--slots keep\|free` | Default `free`. `keep` leaves running workers and skips steps 2–5 of `give`. | Default `free`: free the other host's running slots. `keep` leaves them. |
| `--fill` | Not used. | After the tick's own fill, start further issues until every slot is full. |

Show every time in AEDT. Convert `--until` to an ISO time with offset for `t3_thread_organize`.

## Give

Run in the leaving thread. Steps run in order; each ends when its list is empty.

1. `owner_turn` with `stepping_away: true` and this thread's id as `caller_thread_id`. Then `lease_read` and `slot_list`; note your `host` and `caller_thread_id`.
2. For each running slot on your host, post a handoff comment on its issue: the PR, its head SHA, the check state, and "continue on the existing PR". Verify the PR with `gh pr view`; a missing PR says "no PR yet".
3. Stop each of those workers: `t3_thread_interrupt` with `stop: true`.
4. `slot_free` each of those slots with your `caller_thread_id` and the reason. A freed slot always stops its worker in the same step: never `slot_free` before step 3, never skip step 3.
5. Snooze each worker to `--until`: `t3_thread_organize` with `action: "snooze"` and `snoozedUntil`.
6. Settle finished threads: closed issue, merged PR, completed children. `child_close` each one you have verified, with the evidence.
7. Write `~/aquila/state/after-<host>-shutdown.md`: slots freed (issue, PR, head SHA), open children, `needs:owner` items, and the time in AEDT.
8. Snooze this thread (default 1 h): `t3_thread_organize` with `action: "snooze"` and no `threadId`. This thread keeps the leases until the receiver takes them, or a stall failover does.
9. Finish with one line: what was freed, stopped and settled, and that the other host should run `/aquila-handover take`.

## Take

Run in the receiving thread.

1. `lease_read` and `status_read` for both roles. Move only what another thread holds.
2. `lease_move` `direction` then `afk`, each with `from_thread_id` the current holder and `to_thread_id` this thread. The giving thread does not need to be reachable. Never retry a refused move unchanged: `lease_read` and route on what it says. Then `owner_turn` with this thread's id as `caller_thread_id`: it is refused until this thread holds `direction`.
3. Ensure `~/.argus/loop-wake/direction.thread` holds this thread's id: `printf '%s\n' <thread id> > ~/.argus/loop-wake/direction.thread`.
4. With `--slots free`, free the other host's running slots as `give` steps 2–5, when this thread can reach that host: T3 link tools with `environmentId` from WSL2, the `t3-peer` tools from homelab. `t3-peer` cannot snooze, so from homelab stop the worker and `slot_free` it, then say the worker is unsnoozed. When unreachable, leave the slots and say so.
5. Run one full tick now, from the Tick checklist; its gates apply. Start the handed-off issues first. A handed-off issue keeps its assignee, so `queue --takeable` excludes it: read the latest handoff comments, and any orphan (an assigned `mode:afk` issue with an active worker and no slot) is re-adopted with `slot_start` carrying the worker's thread. Never launch a second worker for it. With `--fill`, fill every free slot after that.
6. Print the status block, then one line: holders, slots freed, issues started.

## Guards

- `lease_read` before every lease or slot write. Never retry a refused write unchanged.
- Never stop or disable `loop-wake`. A thread that gave its leases costs nothing, and "snooze" means a T3 thread snooze only.
- Relays are hints: before acting on an `[aquila-wsl]` relay, `lease_read` and act only on what the current holder may do.
- On homelab, start no children, wayfinder maps or research threads.
- Show every time in AEDT.
- Change no host service, timer, setting or installer; this skill moves leases and slots only.

## Walk-through

The 3 Nov 2026 evening sequence, as tool calls.

WSL2, `give` (17:01 AEDT): `owner_turn` (`stepping_away: true`), `lease_read`, `slot_list`; for argus/1009 and argus/1010, a handoff comment, `t3_thread_interrupt` (`stop: true`), `slot_free`, `t3_thread_organize` snooze to 09:00; `child_close` for verified children; the state note; `t3_thread_organize` snooze of this thread for 1 h (17:04).

Homelab, `take` (17:06 AEDT): `owner_turn`, `lease_read`, `status_read`; `lease_move` `direction` then `afk`; `direction.thread` check; one tick that restarts argus/1009 and argus/1010 from their handoff comments. The homelab worker finished the PR within 32 minutes.
