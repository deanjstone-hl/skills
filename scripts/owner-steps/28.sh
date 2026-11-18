#!/usr/bin/env bash
# Owner step for skills/30: make deanjstone/skills public IN PLACE. Same repository, so its
# history, issues, tags, `deploy`, the T3 project and both local clones all stay.
# Read docs/public-cutover.md first. It replaces the fresh-history cutover of skills/27.
#
# Run on WSL2 or homelab, as ONE approved command, from a checkout of main at the approved commit
# (clean, equal to origin/main, and origin/main equal to the tip of main on GitHub):
#   bash scripts/owner-steps/28.sh --dry-run    # read state, print every action, change nothing
#   bash scripts/owner-steps/28.sh
#
# What it does, in this order. Each step checks the state first, so a run that stopped can be
# run again (idempotent):
#   1. Writes the four Tailscale addresses that skills/syncthing-pair used to carry into
#      Bitwarden Secrets Manager (BWS), from the last commit of this repo's history that still
#      held them, into the project of the existing `syncthing-device-homelab` secret. An
#      existing secret is left as it is.
#   2. Scans the title, body, comments and reviews of EVERY issue and pull request, open and
#      closed, plus every inline review comment, with the scrub rules. Any hit stops the run
#      BEFORE the flip (exit 3): edit what it names, then run this script again.
#   3. Deletes the Actions variable CI_RUNS_ON if it is there (the workflows run on
#      ubuntu-latest). Any other variable is left alone and listed.
#   4. Makes the repository public (gh repo edit --visibility public).
#   5. Sets the fork pull-request approval policy to all_external_contributors. GitHub refuses
#      to read or write it while the repository is private, so it can only come after step 4.
#   6. Verifies: the repository is public, the policy is set, the four keys exist (names only)
#      and CI_RUNS_ON is gone.
# The pre-flight (also under --dry-run) needs the tree at HEAD to pass scripts/scrub-scan.sh and
# no self-hosted runner to be registered on the repository.
# It never pushes `deploy`, never runs promote.sh, never starts a workflow and never renames,
# transfers or deletes anything.
#
# Secrets: read inside this script from BWS, never printed, logged or put in a gh argument. `bws`
# 2.1.0 has no stdin form for a value, so a value being stored is in that one `bws` process's
# arguments for a moment, visible only to this user on this host. It prints only names and counts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OWNER="${SKILLS_OWNER:-deanjstone}"
REPO="skills"
FULL="$OWNER/$REPO"
SOURCE_REF="${SKILLS_SOURCE_REF:-origin/main}"
BWS_TOKEN_FILE="${SKILLS_BWS_TOKEN_FILE:-$HOME/.bws_token}"
LIST_LIMIT=1000
POLICY="all_external_contributors"
RUNNER_VARIABLE="CI_RUNS_ON"

ANCHOR_KEY="syncthing-device-homelab"
IP_NAMES=(wsl lgn5 homelab dj15)
ip_key() { echo "syncthing-tailscale-ip-$1"; }
ip_row() {
  case "$1" in wsl) echo WSL ;; lgn5) echo LGN5 ;; homelab) echo homelab ;; dj15) echo dj15-SyncTrain ;; esac
}

DRY_RUN=0
case "${1:-}" in
  "") ;;
  --dry-run) DRY_RUN=1 ;;
  *) echo "usage: $0 [--dry-run]" >&2; exit 2 ;;
esac
[ "$#" -le 1 ] || { echo "usage: $0 [--dry-run]" >&2; exit 2; }

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
want() { if [ "$DRY_RUN" -eq 1 ]; then echo "[dry-run] $*"; else echo "plan: $*"; fi; }
did() { echo "+ $*"; }

secrets="" project_id="" old_blob=""

secret_id() { jq -r --arg k "$1" '[.[] | select(.key == $k)][0].id // empty' <<< "$secrets"; }
secret_set() { [ -n "$(secret_id "$1")" ]; }

repo_json() { gh api "repos/$FULL" 2> /dev/null || true; }
repo_is_public() { [ "$(jq -r '.private | tostring' <<< "$(repo_json)")" = "false" ]; }

# ---- pre-flight: read-only, also under --dry-run -------------------------------------------

preflight_failed=0
preflight_need() {
  local description="$1"; shift
  if "$@" > /dev/null 2>&1; then
    echo "pre-flight ok: $description"
  else
    echo "pre-flight FAILED: $description" >&2
    preflight_failed=1
  fi
}

have_tools() {
  local tool
  for tool in gh git jq bws gitleaks; do command -v "$tool" > /dev/null || return 1; done
}
gh_authenticated() { gh auth status; }
source_is_clean_and_current() {
  [ -z "$(git -C "$ROOT" status --porcelain)" ] || return 1
  git -C "$ROOT" rev-parse --verify --quiet "$SOURCE_REF^{commit}" > /dev/null || return 1
  [ "$(git -C "$ROOT" rev-parse HEAD)" = "$(git -C "$ROOT" rev-parse "$SOURCE_REF")" ]
}
source_is_tip_of_main_on_github() {
  local tip
  tip=$(gh api "repos/$FULL/branches/main" | jq -r '.commit.sha // empty') || return 1
  [ -n "$tip" ] && [ "$tip" = "$(git -C "$ROOT" rev-parse "$SOURCE_REF")" ]
}
repo_is_ours() { [ "$(jq -r '.full_name // empty' <<< "$(repo_json)" | tr '[:upper:]' '[:lower:]')" = "$FULL" ]; }
head_is_scrubbed() { bash "$ROOT/scripts/scrub-scan.sh" --head; }
no_repo_runner() { [ "$(gh api "repos/$FULL/actions/runners" | jq -r '.total_count // 0')" -eq 0 ]; }
load_secrets() {
  set -a
  # shellcheck source=/dev/null
  . "$BWS_TOKEN_FILE"
  set +a
  secrets=$(bws secret list -o json) || return 1
  jq -e 'type == "array"' <<< "$secrets"
}
resolve_project() {
  project_id=$(jq -r --arg k "$ANCHOR_KEY" '[.[] | select(.key == $k)][0].projectId // empty' <<< "$secrets")
  [ -n "$project_id" ]
}

# The last commit whose syncthing-pair skill still held the addresses (a table row per node, the
# Tailscale IP in its last cell, and none of the key names): the source of the BWS values.
find_unscrubbed_skill() {
  local sha blob
  while read -r sha; do
    blob=$(git -C "$ROOT" show "$sha:skills/syncthing-pair/SKILL.md" 2> /dev/null) || continue
    if ! grep -q 'syncthing-tailscale-ip-' <<< "$blob"; then old_blob="$blob"; return 0; fi
  done < <(git -C "$ROOT" log --format=%H -- skills/syncthing-pair/SKILL.md)
  return 1
}
seed_value() {
  local row value
  row=$(ip_row "$1")
  # Only the devices table: its second cell is a 7-character Syncthing ID prefix. The topology
  # table above it also has a row named homelab, whose last cell is an address with a port.
  value=$(awk -F'|' -v n="$row" '{ c = $2; id = $3; gsub(/[ `]/, "", c); gsub(/[ `]/, "", id); if (c == n && id ~ /^[A-Z0-9]{7}$/) { v = $(NF - 1); gsub(/[ `]/, "", v); print v; exit } }' <<< "$old_blob")
  [[ "$value" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
  printf '%s' "$value"
}
seeds_are_derivable() {
  local name missing=0
  for name in "${IP_NAMES[@]}"; do
    secret_set "$(ip_key "$name")" && continue
    [ -n "$old_blob" ] || find_unscrubbed_skill || { missing=1; continue; }
    seed_value "$name" > /dev/null || missing=1
  done
  [ "$missing" -eq 0 ]
}

# scan_text: the number of scrub-rule findings in the text on stdin. The text is never printed.
scan_text() {
  local report
  report=$(gitleaks stdin --config "$ROOT/.gitleaks.toml" --redact=100 --no-banner --log-level error \
    --report-format json --report-path /dev/stdout --exit-code 0) || return 1
  jq 'length' <<< "$report"
}

# scan_items <label> <json array>: each item's title, body, comments and reviews, one scan per
# item. Prints "  <label> N: K finding(s)" for a hit; returns 1 if there was one.
scan_items() {
  local label="$1" json="$2" item number count hit=0
  while read -r item; do
    [ -n "$item" ] || continue
    number=$(jq -r '.number // .id' <<< "$item")
    count=$(jq -r '[.title // empty, .body // empty, (.comments[]? | .body), (.reviews[]? | .body)] | join("\n\n")' <<< "$item" | scan_text) \
      || die "could not scan $label $number"
    if [ "$count" -gt 0 ]; then echo "  $label $number: $count finding(s)"; hit=1; fi
  done < <(jq -c '.[]' <<< "$json")
  [ "$hit" -eq 0 ]
}

# scan_everything: every issue, pull request and inline review comment, open and closed. Returns 1
# on any finding. A list that reaches its limit may be cut short, so it is an error.
scan_everything() {
  local issues prs review_comments hit=0
  issues=$(gh issue list -R "$FULL" --state all --limit "$LIST_LIMIT" --json number,title,body,comments) || die "could not list the issues"
  prs=$(gh pr list -R "$FULL" --state all --limit "$LIST_LIMIT" --json number,title,body,comments,reviews) || die "could not list the pull requests"
  review_comments=$(gh api "repos/$FULL/pulls/comments" --paginate | jq -s 'add // []') || die "could not list the review comments"
  [ "$(jq 'length' <<< "$issues")" -lt "$LIST_LIMIT" ] || die "the issue list reached its limit ($LIST_LIMIT): raise LIST_LIMIT"
  [ "$(jq 'length' <<< "$prs")" -lt "$LIST_LIMIT" ] || die "the pull request list reached its limit ($LIST_LIMIT): raise LIST_LIMIT"
  echo "  scanned: $(jq 'length' <<< "$issues") issues, $(jq 'length' <<< "$prs") pull requests, $(jq 'length' <<< "$review_comments") inline review comments (open and closed)"
  scan_items "issue" "$issues" || hit=1
  scan_items "pull request" "$prs" || hit=1
  scan_items "review comment" "$review_comments" || hit=1
  [ "$hit" -eq 0 ]
}

policy_now() { gh api "repos/$FULL/actions/permissions/fork-pr-contributor-approval" | jq -r '.approval_policy // empty'; }
variable_names() { gh variable list -R "$FULL" --json name | jq -r '.[].name'; }
has_runner_variable() {
  local names
  names=$(variable_names) || return 1
  grep -qx "$RUNNER_VARIABLE" <<< "$names"
}

echo "skills/30 flip: $FULL goes public in place"
preflight_need "gh, git, jq, bws and gitleaks are installed" have_tools
preflight_need "gh is signed in" gh_authenticated
preflight_need "this checkout is clean and is exactly $SOURCE_REF" source_is_clean_and_current
if [ "$preflight_failed" -eq 0 ]; then
  preflight_need "$SOURCE_REF is the tip of main on GitHub" source_is_tip_of_main_on_github
  preflight_need "$FULL exists" repo_is_ours
fi
if [ "$preflight_failed" -eq 0 ]; then
  preflight_need "the scrubbed tree passes the scrub scan" head_is_scrubbed
  preflight_need "no self-hosted runner is registered on the repository" no_repo_runner
  preflight_need "$BWS_TOKEN_FILE exists (Secrets Manager access)" test -f "$BWS_TOKEN_FILE"
fi
if [ "$preflight_failed" -eq 0 ]; then
  preflight_need "Secrets Manager answers (bws secret list)" load_secrets
fi
if [ "$preflight_failed" -eq 0 ]; then
  preflight_need "Secrets Manager holds $ANCHOR_KEY (its project receives the new keys)" resolve_project
fi
if [ "$preflight_failed" -eq 0 ]; then
  preflight_need "every missing Tailscale address is in this repo's history" seeds_are_derivable
fi
[ "$preflight_failed" -eq 0 ] || { echo "stopping: nothing was changed" >&2; exit 1; }

# ---- the state, and the plan ---------------------------------------------------------------

public=0
repo_is_public && public=1
secret_names=$(gh secret list -R "$FULL" --json name | jq -r '[.[].name] | join(", ")') || die "could not list the Actions secrets"
variables_listed=$(variable_names | paste -sd, - | sed 's/,/, /g') || die "could not list the Actions variables"
hooks=$(gh api "repos/$FULL/hooks" | jq 'length') || die "could not list the webhooks"

echo
echo "State: $FULL is $([ "$public" -eq 1 ] && echo public || echo private)"
echo "Actions secrets (names): $secret_names"
echo "Actions variables (names): $variables_listed"
echo "Webhooks: $hooks"
echo

for name in "${IP_NAMES[@]}"; do
  key=$(ip_key "$name")
  if secret_set "$key"; then echo "Secrets Manager $key: already set, left as is"
  else want "Secrets Manager $key: create (value from this repo's history, in the project of $ANCHOR_KEY; never printed)"; fi
done

want "scan every issue and pull request, open and closed, and every inline review comment, with the scrub rules; stop before the flip on any finding"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "Items carrying a private value (rule findings, values redacted):"
  if scan_everything; then echo "  none"; dirty=0; else dirty=1; fi
  [ "$dirty" -eq 0 ] || echo "  A real run stops before the flip on these: edit them, then run it again."
fi

if has_runner_variable; then want "delete the Actions variable $RUNNER_VARIABLE (the workflows run on ubuntu-latest)"
else echo "Actions variable $RUNNER_VARIABLE: not present, nothing to delete"; fi

if [ "$public" -eq 1 ]; then echo "flip: already public"
else want "make $FULL public (gh repo edit --visibility public --accept-visibility-change-consequences)"; fi

if [ "$public" -eq 1 ]; then
  echo "The fork pull-request approval policy is $(policy_now)"
else
  echo "The fork pull-request approval policy cannot be read while the repository is private (GitHub refuses it)"
fi
want "set the fork pull-request approval policy of $FULL to $POLICY"

if [ "$DRY_RUN" -eq 1 ]; then
  echo
  echo "[dry-run] verify (a real run): repository public, policy $POLICY, the four Secrets Manager keys present, $RUNNER_VARIABLE gone"
  echo "[dry-run] never pushes deploy, never promotes, never starts a workflow: the repository is not renamed, transferred or deleted"
  echo "[dry-run] done: nothing was changed"
  exit 0
fi

# ---- changes -------------------------------------------------------------------------------

# 1. Secrets Manager
for name in "${IP_NAMES[@]}"; do
  key=$(ip_key "$name")
  secret_set "$key" && continue
  [ -n "$old_blob" ] || find_unscrubbed_skill || die "no unscrubbed syncthing-pair skill in history for $key"
  value=$(seed_value "$name") || die "no value for $key"
  bws secret create --note "syncthing-pair Tailscale address (skills/30)" -o none "$key" "$value" "$project_id" || die "could not create $key"
  unset value
  did "created Secrets Manager secret $key"
done
secrets=$(bws secret list -o json) || die "could not re-read Secrets Manager"

# 2. scan everything, right before the flip
echo "Scanning every issue, pull request and review comment:"
if ! scan_everything; then
  echo "stopping before the repository goes public: edit the items above in $FULL (https://github.com/$FULL), then run this script again" >&2
  exit 3
fi

# 3. the runner variable
if has_runner_variable; then
  gh variable delete "$RUNNER_VARIABLE" -R "$FULL"
  did "deleted the Actions variable $RUNNER_VARIABLE"
fi

# 4. public
if [ "$public" -eq 0 ]; then
  gh repo edit "$FULL" --visibility public --accept-visibility-change-consequences
  did "made $FULL public"
fi

# 5. fork pull-request approval policy
gh api -X PUT "repos/$FULL/actions/permissions/fork-pr-contributor-approval" -f "approval_policy=$POLICY" > /dev/null
did "set the fork pull-request approval policy to $POLICY"

# ---- verify --------------------------------------------------------------------------------

verify_failed=0
verify_check() {
  local description="$1"; shift
  if "$@" > /dev/null 2>&1; then echo "verify ok: $description"; else echo "verify FAILED: $description" >&2; verify_failed=1; fi
}
repo_is_now_public() { repo_is_public; }
policy_is_set() { [ "$(policy_now)" = "$POLICY" ]; }
key_exists() { secret_set "$1"; }
runner_variable_is_gone() { ! has_runner_variable; }
verify_check "$FULL repository is public" repo_is_now_public
verify_check "the fork pull-request approval policy is $POLICY" policy_is_set
for name in "${IP_NAMES[@]}"; do
  verify_check "Secrets Manager holds $(ip_key "$name")" key_exists "$(ip_key "$name")"
done
verify_check "$RUNNER_VARIABLE is gone" runner_variable_is_gone
echo
echo "Left for the owner: re-point nothing (same repository); approve the next promotion on the ops-hub card as usual. Decide whether any of the private-marker names in docs/public-cutover.md should go too."
[ "$verify_failed" -eq 0 ] || exit 1
