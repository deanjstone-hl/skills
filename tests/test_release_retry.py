import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ci" / "release-with-retry.sh"


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


class ReleaseRetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.remote = base / "remote.git"
        self.work = base / "work"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "deploy", str(self.remote)], check=True)
        git(base, "clone", "-q", str(self.remote), str(self.work))
        git(self.work, "config", "user.email", "t@example.com")
        git(self.work, "config", "user.name", "t")
        (self.work / "a.txt").write_text("a")
        git(self.work, "add", "a.txt")
        git(self.work, "commit", "-q", "-m", "init")
        git(self.work, "push", "-q", "origin", "HEAD:deploy")
        self.counter = base / "counter"

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, command):
        env = {**os.environ, "RELEASE_COMMAND": command, "RUNNER_TEMP": self.tmp.name, "RELEASE_BRANCH": "deploy"}
        env.pop("GITHUB_TOKEN", None)
        return subprocess.run(["bash", str(SCRIPT)], cwd=self.work, env=env, capture_output=True, text=True)

    def counting(self, body):
        # prints an attempt number to the counter file, then runs `body` with $n set
        return f'n=$(( $(cat {self.counter} 2>/dev/null || echo 0) + 1 )); echo $n > {self.counter}; {body}'

    def attempts(self):
        return int(self.counter.read_text())

    def test_success_runs_once(self):
        result = self.run_script(self.counting("echo released"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.attempts(), 1)

    def test_behind_message_is_retried_then_succeeds(self):
        cmd = self.counting('if [ "$n" -lt 2 ]; then echo "the local branch deploy is behind the remote one"; fi')
        result = self.run_script(cmd)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.attempts(), 2)

    def test_always_behind_fails_after_three_attempts(self):
        result = self.run_script(self.counting('echo "the local branch deploy is behind the remote one"'))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.attempts(), 3)
        self.assertIn("release skipped", result.stdout + result.stderr)

    def test_rejected_push_is_retried(self):
        cmd = self.counting('if [ "$n" -lt 2 ]; then echo "failed to push some refs"; exit 1; fi')
        result = self.run_script(cmd)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.attempts(), 2)

    def test_other_failures_pass_through_without_retry(self):
        result = self.run_script(self.counting("echo 'bad credentials'; exit 7"))
        self.assertEqual(result.returncode, 7)
        self.assertEqual(self.attempts(), 1)

    def test_checkout_matches_remote_tip_before_each_attempt(self):
        # a local-only commit must be dropped before the release command runs
        (self.work / "local.txt").write_text("x")
        git(self.work, "add", "local.txt")
        git(self.work, "commit", "-q", "-m", "local only")
        result = self.run_script(self.counting("test ! -e local.txt"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
