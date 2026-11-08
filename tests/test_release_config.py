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

    def test_workflows_pick_their_runner_from_ci_runs_on_with_a_hosted_fallback(self):
        # Same pattern as the other repos: the CI_RUNS_ON repo variable selects the homelab
        # runners once the repo is enrolled; until then jobs run on GitHub-hosted runners.
        expr = "runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '\"ubuntu-latest\"') }}"
        for name, jobs in (("check.yml", 1), ("release.yml", 2)):
            text = (ROOT / ".github" / "workflows" / name).read_text()
            self.assertEqual(text.count(expr), jobs, name)
            self.assertNotIn("runs-on: ubuntu-latest", text, name)


if __name__ == "__main__":
    unittest.main()
