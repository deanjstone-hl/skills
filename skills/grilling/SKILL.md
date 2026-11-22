---
name: grilling
description: Grill the user relentlessly about a plan, decision, or idea. Use when the user wants to stress-test their thinking, or uses any 'grill' trigger phrases. Say "grill, and write docs" to also record decisions as ADRs and glossary entries.
---

Interview the user relentlessly until you reach a shared understanding. Map the topic as a **design tree**: every decision branches into the decisions that hang off it. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet.

## Read first

Before the first question, read everything the topic touches, with evidence: the issue and every comment, the live state, the code, the docs, recent commits, and the scale in real numbers.

Finding _facts_ is your job, never the user's. Do a lookup of a few reads yourself. Send a broader one to a sub-agent with a fresh context window; the questions that don't depend on it are asked now, and only those downstream of it wait.

Open with:

1. A bold one-line **Status** verdict, then the evidence bullets.
2. A one-paragraph **Summary** of the problem.
3. An **options table** (letter, approach, trade-off), then a **Recommendation**, which may combine options.

## Ask

Ask one question at a time: the frontier question whose answer reshapes the tree most. Each answer can pivot the direction, so recompute the frontier before the next question instead of asking ahead. Say where you are ("Decision 3 of ~8") and name what is still ahead in one line.

Before each `AskUserQuestion`, send formatted text (the harness's message-to-user tool, where it has one) headed `**Next question: <title>**`:

- what is being decided, and why now;
- each option's effect and trade-off, with links;
- small findings from the lookup, as one-line notes.

Then call `AskUserQuestion` with that one question:

- the recommended option first, labelled "(Recommended)", worded so accepting it is one tap;
- "act now" is always a real option; recommend waiting only for a concrete hazard: something irreversible, data loss or a security exposure.

When the user asks for a check or an explanation instead of choosing, investigate, show the findings, then re-ask. A free-text answer is binding. When it changes the plan, confirm the new direction with one `AskUserQuestion`, and re-ask any question it left unanswered; never proceed on "tell me if I read it wrong". A missing answer is re-asked on its own and never inferred. A request to re-order topics is honoured at once.

Follow the user's own reader-format rules where they have them (an ADHD skill, for example). Restate your position every turn, show times in the user's timezone, and write every GitHub reference as a markdown link.

## Close

The session is done when the frontier is empty: every branch visited, nothing left silently assumed. Hold every write until then: no issue, comment, commit or file change.

1. Show the full write batch and the decisions record in the message itself (a `send_to_user` block when it is long): each target and its exact text, never a local file path the reader may not be able to open before approving. Quote the user verbatim, with the time of their answer, never the time of writing.
2. Get one "Apply all" through `AskUserQuestion`.
3. Re-read each target just before writing it, and fold in anything newer than your plan.
4. Write, then read back.
5. End with numbered **Decisions** (time, a link to the verbatim record), **Work filed** (a link each, with labels and dependencies), and what was _not_ changed. The user's own filing and closeout rules decide labels, resolution comments and verification.

## Grill and write docs

Plain grilling writes no docs. When the user asks to "grill, and write docs" (or "grill with docs"), call the Skill tool for `domain-modeling` first, then run the interview above. As each decision lands, draft its record: an ADR for a hard-to-reverse choice, a glossary entry for a term the user fixes. The drafts go in the write batch and are written at "Apply all", with everything else.
