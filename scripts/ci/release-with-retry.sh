#!/usr/bin/env bash
# Runs semantic-release up to 3 times, each attempt from the remote tip of the release
# branch (pattern from atto1 and design-system).
#
# Why: the release branch is `deploy`, and a second promotion can land between this run's
# checkout and semantic-release's push of the tag. That shows up two ways, both safe to
# retry because nothing has been tagged or published yet:
#   1. semantic-release sees the local branch is behind, logs "is behind the remote one"
#      and exits 0 having released nothing. Left alone, the release silently does not
#      happen.
#   2. The tag push is rejected as a non-fast-forward and it exits non-zero.
#
# Before every attempt (the first included) the checkout is made to equal the remote
# branch exactly, dropping a half-finished attempt's local commits and a detached HEAD.
# That is a rebase in effect: the release is redone on top of whatever landed.
#
# Anything else that fails (bad token, a plugin error) is not a race and is not retried:
# its exit status is passed through. Still behind after the last attempt exits 1, so a
# skipped release is never green.
#
# Env: RELEASE_BRANCH (default deploy); GITHUB_TOKEN, when set, authenticates the fetch
# (the checkout has persist-credentials off); RELEASE_COMMAND overrides the command and
# exists for tests/test_release_retry.py.
set -uo pipefail

RELEASE_BRANCH="${RELEASE_BRANCH:-deploy}"
RELEASE_COMMAND="${RELEASE_COMMAND:-pnpm exec semantic-release}"
LOG="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/semantic-release.log"
MAX_ATTEMPTS=3
# `[remote rejected]` (a protected branch or a hook) is deliberately not here.
REJECTED_PATTERN='failed to push some refs|\[rejected\]|non-fast-forward|fetch first|Updates were rejected'

git_authenticated=(git)
if [ -n "${GITHUB_TOKEN:-}" ]; then
  basic=$(printf 'x-access-token:%s' "${GITHUB_TOKEN}" | base64 -w0)
  git_authenticated=(git -c "http.https://github.com/.extraheader=AUTHORIZATION: basic ${basic}")
fi

reason=""
for attempt in $(seq 1 "${MAX_ATTEMPTS}"); do
  if ! "${git_authenticated[@]}" fetch --quiet origin "${RELEASE_BRANCH}"; then
    echo "::error::could not fetch origin ${RELEASE_BRANCH}"
    exit 1
  fi
  git checkout --quiet --force -B "${RELEASE_BRANCH}" FETCH_HEAD || exit 1
  git clean --quiet -fd

  bash -c "${RELEASE_COMMAND}" 2>&1 | tee "${LOG}"
  exit_code="${PIPESTATUS[0]}"

  if [ "${exit_code}" -eq 0 ]; then
    if ! grep -q "is behind the remote one" "${LOG}"; then
      exit 0
    fi
    reason="behind"
    echo "::warning::local ${RELEASE_BRANCH} was behind the remote (attempt ${attempt} of ${MAX_ATTEMPTS})"
  elif grep -qE "${REJECTED_PATTERN}" "${LOG}"; then
    reason="rejected"
    echo "::warning::a release push was rejected, ${RELEASE_BRANCH} moved under it (attempt ${attempt} of ${MAX_ATTEMPTS})"
  else
    exit "${exit_code}"
  fi
done

if [ "${reason}" = "behind" ]; then
  echo "::error::still behind the remote after ${MAX_ATTEMPTS} attempts, release skipped"
else
  echo "::error::release push was rejected ${MAX_ATTEMPTS} times because ${RELEASE_BRANCH} kept moving, release not completed"
fi
exit 1
