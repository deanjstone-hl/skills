#!/usr/bin/env bash
# Name how a project or package actually deploys, so the deploy skill can defer to
# that mechanism instead of re-implementing it. Read-only: never builds or deploys.
#
# Usage: detect.sh [dir]   (default: the current directory)
#
# Prints one "<kind>\t<path relative to the repo root>" line per mechanism found, in
# precedence order, or "none":
#   ci-on-promote    a workflow that deploys on push to the deploy branch, which a
#                    human advances (the deploy-branch model; a merge to main does not
#                    deploy)
#   ci-on-merge      a workflow that deploys on push to main (a repo not yet on the
#                    deploy-branch model). In a monorepo, a package only counts a
#                    workflow whose text names its path
#   promote-script   scripts/promote.sh at the repo root, the promotion mechanism
#   runbook          docs/deployment.md, docs/deploy.md, DEPLOY.md or DEPLOYMENT.md
#   deploy-script    deploy.sh
#   package-script   a "deploy" script in package.json
#   wrangler-config  wrangler.toml / wrangler.json / wrangler.jsonc
# Exits 2 when dir is not a directory.
set -euo pipefail

target="${1:-.}"
if [[ ! -d "$target" ]]; then
  echo "detect.sh: not a directory: $target" >&2
  exit 2
fi
target="$(cd "$target" && pwd -P)"
root="$(git -C "$target" rev-parse --show-toplevel 2>/dev/null || printf '%s' "$target")"
root="$(cd "$root" && pwd -P)"
rel="${target#"$root"}"
rel="${rel#/}"
prefix="${rel:+$rel/}"

found=0
report() {
  printf '%s\t%s\n' "$1" "${2#"$root"/}"
  found=1
}

is_deploy_workflow() {
  local file="$1"
  [[ "$(basename "$file")" == *deploy* ]] \
    || grep -Eq 'wrangler-action|wrangler +(pages +)?deploy' "$file"
}

triggers_on_push_to() {
  local branch="$1" file="$2"
  grep -Eq '^[[:space:]]*push:' "$file" || return 1
  grep -Eq "branches:.*[^[:alnum:]_-]${branch}([^[:alnum:]_-]|\$)" "$file" \
    || grep -Eq "^[[:space:]]*-[[:space:]]*[\"']?${branch}[\"']?[[:space:]]*\$" "$file"
}

shopt -s nullglob
for workflow in "$root"/.github/workflows/*.yml "$root"/.github/workflows/*.yaml; do
  is_deploy_workflow "$workflow" || continue
  if triggers_on_push_to deploy "$workflow"; then
    kind=ci-on-promote
  elif triggers_on_push_to main "$workflow"; then
    kind=ci-on-merge
  else
    continue
  fi
  if [[ -n "$rel" ]] && ! grep -qF "$prefix" "$workflow"; then
    continue
  fi
  report "$kind" "$workflow"
done

[[ -f "$root/scripts/promote.sh" ]] && report promote-script "$root/scripts/promote.sh"

for runbook in docs/deployment.md docs/deploy.md DEPLOY.md DEPLOYMENT.md; do
  [[ -f "$target/$runbook" ]] && report runbook "$target/$runbook"
done

[[ -f "$target/deploy.sh" ]] && report deploy-script "$target/deploy.sh"

if [[ -f "$target/package.json" ]] && grep -Eq '"deploy"[[:space:]]*:' "$target/package.json"; then
  report package-script "$target/package.json"
fi

for config in wrangler.toml wrangler.json wrangler.jsonc; do
  [[ -f "$target/$config" ]] && report wrangler-config "$target/$config"
done

if [[ "$found" -eq 0 ]]; then
  echo none
fi
