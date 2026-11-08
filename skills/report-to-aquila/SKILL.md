---
name: report-to-aquila
description: Close out a thread that reports to the orchestrator (a slot worker, approval thread or research child). Verifies its claims, posts the Resolution, reports, and stops on a Ready to settle line. Run it last.
---

# /report-to-aquila

Run this as the last act of a thread that reports to the orchestrator (Aquila). It leaves the orchestrator one thing to do on its next tick: verify and settle. Read the thread's own claims as unproven until step 1 passes.

Work through the steps in order. Show every time in AEDT.

## 1. Verify

Check your own claims before you make them.

- Run `bash ~/.claude/hooks/verify-claim.sh <kind> <target>` for each claim you will make: `merged` (`<url|owner/repo#N>`), `closed` (`<owner/repo#N>`), `pushed` (`<owner/repo>@<sha>`, a trunk repo with no PR) and `tests` (`<local-repo-path> <sha>`). A non-zero exit fails the claim.
- Check main CI on the merge SHA is done and green (`gh run list --branch main --commit <sha>`). Where main skips the merge push by design, check the merge tree equals the PR-tested head tree instead.
- Any check fails → the outcome is `failed`, not `complete`. Say which check and quote its output. A question for the owner → `needs_owner`.

## 2. Brief

Write the `session-brief` recap (see that skill for the format): project and branch, what changed, commits and PRs (full URLs), deploys, open items. 20 lines or fewer; skip an empty section.

## 3. Record

Post the recap on the issue as the Resolution (`gh issue comment --body-file`, written from a quoted heredoc and read back).

- End it with `Verified: <verify-claim results, CI run or tree check, PR state>`.
- Write each owner step as literal commands with their effect, never a description.
- Name the issue `<repo>/<N>` and PRs by full URL, and show every time in AEDT.

A thread with no issue records the same brief in its final message and says so.

## 4. Hygiene

Confirm each, and fix or list anything that fails:

- `pendingRequestCount` is 0 (`t3_thread_read` on this thread, `limit: 1, runLimit: 1, maxCharsPerItem: 1`). A pending prompt means you are blocked, not done.
- No background job or Monitor is running.
- No live PR watch: `unwatch_pull_request` and `unlink_pull_request` for each PR you watched.
- No dev server or browser page left running.
- List any worktree this thread created, with its path, for cleanup. Never remove your own.

## 5. Report

- **A slot worker:** call `slot_report` (`complete`, `needs_owner` or `failed`, with a one-line note and the PR URL). After it returns, send exactly one `t3_thread_send` to the orchestrator thread with message `[afk-nudge] <issue> <outcome>`, `mode: "queue"` and a `clientRequestId`.
- **Any other thread** (approval thread, research child): send exactly one `t3_thread_send` to the orchestrator thread with message `[aquila-nudge] <threadId> <complete|needs_owner|failed>`, `mode: "queue"` and a `clientRequestId`. The issue is the record.

The orchestrator thread id is in your launch prompt. Without one, report in the final message and send no nudge.

## 6. Stop

End the turn with exactly one last line:

`Ready to settle: <issue> <outcome>`

Never settle itself: no `t3_thread_organize`, no `child_close`, no `slot_close`. The orchestrator verifies the close and settles the thread.
