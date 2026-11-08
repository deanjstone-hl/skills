#!/usr/bin/env bash
# The repo's local check. Run it before every push; CI and the Release test job run the
# same command, so the three cannot drift.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python3 -m unittest discover -s tests
python3 scripts/check_skills.py
