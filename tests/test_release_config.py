import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ReleaseConfigTests(unittest.TestCase):
    def test_deploy_releases_only_alphas(self):
        # Owner decision, 8 Nov 2026: no stable 1.0.0 yet; every release is an alpha prerelease.
        # semantic-release rejects a config with no non-prerelease branch (ERELEASEBRANCHES,
        # checked against semantic-release 24.2.9), so `main` is listed too; the Release
        # workflow runs only on a push to deploy, so main never releases.
        # Drop the prerelease flag deliberately, in a commit that says so, not by accident.
        config = json.loads((ROOT / ".releaserc.json").read_text())
        self.assertEqual(config["branches"], ["main", {"name": "deploy", "prerelease": "alpha"}])

    def test_release_workflow_only_runs_on_deploy(self):
        text = (ROOT / ".github" / "workflows" / "release.yml").read_text()
        self.assertIn("branches: [deploy]", text)
        self.assertEqual(text.count("if: github.ref == 'refs/heads/deploy'"), 2)

    def test_release_commits_nothing_back(self):
        config = json.loads((ROOT / ".releaserc.json").read_text())
        plugins = [p if isinstance(p, str) else p[0] for p in config["plugins"]]
        self.assertNotIn("@semantic-release/git", plugins)
        self.assertNotIn("@semantic-release/changelog", plugins)


if __name__ == "__main__":
    unittest.main()
