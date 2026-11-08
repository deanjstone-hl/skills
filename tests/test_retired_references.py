import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RETIRED = {
    "claude-handoff": r"claude-handoff",
    "context-search": r"context-search",
    "cortex-search": r"cortex-search",
    "github-setup": r"github-setup",
    "project-init-extended": r"project-init-extended",
    "grill-with-docs": r"grill-with-docs",
    "ssh-perms-check": r"ssh-perms-check",
    "new-project": r"new-project",
    "issues skill": r"`issues` skill|\bthe `issues`",
}


class RetiredReferences(unittest.TestCase):
    def test_no_skill_text_names_a_folded_skill(self):
        hits = []
        for path in sorted((ROOT / "skills").rglob("*.md")):
            if path.name == "SOURCE":
                continue
            for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                for name, pattern in RETIRED.items():
                    if re.search(pattern, line):
                        hits.append(f"{path.relative_to(ROOT)}:{number} names retired '{name}'")
        self.assertEqual(hits, [], "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
