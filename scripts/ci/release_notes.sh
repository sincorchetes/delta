#!/bin/sh
# Prints the notes of a version: the section of CHANGELOG.md under "## [X.Y.Z] - date", without its heading.
# Usage: release_notes.sh X.Y.Z [CHANGELOG.md]
set -eu

version=${1:?usage: release_notes.sh X.Y.Z [CHANGELOG.md]}
file=${2:-CHANGELOG.md}

notes=$(awk -v heading="## [$version]" '
    /^## \[/ { if (found) exit; found = (index($0, heading) == 1); next }
    /^\[[0-9][^]]*\]: / { next }
    found && (started || NF) { started = 1; print }
' "$file")

if [ -z "$notes" ]; then
    echo "release_notes.sh: no section for $version in $file" >&2
    exit 1
fi
printf '%s\n' "$notes"
