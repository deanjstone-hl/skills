import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import skills_lib as lib  # noqa: E402

SKILL = "---\nname: {name}\ndescription: Does {name} things.\n---\n\n# {name}\n"


def make_repo(root: Path, name="demo", *, files=None, lock_entry="auto", license_file=True, edited=False):
    """Build a minimal valid repo with one imported skill."""
    files = files or {"SKILL.md": SKILL.format(name=name).encode()}
    skill_dir = root / "skills" / name
    for rel, data in files.items():
        p = skill_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    (skill_dir / "SOURCE").write_text("source note\n")
    h = lib.hash_files(files)
    lock = {"version": 1, "skills": {}}
    if lock_entry == "auto":
        lock["skills"][name] = {
            "source": "o/r",
            "sourceType": "github",
            "skillPath": f"skills/{name}",
            "ref": "a" * 40,
            "upstreamHash": h,
            "localHash": h,
            "computedHash": h,
            "edited": edited,
            "license": {"spdx": "MIT", "file": "licenses/o__r.LICENSE"},
        }
    elif lock_entry:
        lock["skills"][name] = lock_entry
    (root / "skills-lock.json").write_text(json.dumps(lock))
    if license_file:
        (root / "licenses").mkdir(exist_ok=True)
        (root / "licenses" / "o__r.LICENSE").write_text("MIT License\n")
    return skill_dir


class HashTests(unittest.TestCase):
    def test_order_independent(self):
        a = {"a.md": b"1", "b/c.md": b"2"}
        b = {"b/c.md": b"2", "a.md": b"1"}
        self.assertEqual(lib.hash_files(a), lib.hash_files(b))

    def test_content_and_path_sensitive(self):
        base = {"a.md": b"1"}
        self.assertNotEqual(lib.hash_files(base), lib.hash_files({"a.md": b"2"}))
        self.assertNotEqual(lib.hash_files(base), lib.hash_files({"b.md": b"1"}))

    def test_source_note_excluded(self):
        base = {"a.md": b"1"}
        self.assertEqual(lib.hash_files(base), lib.hash_files({**base, "SOURCE": b"note"}))

    def test_read_dir_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "x" / "y").mkdir(parents=True)
            (root / "x" / "y" / "z.md").write_bytes(b"zz")
            (root / "top.md").write_bytes(b"t")
            self.assertEqual(lib.read_dir(root), {"top.md": b"t", "x/y/z.md": b"zz"})


class LockTests(unittest.TestCase):
    def test_load_missing_gives_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(lib.load_lock(Path(d)), {"version": 1, "skills": {}})

    def test_save_is_sorted_and_stable(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            lock = {"version": 1, "skills": {"b": {"x": 1}, "a": {"x": 2}}}
            lib.save_lock(root, lock)
            first = (root / "skills-lock.json").read_text()
            lib.save_lock(root, lib.load_lock(root))
            self.assertEqual(first, (root / "skills-lock.json").read_text())
            self.assertLess(first.index('"a"'), first.index('"b"'))


class FrontMatterTests(unittest.TestCase):
    def test_parses(self):
        fm = lib.parse_front_matter("---\nname: a\ndescription: b\n---\nbody")
        self.assertEqual(fm, {"name": "a", "description": "b"})

    def test_none_when_missing(self):
        self.assertIsNone(lib.parse_front_matter("no front matter"))


class CheckTests(unittest.TestCase):
    def run_check(self, setup):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            setup(root)
            return lib.check(root)

    def test_clean_repo_passes(self):
        errors, warnings = self.run_check(lambda r: make_repo(r))
        self.assertEqual((errors, warnings), ([], []))

    def test_unedited_skill_modified_fails(self):
        def setup(r):
            sd = make_repo(r)
            (sd / "SKILL.md").write_text(SKILL.format(name="demo") + "extra\n")

        errors, _ = self.run_check(setup)
        self.assertTrue(any("unedited" in e and "demo" in e for e in errors), errors)

    def test_edited_skill_with_matching_local_hash_passes(self):
        def setup(r):
            sd = make_repo(r, edited=True)
            new = SKILL.format(name="demo") + "my edit\n"
            (sd / "SKILL.md").write_text(new)
            lock = lib.load_lock(r)
            lock["skills"]["demo"]["localHash"] = lib.hash_files({"SKILL.md": new.encode()})
            lock["skills"]["demo"]["computedHash"] = lock["skills"]["demo"]["localHash"]
            lib.save_lock(r, lock)

        self.assertEqual(self.run_check(setup), ([], []))

    def test_edited_skill_with_stale_local_hash_fails(self):
        def setup(r):
            sd = make_repo(r, edited=True)
            (sd / "SKILL.md").write_text(SKILL.format(name="demo") + "drift\n")

        errors, _ = self.run_check(setup)
        self.assertTrue(any("localHash" in e for e in errors), errors)

    def test_missing_lock_entry_fails(self):
        errors, _ = self.run_check(lambda r: make_repo(r, lock_entry=None))
        self.assertTrue(any("no lock entry" in e for e in errors), errors)

    def test_lock_entry_without_skill_dir_fails(self):
        def setup(r):
            make_repo(r)
            lock = lib.load_lock(r)
            lock["skills"]["ghost"] = dict(lock["skills"]["demo"])
            lib.save_lock(r, lock)

        errors, _ = self.run_check(setup)
        self.assertTrue(any("ghost" in e and "no skill directory" in e for e in errors), errors)

    def test_name_must_match_directory(self):
        def setup(r):
            sd = make_repo(r)
            (sd / "SKILL.md").write_text(SKILL.format(name="other"))
            lock = lib.load_lock(r)
            h = lib.hash_files({"SKILL.md": SKILL.format(name="other").encode()})
            for k in ("upstreamHash", "localHash", "computedHash"):
                lock["skills"]["demo"][k] = h
            lib.save_lock(r, lock)

        errors, _ = self.run_check(setup)
        self.assertTrue(any("name" in e and "demo" in e for e in errors), errors)

    def test_missing_description_fails(self):
        def setup(r):
            files = {"SKILL.md": b"---\nname: demo\n---\nbody"}
            make_repo(r, files=files)

        errors, _ = self.run_check(setup)
        self.assertTrue(any("description" in e for e in errors), errors)

    def test_missing_license_file_fails(self):
        errors, _ = self.run_check(lambda r: make_repo(r, license_file=False))
        self.assertTrue(any("license" in e.lower() for e in errors), errors)

    def test_private_marker_fails(self):
        def setup(r):
            files = {"SKILL.md": (SKILL.format(name="demo") + "see /home/deanj/x\n").encode()}
            make_repo(r, files=files)

        errors, _ = self.run_check(setup)
        self.assertTrue(any("private" in e.lower() for e in errors), errors)

    def test_oversize_skill_md_is_a_warning(self):
        def setup(r):
            big = SKILL.format(name="demo") + ("x" * 9000)
            make_repo(r, files={"SKILL.md": big.encode()})

        errors, warnings = self.run_check(setup)
        self.assertEqual(errors, [])
        self.assertTrue(any("8" in w and "demo" in w for w in warnings), warnings)

    def test_unadapted_status_is_a_warning(self):
        def setup(r):
            make_repo(r)
            lock = lib.load_lock(r)
            lock["skills"]["demo"]["status"] = "unadapted"
            lib.save_lock(r, lock)

        errors, warnings = self.run_check(setup)
        self.assertEqual(errors, [])
        self.assertTrue(any("unadapted" in w for w in warnings), warnings)


class ImportTests(unittest.TestCase):
    def fake_fetch(self, files):
        def fetch(repo, ref, path):
            return files

        return fetch

    def test_import_writes_skill_source_license_and_lock(self):
        import import_skill as imp

        files = {"SKILL.md": SKILL.format(name="demo").encode(), "references/a.md": b"ref"}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            imp.import_skill(
                root,
                repo="o/r",
                path="skills/demo",
                name="demo",
                ref="b" * 40,
                spdx="MIT",
                license_text="MIT License\n",
                fetch=self.fake_fetch(files),
            )
            self.assertEqual((root / "skills/demo/references/a.md").read_bytes(), b"ref")
            self.assertIn("o/r", (root / "skills/demo/SOURCE").read_text())
            self.assertTrue((root / "licenses/o__r.LICENSE").exists())
            entry = lib.load_lock(root)["skills"]["demo"]
            self.assertEqual(entry["ref"], "b" * 40)
            self.assertFalse(entry["edited"])
            self.assertEqual(entry["upstreamHash"], entry["localHash"])
            self.assertEqual(lib.check(root), ([], []))

    def test_import_refuses_to_overwrite_existing_skill(self):
        import import_skill as imp

        files = {"SKILL.md": SKILL.format(name="demo").encode()}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            kwargs = dict(repo="o/r", path="skills/demo", name="demo", ref="b" * 40, spdx="MIT", license_text="L\n", fetch=self.fake_fetch(files))
            imp.import_skill(root, **kwargs)
            with self.assertRaises(FileExistsError):
                imp.import_skill(root, **kwargs)

    def test_license_file_name_is_per_source(self):
        import import_skill as imp

        self.assertEqual(imp.license_file_name("cursor/plugins", "pstack"), "licenses/cursor__plugins__pstack.LICENSE")
        self.assertEqual(imp.license_file_name("o/r", ""), "licenses/o__r.LICENSE")


class RefreshTests(unittest.TestCase):
    def test_refresh_marks_edited_and_updates_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            sd = make_repo(root)
            before = lib.load_lock(root)["skills"]["demo"]
            (sd / "SKILL.md").write_text(SKILL.format(name="demo") + "tweak\n")
            entry = lib.refresh(root, "demo")
            self.assertTrue(entry["edited"])
            self.assertEqual(entry["upstreamHash"], before["upstreamHash"])
            self.assertNotEqual(entry["localHash"], before["upstreamHash"])
            self.assertEqual(entry["computedHash"], entry["localHash"])
            self.assertIn("edited locally", (sd / "SOURCE").read_text())
            self.assertEqual(lib.check(root), ([], []))

    def test_refresh_back_to_upstream_clears_edited(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            sd = make_repo(root, edited=True)
            entry = lib.refresh(root, "demo")
            self.assertFalse(entry["edited"])

    def test_refresh_adapted_clears_unadapted_status(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            sd = make_repo(root)
            lock = lib.load_lock(root)
            lock["skills"]["demo"]["status"] = "unadapted"
            lib.save_lock(root, lock)
            (sd / "SKILL.md").write_text(SKILL.format(name="demo") + "adapted\n")
            entry = lib.refresh(root, "demo", adapted=True)
            self.assertNotIn("status", entry)
            self.assertEqual(lib.check(root), ([], []))

    def test_refresh_without_adapted_keeps_status(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            make_repo(root)
            lock = lib.load_lock(root)
            lock["skills"]["demo"]["status"] = "unadapted"
            lib.save_lock(root, lock)
            self.assertEqual(lib.refresh(root, "demo")["status"], "unadapted")

    def test_refresh_unknown_skill_raises(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            make_repo(root)
            with self.assertRaises(KeyError):
                lib.refresh(root, "nope")


if __name__ == "__main__":
    unittest.main()
