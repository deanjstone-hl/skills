#!/usr/bin/env python3
"""After editing an imported skill, refresh its lock entry and SOURCE note."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skills_lib as lib  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print("usage: refresh_lock.py <skill> [<skill> ...]", file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parent.parent
    for name in sys.argv[1:]:
        entry = lib.refresh(root, name)
        print(f"{name}: edited={entry['edited']} localHash={entry['localHash'][:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
