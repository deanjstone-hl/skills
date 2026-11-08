---
name: tech-evaluation
description: >
  Evaluate a third-party tool, library, product or repo for adoption: read its docs and
  source, check memory, interview on requirements, give a cited adopt/adapt/pass verdict.
  Use for "is X worth it", "should I adopt/fork/port this", "this looks exactly like what
  I'm trying to build", "review my starred repos for value", "would <product> be useful for
  me".
---

Run this as a sequence, not a single pass — each step changes what the next one needs to ask.

1. **Fetch the primary source.** Same discipline as `research`: the product's own docs,
   README, or landing page — not someone else's summary of it. Use WebFetch, or `gh` for a
   repo. If evaluating a batch (e.g. a starred-repos pass), fan the fetches out as parallel
   background agents rather than working through them one at a time.

2. **Ground it against what already exists.** Before judging fit, search memory
   (`memory_search`/`memory_recall`, the relevant `project_*.md` entries) for whatever this
   would replace, complement, or duplicate. An evaluation that skips this and reacts only to
   the docs will re-discover things already tried, already rejected, or already half-built.

3. **Interrogate the fit.** The decision is the user's, not a snap read of the docs. Load
   `grilling` when the tradeoffs are genuinely foggy — several viable options, unclear
   requirements. For a narrower yes/no call, a couple of targeted `AskUserQuestion` calls on
   what the docs can't answer (migration cost, what's actually different from the status quo,
   the dealbreaker if there is one) is enough — don't over-interview an obvious case.

4. **Write the verdict.** Adopt / adapt-partially / pass, with the reasoning laid out, not
   just the conclusion — cite back to the source per `research`'s convention. Publish it as an
   Artifact when it's a real deliverable worth keeping (per `artifact-design`) rather than
   leaving it in chat scrollback; a comparison or one-pager verdict reads far better as a page
   than as a wall of text.

5. **Route any follow-up work through `todo`**, never a raw `gh issue create` — that's what
   gets it into the backlog (a chosen wave with a reason line; default `wave:later`, `wave:w1` in argus-config) with a mode label.

This composes with `research` (source-gathering), `grilling` (fog-clearing interview),
`artifact-design` (the writeup), and `todo` (follow-up work) — reach for those directly by
name rather than re-implementing their steps here.
