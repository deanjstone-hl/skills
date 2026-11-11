#!/usr/bin/env bash
# Decides whether a promotion to `deploy` has anything to release (argus-config#1167).
# Prints `releasable=true|false` to $GITHUB_OUTPUT (stdout when unset).
#
# Looks at the commits since the last v* tag (all of them with no tag yet) and says true
# when one is a feat, fix, perf or revert, or a breaking change (a `!` after the type, or a
# BREAKING CHANGE footer). That is semantic-release's default commit analysis, so a
# promotion made only of chore, docs, ci, test and refactor commits releases nothing and
# release.yml skips both the test and the version.
#
# Run it from a checkout with full history and tags (fetch-depth: 0).
set -euo pipefail

last_tag="$(git describe --tags --abbrev=0 --match 'v*' 2> /dev/null || true)"
range="HEAD"
[[ -z "$last_tag" ]] || range="${last_tag}..HEAD"

releasable=false
subject_pattern='^(feat|fix|perf|revert)(\([^)]*\))?!?:|^[a-z]+(\([^)]*\))?!:'
while IFS= read -r -d '' message; do
  subject="${message%%$'\n'*}"
  if [[ "$subject" =~ $subject_pattern ]] || [[ "$message" =~ (^|$'\n')BREAKING[\ -]CHANGE: ]]; then
    releasable=true
    break
  fi
done < <(git log -z --format=%B "$range")

echo "release-needed: releasable=$releasable (${last_tag:-no tag yet}..HEAD)" >&2
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  printf 'releasable=%s\n' "$releasable" >> "$GITHUB_OUTPUT"
else
  printf 'releasable=%s\n' "$releasable"
fi
