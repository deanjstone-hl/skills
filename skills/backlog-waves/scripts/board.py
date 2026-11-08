#!/usr/bin/env python3
"""Read the Argus Ecosystem Backlog as compact rows.

The backlog lives in `wave:*` / `mode:*` labels on issues (argus-config#566); the
project board is no longer read. Rows come from `hooks/backlog-labels.py rows`,
which reads every open issue in the in-scope repos with one GraphQL search and
derives `wave` (wave:w1 -> W1, wave:held -> Held, ...) and `mode` from labels.
Closed issues are not read: closed history stays on the frozen board.

The backlog is run as rolling waves (argus ADR-011): the lowest-numbered `W<n>`
with open issues is Current, the next one up is Next, everything else open is
`Later` (unordered, where new issues are filed) or `Held` (parked on owner hold,
never takeable). A wave has no closing review: when its last issue closes, Next
becomes Current on its own.

Usage:
  board.py dump            open issues, TSV: wave, state, ref, title
  board.py open            the same (kept for callers of the old name)
  board.py next            takeable set for the Current wave, human-readable
  board.py drift           coverage and hygiene discrepancies, human-readable
  board.py cut-next        read-only proposal for the next wave and the Later prune
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

LATER = "Later"
HELD = "Held"
NUMBERED_WAVE = re.compile(r"^W(\d+)$")

# Wave names — the editorial content labels cannot supply. Edit waves.json.
# Overridable so tests can use a fixture instead of the live file, whose names change every wave.
WAVES_META = os.environ.get("BACKLOG_WAVES_META") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "waves.json")
DEFAULT_STALE_DAYS = 90

# The label reader. This file is reached through a symlink (~/.claude/skills/...),
# so resolve it into the repo checkout first; hooks/ sits at the repo root.
LABELS_SCRIPT = os.environ.get("BACKLOG_LABELS_SCRIPT") or os.path.join(
    os.path.dirname(os.path.realpath(__file__)), *[".."] * 5, "hooks", "backlog-labels.py")


def fetch():
    """Every open in-scope issue, as row dicts, from the labels."""
    result = subprocess.run([sys.executable, LABELS_SCRIPT, "rows"], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"backlog-labels.py rows failed: {result.stderr.strip()}")
    rows = json.loads(result.stdout)
    for row in rows:
        row.setdefault("state", "OPEN")
        row.setdefault("updated_at", "")
        row.setdefault("assignees", [])
        row.setdefault("blocked_by", [])
        row.setdefault("parent", "")
        row["wave"] = row.get("wave") or ""
        row["mode"] = row.get("mode") or ""
    return rows


def ref(row):
    return f"{row['repo'].split('/')[-1]}#{row['number']}"


def open_rows(rows):
    return [r for r in rows if r["state"] == "OPEN"]


def open_blockers(row):
    return [b for b in row["blocked_by"] if b["state"] == "OPEN"]


def cmd_dump(rows):
    # `ref` stays in column 3 for the cross-check snippet in SKILL.md's `drift` section.
    for r in rows:
        print(f"{r['wave'] or '-'}\t{r['state']}\t{ref(r)}\t{r['title']}")


def cmd_open(rows):
    cmd_dump(open_rows(rows))


# ---- rolling-wave model ---------------------------------------------------


def wave_number(wave):
    """`W<n>` -> n. Anything else (`old-W3`, `Later`, `Held`, blank) -> None."""
    match = NUMBERED_WAVE.match(wave or "")
    return int(match.group(1)) if match else None


def load_meta():
    """waves.json, tolerating a missing file and missing names."""
    try:
        with open(WAVES_META) as handle:
            meta = json.load(handle)
    except FileNotFoundError:
        meta = {}
    defaults = meta.get("defaults") or {}
    return {
        "stale_days": defaults.get("stale_later_days") or DEFAULT_STALE_DAYS,
        "waves": meta.get("waves") or {},
    }


def open_numbered_waves(rows):
    """Numbered waves that still hold an open issue, lowest first."""
    return sorted(
        {r["wave"] for r in open_rows(rows) if wave_number(r["wave"]) is not None},
        key=wave_number,
    )


def current_and_next(rows):
    waves = open_numbered_waves(rows)
    return (waves[0] if waves else None, waves[1] if len(waves) > 1 else None)


def now():
    """Overridable so tests can pin the clock: BACKLOG_WAVES_NOW=2026-09-29T00:00:00Z."""
    override = os.environ.get("BACKLOG_WAVES_NOW")
    if override:
        return _parse_time(override)
    return datetime.now(timezone.utc)


def _parse_time(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def age_days(row, at):
    if not row["updated_at"]:
        return None
    return (at - _parse_time(row["updated_at"])).days


def stale_later(rows, meta, at):
    """Open `Later` items untouched for `stale_days` or more, oldest first."""
    stale = [
        r for r in open_rows(rows)
        if r["wave"] == LATER and (age_days(r, at) or 0) >= meta["stale_days"]
    ]
    return sorted(stale, key=lambda r: r["updated_at"])


def _by_ref(rows):
    return sorted(rows, key=lambda r: (r["repo"], r["number"]))


def _gates(row):
    return ", ".join(f"{b['repo'].split('/')[-1]}#{b['number']}" for b in open_blockers(row))


def _count(rows, wave):
    return len([r for r in open_rows(rows) if r["wave"] == wave])


# ---- modes -----------------------------------------------------------------


def cmd_next(rows):
    """The Current wave (lowest open `W<n>`), minus anything with an open blocker."""
    current, upcoming = current_and_next(rows)
    if current is None:
        print(
            "No numbered wave has an open issue. Run `cut-next` to cut the next one "
            "from Later."
        )
        return
    in_wave = [r for r in open_rows(rows) if r["wave"] == current]
    takeable = [r for r in in_wave if not open_blockers(r)]
    blocked = [r for r in in_wave if open_blockers(r)]

    print(f"Current wave: {current} — {len(in_wave)} open, {len(takeable)} takeable\n")
    for r in _by_ref(takeable):
        claim = f"  [claimed: {', '.join(r['assignees'])}]" if r["assignees"] else ""
        print(f"  {ref(r):<24} {r['title']}  [mode: {r['mode'] or 'unset'}]{claim}")

    if blocked:
        print(f"\nGated in {current} by an open blocker:")
        for r in _by_ref(blocked):
            print(f"  {ref(r):<24} {r['title']}\n      blocked by {_gates(r)}")

    if not takeable:
        print(
            f"\nNothing takeable: every open issue in {current} is gated. "
            "Clear a gate above to advance the wave."
        )

    hidden = []
    if upcoming:
        hidden.append(f"{_count(rows, upcoming)} in {upcoming} (Next)")
    for pool in (LATER, HELD):
        if _count(rows, pool):
            hidden.append(f"{_count(rows, pool)} in {pool}")
    if hidden:
        print(f"\nHidden by wave order: {', '.join(hidden)}.")


def cmd_drift(rows):
    meta = load_meta()
    at = now()
    live = open_rows(rows)
    uncharted = [r for r in live if not r["wave"]]

    print(f"Backlog: {len(live)} open issues in scope.\n")

    if uncharted:
        print(f"Open, no wave:* label — {len(uncharted)} (the daily label sweep sets wave:w1 in argus-config, wave:later elsewhere):")
        for r in _by_ref(uncharted):
            print(f"  {ref(r):<24} {r['title']}")
    else:
        print("Open, no wave:* label — none. Coverage is 100%.")

    conflicting = [r for r in live if len(r.get("wave_labels") or []) > 1]
    if conflicting:
        print(f"\nConflicting wave labels — {len(conflicting)} (keep one):")
        for r in _by_ref(conflicting):
            print(f"  {ref(r):<24} {' '.join(r['wave_labels'])}")

    no_mode = [r for r in live if not r["mode"]]
    if no_mode:
        print(f"\nNo single mode:* label — {len(no_mode)} (set one; never guess):")
        for r in _by_ref(no_mode):
            print(f"  {ref(r):<24} {r['title']}")

    stale = stale_later(rows, meta, at)
    if stale:
        print(
            f"\nStale in Later — {len(stale)} untouched for "
            f"{meta['stale_days']}+ days (close as stale, or keep explicitly):"
        )
        for r in stale:
            print(f"  {ref(r):<24} {r['updated_at'][:10]}  {r['title']}")

    held = _count(rows, HELD)
    if held:
        print(f"\nHeld — {held} parked on owner hold (wave:held); not takeable, not checked.")


def cmd_cut_next(rows):
    """Propose the next wave from Later, and the Later prune. Proposes; never writes.

    Waves have no closing review: Current advances on its own when its last
    issue closes, so the only planning left is cutting a new Next once the old
    Next has been promoted. Every move suggested here is applied afterwards, by
    hand, via the `assign` procedure, once each one has been approved.
    """
    meta = load_meta()
    at = now()
    current, upcoming = current_and_next(rows)
    live = open_rows(rows)

    print("Cut the next wave — PROPOSAL ONLY, nothing has been changed.\n")
    print(f"Current: {current or 'none'}    Next: {upcoming or 'none'}")

    stale = stale_later(rows, meta, at)

    # 1. Cut a new Next wave from Later, unless one already exists: at most two
    #    waves are detailed at a time.
    if upcoming:
        print(f"\n1. {upcoming} is already Next, so no new wave is cut. "
              f"Run this again once {current} empties.")
    else:
        highest = max((wave_number(w) for w in open_numbered_waves(rows)), default=0)
        new_next = f"W{highest + 1}"
        stale_refs = {ref(r) for r in stale}
        candidates = sorted(
            (r for r in live if r["wave"] == LATER and ref(r) not in stale_refs),
            key=lambda r: r["updated_at"],
        )
        print(f"\n1. Cut a new Next wave ({new_next}) from Later.")
        print(f"   {len(candidates)} non-stale Later candidate(s), oldest-updated first:")
        for r in candidates:
            gate = f"  (blocked by {_gates(r)})" if open_blockers(r) else ""
            print(f"   {ref(r):<24} {r['updated_at'][:10]}  {r['title']}{gate}")
        print(f"   Add {new_next} to waves.json with a name.")

    # 2. Prune Later.
    print(f"\n2. Prune Later — {len(stale)} untouched for {meta['stale_days']}+ days.")
    print("   Close each as stale with a comment, or keep it explicitly:")
    for r in stale:
        print(f"   {ref(r):<24} {r['updated_at'][:10]}  {r['title']}")

    print("\nNothing was written. Apply approved moves via the `assign` procedure in SKILL.md.")


COMMANDS = {
    "dump": cmd_dump,
    "open": cmd_open,
    "next": cmd_next,
    "drift": cmd_drift,
    "cut-next": cmd_cut_next,
}

if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "next"
    if command not in COMMANDS:
        raise SystemExit(f"unknown command {command!r}; expected one of {', '.join(COMMANDS)}")
    COMMANDS[command](fetch())
