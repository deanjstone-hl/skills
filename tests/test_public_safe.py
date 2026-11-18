"""What keeps this repository safe to publish (skills/27, skills/30).

The repo goes public in place (scripts/owner-steps/28.sh), so a pull request from a fork runs the
workflows on this repository's behalf and every file is world-readable. These tests pin the
rules: GitHub-hosted runners only, nothing that could send a job to the homelab, no
`pull_request_target`, no secret in a workflow a pull request starts, and no private value in
the tree. GitHub, secure use of Actions: self-hosted runners "should almost never be used for
public repositories"; secrets are not passed to workflows started from forks.

Any value that looks private is built at run time, so this file holds none.
"""

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
SYNCTHING_SKILL = ROOT / "skills" / "syncthing-pair" / "SKILL.md"
IP_KEYS = ("wsl", "lgn5", "homelab", "dj15")
HAVE_GITLEAKS = shutil.which("gitleaks") is not None and shutil.which("jq") is not None


def code_of(path: Path) -> str:
    """The file without comment lines: a comment may name what the workflow avoids."""
    return re.sub(r"(?m)^\s*#.*$", "", path.read_text())


def triggers(workflow: dict) -> dict:
    on = workflow.get("on", workflow.get(True)) or {}
    return on if isinstance(on, dict) else {name: None for name in ([on] if isinstance(on, str) else on)}


class WorkflowTests(unittest.TestCase):
    def test_there_are_workflows_to_check(self):
        self.assertTrue(WORKFLOWS)

    def test_every_job_runs_on_ubuntu_latest_and_only_there(self):
        for path in WORKFLOWS:
            code = code_of(path)
            self.assertNotRegex(code, r"self-hosted|homelab", path.name)
            runs_on = re.findall(r"(?m)^\s*runs-on:\s*(.+)$", code)
            self.assertTrue(runs_on, path.name)
            self.assertEqual({value.strip() for value in runs_on}, {"ubuntu-latest"}, path.name)

    def test_no_runner_selecting_variable_and_no_self_hosted_only_step(self):
        for path in WORKFLOWS:
            self.assertNotRegex(code_of(path), r"CI_RUNS_ON|vars\.[A-Z_]*RUNS_ON|runner\.environment", path.name)

    def test_no_pull_request_target(self):
        for path in WORKFLOWS:
            self.assertNotIn("pull_request_target", code_of(path), path.name)

    def test_no_action_or_workflow_from_a_private_repository_of_the_owner(self):
        for path in WORKFLOWS:
            uses = re.findall(r"uses:\s*([^\s#]+)", code_of(path))
            self.assertEqual([u for u in uses if u.startswith("deanjstone/")], [], path.name)

    def test_a_workflow_a_pull_request_starts_uses_no_secret_but_the_read_only_token(self):
        started = [p for p in WORKFLOWS if "pull_request" in triggers(yaml.safe_load(p.read_text()))]
        self.assertIn("check.yml", [p.name for p in started])
        for path in started:
            secrets = re.findall(r"secrets\.([A-Za-z0-9_]+)", code_of(path))
            self.assertEqual([s for s in secrets if s != "GITHUB_TOKEN"], [], path.name)
            workflow = yaml.safe_load(path.read_text())
            self.assertEqual(workflow["permissions"], {"contents": "read"}, path.name)

    def test_no_workflow_needs_a_secrets_manager_token(self):
        # No workflow reads a private value, so none is given the Secrets Manager token.
        for path in WORKFLOWS:
            self.assertNotIn("BWS_ACCESS_TOKEN", code_of(path), path.name)


class PrivateValueTests(unittest.TestCase):
    def test_syncthing_pair_names_no_address_but_loopback(self):
        text = SYNCTHING_SKILL.read_text()
        addresses = set(re.findall(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", text))
        self.assertEqual(addresses - {"127.0.0.1"}, set())

    def test_syncthing_pair_reads_each_tailscale_address_from_secrets_manager_by_name(self):
        text = SYNCTHING_SKILL.read_text()
        for key in IP_KEYS:
            self.assertIn(f"syncthing-tailscale-ip-{key}", text)
        self.assertIn("bws secret list", text)

    def test_env_example_names_the_secrets_manager_keys_and_holds_no_value(self):
        lines = (ROOT / ".env.example").read_text().splitlines()
        assignments = [line for line in lines if line.strip() and not line.lstrip().startswith("#")]
        self.assertTrue(assignments)
        for line in assignments:
            self.assertRegex(line, r"^[A-Z][A-Z0-9_]*=$", "a value belongs in Secrets Manager, not here")
        named = {m for m in re.findall(r"(?m)^# BWS secret (\S+?):", "\n".join(lines))}
        self.assertEqual(named, {f"syncthing-tailscale-ip-{key}" for key in IP_KEYS})

    def test_dot_env_is_ignored(self):
        ignored = (ROOT / ".gitignore").read_text().split()
        self.assertIn(".env", ignored)

    def test_the_scrub_config_and_script_exist(self):
        self.assertTrue((ROOT / ".gitleaks.toml").is_file())
        self.assertTrue((ROOT / "scripts" / "scrub-scan.sh").is_file())


@unittest.skipUnless(HAVE_GITLEAKS, "gitleaks and jq are not installed (main CI has neither)")
class ScrubScanTests(unittest.TestCase):
    def scan(self, directory: Path):
        return subprocess.run(
            ["bash", str(ROOT / "scripts" / "scrub-scan.sh"), str(directory)], capture_output=True, text=True
        )

    def planted(self, name: str, text: str) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="skills-scrub-"))
        self.addCleanup(shutil.rmtree, directory, True)
        (directory / name).write_text(text)
        return directory

    def test_the_tree_at_head_has_no_finding(self):
        result = subprocess.run(
            ["bash", str(ROOT / "scripts" / "scrub-scan.sh")], capture_output=True, text=True, cwd=ROOT
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("scrub-scan: pass (0 findings)", result.stdout)

    def test_a_clean_directory_passes(self):
        self.assertEqual(self.scan(self.planted("a.md", "nothing private here\n")).returncode, 0)

    def test_each_private_value_kind_fails_and_is_never_printed(self):
        values = {
            "tailnet-ip": ".".join(["100", "97", "96", "95"]),
            "lan-ip": ".".join(["192", "168", "7", "9"]),
            "tailnet-hostname": "box." + ".".join(["tail1a2b3", "ts", "net"]),
            "personal-email": "someone@" + ".".join(["mail", "invalid-tld-example", "org"]),
            "cloudflare-id": "ab" * 16,
            "access-team-domain": "team-" + "x" * 4 + "." + ".".join(["cloudflareaccess", "com"]),
        }
        for rule, value in values.items():
            with self.subTest(rule=rule):
                result = self.scan(self.planted("leak.txt", f"value {value}\n"))
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(rule, result.stdout)
                self.assertNotIn(value, result.stdout + result.stderr)

    def test_placeholders_and_content_hashes_in_the_lock_file_pass(self):
        directory = self.planted("a.md", "write to owner@example.com\n")
        (directory / "skills-lock.json").write_text('{"hash": "' + "ab" * 32 + '"}\n')
        self.assertEqual(self.scan(directory).returncode, 0)

    def test_a_cloudflare_id_outside_the_lock_file_is_still_caught(self):
        self.assertEqual(self.scan(self.planted("other.json", '{"hash": "' + "ab" * 32 + '"}\n')).returncode, 1)


if __name__ == "__main__":
    unittest.main()
