#!/bin/sh
# Says which pipelines a change needs, as lines for $GITHUB_OUTPUT:
#   code=true      something outside website/ changed (the tests, the packages, the documents...)
#   web=true       website/ changed, or the workflow that builds it
#   mutation=true  something that the mutation tests read changed: src/, tests/, po/, their configuration and what installs
#                  them. The documents, the packaging, the Flatpak, Nix and the other CI scripts cannot change its result.
# If the change cannot be compared (an unknown base), all three are true: it is better to run too much than to skip.
# Usage: changed_areas.sh BASE HEAD
set -eu

base=${1:?usage: changed_areas.sh BASE HEAD}
head=${2:?usage: changed_areas.sh BASE HEAD}
code=false
web=false
mutation=false

if files=$(git diff --name-only "$base" "$head" 2>/dev/null); then
    while IFS= read -r file; do
        [ -n "$file" ] || continue
        case "$file" in
            website/*) web=true ;;
            .github/workflows/ci.yml) web=true; code=true; mutation=true ;;
            *)
                code=true
                # Only what is listed here is known not to matter; anything new runs the mutation tests.
                case "$file" in
                    scripts/ci/check_mutants.sh | scripts/ci/mutants_by_module.sh) mutation=true ;;
                    *.md | LICENSE | docs/* | packaging/* | debian/* | flatpak/* | nix/* | flake.nix | flake.lock) ;;
                    .github/* | scripts/ci/*) ;;
                    *) mutation=true ;;
                esac
                ;;
        esac
    done <<EOF
$files
EOF
else
    code=true
    web=true
    mutation=true
fi

echo "code=$code"
echo "web=$web"
echo "mutation=$mutation"
