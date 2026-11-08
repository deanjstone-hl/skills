import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import skills_lib as lib  # noqa: E402
import update_skill as up  # noqa: E402

R1, R2, R3 = "1" * 40, "2" * 40, "3" * 40
REPO = "o/r"
UPATH = "skills/demo"


def skill_md(body):
    return f"---\nname: demo\ndescription: Does demo things.\n---\n\n{body}".encode()


BASE_BODY = "# demo\n\nstep one\nstep two\nstep three\nstep four\nstep five\nstep six\n"


class Upstream:
    """In-memory upstream: {(repo, ref): {path: {rel: bytes}}} plus a HEAD per repo."""

    def __init__(self, head):
        self.refs = {}
        self.head = head

    def put(self, ref, path, files):
        self.refs.setdefault((REPO, ref), {})[path] = files

    def fetch(self, repo, ref, path):
        try:
            return dict(self.refs[(repo, ref)][path])
        except KeyError:
            raise FileNotFoundError(f"{repo}:{path}@{ref}")

    def resolve(self, repo, ref=None):
        return ref or self.head

    def shas(self, repo, ref, path):
        files = self.fetch(repo, ref, path)
        return {rel: hashlib.sha1(data).hexdigest() for rel, data in files.items()}


def setup_repo(root, base_files, *, edited_files=None):
    """Create a repo whose skill is `base_files` pinned at R1, optionally with local edits."""
    skill_dir = root / "skills" / "demo"
    for rel, data in base_files.items():
        p = skill_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    h = lib.hash_files(base_files)
    lock = {
        "version": 1,
        "skills": {
            "demo": {
                "source": REPO,
                "sourceType": "github",
                "skillPath": UPATH,
                "ref": R1,
                "upstreamHash": h,
                "localHash": h,
                "computedHash": h,
                "edited": False,
                "license": {"spdx": "MIT", "file": "licenses/o__r.LICENSE"},
            }
        },
    }
    lib.save_lock(root, lock)
    (skill_dir / "SOURCE").write_text("old note\n")
    (root / "licenses").mkdir(exist_ok=True)
    (root / "licenses" / "o__r.LICENSE").write_text("MIT License\n")
    if edited_files:
        for rel, data in edited_files.items():
            (skill_dir / rel).write_bytes(data)
        lib.refresh(root, "demo")


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.base = {"SKILL.md": skill_md(BASE_BODY), "references/a.md": b"ref a\n"}
        self.upstream = Upstream(head=R2)
        self.upstream.put(R1, UPATH, self.base)

    def tearDown(self):
        self.tmp.cleanup()

    def run_update(self, **kw):
        return up.update_skill(self.root, "demo", fetch=self.upstream.fetch, resolve=self.upstream.resolve, **kw)

    def entry(self):
        return lib.load_lock(self.root)["skills"]["demo"]

    def test_up_to_date_changes_nothing(self):
        setup_repo(self.root, self.base)
        self.upstream.head = R1
        report = self.run_update()
        self.assertEqual(report["state"], "current")
        self.assertEqual(self.entry()["ref"], R1)

    def test_unedited_skill_takes_the_new_upstream(self):
        setup_repo(self.root, self.base)
        theirs = {**self.base, "SKILL.md": skill_md(BASE_BODY.replace("step five", "step FIVE"))}
        self.upstream.put(R2, UPATH, theirs)
        report = self.run_update()
        self.assertEqual(report["state"], "updated")
        self.assertIn(b"step FIVE", (self.root / "skills/demo/SKILL.md").read_bytes())
        e = self.entry()
        self.assertEqual(e["ref"], R2)
        self.assertFalse(e["edited"])
        self.assertEqual(e["upstreamHash"], lib.hash_files(theirs))
        self.assertEqual(e["localHash"], e["upstreamHash"])
        self.assertIn(R2, (self.root / "skills/demo/SOURCE").read_text())
        self.assertEqual(lib.check(self.root), ([], []))

    def test_local_edit_survives_an_upstream_change_elsewhere(self):
        mine = {"SKILL.md": skill_md(BASE_BODY.replace("step one", "step ONE (mine)"))}
        setup_repo(self.root, self.base, edited_files=mine)
        theirs = {**self.base, "SKILL.md": skill_md(BASE_BODY.replace("step six", "step SIX (theirs)"))}
        self.upstream.put(R2, UPATH, theirs)
        report = self.run_update()
        self.assertEqual(report["state"], "updated")
        text = (self.root / "skills/demo/SKILL.md").read_text()
        self.assertIn("step ONE (mine)", text)
        self.assertIn("step SIX (theirs)", text)
        e = self.entry()
        self.assertTrue(e["edited"])
        self.assertEqual(e["ref"], R2)
        self.assertEqual(e["upstreamHash"], lib.hash_files(theirs))
        self.assertEqual(lib.check(self.root), ([], []))

    def test_edit_that_upstream_adopted_becomes_unedited(self):
        both = skill_md(BASE_BODY.replace("step two", "step TWO"))
        setup_repo(self.root, self.base, edited_files={"SKILL.md": both})
        self.upstream.put(R2, UPATH, {**self.base, "SKILL.md": both})
        self.run_update()
        self.assertFalse(self.entry()["edited"])

    def test_conflict_marks_the_skill_and_blocks_check(self):
        mine = {"SKILL.md": skill_md(BASE_BODY.replace("step three", "step 3 mine"))}
        setup_repo(self.root, self.base, edited_files=mine)
        theirs = {**self.base, "SKILL.md": skill_md(BASE_BODY.replace("step three", "step 3 theirs"))}
        self.upstream.put(R2, UPATH, theirs)
        report = self.run_update()
        self.assertEqual(report["state"], "conflict")
        self.assertEqual(report["conflicts"], ["SKILL.md"])
        e = self.entry()
        self.assertEqual(e["status"], "merge-conflict")
        self.assertEqual(e["ref"], R1)  # not advanced until resolved
        self.assertEqual(e["pending"]["ref"], R2)
        errors, _ = lib.check(self.root)
        self.assertTrue(any("merge-conflict" in x or "conflict" in x for x in errors), errors)

    def test_resolve_finishes_a_conflicted_update(self):
        mine = {"SKILL.md": skill_md(BASE_BODY.replace("step three", "step 3 mine"))}
        setup_repo(self.root, self.base, edited_files=mine)
        theirs = {**self.base, "SKILL.md": skill_md(BASE_BODY.replace("step three", "step 3 theirs"))}
        self.upstream.put(R2, UPATH, theirs)
        self.run_update()
        resolved = skill_md(BASE_BODY.replace("step three", "step 3 both"))
        (self.root / "skills/demo/SKILL.md").write_bytes(resolved)
        up.resolve_update(self.root, "demo")
        e = self.entry()
        self.assertEqual(e["ref"], R2)
        self.assertNotIn("status", e)
        self.assertNotIn("pending", e)
        self.assertTrue(e["edited"])
        self.assertEqual(e["upstreamHash"], lib.hash_files(theirs))
        self.assertEqual(lib.check(self.root), ([], []))

    def test_resolve_refuses_while_markers_remain(self):
        mine = {"SKILL.md": skill_md(BASE_BODY.replace("step three", "step 3 mine"))}
        setup_repo(self.root, self.base, edited_files=mine)
        self.upstream.put(R2, UPATH, {**self.base, "SKILL.md": skill_md(BASE_BODY.replace("step three", "step 3 theirs"))})
        self.run_update()
        with self.assertRaises(ValueError):
            up.resolve_update(self.root, "demo")

    def test_refuses_when_the_pinned_base_does_not_match_the_lock(self):
        setup_repo(self.root, self.base)
        self.upstream.put(R1, UPATH, {**self.base, "references/a.md": b"rewritten history\n"})
        self.upstream.put(R2, UPATH, self.base)
        with self.assertRaises(ValueError):
            self.run_update()

    def test_new_path_when_upstream_moved_the_skill(self):
        setup_repo(self.root, self.base)
        theirs = {**self.base, "SKILL.md": skill_md(BASE_BODY.replace("step five", "step FIVE"))}
        self.upstream.put(R2, "skills/engineering/demo", theirs)
        with self.assertRaises(FileNotFoundError):
            self.run_update()
        self.run_update(new_path="skills/engineering/demo")
        e = self.entry()
        self.assertEqual(e["skillPath"], "skills/engineering/demo")
        self.assertEqual(e["ref"], R2)

    def test_explicit_ref_is_used(self):
        setup_repo(self.root, self.base)
        self.upstream.put(R3, UPATH, {**self.base, "references/a.md": b"ref a v3\n"})
        self.run_update(new_ref=R3)
        self.assertEqual(self.entry()["ref"], R3)
        self.assertEqual((self.root / "skills/demo/references/a.md").read_bytes(), b"ref a v3\n")

    def test_upstream_file_added_and_removed(self):
        setup_repo(self.root, self.base)
        theirs = {"SKILL.md": self.base["SKILL.md"], "references/b.md": b"new\n"}
        self.upstream.put(R2, UPATH, theirs)
        self.run_update()
        self.assertTrue((self.root / "skills/demo/references/b.md").exists())
        self.assertFalse((self.root / "skills/demo/references/a.md").exists())
        self.assertEqual(lib.check(self.root), ([], []))


class StatusTests(unittest.TestCase):
    def test_status_reports_current_and_changed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            base = {"SKILL.md": skill_md(BASE_BODY)}
            setup_repo(root, base)
            upstream = Upstream(head=R2)
            upstream.put(R1, UPATH, base)
            upstream.put(R2, UPATH, base)
            rows = up.status(root, resolve=upstream.resolve, shas=upstream.shas)
            self.assertEqual([(r["name"], r["state"]) for r in rows], [("demo", "current")])
            upstream.put(R2, UPATH, {"SKILL.md": skill_md(BASE_BODY + "more\n")})
            rows = up.status(root, resolve=upstream.resolve, shas=upstream.shas)
            self.assertEqual(rows[0]["state"], "changed")
            self.assertEqual(rows[0]["files"], 1)
            self.assertFalse(rows[0]["edited"])

    def test_status_reports_a_missing_path(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            base = {"SKILL.md": skill_md(BASE_BODY)}
            setup_repo(root, base)
            upstream = Upstream(head=R2)
            upstream.put(R1, UPATH, base)
            rows = up.status(root, resolve=upstream.resolve, shas=upstream.shas)
            self.assertEqual(rows[0]["state"], "path-missing")


class CheckConflictTests(unittest.TestCase):
    def test_check_fails_on_leftover_conflict_markers(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            base = {"SKILL.md": skill_md(BASE_BODY)}
            setup_repo(root, base)
            (root / "skills/demo/SKILL.md").write_bytes(skill_md("<<<<<<< local\na\n=======\nb\n>>>>>>> upstream\n"))
            lib.refresh(root, "demo")
            errors, _ = lib.check(root)
            self.assertTrue(any("conflict marker" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
