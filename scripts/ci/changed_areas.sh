#!/bin/sh
# Says which pipelines a change needs, as lines for $GITHUB_OUTPUT:
#   code=true  something outside website/ changed (the tests, the packages, the documents...)
#   web=true   website/ changed, or the workflow that builds it
# If the change cannot be compared (an unknown base), both are true: it is better to run too much than to skip.
# Usage: changed_areas.sh BASE HEAD
set -eu

base=${1:?usage: changed_areas.sh BASE HEAD}
head=${2:?usage: changed_areas.sh BASE HEAD}
code=false
web=false

if files=$(git diff --name-only "$base" "$head" 2>/dev/null); then
    while IFS= read -r file; do
        [ -n "$file" ] || continue
        case "$file" in
            website/*) web=true ;;
            .github/workflows/ci.yml) web=true; code=true ;;
            *) code=true ;;
        esac
    done <<EOF
$files
EOF
else
    code=true
    web=true
fi

echo "code=$code"
echo "web=$web"
