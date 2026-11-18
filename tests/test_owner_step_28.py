"""scripts/owner-steps/28.sh: the owner's in-place flip of this repository to public (skills/30).

The owner runs it live: it creates the Secrets Manager keys syncthing-pair reads, scans every
issue and pull request, deletes the CI_RUNS_ON variable, makes the repository public and sets the
fork pull-request approval policy. These cases run it in a throwaway checkout against stub `gh` and
`bws` programs that serve canned state and log every call, so they prove what it would do, and that
it prints no value, without touching GitHub or Secrets Manager. It needs jq, git and gitleaks; a
host without one skips the file (main CI has jq and git, not gitleaks).

Every private-looking value is built at run time, so this file holds none.
"""

import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "owner-steps" / "28.sh"
HAVE_TOOLS = all(shutil.which(tool) for tool in ("jq", "git", "gitleaks", "bash"))

ADDRESS = {
    "wsl": ".".join(["100", "99", "98", "97"]),
    "lgn5": ".".join(["100", "96", "95", "94"]),
    "homelab": ".".join(["100", "93", "92", "91"]),
    "dj15": ".".join(["100", "90", "89", "88"]),
}
ROW = {"wsl": "WSL", "lgn5": "LGN5", "homelab": "homelab", "dj15": "dj15-SyncTrain"}
KEYS = [f"syncthing-tailscale-ip-{name}" for name in ADDRESS]
ANCHOR = "syncthing-device-homelab"
OWNER_EMAIL = "@".join(["owner", "example.invalid"])
LEAK = ".".join(["100", "101", "102", "103"])
HEX = "abcdef0123456789" * 2
MUTATING = r"repo edit|variable delete|secret set|-X PUT|-X PATCH|-X POST|-X DELETE|issue edit|pr edit"

GH_STUB = r"""#!/bin/bash
echo "gh $*" >> "$STUB_DIR/calls.log"
fx="$STUB_DIR/fixtures"
case "$1" in
  auth) exit 0 ;;
  api)
    shift
    method=GET; [ "$1" = "-X" ] && { method=$2; shift 2; }
    path=$1
    if [ "$method" = PUT ]; then
      case "$path" in
        */actions/permissions/fork-pr-contributor-approval)
          [ -f "$fx/policy_ignored" ] || { for a in "$@"; do case "$a" in approval_policy=*) echo "${a#approval_policy=}" > "$STUB_DIR/policy" ;; esac; done; }
          echo ''; exit 0 ;;
      esac
      echo ''; exit 0
    fi
    case "$path" in
      repos/deanjstone/skills) cat "$fx/repo.json" ;;
      repos/deanjstone/skills/branches/main) echo "{\"commit\":{\"sha\":\"$(cat "$fx/remote_main_sha")\"}}" ;;
      repos/deanjstone/skills/actions/permissions/fork-pr-contributor-approval)
        if grep -q '"private":true' "$fx/repo.json"; then
          echo '{"message":"Validation Failed","errors":"Fork PR approval is not allowed for private repositories."}'; exit 1
        fi
        echo "{\"approval_policy\":\"$(cat "$STUB_DIR/policy" 2> /dev/null || echo first_time_contributors)\"}" ;;
      repos/deanjstone/skills/actions/runners) cat "$fx/runners.json" ;;
      repos/deanjstone/skills/hooks) echo '[]' ;;
      repos/deanjstone/skills/pulls/comments) cat "$fx/review_comments.json" ;;
      *) echo '{}' ;;
    esac ;;
  repo)
    case "$2" in
      edit) sed -i 's/"private":true/"private":false/' "$fx/repo.json" ;;
    esac ;;
  secret) cat "$fx/secrets.json" ;;
  variable)
    case "$2" in
      list) cat "$fx/variables.json" ;;
      delete) jq --arg n "$3" 'map(select(.name != $n))' "$fx/variables.json" > "$fx/variables.new" && mv "$fx/variables.new" "$fx/variables.json" ;;
    esac ;;
  issue) cat "$fx/issues.json" ;;
  pr) cat "$fx/prs.json" ;;
esac
exit 0
"""

BWS_STUB = r"""#!/bin/bash
[ -n "${BWS_ACCESS_TOKEN:-}" ] || { echo "Missing access token" >&2; exit 1; }
sub="$1 $2"; shift 2
case "$sub" in
  "secret list") cat "$STUB_DIR/bws_list.json" ;;
  "secret create")
    key=${@: -3:1}; value=${@: -2:1}; project=${@: -1}
    echo "$key $project" >> "$STUB_DIR/bws_created.log"; echo "$value" > "$STUB_DIR/bws_value_$key"
    jq --arg k "$key" --arg v "$value" --arg p "$project" '. + [{key: $k, id: ("id-" + $k), projectId: $p, value: $v}]' "$STUB_DIR/bws_list.json" > "$STUB_DIR/bws_list.new" && mv "$STUB_DIR/bws_list.new" "$STUB_DIR/bws_list.json" ;;
esac
exit 0
"""


def git(cwd, *args):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr}")
    return result.stdout.strip()


def table(addresses):
    rows = "\n".join(
        f"| `{ROW[name]}` | `ABCDEFG` | — | `{addresses[name]}` |" for name in ("wsl", "lgn5", "homelab", "dj15")
    )
    topology = (
        "| Node | Service | GUI | BEP listen |\n|---|---|---|---|\n"
        f"| WSL | apt | `http://127.0.0.1:8385` | `{addresses['wsl']}:22001`, `127.0.0.1:22001` |\n"
        f"| homelab | apt | `https://{addresses['homelab']}:8384` | `{addresses['homelab']}:22000` |\n"
    )
    devices = f"| Name | ID prefix | Live names | Tailscale IP |\n|---|---|---|---|\n{rows}\n"
    return f"# Syncthing\n\n{topology}\n{devices}"


def issue(number, body="plain text", comments=(), reviews=()):
    return {
        "number": number,
        "title": f"item {number}",
        "body": body,
        "comments": [{"body": text} for text in comments],
        "reviews": [{"body": text} for text in reviews],
    }


class Fixture:
    def __init__(self, test, keys_present=(), issues=None, prs=None, review_comments=(), scrub_fails=False,
                 public=False, variables=(), runners=0, dirty=False, behind=False, remote_moved=False,
                 policy_ignored=False, no_anchor=False):
        self.work = Path(tempfile.mkdtemp(prefix="skills-28-"))
        test.addCleanup(shutil.rmtree, self.work, True)
        self.stub = self.work / "stub"
        fx = self.stub / "fixtures"
        bin_dir = self.work / "bin"
        self.checkout = self.work / "checkout"
        origin = self.work / "origin.git"
        for directory in (fx, bin_dir, self.checkout):
            directory.mkdir(parents=True, exist_ok=True)
        for name, body in (("gh", GH_STUB), ("bws", BWS_STUB)):
            (bin_dir / name).write_text(body)
            (bin_dir / name).chmod((bin_dir / name).stat().st_mode | stat.S_IXUSR)

        # The history as it is: one commit with the addresses in the table, then the scrub.
        git(self.checkout, "init", "-q", "-b", "main")
        git(self.checkout, "config", "user.name", "Owner")
        git(self.checkout, "config", "user.email", OWNER_EMAIL)
        (self.checkout / "scripts" / "owner-steps").mkdir(parents=True)
        shutil.copy(SCRIPT, self.checkout / "scripts" / "owner-steps" / "28.sh")
        shutil.copy(ROOT / "scripts" / "scrub-scan.sh", self.checkout / "scripts" / "scrub-scan.sh")
        shutil.copy(ROOT / ".gitleaks.toml", self.checkout / ".gitleaks.toml")
        skill = self.checkout / "skills" / "syncthing-pair"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(table(ADDRESS))
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "feat: first")
        (skill / "SKILL.md").write_text("Read each address with `bws secret list`: " + ", ".join(KEYS) + "\n")
        (self.checkout / ("leak.txt" if scrub_fails else "ok.txt")).write_text(f"host {LEAK}\n" if scrub_fails else "clean\n")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "chore: scrub")
        git(self.work, "init", "-q", "--bare", "-b", "main", str(origin))
        git(self.checkout, "remote", "add", "origin", str(origin))
        git(self.checkout, "push", "-q", "origin", "main")
        git(self.checkout, "fetch", "-q", "origin")
        remote_sha = git(self.checkout, "rev-parse", "HEAD")
        if behind:
            # Local origin/main is ahead of the checked-out commit.
            (self.checkout / "later.txt").write_text("later\n")
            git(self.checkout, "add", "-A")
            git(self.checkout, "commit", "-q", "-m", "chore: later")
            git(self.checkout, "push", "-q", "origin", "main")
            git(self.checkout, "fetch", "-q", "origin")
            git(self.checkout, "checkout", "-q", "--detach", "HEAD~1")
            remote_sha = git(self.checkout, "rev-parse", "origin/main")
        if dirty:
            (self.checkout / "scratch.txt").write_text("untracked\n")
        (fx / "remote_main_sha").write_text(("0" * 40) if remote_moved else remote_sha)

        listing = [] if no_anchor else [{"key": ANCHOR, "id": f"id-{ANCHOR}", "projectId": "proj-personal", "value": "device-id-VALUE"}]
        listing += [{"key": key, "id": f"id-{key}", "projectId": "proj-personal", "value": "v"} for key in keys_present]
        (self.stub / "bws_list.json").write_text(json.dumps(listing))

        (fx / "repo.json").write_text(json.dumps({"private": not public, "full_name": "deanjstone/skills"}).replace(": ", ":").replace(", ", ","))
        (fx / "issues.json").write_text(json.dumps(issues if issues is not None else [issue(n) for n in (16, 17, 29)]))
        (fx / "prs.json").write_text(json.dumps(prs if prs is not None else [issue(n) for n in (10, 11)]))
        (fx / "review_comments.json").write_text(json.dumps([{"id": i, "body": text} for i, text in enumerate(review_comments)]))
        (fx / "secrets.json").write_text(json.dumps([]))
        (fx / "variables.json").write_text(json.dumps([{"name": name} for name in variables]))
        (fx / "runners.json").write_text(json.dumps({"total_count": runners, "runners": [{"id": i} for i in range(runners)]}))
        if policy_ignored:
            (fx / "policy_ignored").write_text("")
        (self.work / "bws_token").write_text("BWS_ACCESS_TOKEN=machine-token\n")
        self.bin = bin_dir

    def run(self, *args):
        env = {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "HOME": str(self.work),
            "STUB_DIR": str(self.stub),
            "SKILLS_BWS_TOKEN_FILE": str(self.work / "bws_token"),
        }
        result = subprocess.run(
            ["bash", str(self.checkout / "scripts" / "owner-steps" / "28.sh"), *args],
            capture_output=True, text=True, cwd=self.checkout, env=env, timeout=120,
        )
        return result.returncode, result.stdout + result.stderr

    def log(self, name):
        path = self.stub / name
        return path.read_text() if path.exists() else ""

    def mutations(self):
        return [line for line in self.log("calls.log").splitlines() if re.search(MUTATING, line)]


def assert_no_value(test, output):
    for value in [*ADDRESS.values(), LEAK, OWNER_EMAIL, HEX]:
        test.assertNotIn(value, output)


@unittest.skipUnless(HAVE_TOOLS, "jq, git and gitleaks are needed (main CI has no gitleaks)")
class OwnerStep28Tests(unittest.TestCase):
    def test_rejects_unknown_arguments(self):
        status, _ = Fixture(self).run("--bogus")
        self.assertEqual(status, 2)

    def test_dry_run_reads_state_prints_every_action_changes_nothing_and_prints_no_value(self):
        fixture = Fixture(self, variables=["CI_RUNS_ON"])
        status, output = fixture.run("--dry-run")
        self.assertEqual(status, 0, output)
        self.assertIn("pre-flight ok: the scrubbed tree passes the scrub scan", output)
        for action in (
            *[f"Secrets Manager {key}" for key in KEYS],
            "scan every issue and pull request",
            "delete the Actions variable CI_RUNS_ON",
            "make deanjstone/skills public",
            "fork pull-request approval policy",
            "never pushes deploy",
        ):
            self.assertIn(action, output)
        assert_no_value(self, output)
        self.assertEqual(fixture.mutations(), [])
        self.assertEqual(fixture.log("bws_created.log"), "")
        self.assertEqual(fixture.log("policy"), "")

    def test_dry_run_stops_before_anything_when_the_tree_would_still_leak(self):
        fixture = Fixture(self, scrub_fails=True)
        status, output = fixture.run("--dry-run")
        self.assertEqual(status, 1)
        self.assertIn("pre-flight FAILED: the scrubbed tree passes the scrub scan", output)
        self.assertNotIn(LEAK, output)
        self.assertEqual(fixture.mutations(), [])

    def test_the_policy_is_not_read_while_the_repository_is_private(self):
        fixture = Fixture(self)
        status, output = fixture.run("--dry-run")
        self.assertEqual(status, 0, output)
        self.assertNotIn("fork-pr-contributor-approval", fixture.log("calls.log"))
        self.assertIn("cannot be read while the repository is private", output)

    def test_a_public_repository_reports_its_current_policy(self):
        fixture = Fixture(self, public=True)
        status, output = fixture.run("--dry-run")
        self.assertEqual(status, 0, output)
        self.assertIn("fork pull-request approval policy is first_time_contributors", output)
        self.assertIn("State: deanjstone/skills is public", output)

    def test_every_issue_pr_comment_and_review_is_scanned_open_or_closed(self):
        cases = {
            "issue 16": dict(issues=[issue(16, f"see {HEX}"), issue(17)]),
            "issue 17": dict(issues=[issue(16), issue(17, comments=[f"see {HEX}"])]),
            "pull request 10": dict(prs=[issue(10, reviews=[f"see {HEX}"])]),
            "pull request 11": dict(prs=[issue(10), issue(11, comments=[f"host {LEAK}"])]),
            "review comment 0": dict(review_comments=[f"host {LEAK}"]),
        }
        for label, kwargs in cases.items():
            with self.subTest(label):
                fixture = Fixture(self, **kwargs)
                status, output = fixture.run("--dry-run")
                self.assertEqual(status, 0, output)
                self.assertIn(f"{label}: 1 finding", output)
                self.assertIn("A real run stops before the flip", output)
                assert_no_value(self, output)

    def test_gh_is_asked_for_every_state_not_only_open(self):
        fixture = Fixture(self)
        fixture.run("--dry-run")
        calls = fixture.log("calls.log")
        self.assertRegex(calls, r"issue list .*--state all")
        self.assertRegex(calls, r"pr list .*--state all")

    def test_a_real_run_stops_before_the_flip_when_an_item_leaks(self):
        fixture = Fixture(self, prs=[issue(10, comments=[f"host {LEAK}"])], variables=["CI_RUNS_ON"])
        status, output = fixture.run()
        self.assertEqual(status, 3, output)
        assert_no_value(self, output)
        calls = fixture.log("calls.log")
        self.assertNotIn("--visibility public", calls)
        self.assertNotIn("variable delete", calls)
        self.assertNotIn("fork-pr-contributor-approval", calls)
        self.assertIn("stopping before the repository goes public", output)

    def test_a_missing_anchor_secret_stops_a_real_run_before_any_change(self):
        fixture = Fixture(self, no_anchor=True, variables=["CI_RUNS_ON"])
        status, output = fixture.run()
        self.assertEqual(status, 1)
        self.assertIn(f"pre-flight FAILED: Secrets Manager holds {ANCHOR}", output)
        self.assertEqual(fixture.mutations(), [])

    def test_a_dirty_checkout_stops_a_real_run(self):
        fixture = Fixture(self, dirty=True)
        status, output = fixture.run()
        self.assertEqual(status, 1)
        self.assertIn("pre-flight FAILED: this checkout is clean and is exactly origin/main", output)
        self.assertEqual(fixture.mutations(), [])

    def test_a_checkout_behind_origin_main_stops_a_real_run(self):
        fixture = Fixture(self, behind=True)
        status, output = fixture.run()
        self.assertEqual(status, 1)
        self.assertIn("pre-flight FAILED: this checkout is clean and is exactly origin/main", output)

    def test_a_stale_origin_main_stops_a_real_run(self):
        fixture = Fixture(self, remote_moved=True)
        status, output = fixture.run()
        self.assertEqual(status, 1)
        self.assertIn("pre-flight FAILED: origin/main is the tip of main on GitHub", output)
        self.assertEqual(fixture.mutations(), [])

    def test_a_repository_level_runner_stops_the_flip(self):
        fixture = Fixture(self, runners=1)
        status, output = fixture.run()
        self.assertEqual(status, 1)
        self.assertIn("pre-flight FAILED: no self-hosted runner is registered on the repository", output)
        self.assertEqual(fixture.mutations(), [])

    def test_a_clean_real_run_flips_in_order_and_never_pushes_deploy(self):
        fixture = Fixture(self, variables=["CI_RUNS_ON", "KEEP_ME"])
        status, output = fixture.run()
        self.assertEqual(status, 0, output)
        assert_no_value(self, output)
        calls = fixture.log("calls.log")
        self.assertIn("gh variable delete CI_RUNS_ON -R deanjstone/skills", calls)
        self.assertNotIn("KEEP_ME", "\n".join(fixture.mutations()))
        self.assertIn("gh repo edit deanjstone/skills --visibility public --accept-visibility-change-consequences", calls)
        self.assertIn("-X PUT repos/deanjstone/skills/actions/permissions/fork-pr-contributor-approval -f approval_policy=all_external_contributors", calls)
        self.assertEqual(len(fixture.log("bws_created.log").splitlines()), 4)
        self.assertLess(calls.index("variable delete"), calls.index("--visibility public"))
        self.assertLess(calls.index("--visibility public"), calls.index("-X PUT"))
        self.assertIsNone(re.search(r"git push|deploy", calls))
        for check in ("repository is public", "approval policy is all_external_contributors", *KEYS, "CI_RUNS_ON is gone"):
            self.assertRegex(output, rf"verify ok: .*{re.escape(check)}")
        self.assertEqual(fixture.log("policy").strip(), "all_external_contributors")

    def test_each_tailscale_address_is_stored_under_its_key_from_the_old_table_in_the_anchors_project(self):
        fixture = Fixture(self)
        status, output = fixture.run()
        self.assertEqual(status, 0, output)
        created = fixture.log("bws_created.log").splitlines()
        self.assertEqual(sorted(created), sorted(f"{key} proj-personal" for key in KEYS))
        for name, address in ADDRESS.items():
            self.assertEqual((fixture.stub / f"bws_value_syncthing-tailscale-ip-{name}").read_text().strip(), address)

    def test_a_key_that_already_exists_is_left_as_it_is(self):
        fixture = Fixture(self, keys_present=[KEYS[0], KEYS[2]])
        status, output = fixture.run()
        self.assertEqual(status, 0, output)
        created = fixture.log("bws_created.log")
        self.assertNotIn(KEYS[0], created)
        self.assertNotIn(KEYS[2], created)
        self.assertIn(KEYS[1], created)
        self.assertIn(f"Secrets Manager {KEYS[0]}: already set, left as is", output)

    def test_no_variable_delete_when_ci_runs_on_is_absent(self):
        fixture = Fixture(self)
        status, output = fixture.run()
        self.assertEqual(status, 0, output)
        self.assertNotIn("variable delete", fixture.log("calls.log"))
        self.assertIn("CI_RUNS_ON: not present", output)

    def test_a_second_run_after_a_full_run_creates_nothing_and_flips_nothing(self):
        fixture = Fixture(self, variables=["CI_RUNS_ON"])
        self.assertEqual(fixture.run()[0], 0)
        before = fixture.log("calls.log").count("repo edit"), fixture.log("calls.log").count("variable delete")
        status, output = fixture.run()
        self.assertEqual(status, 0, output)
        self.assertEqual(len(fixture.log("bws_created.log").splitlines()), 4)
        self.assertEqual((fixture.log("calls.log").count("repo edit"), fixture.log("calls.log").count("variable delete")), before)
        self.assertIn("flip: already public", output)

    def test_resumes_on_a_repository_that_is_already_public(self):
        fixture = Fixture(self, public=True)
        status, output = fixture.run()
        self.assertEqual(status, 0, output)
        self.assertNotIn("repo edit", fixture.log("calls.log"))
        self.assertEqual(fixture.log("policy").strip(), "all_external_contributors")

    def test_a_policy_that_does_not_stick_fails_the_verify(self):
        fixture = Fixture(self, policy_ignored=True)
        status, output = fixture.run()
        self.assertEqual(status, 1)
        self.assertIn("verify FAILED: the fork pull-request approval policy is all_external_contributors", output)


class OwnerStep28TextTests(unittest.TestCase):
    code = re.sub(r"(?m)^\s*#.*$", "", SCRIPT.read_text()) if SCRIPT.exists() else ""

    def test_the_script_exists_and_the_fresh_history_cutover_is_retired(self):
        self.assertTrue(SCRIPT.exists())
        self.assertFalse((ROOT / "scripts" / "owner-steps" / "27.sh").exists())
        self.assertFalse((ROOT / "tests" / "test_owner_step_27.py").exists())

    def test_it_never_promotes_pushes_deploy_or_starts_a_workflow(self):
        self.assertIsNone(re.search(r"promote\.sh|git push|gh workflow run|refs/heads/deploy", self.code))

    def test_it_never_renames_transfers_or_deletes_the_repository(self):
        self.assertIsNone(re.search(r"repo (rename|delete|create|archive)|issue transfer|-X PATCH|-X DELETE", self.code))

    def test_it_never_runs_a_cloudflare_or_wrangler_write(self):
        self.assertIsNone(re.search(r"wrangler|api\.cloudflare\.com", self.code))

    def test_it_never_gives_a_secret_to_gh_on_the_command_line(self):
        self.assertIsNone(re.search(r"gh secret set", self.code))


if __name__ == "__main__":
    unittest.main()
