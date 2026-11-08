import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import merge_lib as ml  # noqa: E402

BASE = b"line1\nline2\nline3\nline4\nline5\nline6\n"


class MergeFilesTests(unittest.TestCase):
    def test_upstream_unchanged_keeps_local_edit(self):
        ours = BASE.replace(b"line2", b"MINE")
        r = ml.merge_files({"a.md": BASE}, {"a.md": ours}, {"a.md": BASE})
        self.assertEqual(r.files, {"a.md": ours})
        self.assertEqual(r.conflicts, [])

    def test_local_unchanged_takes_upstream(self):
        theirs = BASE.replace(b"line5", b"THEIRS")
        r = ml.merge_files({"a.md": BASE}, {"a.md": BASE}, {"a.md": theirs})
        self.assertEqual(r.files, {"a.md": theirs})
        self.assertEqual(r.conflicts, [])

    def test_both_changed_in_different_places_merges_cleanly(self):
        ours = BASE.replace(b"line1", b"MINE")
        theirs = BASE.replace(b"line6", b"THEIRS")
        r = ml.merge_files({"a.md": BASE}, {"a.md": ours}, {"a.md": theirs})
        self.assertEqual(r.conflicts, [])
        self.assertIn(b"MINE", r.files["a.md"])
        self.assertIn(b"THEIRS", r.files["a.md"])

    def test_same_lines_changed_conflicts_with_markers(self):
        ours = BASE.replace(b"line3", b"MINE")
        theirs = BASE.replace(b"line3", b"THEIRS")
        r = ml.merge_files({"a.md": BASE}, {"a.md": ours}, {"a.md": theirs})
        self.assertEqual(r.conflicts, ["a.md"])
        text = r.files["a.md"]
        self.assertIn(b"<<<<<<< local", text)
        self.assertIn(b">>>>>>> upstream", text)
        self.assertIn(b"MINE", text)
        self.assertIn(b"THEIRS", text)

    def test_file_added_upstream_is_added(self):
        r = ml.merge_files({}, {}, {"new.md": b"x\n"})
        self.assertEqual(r.files, {"new.md": b"x\n"})

    def test_file_added_locally_is_kept(self):
        r = ml.merge_files({}, {"mine.md": b"x\n"}, {})
        self.assertEqual(r.files, {"mine.md": b"x\n"})
        self.assertEqual(r.conflicts, [])

    def test_added_on_both_sides_with_different_content_conflicts(self):
        r = ml.merge_files({}, {"a.md": b"mine\n"}, {"a.md": b"theirs\n"})
        self.assertEqual(r.conflicts, ["a.md"])

    def test_added_on_both_sides_with_same_content_is_fine(self):
        r = ml.merge_files({}, {"a.md": b"same\n"}, {"a.md": b"same\n"})
        self.assertEqual(r.conflicts, [])
        self.assertEqual(r.files, {"a.md": b"same\n"})

    def test_deleted_upstream_and_unchanged_locally_is_removed(self):
        r = ml.merge_files({"a.md": BASE}, {"a.md": BASE}, {})
        self.assertEqual(r.files, {})
        self.assertEqual(r.conflicts, [])

    def test_deleted_upstream_but_edited_locally_conflicts_and_keeps_ours(self):
        ours = BASE + b"mine\n"
        r = ml.merge_files({"a.md": BASE}, {"a.md": ours}, {})
        self.assertEqual(r.conflicts, ["a.md"])
        self.assertEqual(r.files["a.md"], ours)

    def test_deleted_locally_and_changed_upstream_conflicts_and_takes_theirs(self):
        theirs = BASE + b"new\n"
        r = ml.merge_files({"a.md": BASE}, {}, {"a.md": theirs})
        self.assertEqual(r.conflicts, ["a.md"])
        self.assertEqual(r.files["a.md"], theirs)

    def test_deleted_on_both_sides_stays_deleted(self):
        r = ml.merge_files({"a.md": BASE}, {}, {})
        self.assertEqual((r.files, r.conflicts), ({}, []))

    def test_binary_changed_upstream_only_takes_theirs(self):
        base, theirs = b"\x00\x01\x02", b"\x00\x09\x09"
        r = ml.merge_files({"i.bin": base}, {"i.bin": base}, {"i.bin": theirs})
        self.assertEqual(r.files, {"i.bin": theirs})

    def test_binary_changed_on_both_sides_conflicts_and_keeps_ours(self):
        r = ml.merge_files({"i.bin": b"\x00a"}, {"i.bin": b"\x00b"}, {"i.bin": b"\x00c"})
        self.assertEqual(r.conflicts, ["i.bin"])
        self.assertEqual(r.files["i.bin"], b"\x00b")

    def test_result_has_no_notes_when_nothing_happened(self):
        r = ml.merge_files({"a.md": BASE}, {"a.md": BASE}, {"a.md": BASE})
        self.assertEqual((r.files, r.conflicts), ({"a.md": BASE}, []))


class MarkerTests(unittest.TestCase):
    def test_has_conflict_markers(self):
        self.assertTrue(ml.has_conflict_markers(b"a\n<<<<<<< local\nb\n=======\nc\n>>>>>>> upstream\n"))
        self.assertFalse(ml.has_conflict_markers(b"a\n=======\nb\n"))


if __name__ == "__main__":
    unittest.main()
