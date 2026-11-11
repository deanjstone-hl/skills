"""Rollback wiring for deploy workflows (argus#1179, ops-hub rollback card, argus#1068).

The ops hub's Roll back card dispatches every workflow that ran on a push to `deploy`, less the
release workflow (`release*.yml`), at a release tag. A workflow that runs on a push to `deploy` must
therefore take that dispatch and pass the tag to its checkout guard, as ops-hub's `deploy.yml` does.

This repo has no such workflow today: `release.yml` is the only one on a push to `deploy`, and
nothing is installed from the repo yet (argus-config#1225). The tests fail the moment one is added
without the wiring, so the rollback card is not silently useless for it.
"""

import re
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
GUARD = Path("scripts") / "require-deploy-checkout.sh"

# The hub's own filter (apps/ops-hub/src/promotions/service.ts, RELEASE_WORKFLOW).
RELEASE_WORKFLOW = re.compile(r"(^|/)release[^/]*\.ya?ml$")


def triggers(workflow: dict) -> dict:
    # PyYAML reads the bare key `on` as the boolean True.
    on = workflow.get("on", workflow.get(True)) or {}
    return on if isinstance(on, dict) else {name: None for name in ([on] if isinstance(on, str) else on)}


def runs_on_push_to_deploy(workflow: dict) -> bool:
    on = triggers(workflow)
    if "push" not in on:
        return False
    push = on["push"]
    branches = push.get("branches") if isinstance(push, dict) else None
    return branches is None or "deploy" in branches


def rollback_gaps(root: Path) -> list[str]:
    """What each non-release workflow on a push to `deploy` lacks of the rollback wiring."""
    gaps = []
    for path in sorted((root / ".github" / "workflows").glob("*.y*ml")):
        if RELEASE_WORKFLOW.search(path.name):
            continue
        workflow = yaml.safe_load(path.read_text())
        if not runs_on_push_to_deploy(workflow):
            continue
        text = path.read_text()
        if "workflow_dispatch" not in triggers(workflow):
            gaps.append(f"{path.name}: no workflow_dispatch trigger")
        if "github.event_name == 'workflow_dispatch' && startsWith(github.ref, 'refs/tags/v')" not in text:
            gaps.append(f"{path.name}: no job `if:` that allows a dispatch at refs/tags/v*")
        if "DEPLOY_ROLLBACK_TAG" not in text:
            gaps.append(f"{path.name}: DEPLOY_ROLLBACK_TAG is never set")
        if not (root / GUARD).is_file():
            gaps.append(f"{path.name}: {GUARD} is missing")
    return gaps


class DeployRollbackWiringTests(unittest.TestCase):
    def test_every_deploy_workflow_in_this_repo_takes_a_rollback_dispatch(self):
        self.assertEqual(rollback_gaps(ROOT), [])

    def test_a_deploy_workflow_without_the_wiring_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            workflows = Path(tmp) / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "deploy.yml").write_text(
                "name: Deploy\non:\n  push:\n    branches: [deploy]\njobs:\n  deploy:\n"
                "    if: github.ref == 'refs/heads/deploy'\n    runs-on: ubuntu-latest\n    steps: []\n"
            )
            gaps = rollback_gaps(Path(tmp))
        self.assertEqual(len(gaps), 4, gaps)

    def test_a_deploy_workflow_with_the_wiring_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            workflows = Path(tmp) / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "deploy.yml").write_text(
                "name: Deploy\non:\n  push:\n    branches: [deploy]\n  workflow_dispatch:\njobs:\n  deploy:\n"
                "    if: github.ref == 'refs/heads/deploy' || (github.event_name == 'workflow_dispatch' && startsWith(github.ref, 'refs/tags/v'))\n"
                "    runs-on: ubuntu-latest\n    env:\n      DEPLOY_ROLLBACK_TAG: ${{ github.ref_type == 'tag' && github.ref_name || '' }}\n    steps: []\n"
            )
            (Path(tmp) / "scripts").mkdir()
            (Path(tmp) / GUARD).write_text("#!/usr/bin/env bash\n")
            self.assertEqual(rollback_gaps(Path(tmp)), [])

    def test_a_release_workflow_is_not_a_deploy_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            workflows = Path(tmp) / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "release.yml").write_text(
                "name: Release\non:\n  push:\n    branches: [deploy]\njobs: {}\n"
            )
            self.assertEqual(rollback_gaps(Path(tmp)), [])


if __name__ == "__main__":
    unittest.main()
