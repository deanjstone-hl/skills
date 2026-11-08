---
name: session-brief
description: On-demand recap of the current session — project, branch, what was done, commits, deployments, open items. Works in headless/non-interactive mode, unlike the built-in /recap which is always skipped there.
argument-hint: (optional) a specific area to focus the recap on
user_invocable: true
---

Give a concise recap of the current session, using the conversation history directly (do not re-derive from git timestamps or heuristics — you already have the full turn history in context).

Include, in this order:

1. **Project**: repo name and current branch (run `git rev-parse --show-toplevel` and `git branch --show-current`; if not a git repo, use the working directory name)
2. **What was done**: bullet list of completed actions this session, max one line each, plain language — no file paths or jargon unless unavoidable
3. **Commits**: any commits made this session (short hash + message) — run `git log --oneline` scoped to this session's timeframe if unsure
4. **Deployed**: any deployments made this session (service name + URL), only if applicable
5. **Open items**: anything unfinished, blocked, or flagged for follow-up

Rules:
- Keep the entire recap under 20 lines total
- Skip any section with nothing to report — do not print empty headers
- If the user passed an argument, treat it as the area to focus the recap on and omit unrelated sections
- This is a summary for the user to scan, not a handoff document for another agent — if a full handoff is needed instead, suggest the `handoff` skill
