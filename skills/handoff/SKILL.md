---
name: handoff
description: >
  Write a handoff document to the OS temp dir for a later agent to pick up, or hand the work
  straight to a new T3 thread. Use for "hand this off", "write a handoff", "continue this in
  a new thread".
argument-hint: "What will the next session be used for?"
disable-model-invocation: true
---

Write a handoff document summarising the current conversation so a fresh agent can continue the work. Save to the temporary directory of the user's OS (`$TMPDIR`, else `/tmp`; `%TEMP%` on Windows) - not the current workspace.

Include a "suggested skills" section in the document, naming which skills the next agent should call the Skill tool for.

Do not duplicate content already captured in other artifacts (specs, plans, ADRs, issues, commits, diffs). Reference them by path or URL instead.

Redact any sensitive information, such as API keys, passwords, or personally identifiable information.

If the user passed arguments, treat them as a description of what the next session will focus on and tailor the doc accordingly.

## Hand to a T3 thread now

When the user wants the next agent to start now rather than later, write the document as above, then call the `t3-thread` skill with that document's path as the first-turn prompt (the thread reads the file; do not paste its contents). Name the thread for the work, not the handoff.
