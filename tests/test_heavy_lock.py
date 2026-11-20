"""Host-wide heavy lock (argus-config#1506): two overlapping full checks made systemd-oomd kill
agent scopes, so the gate (scripts/check.sh) takes the lock itself, from a copy of argus-config's
scripts/heavy-lock.sh."""

import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "scripts" / "check.sh"


class HeavyLockTest(unittest.TestCase):
    def test_vendored_copy_matches_the_sha256_in_its_lock_file(self):
        digest = hashlib.sha256((ROOT / "scripts" / "heavy-lock.sh").read_bytes()).hexdigest()
        lock = (ROOT / "scripts" / "heavy-lock.lock").read_text()
        self.assertIn(f"{digest}  heavy-lock.sh", lock)

    def test_the_gate_reruns_itself_under_the_lock(self):
        text = GATE.read_text()
        self.assertIn("heavy-lock.sh", text)
        self.assertIn("HEAVY_LOCK_HELD", text)

    def test_a_busy_lock_gives_exit_75_without_running_a_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_file = str(Path(tmp) / "heavy.lock")
            holder = subprocess.Popen(
                ["bash", "-c", 'exec 9>>"$LOCK_FILE"; flock 9; echo held; sleep 30'],
                env={**os.environ, "LOCK_FILE": lock_file},
                stdout=subprocess.PIPE,
                text=True,
            )
            try:
                self.assertEqual(holder.stdout.readline().strip(), "held")
                # The gate itself runs under the lock with HEAVY_LOCK_HELD=1: a nested call must not inherit it.
                env = {key: value for key, value in os.environ.items() if key != "HEAVY_LOCK_HELD"}
                env.update(
                    HEAVY_LOCK_FILE=lock_file,
                    HEAVY_LOCK_TIMEOUT="1",
                    HEAVY_LOCK_PSI_FILE=str(Path(tmp) / "none"),
                )
                result = subprocess.run(
                    ["bash", str(GATE)], env=env, capture_output=True, text=True, timeout=30
                )
                self.assertEqual(result.returncode, 75, result.stdout + result.stderr)
                self.assertIn("waiting for the host lock", result.stderr)
                self.assertNotIn("check: step", result.stderr)
            finally:
                holder.kill()
                holder.wait()


if __name__ == "__main__":
    unittest.main()
