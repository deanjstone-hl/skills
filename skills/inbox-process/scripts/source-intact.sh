#!/usr/bin/env bash
# Checks that an article moved to SOURCES/ kept its content.
# Usage: source-intact.sh ORIGINAL MOVED
#
# argus-config#319: ingest re-emitted every briefing's body and silently dropped
# its `## BLUF` section. Part B's B1 is a move, not a rewrite, so the moved file
# must be byte-identical to the original apart from exactly two things:
#   - frontmatter: a top-level `type:` line added or replaced (`type: source`),
#     including a frontmatter block prepended to a file that had none, if that
#     block sets only `type`;
#   - body: B2's rewrite of an external image URL to `attachments/<file>`
#     (`../attachments/<file>` before context#317 put the images beside the
#     notes), on a line that is otherwise unchanged.
# Line endings, trailing newlines and every other byte must survive.
#
# Exit 0 intact, 1 not intact (one reason line on stdout), 2 usage.
set -uo pipefail

[ "$#" -eq 2 ] || { echo "usage: $(basename "$0") ORIGINAL MOVED" >&2; exit 2; }
ORIGINAL="$1" MOVED="$2"

fail() { echo "source-intact: ${MOVED##*/}: $*"; exit 1; }

[ -f "$ORIGINAL" ] || { echo "source-intact: no original at $ORIGINAL" >&2; exit 2; }
[ -f "$MOVED" ] || fail "not found at $MOVED"
cmp -s "$ORIGINAL" "$MOVED" && exit 0

# Line number of the frontmatter's closing `---`, or 0 when there is none. A
# byte-order mark and CRs are ignored for detection only.
frontmatter_end() {
  awk '
    { line = $0; sub(/\r$/, "", line) }
    NR == 1 { sub(/^\xEF\xBB\xBF/, "", line); if (line != "---") exit; next }
    line == "---" { end = NR; exit }
    END { print end + 0 }
  ' "$1"
}

# Frontmatter lines minus top-level `type:` lines, byte for byte.
frontmatter_rest() {
  local file="$1" end="$2"
  [ "$end" -gt 0 ] || return 0
  sed -n "2,$((end - 1))p" "$file" | grep -v '^type:' || true
}

orig_end=$(frontmatter_end "$ORIGINAL")
moved_end=$(frontmatter_end "$MOVED")

if [ "$orig_end" -gt 0 ]; then
  [ "$moved_end" -gt 0 ] || fail "frontmatter removed"
  [ "$(head -n1 "$ORIGINAL")" = "$(head -n1 "$MOVED")" ] \
    || fail "frontmatter opening line changed"
  [ "$(sed -n "${orig_end}p" "$ORIGINAL")" = "$(sed -n "${moved_end}p" "$MOVED")" ] \
    || fail "frontmatter closing line changed"
fi
[ "$(frontmatter_rest "$ORIGINAL" "$orig_end")" = "$(frontmatter_rest "$MOVED" "$moved_end")" ] \
  || fail "frontmatter changed beyond the type line"

orig_body=$(mktemp) moved_body=$(mktemp)
trap 'rm -f "$orig_body" "$moved_body"' EXIT
tail -n "+$((orig_end + 1))" "$ORIGINAL" >"$orig_body"
tail -n "+$((moved_end + 1))" "$MOVED" >"$moved_body"
cmp -s "$orig_body" "$moved_body" && exit 0

if grep -q '^## BLUF' "$orig_body" && ! grep -q '^## BLUF' "$moved_body"; then
  fail "## BLUF section dropped — the body was re-emitted, not moved"
fi
[ "$(tail -c1 "$orig_body" | od -An -c)" = "$(tail -c1 "$moved_body" | od -An -c)" ] \
  || fail "trailing newline changed"

# The only body edit allowed: an image line whose external URLs became
# attachments/ paths and is otherwise identical.
reason=$(awk '
  function mask(s, pattern) { gsub(pattern, "\001", s); return s }
  NR == FNR { orig[FNR] = $0; n = FNR; next }
  {
    m = FNR
    if ($0 == orig[FNR]) next
    o = orig[FNR]
    if (o !~ /(!\[|<img)/ || o !~ /https?:\/\// || $0 !~ /(\.\.\/)?attachments\//) {
      print "body line " FNR " changed"; exit
    }
    if (mask(o, "https?://[^)\"'\'' ]+") != mask($0, "(\\.\\./)?attachments/[^)\"'\'' ]+")) {
      print "body line " FNR " changed beyond its image URL"; exit
    }
  }
  END { if (n != m) print "body has " m " lines, original " n }
' "$orig_body" "$moved_body")
[ -z "$reason" ] || fail "$reason"
exit 0
