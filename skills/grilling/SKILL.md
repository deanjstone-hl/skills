---
name: grilling
description: Grill the user relentlessly about a plan, decision, or idea. Use when the user wants to stress-test their thinking, or uses any 'grill' trigger phrases. Say "grill, and write docs" to also record decisions as ADRs and glossary entries.
---

Interview the user relentlessly about every aspect of this until reaching a shared understanding. Walk down each branch of the decision tree, resolving dependencies between decisions one by one. For each question, provide a recommended answer.

Ask the questions one at a time via `AskUserQuestion`, waiting for the answer to each before continuing. Asking multiple questions at once is bewildering.

If a *fact* can be found by exploring the environment (filesystem, tools, etc.), look it up rather than asking. The *decisions*, though, belong to the user — put each one to them and wait for their answer.

Do not act on any of it until the user confirms a shared understanding has been reached.

## Grill and write docs

Plain grilling writes no docs. When the user asks to "grill, and write docs" (or "grill with docs"), call the Skill tool for `domain-modeling` first, then run the interview above and record each decision as it lands: an ADR for a hard-to-reverse choice, a glossary entry for a term the user fixes. Still change nothing else until the user confirms shared understanding.
