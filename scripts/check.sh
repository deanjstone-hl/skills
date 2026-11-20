#!/usr/bin/env bash
# The repo's local check. Run it before every push; CI and the Release test job run the
# same command, so the three cannot drift.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# One full check at a time per host (argus-config#1506): two overlapping gates made
# systemd-oomd kill agent scopes. The re-exec waits for the host lock (HEAVY_LOCK_TIMEOUT,
# default 3600 s, then exit 75) and runs this script with HEAVY_LOCK_HELD=1 so it does not
# wait again. scripts/heavy-lock.sh is vendored from argus-config.
if [ "${HEAVY_LOCK_HELD:-}" != 1 ]; then
  exec bash "$PWD/scripts/heavy-lock.sh" bash "$PWD/scripts/check.sh" "$@"
fi
python3 -m unittest discover -s tests
python3 scripts/check_skills.py
