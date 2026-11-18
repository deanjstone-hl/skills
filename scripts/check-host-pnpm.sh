#!/usr/bin/env bash
# The pnpm check for a job on a homelab runner (homelab#475): pnpm/action-setup only runs on
# GitHub-hosted runners, so a self-hosted job checks the host's pnpm against the root
# `packageManager` pin instead. corepack or pnpm >= 9.7 run the pinned version themselves, so
# this fails only when that is switched off. It replaces the host-pnpm action of the private
# argus repo, which does not resolve from this repository. Run from the repository root.
set -euo pipefail

fnm_bin="$HOME/.local/share/fnm/aliases/default/bin"
if [ -d "$fnm_bin" ]; then
  [ -z "${GITHUB_PATH:-}" ] || echo "$fnm_bin" >> "$GITHUB_PATH"
  export PATH="$fnm_bin:$PATH"
fi

pin="$(node -p "require('./package.json').packageManager || ''")"
expected="${pin#pnpm@}"
expected="${expected%%+*}"
if [ "$pin" = "$expected" ] || [ -z "$expected" ]; then
  echo "::error::package.json has no pnpm@<version> packageManager pin (got '$pin')"
  exit 1
fi

actual="$(pnpm --version)"
echo "pnpm --version: $actual (packageManager pin: $expected)"
if [ "$actual" != "$expected" ]; then
  echo "::error::pnpm $actual does not match the packageManager pin $expected"
  exit 1
fi
