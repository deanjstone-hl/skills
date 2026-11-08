# Line-level hygiene scan of one GitHub Actions workflow file. Not a YAML
# parser: it reads the shapes this account's workflows actually use and emits
# one tab-separated record:
#   concurrency  cancel  paths  push  push_restricted  pull_request  schedule  runs_on  ref_keyed  supersede_intended
# Booleans are 0/1. ref_keyed is 1 when a concurrency group is keyed on github.ref with
# no per-commit or per-PR term, which lets a queued main run be superseded. A group marked
# `# ci-review: supersede-intended` on its own line or the line directly above counts toward
# supersede_intended instead: superseding is the documented point of that group.
# runs_on is every job's runs-on value, joined by \x1f; a
# block-list runs-on (`runs-on:` then `- label` lines) is folded to [a,b].

function indent(text) { match(text, /^ */); return RLENGTH }

function flush_block() {
  if (block_open) { add_runs_on("[" block_items "]"); block_open = 0; block_items = "" }
}

function add_runs_on(value) { runs_on = runs_on (runs_on == "" ? "" : "\037") value }

BEGIN {
  concurrency = cancel = paths = push = push_restricted = pull_request = schedule = ref_keyed = 0
  supersede_intended = 0; marker = "#[ \t]*ci-review:[ \t]*supersede-intended"; prev = ""
  in_on = 0; on_child = -1; in_push = 0; block_open = 0; runs_on = ""
}

{
  line = $0
  sub(/\r$/, "", line)
  marked = (line ~ marker || prev ~ marker)
  prev = line
  if (line ~ /^[ \t]*#/) next
  sub(/[ \t]+#.*$/, "", line)
  if (line ~ /^[ \t]*$/) next

  depth = indent(line)
  text = substr(line, depth + 1)

  if (block_open) {
    if (depth > block_depth && text ~ /^- /) {
      item = substr(text, 3)
      gsub(/["']/, "", item)
      block_items = block_items (block_items == "" ? "" : ",") item
      next
    }
    flush_block()
  }

  if (depth == 0) {
    in_on = 0; in_push = 0
    if (text ~ /^("on"|'on'|on|true):/) {
      rest = text
      sub(/^[^:]*:[ ]*/, "", rest)
      if (rest != "") {
        if (rest ~ /push/) push = 1
        if (rest ~ /pull_request/) pull_request = 1
        if (rest ~ /schedule/) schedule = 1
      } else {
        in_on = 1; on_child = -1
      }
    }
  } else if (in_on) {
    if (on_child < 0) on_child = depth
    if (depth == on_child) {
      in_push = 0
      key = text
      sub(/:.*$/, "", key)
      if (key == "push") {
        push = 1; in_push = 1; push_depth = depth
        value = text
        sub(/^push:[ ]*/, "", value)
        if (value ~ /branches|tags/) push_restricted = 1
      }
      if (key == "pull_request" || key == "pull_request_target") pull_request = 1
      if (key == "schedule") schedule = 1
    } else if (depth < on_child) {
      in_on = 0; in_push = 0
    } else if (in_push && depth > push_depth) {
      if (text ~ /^(branches|branches-ignore|tags|tags-ignore):/) push_restricted = 1
    }
  }

  if (text ~ /^concurrency:/) concurrency = 1
  if (text ~ /^group:/ && text ~ /github\.ref/ && text !~ /github\.sha|pull_request\.number|run_id/) {
    if (marked) supersede_intended = 1
    else ref_keyed = 1
  }
  if (text ~ /^cancel-in-progress:/) {
    value = text
    sub(/^cancel-in-progress:[ ]*/, "", value)
    if (value !~ /^false/) cancel = 1
  }
  if (text ~ /^-?[ ]*(paths|paths-ignore):/) paths = 1
  if (text ~ /^runs-on:/) {
    value = text
    sub(/^runs-on:[ ]*/, "", value)
    if (value == "") { block_open = 1; block_depth = depth; block_items = "" }
    else add_runs_on(value)
  }
}

END {
  flush_block()
  printf "%d\t%d\t%d\t%d\t%d\t%d\t%d\t%s\t%d\t%d\n", concurrency, cancel, paths, push, push_restricted, pull_request, schedule, runs_on, ref_keyed, supersede_intended
}
