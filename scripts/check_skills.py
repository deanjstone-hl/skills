#!/usr/bin/env python3
"""Validate skills, the lockfile and licences. Exit 1 on any error."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skills_lib as lib  # noqa: E402


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    errors, warnings = lib.check(root)
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    count = len(list((root / "skills").glob("*/SKILL.md"))) if (root / "skills").exists() else 0
    print(f"{count} skills, {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
