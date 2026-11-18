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

    def test_every_job_runs_on_the_ci_runs_on_fallback(self):
        # The repo is private (homelab#475): every job reads CI_RUNS_ON so the billing guard can
        # move it, defaulting to ubuntu-latest. The public-safety rules are in test_public_safe.py.
        runs_on = "runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '\"ubuntu-latest\"') }}"
        for name, jobs in (("check.yml", 1), ("release.yml", 2)):
            text = (ROOT / ".github" / "workflows" / name).read_text()
            self.assertEqual(text.count(runs_on), jobs, name)

    def test_release_retry_wrapper_is_authenticated_and_pointed_at_deploy(self):
        # The vendored script reads these; its own behaviour is tested in argus-config.
        text = (ROOT / ".github" / "workflows" / "release.yml").read_text()
        step = next(s for s in yaml.safe_load(text)["jobs"]["release"]["steps"] if s.get("name") == "Release")
        self.assertEqual(step["run"], "bash scripts/ci/release-with-retry.sh")
        self.assertEqual(step["env"]["GITHUB_TOKEN"], "${{ secrets.GITHUB_TOKEN }}")
        self.assertEqual(step["env"]["RELEASE_BRANCH"], "deploy")

    def test_check_workflow_fails_on_a_hand_edited_vendored_release_script(self):
        text = (ROOT / ".github" / "workflows" / "check.yml").read_text()
        workflow = yaml.safe_load(text)
        triggers = workflow.get("on", workflow.get(True))
        self.assertIn("pull_request", triggers)
        self.assertEqual(triggers["push"], {"branches": ["main"]})
        runs = [s.get("run") for s in workflow["jobs"]["check"]["steps"]]
        self.assertIn("bash scripts/ci/release-scripts-check.sh", runs)

    def test_vendored_release_scripts_have_a_lock_naming_the_argus_config_source(self):
        lock = (ROOT / "scripts" / "ci" / "release-scripts.lock").read_text()
        self.assertRegex(lock, r"(?m)^source deanjstone/argus-config [0-9a-f]{40}$")
        for name in ("release-proof.sh", "release-scripts-check.sh", "release-with-retry.sh"):
            self.assertRegex(lock, rf"(?m)^[0-9a-f]{{64}}  {name}$")


if __name__ == "__main__":
    unittest.main()
