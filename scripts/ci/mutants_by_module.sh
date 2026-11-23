#!/bin/sh
# After `uv run mutmut run`: how many mutants survived in each module, most first.
#
#     sh scripts/ci/mutants_by_module.sh
set -eu

uv run mutmut results | grep ': survived' |
    sed -E 's/^ *(delta\.[a-z_.]+)\.x[_ǁ].*/\1/' |
    sort | uniq -c | sort -rn
