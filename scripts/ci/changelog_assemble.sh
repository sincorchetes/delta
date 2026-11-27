#!/bin/sh
# Gathers the fragments of changelog.d/ into the section of a new version of CHANGELOG.md, and deletes them.
# Usage: changelog_assemble.sh X.Y.Z [YYYY-MM-DD [ROOT]]   (the date is today's; ROOT holds CHANGELOG.md and changelog.d/)
set -eu

version=${1:?usage: changelog_assemble.sh X.Y.Z [YYYY-MM-DD [ROOT]]}
date=${2:-$(date +%F)}
root=${3:-$(dirname "$0")/../..}
changelog=$root/CHANGELOG.md
fragments=$root/changelog.d
kinds="added changed deprecated removed fixed security"

fail() {
    echo "changelog_assemble.sh: $*" >&2
    exit 1
}

grep -q '^## \[Unreleased\]' "$changelog" || fail "CHANGELOG.md has no [Unreleased] heading"
! grep -qF "## [$version]" "$changelog" || fail "CHANGELOG.md already has a section for $version"
# What is under [Unreleased] would be left behind: it has to be a fragment too.
if awk '/^## \[Unreleased\]/ { inside = 1; next } /^## \[/ { inside = 0 } inside && NF { found = 1 } END { exit !found }' "$changelog"; then
    fail "[Unreleased] has text of its own: move it to a fragment of changelog.d/"
fi

for file in "$fragments"/*.md; do
    [ -e "$file" ] || continue
    case $file in
        */README.md) ;;
        *.added.md | *.changed.md | *.deprecated.md | *.removed.md | *.fixed.md | *.security.md) ;;
        *) fail "$file is not named <name>.<kind>.md" ;;
    esac
done

body=$(mktemp)
result=$(mktemp)
trap 'rm -f "$body" "$result"' EXIT

for kind in $kinds; do
    set -- "$fragments"/*."$kind".md
    [ -e "$1" ] || continue
    printf '### %s\n\n' "$(echo "$kind" | awk '{ print toupper(substr($0, 1, 1)) substr($0, 2) }')" >> "$body"
    for file in "$@"; do
        printf '%s\n\n' "$(cat "$file")" >> "$body"
    done
done
[ -s "$body" ] || fail "no fragments in $fragments"

awk -v heading="## [$version] - $date" -v body="$body" '
    /^## \[Unreleased\]/ {
        print; print ""; print heading; print ""
        while ((getline line < body) > 0) print line
        skipping = 1; next
    }
    skipping && !NF { next }
    { skipping = 0; print }
' "$changelog" > "$result"
cat "$result" > "$changelog"

for kind in $kinds; do
    rm -f "$fragments"/*."$kind".md
done
echo "changelog_assemble.sh: $version assembled in CHANGELOG.md"
