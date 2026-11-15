#!/usr/bin/env bash
# Owner step for skills/27 and skills/28: cut skills over to a fresh-history PUBLIC repository.
# Read docs/public-cutover.md first.
#
# Run on WSL2, from an approval thread or a terminal, as ONE approved command, from a checkout
# of main at the merged commit (clean, equal to origin/main):
#   bash scripts/owner-steps/27.sh --dry-run    # read state, print every action, change nothing
#   bash scripts/owner-steps/27.sh
#
# What it does, in this order. Each step checks the state first, so a run that stopped can be
# run again (idempotent):
#   1. Renames deanjstone/skills to skills-archive. It stays PRIVATE. GitHub redirects the old
#      name only until a repository is created under it again, which step 3 does on purpose.
#   2. Writes the four Tailscale addresses that skills/syncthing-pair used to carry into
#      Bitwarden Secrets Manager (BWS), from the last commit of this repo's history that still
#      held them, into the project of the existing `syncthing-device-homelab` secret. An
#      existing secret is left as it is.
#   3. Creates deanjstone/skills as a PRIVATE repository from ONE squashed commit of the scrubbed
#      tree at main (scripts/scrub-scan.sh must pass on it) and pushes main. It is private
#      first because GitHub cannot transfer an issue from a private repository to a public one.
#   4. Clones the labels (a transferred issue keeps a label only if the target has it) and sets
#      the Actions secrets named in SKILLS_ACTIONS_SECRETS from BWS. Today there are none: the
#      workflows use only the read-only GITHUB_TOKEN, so BWS_ACCESS_TOKEN is deliberately not
#      created. The variable CI_RUNS_ON is not recreated (the workflows run on ubuntu-latest).
#   5. Transfers the open issues from skills-archive (gh issue transfer), oldest first, except
#      those named in SKILLS_KEEP_ISSUES (default "27 28", the cutover's own tickets).
#   6. Scans the transferred issues' text with the scrub rules. Any hit stops the run BEFORE the
#      repository goes public (exit 3): edit those issues, then run this script again.
#   7. Makes deanjstone/skills public and sets the fork pull-request approval policy to
#      all_external_contributors.
#   8. Prints the wiring to re-point and the local checkouts to re-clone on both hosts.
# It never pushes `deploy`, never runs promote.sh and never starts a workflow: the first
# promotion creates `deploy` in the new repository.
#
# Secrets: read inside this script from BWS, never printed, logged or put in a gh argument
# (`gh secret set` reads its value from stdin). `bws` 2.1.0 has no stdin form for a value, so a
# value being stored is in that one `bws` process's arguments for a moment, visible only to this
# user on this host. It prints only names, ids and counts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OWNER="${SKILLS_OWNER:-deanjstone}"
REPO="skills"
ARCHIVE="skills-archive"
SOURCE_REF="${SKILLS_SOURCE_REF:-origin/main}"
BWS_TOKEN_FILE="${SKILLS_BWS_TOKEN_FILE:-$HOME/.bws_token}"
KEEP_ISSUES="${SKILLS_KEEP_ISSUES:-27 28}"
REMOTE_BASE="${SKILLS_GIT_REMOTE_BASE:-https://github.com}"
# "NAME=bws-key" pairs: an Actions secret on the old repository and the BWS secret holding its value.
ACTIONS_SECRETS="${SKILLS_ACTIONS_SECRETS:-}"

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
export_dir=""
cleanup() { [ -z "$export_dir" ] || rm -rf "$export_dir"; }
trap cleanup EXIT

secret_id() { jq -r --arg k "$1" '[.[] | select(.key == $k)][0].id // empty' <<< "$secrets"; }
secret_value() { jq -r --arg k "$1" '[.[] | select(.key == $k)][0].value // empty' <<< "$secrets"; }
secret_set() { [ -n "$(secret_id "$1")" ]; }

repo_json() { gh api "repos/$OWNER/$1" 2> /dev/null || true; }
repo_full_name() { jq -r '.full_name // empty' <<< "$(repo_json "$1")" | tr '[:upper:]' '[:lower:]'; }
repo_is_private() { [ "$(jq -r '.private // empty' <<< "$(repo_json "$1")")" = "true" ]; }
new_repo_exists() { [ "$(repo_full_name "$REPO")" = "$OWNER/$REPO" ]; }
archive_exists() { [ "$(repo_full_name "$ARCHIVE")" = "$OWNER/$ARCHIVE" ]; }

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

# owner_need: a prerequisite only the owner can supply. A dry run lists it and carries on, so the
# plan still prints; a real run stops.
owner_missing=0
owner_notes=()
owner_need() {
  local description="$1" note="$2"; shift 2
  if "$@" > /dev/null 2>&1; then
    echo "pre-flight ok: $description"
  elif [ "$DRY_RUN" -eq 1 ]; then
    echo "pre-flight MISSING (owner step before the real run): $description"
    owner_missing=1
    owner_notes+=("$note")
  else
    echo "pre-flight FAILED: $description" >&2
    preflight_failed=1
  fi
}

have_tools() {
  local tool
  for tool in gh git jq bws gitleaks tar; do command -v "$tool" > /dev/null || return 1; done
}
gh_authenticated() { gh auth status; }
source_is_clean_and_current() {
  [ -z "$(git -C "$ROOT" status --porcelain)" ] || return 1
  git -C "$ROOT" rev-parse --verify --quiet "$SOURCE_REF^{commit}" > /dev/null || return 1
  [ "$(git -C "$ROOT" rev-parse HEAD)" = "$(git -C "$ROOT" rev-parse "$SOURCE_REF")" ]
}
repo_state_is_known() {
  # Fresh: skills is the old private repo. Renamed or resumed: skills-archive exists and is private.
  if archive_exists; then repo_is_private "$ARCHIVE"; else [ "$(repo_full_name "$REPO")" = "$OWNER/$REPO" ] && repo_is_private "$REPO"; fi
}
export_tree() {
  export_dir="$(mktemp -d)"
  git -C "$ROOT" archive "$SOURCE_REF" | tar -x -C "$export_dir"
}
tree_is_scrubbed() { bash "$ROOT/scripts/scrub-scan.sh" "$export_dir"; }
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

# secret_source <Actions secret name>: the BWS key mapped to it, or nothing.
secret_source() {
  local pair
  for pair in $ACTIONS_SECRETS; do
    [ "${pair%%=*}" = "$1" ] && { echo "${pair#*=}"; return 0; }
  done
  return 0
}
secret_has_source() {
  local key
  key=$(secret_source "$1")
  [ -n "$key" ] && secret_set "$key"
}

# scan_issue <repo> <number>: the number of scrub-rule findings in the issue's title, body and
# comments. The text goes to gitleaks on stdin and is never printed.
scan_issue() {
  local json text report
  json=$(gh issue view "$2" -R "$OWNER/$1" --json title,body,comments) || return 1
  text=$(jq -r '[.title, .body, (.comments[]? | .body)] | join("\n\n")' <<< "$json") || return 1
  report=$(gitleaks stdin --config "$ROOT/.gitleaks.toml" --redact=100 --no-banner --log-level error \
    --report-format json --report-path /dev/stdout --exit-code 0 <<< "$text") || return 1
  jq 'length' <<< "$report"
}
open_issues() { gh issue list -R "$OWNER/$1" --state open --limit 200 --json number | jq -r 'sort_by(.number) | .[].number'; }
is_kept() { [[ " $KEEP_ISSUES " == *" $1 "* ]]; }

echo "skills/27 cutover: $OWNER/$REPO -> $OWNER/$ARCHIVE (private) and a new public $OWNER/$REPO"
preflight_need "gh, git, jq, bws, gitleaks and tar are installed" have_tools
preflight_need "gh is signed in" gh_authenticated
preflight_need "this checkout is clean and is exactly $SOURCE_REF" source_is_clean_and_current
if [ "$preflight_failed" -eq 0 ]; then
  preflight_need "the repository state is known (the old private $REPO, or the private $ARCHIVE already renamed)" repo_state_is_known
  preflight_need "the tree at $SOURCE_REF exports" export_tree
fi
if [ "$preflight_failed" -eq 0 ]; then
  preflight_need "the scrubbed tree passes the scrub scan" tree_is_scrubbed
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

have_archive=0; have_new=0
archive_exists && have_archive=1
if [ "$have_archive" -eq 1 ] && new_repo_exists; then have_new=1; fi
src_repo="$REPO"; [ "$have_archive" -eq 1 ] && src_repo="$ARCHIVE"

names_of() { jq -r '[.[].name] | join(", ")' <<< "$1"; }
secret_names=$(gh secret list -R "$OWNER/$src_repo" --json name) || die "could not list the Actions secrets"
variable_names=$(gh variable list -R "$OWNER/$src_repo" --json name) || die "could not list the Actions variables"
hooks=$(gh api "repos/$OWNER/$src_repo/hooks") || die "could not list the webhooks"
runners=$(gh api "repos/$OWNER/$src_repo/actions/runners") || die "could not list the runners"

while read -r name; do
  [ -n "$name" ] || continue
  owner_need "Actions secret $name has a Secrets Manager source" \
    "Actions secret $name on $src_repo: GitHub never returns its value. Store it in Secrets Manager, then run with SKILLS_ACTIONS_SECRETS=\"$name=<bws key>\"" \
    secret_has_source "$name"
done < <(jq -r '.[].name' <<< "$secret_names")
[ "$preflight_failed" -eq 0 ] || { echo "stopping: nothing was changed" >&2; exit 1; }

echo
echo "State: old repository is $OWNER/$src_repo (private); new $OWNER/$REPO exists: $([ "$have_new" -eq 1 ] && echo yes || echo no)"
echo "Open issues in $src_repo, not transferred (SKILLS_KEEP_ISSUES): skip $KEEP_ISSUES"
echo "Actions secrets on $src_repo (names): $(names_of "$secret_names")"
echo "Actions variables on $src_repo (names): $(names_of "$variable_names")"
echo "Webhooks on $src_repo: $(jq 'length' <<< "$hooks"); repo-level runners: $(jq '.runners | length' <<< "$runners")"
echo

if [ "$have_archive" -eq 1 ]; then echo "rename: already done ($ARCHIVE exists)"
else want "rename $OWNER/$REPO to $ARCHIVE (stays private; GitHub redirects the old name until step 3 reuses it)"; fi
for name in "${IP_NAMES[@]}"; do
  key=$(ip_key "$name")
  if secret_set "$key"; then echo "Secrets Manager $key: already set, left as is"
  else want "Secrets Manager $key: create (value from this repo's history, in the project of $ANCHOR_KEY; never printed)"; fi
done
if [ "$have_new" -eq 1 ]; then echo "create: $OWNER/$REPO already exists"
else want "create $OWNER/$REPO as a PRIVATE repository, then push ONE squashed commit of the scrubbed tree at $SOURCE_REF to main (never deploy)"; fi
want "labels: gh label clone $OWNER/$ARCHIVE into $OWNER/$REPO (a transferred issue keeps a label only if the target has it)"
mapped=0
while read -r name; do
  [ -n "$name" ] || continue
  mapped=1
  want "Actions secret $name on $OWNER/$REPO: set from Secrets Manager ($(secret_source "$name"))"
done < <(jq -r '.[].name' <<< "$secret_names")
[ "$mapped" -eq 1 ] || want "Actions secrets: none to recreate; BWS_ACCESS_TOKEN is deliberately not created (no workflow reads Secrets Manager)"
want "Actions variable CI_RUNS_ON: not recreated (the workflows run on ubuntu-latest); any other variable listed above has no Secrets Manager source and is not copied"
want "transfer the open issues of $ARCHIVE to $OWNER/$REPO (gh issue transfer, oldest first; GitHub allows it only while both are private), skip $KEEP_ISSUES"

echo
echo "Issue text carrying a private value (rule findings, values redacted):"
dirty=0
while read -r number; do
  [ -n "$number" ] || continue
  is_kept "$number" && continue
  count=$(scan_issue "$src_repo" "$number") || die "could not scan issue $number"
  if [ "$count" -gt 0 ]; then echo "  issue $number: $count finding(s)"; dirty=1; fi
done < <(open_issues "$src_repo")
[ "$dirty" -eq 1 ] || echo "  none"
[ "$dirty" -eq 0 ] || echo "  A real run stops before step 7 on these (after transferring them, so they can be edited in the new repository)."
want "make $OWNER/$REPO public (gh repo edit --visibility public), only when no transferred issue has a finding"
want "set the fork pull-request approval policy of $OWNER/$REPO to all_external_contributors"

print_wiring() {
  cat <<EOF

Wiring to re-point (nothing here is automatic):
  - The first promotion creates \`deploy\` in the new repository: approve it on the ops-hub promotion card, never push it by hand. Withdraw any promotion flag for a SHA of the old history. ops-hub's promotion-repos.txt names $OWNER/$REPO and the name is unchanged.
  - Issue numbers restart. Transferred issues get new numbers (listed above as archive#N -> $REPO#M); every other old issue and pull request stays in $OWNER/$ARCHIVE. A reference to $OWNER/$REPO#N in another repository, a wayfinder map or a loop-state slot now means the NEW repository's #N: repoint anything that should mean the old history to $OWNER/$ARCHIVE#N.
  - Releases and tags stay in $ARCHIVE (v1.0.0); the new history has none. Its first commit is a \`chore\`, so a promotion cuts no version until a \`feat\` or \`fix\` lands, and the hub's Roll back card has nothing to dispatch until a release exists (this repository has no deploy workflow besides release.yml).
  - Webhooks, GitHub App installations and deploy keys on $OWNER/$ARCHIVE are not copied; Actions secrets and variables are recreated by name only as listed above.
  - Runners: $REPO has no repository-level runner and is not enrolled in the JIT dispatcher (homelab runbook jit-dispatcher.md), and its workflows run on ubuntu-latest, so there is nothing to re-point. Do not register one on the public repository.
  - Decide whether to archive $OWNER/$ARCHIVE (gh repo archive), which also stops its workflows.
  - The local checkouts to re-clone on both hosts (WSL2 and homelab): move the old one aside, then clone the new repository:
      mv ~/repos/$REPO ~/repos/$ARCHIVE && git clone https://github.com/$OWNER/$REPO.git ~/repos/$REPO
    and point the T3 project for $REPO at the new clone. Worktrees under ~/.t3/worktrees/$REPO belong to the old history: remove them (git worktree remove) once their branches are merged or abandoned.
EOF
}

if [ "$DRY_RUN" -eq 1 ]; then
  if [ "$owner_missing" -eq 1 ]; then
    echo
    echo "Owner steps before the real run (a real run stops without them):"
    for note in "${owner_notes[@]}"; do echo "  - $note"; done
  fi
  echo
  echo "[dry-run] verify (a real run): new repository public, archive private, open issues moved, main is one commit, no deploy branch"
  print_wiring | sed 's/^/[dry-run] /'
  echo "[dry-run] done: nothing was changed"
  exit 0
fi

# ---- changes -------------------------------------------------------------------------------

# 1. rename
if [ "$have_archive" -eq 0 ]; then
  gh api -X PATCH "repos/$OWNER/$REPO" -f "name=$ARCHIVE" > /dev/null
  did "renamed $OWNER/$REPO to $ARCHIVE"
  archive_exists || die "$ARCHIVE does not exist after the rename"
  repo_is_private "$ARCHIVE" || die "$ARCHIVE is not private: stop and fix it before anything else"
fi

# 2. Secrets Manager
for name in "${IP_NAMES[@]}"; do
  key=$(ip_key "$name")
  secret_set "$key" && continue
  [ -n "$old_blob" ] || find_unscrubbed_skill || die "no unscrubbed syncthing-pair skill in history for $key"
  value=$(seed_value "$name") || die "no value for $key"
  bws secret create --note "syncthing-pair Tailscale address (skills/27)" -o none "$key" "$value" "$project_id" || die "could not create $key"
  unset value
  did "created Secrets Manager secret $key"
done
secrets=$(bws secret list -o json) || die "could not re-read Secrets Manager"

# 3. the new repository, private, one squashed commit
description=$(jq -r '.description // empty' <<< "$(repo_json "$src_repo")")
if [ "$have_new" -eq 0 ]; then
  gh repo create "$OWNER/$REPO" --private --description "$description" > /dev/null
  did "created $OWNER/$REPO (private)"
fi
if ! gh api "repos/$OWNER/$REPO/branches/main" > /dev/null 2>&1; then
  src_short=$(git -C "$ROOT" rev-parse --short "$SOURCE_REF")
  git -C "$export_dir" init -q -b main
  git -C "$export_dir" add -A
  git -C "$export_dir" -c "user.name=$(git -C "$ROOT" config user.name)" -c "user.email=$(git -C "$ROOT" config user.email)" \
    commit -q -m "chore: start the public history from $ARCHIVE@$src_short" -m "The earlier history is kept, private, in $OWNER/$ARCHIVE. Refs $OWNER/$ARCHIVE#27"
  git -C "$export_dir" remote add origin "$REMOTE_BASE/$OWNER/$REPO.git"
  git -C "$export_dir" -c "credential.helper=!gh auth git-credential" push -q origin main
  did "pushed one squashed commit to $OWNER/$REPO main (from $ARCHIVE@$src_short)"
fi

# 4. labels, Actions secrets
gh label clone "$OWNER/$ARCHIVE" -R "$OWNER/$REPO" > /dev/null
did "cloned the labels of $ARCHIVE into $REPO"
while read -r name; do
  [ -n "$name" ] || continue
  key=$(secret_source "$name")
  value=$(secret_value "$key")
  [ -n "$value" ] || die "Secrets Manager has no value for $key"
  gh secret set "$name" -R "$OWNER/$REPO" < <(printf '%s' "$value") || die "could not set the Actions secret $name"
  unset value
  did "set the Actions secret $name on $OWNER/$REPO (from $key)"
done < <(jq -r '.[].name' <<< "$secret_names")

# 5. issues
echo "Issue transfers (archive -> new):"
while read -r number; do
  [ -n "$number" ] || continue
  if is_kept "$number"; then echo "  archive#$number stays (kept)"; continue; fi
  url=$(gh issue transfer "$number" "$OWNER/$REPO" -R "$OWNER/$ARCHIVE") || die "could not transfer issue $number"
  echo "  archive#$number -> $REPO#${url##*/}"
done < <(open_issues "$ARCHIVE")

# 6. scan every open issue in the new repository, the transferred ones included
dirty=0
while read -r number; do
  [ -n "$number" ] || continue
  count=$(scan_issue "$REPO" "$number") || die "could not scan issue $number"
  if [ "$count" -gt 0 ]; then echo "issue $number: $count finding(s) (values redacted)" >&2; dirty=1; fi
done < <(open_issues "$REPO")
if [ "$dirty" -eq 1 ]; then
  echo "stopping before the repository goes public: edit the issues above in $OWNER/$REPO (https://github.com/$OWNER/$REPO/issues), then run this script again" >&2
  exit 3
fi

# 7. public
if repo_is_private "$REPO"; then
  gh repo edit "$OWNER/$REPO" --visibility public --accept-visibility-change-consequences
  did "made $OWNER/$REPO public"
fi
gh api -X PUT "repos/$OWNER/$REPO/actions/permissions/fork-pr-contributor-approval" -f approval_policy=all_external_contributors > /dev/null
did "set the fork pull-request approval policy to all_external_contributors"

# ---- verify --------------------------------------------------------------------------------

verify_failed=0
verify_check() {
  local description="$1"; shift
  if "$@" > /dev/null 2>&1; then echo "verify ok: $description"; else echo "verify FAILED: $description" >&2; verify_failed=1; fi
}
new_is_public() { [ "$(jq -r '.private' <<< "$(repo_json "$REPO")")" = "false" ]; }
archive_is_private() { repo_is_private "$ARCHIVE"; }
main_is_one_commit() { [ "$(jq 'length' <<< "$(gh api "repos/$OWNER/$REPO/commits?per_page=2")")" -eq 1 ]; }
no_deploy_branch() { ! gh api "repos/$OWNER/$REPO/branches/deploy"; }
verify_check "$OWNER/$REPO is public" new_is_public
verify_check "$OWNER/$ARCHIVE is private" archive_is_private
verify_check "$OWNER/$REPO main is one commit" main_is_one_commit
verify_check "$OWNER/$REPO has no deploy branch yet" no_deploy_branch
print_wiring
[ "$verify_failed" -eq 0 ] || exit 1
