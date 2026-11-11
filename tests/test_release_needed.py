"""scripts/release-needed.sh is the "anything to release?" pre-check of release.yml
(argus-config#1167): a promotion made only of chore, docs, ci, test and refactor commits releases
nothing, so the workflow skips the test and the version. It must agree with semantic-release's
default commit analysis: feat, fix, perf, revert and breaking changes."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "release-needed.sh"
IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
}


class ReleaseNeededTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        subprocess.run(["git", "init", "-q", "-b", "deploy", str(self.repo)], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True, env={**os.environ, **IDENTITY})

    def commit(self, message):
        self.git("commit", "-q", "--allow-empty", "-m", message)

    def run_script(self, github_output=None):
        env = {**os.environ, **IDENTITY, "GITHUB_OUTPUT": github_output or ""}
        return subprocess.run(["bash", str(SCRIPT)], cwd=self.repo, env=env, capture_output=True, text=True)

    def releasable(self):
        output = Path(self.tmp.name) / "output"
        output.write_text("")
        result = self.run_script(str(output))
        self.assertEqual(result.returncode, 0, result.stderr)
        return output.read_text().strip()

    def test_false_when_no_tag_and_every_commit_is_non_releasing(self):
        self.commit("chore: init")
        self.commit("docs: explain it")
        self.commit("ci: wire it")
        self.assertEqual(self.releasable(), "releasable=false")

    def test_true_for_a_feat_or_a_fix_with_no_tag_yet(self):
        self.commit("chore: init")
        self.commit("feat: add a skill")
        self.assertEqual(self.releasable(), "releasable=true")

    def test_looks_only_at_commits_since_the_last_v_tag(self):
        self.commit("feat: old feature")
        self.git("tag", "v1.0.0")
        self.commit("test: pin it")
        self.commit("refactor: tidy")
        self.assertEqual(self.releasable(), "releasable=false")
        self.commit("fix(check): stop a crash")
        self.assertEqual(self.releasable(), "releasable=true")

    def test_counts_perf(self):
        self.commit("feat: x")
        self.git("tag", "v1.0.0")
        self.commit("perf: faster")
        self.assertEqual(self.releasable(), "releasable=true")

    def test_counts_a_revert(self):
        self.commit("feat: x")
        self.git("tag", "v1.0.0")
        self.commit('revert: undo "feat: x"')
        self.assertEqual(self.releasable(), "releasable=true")

    def test_counts_a_breaking_change_by_bang_or_by_footer(self):
        self.commit("feat: x")
        self.git("tag", "v1.0.0")
        self.commit("chore!: drop python 3.11")
        self.assertEqual(self.releasable(), "releasable=true")
        self.git("tag", "v2.0.0")
        self.commit("chore: tidy\n\nBREAKING CHANGE: the check flag is renamed")
        self.assertEqual(self.releasable(), "releasable=true")

    def test_is_not_fooled_by_a_type_word_inside_a_chore_subject(self):
        self.commit("feat: x")
        self.git("tag", "v1.0.0")
        self.commit("chore: stop feat: and fix: from leaking into the notes")
        self.assertEqual(self.releasable(), "releasable=false")

    def test_falls_back_to_stdout_when_github_output_is_unset(self):
        self.commit("feat: x")
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("releasable=true", result.stdout)


if __name__ == "__main__":
    unittest.main()
