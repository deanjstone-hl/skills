#!/usr/bin/env bash
# Mirror a wayfinder map to myargus.cc/plans as a read-only checklist
# (argus-config#884). GitHub stays canonical: ticking a step on the plan page
# never touches the ticket, and every run rebuilds the plan from GitHub.
#
# Usage: mirror-map.sh [--dry-run] <owner/repo> <map-number>
#   --dry-run  print the plan JSON and publish nothing
#
# Prints exactly one line, passed through from the impl-plan skill's publish.sh:
#   published <url> created|republished          exit 0
#   fallback <reason>: <detail>                  exit 0  (no-token, unreachable, ...)
# A fallback exits 0 on purpose: the closeout reports it and carries on.
# Exit 1 is a usage error; any other non-zero is a real failure (gh could not
# read the map, publish.sh broke).
#
# Plan shape: slug wayfinder-<repo>-<map#>; step 1 the destination (pre-done);
# then open tickets as checkable steps, claimed -> frontier -> blocked; then
# closed tickets as pre-done steps carrying their Decisions-so-far gist. The
# plans page sanitiser keeps only a small HTML set, so content is plain
# <p>/<strong>/<a> and every title is escaped.
#
# Env: WAYFINDER_PUBLISH_SH overrides the publish.sh path (tests).
set -euo pipefail

script_dir="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
publish_sh="${WAYFINDER_PUBLISH_SH:-$script_dir/../../impl-plan/scripts/publish.sh}"

usage_error() {
  printf 'mirror-map.sh: %s\n' "$1" >&2
  exit 1
}

dry_run=false
if [[ "${1:-}" == "--dry-run" ]]; then
  dry_run=true
  shift
fi
repo="${1:-}"
map_number="${2:-}"
[[ "$repo" =~ ^[^/]+/[^/]+$ && "$map_number" =~ ^[0-9]+$ ]] \
  || usage_error "usage: mirror-map.sh [--dry-run] <owner/repo> <map-number>"

map_json="$(gh api "repos/$repo/issues/$map_number")" \
  || { echo "mirror-map.sh: could not read $repo#$map_number" >&2; exit 3; }
children_json="$(gh api "repos/$repo/issues/$map_number/sub_issues" --paginate --slurp)" \
  || { echo "mirror-map.sh: could not read the sub-issues of $repo#$map_number" >&2; exit 3; }

# map_section <heading>: the body of a "## <heading>" section of the map, up to the next "## ".
map_section() {
  jq -r '.body // ""' <<<"$map_json" \
    | awk -v want="## $1" '$0 ~ /^## / { in_section = ($0 == want); next } in_section { print }'
}

destination="$(map_section Destination | awk 'NF { sub(/^[ \t]+/, ""); sub(/[ \t]+$/, ""); printf "%s%s", sep, $0; sep = " " }')"
decisions="$(map_section "Decisions so far")"

# Bodies and sub-issue JSON can top MAX_ARG_STRLEN (128 KiB) for one argv
# argument, so jq reads them from files, never --argjson (argus-config#937).
plan_file="$(mktemp)"
map_file="$(mktemp)"
children_file="$(mktemp)"
trap 'rm -f "$plan_file" "$map_file" "$children_file"' EXIT
printf '%s' "$map_json" >"$map_file"
printf '%s' "$children_json" >"$children_file"

TZ=Australia/Sydney jq -n \
  --arg repo "$repo" \
  --arg destination "$destination" \
  --arg decisions "$decisions" \
  --slurpfile map_docs "$map_file" \
  --slurpfile page_docs "$children_file" '
  def esc: gsub("&"; "&amp;") | gsub("<"; "&lt;") | gsub(">"; "&gt;") | gsub("\""; "&quot;");
  def slug_part: ascii_downcase | gsub("[^a-z0-9]+"; "-") | sub("^-+"; "") | sub("-+$"; "");
  def ticket_type: ([.labels[].name | select(startswith("wayfinder:")) | sub("^wayfinder:"; "")] | first) // "ticket";
  def state_of:
    if .assignee != null then "Claimed"
    elif .issue_dependencies_summary.blocked_by > 0 then "Blocked"
    else "Frontier" end;
  def state_rank: {"Claimed": 0, "Frontier": 1, "Blocked": 2}[state_of];
  def when: .closed_at | fromdate | localtime | strftime("%-d %b %Y");

  $map_docs[0] as $map
  | $page_docs[0] as $pages
  | ($decisions | split("\n")
    | map(capture("issues/(?<n>[0-9]+)\\)\\s*[:—–-]+\\s*(?<gist>.+)$")? // empty)
    | map({key: .n, value: (.gist | sub("\\s+$"; ""))}) | from_entries) as $gists
  | ($pages | add // []) as $children
  | ($repo | split("/")[1]) as $name
  | {
      title: $map.title,
      subtitle: ("A read-only mirror of \($repo)#\($map.number). GitHub is canonical; ticking a step here does not touch the ticket."),
      slug: (("wayfinder-\($name | slug_part)-\($map.number)") | .[0:80] | sub("-+$"; "")),
      sessionId: null,
      steps: (
        [ {type: "predone", title: "Destination",
           doneNote: (if $destination == "" then "Not recorded on the map." else $destination end)} ]
        + ([ $children[] | select(.state == "open") ] | sort_by([state_rank, .number])
           | map({type: "user", title: .title, badge: null,
                  checkLabel: "Mark seen here; the GitHub ticket stays as it is",
                  content: "<p><strong>\(state_of)</strong> · \(ticket_type | esc) · <a href=\"\(.html_url | esc)\">\($name | esc)#\(.number)</a></p>"}))
        + ([ $children[] | select(.state == "closed") ] | sort_by(.closed_at)
           | map({type: "predone", title: .title,
                  doneNote: ("Closed \(when)" + (($gists[.number | tostring] // "") | if . == "" then "" else ": " + . end)
                             + " (\($name)#\(.number))")}))
      )
    }' >"$plan_file"

if [[ "$dry_run" == true ]]; then
  cat "$plan_file"
  exit 0
fi

if [[ ! -f "$publish_sh" ]]; then
  echo "fallback no-publisher: impl-plan publish.sh not found at $publish_sh"
  exit 0
fi

publish_exit=0
publish_line="$(bash "$publish_sh" "$plan_file")" || publish_exit=$?
case "$publish_exit" in
  0 | 2) printf '%s\n' "$publish_line"; exit 0 ;;
  *) echo "mirror-map.sh: publish.sh failed (exit $publish_exit): $publish_line" >&2; exit "$publish_exit" ;;
esac
