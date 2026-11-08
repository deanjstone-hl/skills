#!/usr/bin/env python3
"""Validate skills, the lockfile and licences. Exit 1 on any error.

    check_skills.py [root] [--privacy | --no-privacy]

The private-marker screen follows skills-config.json (on by default); a flag overrides it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skills_lib as lib  # noqa: E402


def main():
    args = sys.argv[1:]
    privacy = True if "--privacy" in args else False if "--no-privacy" in args else None
    paths = [a for a in args if not a.startswith("--")]
    root = Path(paths[0]) if paths else Path(__file__).resolve().parent.parent
    errors, warnings = lib.check(root, privacy=privacy)
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    count = len(list((root / "skills").glob("*/SKILL.md"))) if (root / "skills").exists() else 0
    print(f"{count} skills, {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
