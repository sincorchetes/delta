#!/bin/sh
# A version tag is only published when the tree it points to says the same version: meson.build, and a section of CHANGELOG.md.
# A tag pushed before the pull request that raises the version is merged would publish the old version under the new name (the
# AUR and the GitHub Release fail, and OBS builds something it cannot name).
#
#   check_tag.sh TAG [TREE]      TAG is vX.Y.Z; TREE is the checkout of the tag (default: the current directory)
set -eu

tag=${1:?usage: check_tag.sh TAG [TREE]}
tree=${2:-.}
version=${tag#v}

fail() {
    echo "check_tag.sh: $*" >&2
    exit 1
}

case $tag in v*) ;; *) fail "'$tag' is not a version tag: it starts with v" ;; esac
printf '%s\n' "$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || fail "'$tag' is not like v0.1.3"

built=$(sed -n "s/^ *version: *'\([^']*\)'.*/\1/p" "$tree/meson.build" | head -1)
[ "$built" = "$version" ] ||
    fail "the tag is $tag and meson.build says '${built:-nothing}': merge the pull request that raises the version before pushing the tag"

sh "$(dirname "$0")/release_notes.sh" "$version" "$tree/CHANGELOG.md" > /dev/null ||
    fail "CHANGELOG.md has no section for $version"
echo "check_tag.sh: $tag matches meson.build and CHANGELOG.md"
