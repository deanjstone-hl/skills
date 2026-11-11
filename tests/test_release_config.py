import json
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


class ReleaseConfigTests(unittest.TestCase):
    def test_deploy_is_the_only_release_branch_and_releases_plain_versions(self):
        # `main` as a stable release branch plus `deploy` as an alpha prerelease would tag the
        # first promotion X.Y.Z-alpha.N. Every other repo lists ["deploy"] alone.
        config = json.loads((ROOT / ".releaserc.json").read_text())
        self.assertEqual(config["branches"], ["deploy"])

    def test_github_plugin_does_not_comment_on_or_label_issues(self):
        # Commit subjects cite #N refs that may point at issues in other repos; the plugin's
        # success step cannot resolve them and turns the Release job red after the tag is cut
        # (x-mcp 71682f8).
        config = json.loads((ROOT / ".releaserc.json").read_text())
        options = next(p[1] for p in config["plugins"] if not isinstance(p, str) and p[0] == "@semantic-release/github")
        self.assertIs(options["successComment"], False)
        self.assertIs(options["failComment"], False)
        self.assertIs(options["releasedLabels"], False)

    def test_release_concurrency_group_is_release(self):
        workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml").read_text())
        self.assertEqual(workflow["concurrency"], {"group": "release", "cancel-in-progress": False})

    def test_release_precheck_gates_the_test_and_the_release(self):
        # Nothing releasable (no feat, fix, perf, revert or breaking commit since the last tag)
        # runs no test and cuts no version.
        text = (ROOT / ".github" / "workflows" / "release.yml").read_text()
        workflow = yaml.safe_load(text)
        test, release = workflow["jobs"]["test"], workflow["jobs"]["release"]
        self.assertEqual(test["outputs"], {"releasable": "${{ steps.precheck.outputs.releasable }}"})
        checkout = test["steps"][0]
        self.assertEqual(checkout["with"]["fetch-depth"], 0)
        precheck = next(s for s in test["steps"] if s.get("id") == "precheck")
        self.assertEqual(precheck["run"], "bash scripts/release-needed.sh")
        gate = "steps.precheck.outputs.releasable == 'true'"
        after = test["steps"][test["steps"].index(precheck) + 1 :]
        self.assertTrue(after)
        for step in after:
            self.assertIn(gate, step.get("if", ""), step.get("name") or step.get("uses"))
        self.assertEqual(release["needs"], "test")
        self.assertEqual(release["if"], "needs.test.outputs.releasable == 'true'")

    def test_release_workflow_only_runs_on_deploy(self):
        text = (ROOT / ".github" / "workflows" / "release.yml").read_text()
        self.assertIn("branches: [deploy]", text)
        self.assertEqual(text.count("if: github.ref == 'refs/heads/deploy'"), 1)

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
