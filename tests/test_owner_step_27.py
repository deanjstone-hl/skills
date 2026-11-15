"""scripts/owner-steps/27.sh: the owner's cutover of this repo to a fresh-history public one.

The owner runs it live (skills/28): it renames this repository to skills-archive, publishes one
squashed commit of the scrubbed tree as a new skills, and moves the open issues, Secrets Manager
keys and wiring across. These cases run it in a throwaway checkout against stub `gh` and `bws`
programs that serve canned state and log every call, so they prove what it would do, and that it
prints no value, without touching GitHub or Secrets Manager. It needs jq, git and gitleaks; a host
without one skips the file (main CI has jq and git, not gitleaks).

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
SCRIPT = ROOT / "scripts" / "owner-steps" / "27.sh"
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
SECRET_VALUE = "mapped-secret-VALUE"

GH_STUB = r"""#!/bin/bash
echo "gh $*" >> "$STUB_DIR/calls.log"
fx="$STUB_DIR/fixtures"
repo=""; args=("$@"); for i in "${!args[@]}"; do [ "${args[$i]}" = -R ] && repo=${args[$((i+1))]}; done
case "$1" in
  auth) exit 0 ;;
  api)
    shift
    method=GET; [ "$1" = "-X" ] && { method=$2; shift 2; }
    path=$1
    if [ "$method" = PATCH ] && [ "$path" = "repos/deanjstone/skills" ]; then
      sed 's#deanjstone/skills"#deanjstone/skills-archive"#' "$fx/repo_skills.json" > "$fx/repo_skills-archive.json"
      rm "$fx/repo_skills.json"; touch "$STUB_DIR/renamed"; echo '{}'; exit 0
    fi
    if [ "$method" = PUT ]; then echo ''; exit 0; fi
    name=${path#repos/deanjstone/}
    case "$name" in
      skills|skills-archive)
        f="$fx/repo_$name.json"
        if [ "$name" = skills ] && [ -f "$STUB_DIR/renamed" ] && [ ! -f "$fx/repo_skills.json" ]; then f="$fx/repo_skills-archive.json"; fi
        if [ -f "$f" ]; then cat "$f"; else echo '{"message":"Not Found"}'; exit 1; fi ;;
      skills/branches/main)
        if git -C "$STUB_DIR/remotes/deanjstone/skills.git" rev-parse --verify -q refs/heads/main > /dev/null 2>&1; then echo '{"name":"main"}'; else echo '{"message":"Not Found"}'; exit 1; fi ;;
      */branches/deploy) echo '{"message":"Not Found"}'; exit 1 ;;
      skills/commits*) echo '[{}]' ;;
      */hooks) echo '[]' ;;
      */keys) echo '[]' ;;
      */actions/runners) echo '{"total_count":0,"runners":[]}' ;;
      *) echo '{}' ;;
    esac ;;
  repo)
    case "$2" in
      create) touch "$STUB_DIR/created"; echo '{"private":true,"full_name":"deanjstone/skills"}' > "$fx/repo_skills.json"
              git init -q --bare "$STUB_DIR/remotes/deanjstone/skills.git"; echo "https://github.com/deanjstone/skills" ;;
      edit) sed -i 's/"private":true/"private":false/' "$fx/repo_skills.json"; touch "$STUB_DIR/public" ;;
    esac ;;
  label) exit 0 ;;
  secret)
    case "$2" in
      set) cat > "$STUB_DIR/secret_$3.value"; echo "$3" >> "$STUB_DIR/secrets_set.log" ;;
      list) if [ "$repo" = deanjstone/skills ] && [ -f "$STUB_DIR/secrets_set.log" ]; then jq -R '{name: .}' "$STUB_DIR/secrets_set.log" | jq -s .; else cat "$fx/secrets.json"; fi ;;
    esac ;;
  variable) cat "$fx/variables.json" ;;
  issue)
    case "$2" in
      list)
        if [ "$repo" = deanjstone/skills ] && [ ! -f "$STUB_DIR/renamed" ] && [ ! -f "$STUB_DIR/created" ]; then cat "$fx/issues.json"
        elif [ "$repo" = deanjstone/skills-archive ]; then
          if [ -f "$STUB_DIR/transferred" ]; then echo '[{"number":27},{"number":28}]'; else cat "$fx/issues.json"; fi
        elif [ -f "$STUB_DIR/transferred" ]; then jq -R '{number: (tonumber + 1000)}' "$STUB_DIR/transfers.log" | jq -s .
        else echo '[]'; fi ;;
      view) n=$3; [ "$n" -gt 1000 ] && n=$((n-1000)); cat "$fx/issue_$n.json" ;;
      transfer) touch "$STUB_DIR/transferred"; echo "$3" >> "$STUB_DIR/transfers.log"; echo "https://github.com/deanjstone/skills/issues/$((${3}+1000))" ;;
    esac ;;
esac
exit 0
"""

BWS_STUB = r"""#!/bin/bash
[ -n "${BWS_ACCESS_TOKEN:-}" ] || { echo "Missing access token" >&2; exit 1; }
sub="$1 $2"; shift 2
case "$sub" in
  "secret list") cat "$STUB_DIR/bws_list.json" ;;
  "project list") cat "$STUB_DIR/bws_projects.json" ;;
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
    return f"# Syncthing\n\n| Name | ID prefix | Live names | Tailscale IP |\n|---|---|---|---|\n{rows}\n"


class Fixture:
    def __init__(self, test, secrets_json=None, keys_present=(), issues=None, scrub_fails=False, renamed=False,
                 actions_secrets=(), mapping=None):
        self.work = Path(tempfile.mkdtemp(prefix="skills-27-"))
        test.addCleanup(shutil.rmtree, self.work, True)
        self.stub = self.work / "stub"
        fx = self.stub / "fixtures"
        bin_dir = self.work / "bin"
        self.checkout = self.work / "checkout"
        origin = self.work / "origin.git"
        for directory in (fx, bin_dir, self.checkout, self.stub / "remotes" / "deanjstone"):
            directory.mkdir(parents=True, exist_ok=True)
        for name, body in (("gh", GH_STUB), ("bws", BWS_STUB)):
            (bin_dir / name).write_text(body)
            (bin_dir / name).chmod((bin_dir / name).stat().st_mode | stat.S_IXUSR)

        # The history as it is: one commit with the addresses in the table, then the scrub.
        git(self.checkout, "init", "-q", "-b", "main")
        git(self.checkout, "config", "user.name", "Owner")
        git(self.checkout, "config", "user.email", OWNER_EMAIL)
        (self.checkout / "scripts" / "owner-steps").mkdir(parents=True)
        shutil.copy(SCRIPT, self.checkout / "scripts" / "owner-steps" / "27.sh")
        shutil.copy(ROOT / "scripts" / "scrub-scan.sh", self.checkout / "scripts" / "scrub-scan.sh")
        shutil.copy(ROOT / ".gitleaks.toml", self.checkout / ".gitleaks.toml")
        skill = self.checkout / "skills" / "syncthing-pair"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(table(ADDRESS))
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "feat: first")
        (skill / "SKILL.md").write_text("Read each address with `bws secret list`: " + ", ".join(KEYS) + "\n")
        leak = f"host {LEAK}\n" if scrub_fails else "clean\n"
        (self.checkout / ("leak.txt" if scrub_fails else "ok.txt")).write_text(leak)
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "chore: scrub")
        git(self.work, "init", "-q", "--bare", "-b", "main", str(origin))
        git(self.checkout, "remote", "add", "origin", str(origin))
        git(self.checkout, "push", "-q", "origin", "main")
        git(self.checkout, "fetch", "-q", "origin")

        listing = [
            {"key": ANCHOR, "id": f"id-{ANCHOR}", "projectId": "proj-personal", "value": "device-id-VALUE"},
            {"key": "mapped-bws-key", "id": "id-mapped", "projectId": "proj-personal", "value": SECRET_VALUE},
        ] + [
            {"key": key, "id": f"id-{key}", "projectId": "proj-personal", "value": "v"} for key in keys_present
        ]
        (self.stub / "bws_list.json").write_text(json.dumps(listing))
        (self.stub / "bws_projects.json").write_text(json.dumps([{"id": "proj-personal", "name": "personal-machine-secrets"}]))

        description = "A test description."
        if renamed:
            (fx / "repo_skills-archive.json").write_text(
                json.dumps({"private": True, "full_name": "deanjstone/skills-archive", "description": description})
            )
            (self.stub / "renamed").write_text("")
        else:
            (fx / "repo_skills.json").write_text(
                json.dumps({"private": True, "full_name": "deanjstone/skills", "description": description})
            )
        numbers = [16, 17, 27, 28]
        (fx / "issues.json").write_text(json.dumps([{"number": n} for n in reversed(numbers)]))
        for number in numbers:
            body = (issues or {}).get(number, "plain text")
            (fx / f"issue_{number}.json").write_text(json.dumps({"title": f"issue {number}", "body": body, "comments": []}))
        (fx / "secrets.json").write_text(json.dumps([{"name": name} for name in actions_secrets]))
        (fx / "variables.json").write_text(json.dumps([]))
        (self.work / "bws_token").write_text("BWS_ACCESS_TOKEN=machine-token\n")
        self.mapping = mapping
        self.bin = bin_dir

    def run(self, *args):
        env = {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "HOME": str(self.work),
            "STUB_DIR": str(self.stub),
            "SKILLS_BWS_TOKEN_FILE": str(self.work / "bws_token"),
            "SKILLS_GIT_REMOTE_BASE": f"file://{self.stub / 'remotes'}",
        }
        if self.mapping:
            env["SKILLS_ACTIONS_SECRETS"] = self.mapping
        result = subprocess.run(
            ["bash", str(self.checkout / "scripts" / "owner-steps" / "27.sh"), *args],
            capture_output=True, text=True, cwd=self.checkout, env=env, timeout=120,
        )
        return result.returncode, result.stdout + result.stderr

    def log(self, name):
        path = self.stub / name
        return path.read_text() if path.exists() else ""


def assert_no_value(test, output):
    for value in [*ADDRESS.values(), LEAK, SECRET_VALUE, OWNER_EMAIL, HEX]:
        test.assertNotIn(value, output)


@unittest.skipUnless(HAVE_TOOLS, "jq, git and gitleaks are needed (main CI has no gitleaks)")
class OwnerStep27Tests(unittest.TestCase):
    def test_rejects_unknown_arguments(self):
        status, _ = Fixture(self).run("--bogus")
        self.assertEqual(status, 2)

    def test_dry_run_reads_state_prints_every_action_changes_nothing_and_prints_no_value(self):
        fixture = Fixture(self)
        status, output = fixture.run("--dry-run")
        self.assertEqual(status, 0, output)
        self.assertIn("pre-flight ok: the scrubbed tree passes the scrub scan", output)
        for action in (
            "rename deanjstone/skills to skills-archive",
            "create deanjstone/skills as a PRIVATE repository",
            *[f"Secrets Manager {key}" for key in KEYS],
            "transfer the open issues",
            "make deanjstone/skills public",
            "fork pull-request approval policy",
            "BWS_ACCESS_TOKEN",
            "CI_RUNS_ON",
            "local checkouts to re-clone",
        ):
            self.assertIn(action, output)
        self.assertIn("skip 27 28", output)
        assert_no_value(self, output)
        mutating = [l for l in fixture.log("calls.log").splitlines() if re.search(r"PATCH|repo create|repo edit|secret set|issue transfer|-X PUT", l)]
        self.assertEqual(mutating, [])
        self.assertEqual(fixture.log("bws_created.log"), "")
        self.assertEqual(fixture.log("secrets_set.log"), "")

    def test_dry_run_stops_before_anything_when_the_tree_would_still_leak(self):
        fixture = Fixture(self, scrub_fails=True)
        status, output = fixture.run("--dry-run")
        self.assertEqual(status, 1)
        self.assertIn("pre-flight FAILED: the scrubbed tree passes the scrub scan", output)
        self.assertNotIn(LEAK, output)
        self.assertNotRegex(fixture.log("calls.log"), r"PATCH|repo create")

    def test_dry_run_reports_issues_whose_text_still_carries_a_private_value(self):
        status, output = Fixture(self, issues={16: f"see {HEX} here"}).run("--dry-run")
        self.assertEqual(status, 0, output)
        self.assertIn("issue 16: 1 finding", output)
        self.assertNotIn(HEX, output)

    def test_a_missing_anchor_secret_stops_a_real_run_before_any_change(self):
        fixture = Fixture(self)
        listing = [e for e in json.loads(fixture.log("bws_list.json")) if e["key"] != ANCHOR]
        (fixture.stub / "bws_list.json").write_text(json.dumps(listing))
        status, output = fixture.run()
        self.assertEqual(status, 1)
        self.assertIn(f"pre-flight FAILED: Secrets Manager holds {ANCHOR}", output)
        self.assertNotRegex(fixture.log("calls.log"), r"PATCH|repo create")

    def test_an_actions_secret_with_no_secrets_manager_source_is_listed_and_stops_a_real_run(self):
        fixture = Fixture(self, actions_secrets=["SOME_TOKEN"])
        status, output = fixture.run("--dry-run")
        self.assertEqual(status, 0, output)
        self.assertIn("pre-flight MISSING (owner step before the real run): Actions secret SOME_TOKEN has a Secrets Manager source", output)
        status, output = fixture.run()
        self.assertEqual(status, 1)
        self.assertIn("pre-flight FAILED: Actions secret SOME_TOKEN has a Secrets Manager source", output)
        self.assertNotRegex(fixture.log("calls.log"), r"PATCH|repo create")

    def test_a_mapped_actions_secret_is_set_by_name_from_secrets_manager(self):
        fixture = Fixture(self, actions_secrets=["SOME_TOKEN"], mapping="SOME_TOKEN=mapped-bws-key")
        status, output = fixture.run()
        self.assertEqual(status, 0, output)
        assert_no_value(self, output)
        self.assertEqual((fixture.stub / "secret_SOME_TOKEN.value").read_text(), SECRET_VALUE)

    def test_a_real_run_stops_before_public_when_a_transferred_issue_leaks(self):
        fixture = Fixture(self, issues={16: f"see {HEX} here"})
        status, output = fixture.run()
        self.assertEqual(status, 3, output)
        assert_no_value(self, output)
        calls = fixture.log("calls.log")
        self.assertIn("gh api -X PATCH repos/deanjstone/skills -f name=skills-archive", calls)
        self.assertIn("gh repo create deanjstone/skills --private", calls)
        self.assertEqual(fixture.log("transfers.log").split(), ["16", "17"])
        self.assertFalse((fixture.stub / "public").exists())
        self.assertIn("stopping before the repository goes public", output)
        self.assertIn("issue 1016", output)
        self.assertNotIn("--visibility public", calls)

    def test_a_clean_real_run_goes_public_in_order_and_never_pushes_deploy(self):
        fixture = Fixture(self)
        status, output = fixture.run()
        self.assertEqual(status, 0, output)
        assert_no_value(self, output)
        calls = fixture.log("calls.log")
        self.assertIn("gh repo edit deanjstone/skills --visibility public --accept-visibility-change-consequences", calls)
        self.assertIn("fork-pr-contributor-approval -f approval_policy=all_external_contributors", calls)
        self.assertLess(calls.index("repo create"), calls.index("issue transfer"))
        self.assertLess(calls.index("issue transfer"), calls.index("--visibility public"))
        self.assertLess(calls.index("--visibility public"), calls.index("fork-pr-contributor-approval"))
        self.assertIn("--description", calls)
        self.assertIsNone(re.search(r"git push[^\n]*\bdeploy\b", output))
        self.assertFalse((fixture.stub / "remotes" / "deanjstone" / "skills.git" / "refs" / "heads" / "deploy").exists())
        self.assertIn("local checkouts to re-clone", output)
        self.assertIn("archive#16 -> skills#1016", output)

    def test_the_new_history_is_one_commit_of_the_scrubbed_tree(self):
        fixture = Fixture(self)
        status, output = fixture.run()
        self.assertEqual(status, 0, output)
        bare = fixture.stub / "remotes" / "deanjstone" / "skills.git"
        self.assertEqual(git(bare, "rev-list", "--count", "main"), "1")
        tree = git(bare, "ls-tree", "-r", "--name-only", "main").splitlines()
        self.assertIn("ok.txt", tree)
        text = git(bare, "show", "main:skills/syncthing-pair/SKILL.md")
        for address in ADDRESS.values():
            self.assertNotIn(address, text)

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

    def test_resumes_after_a_rename_without_renaming_again(self):
        fixture = Fixture(self, renamed=True)
        status, output = fixture.run()
        self.assertEqual(status, 0, output)
        self.assertNotIn("-X PATCH", fixture.log("calls.log"))
        self.assertIn("gh repo create deanjstone/skills --private", fixture.log("calls.log"))


class OwnerStep27TextTests(unittest.TestCase):
    code = re.sub(r"(?m)^\s*#.*$", "", SCRIPT.read_text())

    def test_it_never_promotes_pushes_deploy_or_starts_a_workflow(self):
        self.assertIsNone(re.search(r"promote\.sh|git push[^\n]*deploy|gh workflow run|refs/heads/deploy", self.code))

    def test_it_never_runs_a_cloudflare_or_wrangler_write(self):
        self.assertIsNone(re.search(r"wrangler|api\.cloudflare\.com", self.code))

    def test_it_never_gives_a_secret_to_gh_on_the_command_line(self):
        self.assertIsNone(re.search(r"gh secret set[^\n]*(--body|-b )", self.code))


if __name__ == "__main__":
    unittest.main()
