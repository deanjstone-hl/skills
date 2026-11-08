#!/usr/bin/env python3
"""After editing an imported skill, refresh its lock entry and SOURCE note.

    refresh_lock.py [--adapted] <skill> [<skill> ...]

--adapted also clears the `unadapted` status.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skills_lib as lib  # noqa: E402


def main():
    args = sys.argv[1:]
    adapted = "--adapted" in args
    names = [a for a in args if a != "--adapted"]
    if not names:
        print("usage: refresh_lock.py [--adapted] <skill> [<skill> ...]", file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parent.parent
    for name in names:
        entry = lib.refresh(root, name, adapted=adapted)
        print(f"{name}: edited={entry['edited']} localHash={entry['localHash'][:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
