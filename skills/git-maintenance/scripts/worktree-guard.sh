#!/usr/bin/env bash
# The only path git-maintenance uses to remove a worktree or delete a branch.
# Run it from inside the target repo.
#
#   worktree-guard.sh list                     classify every linked worktree
#   worktree-guard.sh remove <path>...         remove approved worktrees
#   worktree-guard.sh delete-branch <name>...  delete approved branches (-D)
#
# T3 Code owns every worktree under $T3_HOME/worktrees (default ~/.t3) and the
# branches its threads use; its own storageCleanup removes them. This script
# never removes one or deletes one (argus-config#501).
#
# Every removal and deletion is recorded, with its SHA, in
# $XDG_STATE_HOME/git-maintenance/<date>.tsv (default ~/.local/state), not /tmp.
#
# Exit: 0 all done, 1 something was kept, 2 refused outright (bad usage, or the
# T3 state DB exists but cannot be read — fail closed).
set -euo pipefail

T3_ROOT="${T3_HOME:-$HOME/.t3}"
T3_DB="$T3_ROOT/userdata/statev2.sqlite"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/git-maintenance"

die() { echo "worktree-guard: $*" >&2; exit 2; }

REPO=$(git rev-parse --show-toplevel 2>/dev/null) || die "not inside a git repo"
T3_WORKTREES=$(realpath -m "$T3_ROOT/worktrees")

is_t3_path() {
  local resolved
  resolved=$(realpath -m "$1")
  [[ "$resolved" == "$T3_WORKTREES" || "$resolved" == "$T3_WORKTREES"/* ]]
}

record() {
  mkdir -p "$STATE_DIR"
  printf '%s\t%s\n' "$(date -Iseconds)" "$(IFS=$'\t'; echo "$*")" \
    >>"$STATE_DIR/$(date +%F).tsv"
}

# Linked worktrees as "<path>\t<branch>", main worktree excluded. A detached
# worktree has an empty branch.
linked_worktrees() {
  local path="" branch="" first=1
  while IFS= read -r line; do
    case "$line" in
      "worktree "*) path=${line#worktree }; branch="" ;;
      "branch "*) branch=${line#branch refs/heads/} ;;
      "")
        if [[ -n "$path" ]]; then
          [[ $first -eq 1 ]] || printf '%s\t%s\n' "$path" "$branch"
          first=0
        fi
        path=""
        ;;
    esac
  done < <(git worktree list --porcelain; echo)
}

# Branches T3 depends on: checked out in a T3 worktree, or named by a live
# (non-deleted) thread. Fails when the DB exists but cannot be read.
t3_branches() {
  local path branch
  while IFS=$'\t' read -r path branch; do
    [[ -n "$branch" ]] && is_t3_path "$path" && echo "$branch"
  done < <(linked_worktrees)
  [[ -e "$T3_DB" ]] || return 0
  python3 -I - "$T3_DB" <<'EOF'
import sqlite3, sys
db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
for (branch,) in db.execute(
    "select distinct branch from projection_threads"
    " where deleted_at is null and branch is not null and branch != ''"):
    print(branch)
EOF
}

cmd_list() {
  local path branch
  while IFS=$'\t' read -r path branch; do
    if is_t3_path "$path"; then
      printf 't3-owned\t%s\t%s\n' "$path" "$branch"
    else
      printf 'removable\t%s\t%s\n' "$path" "$branch"
    fi
  done < <(linked_worktrees)
}

cmd_remove() {
  local kept=0 target path branch match sha
  for target in "$@"; do
    if is_t3_path "$target"; then
      echo "kept (owned by T3): $target"; kept=1; continue
    fi
    match=""
    while IFS=$'\t' read -r path branch; do
      if [[ "$(realpath -m "$path")" == "$(realpath -m "$target")" ]]; then
        match=$path; break
      fi
    done < <(linked_worktrees)
    if [[ -z "$match" ]]; then
      echo "kept (not a linked worktree of $REPO): $target"; kept=1; continue
    fi
    if [[ -n "$(git -C "$match" status --porcelain)" ]]; then
      echo "kept (dirty): $match"; kept=1; continue
    fi
    sha=$(git -C "$match" rev-parse HEAD)
    git worktree remove "$match"
    record worktree "$REPO" "$match" "$branch" "$sha"
    echo "removed: $match"
  done
  return $kept
}

cmd_delete_branch() {
  local kept=0 protected name sha
  protected=$(t3_branches) || die "cannot read $T3_DB — refusing to delete any branch"
  for name in "$@"; do
    if grep -qxF -- "$name" <<<"$protected"; then
      echo "kept (T3 branch): $name"; kept=1; continue
    fi
    if ! sha=$(git rev-parse -q --verify "refs/heads/$name"); then
      echo "kept (no such branch): $name"; kept=1; continue
    fi
    record branch "$REPO" "$name" "$sha"
    git branch -D -- "$name" >/dev/null
    echo "deleted: $name ($sha)"
  done
  return $kept
}

case "${1:-}" in
  list) cmd_list ;;
  remove) shift; [[ $# -gt 0 ]] || die "remove needs a path"; cmd_remove "$@" ;;
  delete-branch) shift; [[ $# -gt 0 ]] || die "delete-branch needs a name"; cmd_delete_branch "$@" ;;
  *) die "usage: worktree-guard.sh list | remove <path>... | delete-branch <name>..." ;;
esac
