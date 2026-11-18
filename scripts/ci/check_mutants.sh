#!/bin/sh
# Runs the mutation tests and fails if more mutants survive than the one that no test can tell apart.
#
# A mutant that survives is a change to the code that no test notices. The one allowed is equivalent: in
# `TimerScheduler.apply` a `None` where the code has `False`, which Python treats the same. Anything above that
# is a test that does not really watch the code. Timeouts are changes that make the program loop forever:
# they are caught, so they are not counted.
#
#     sh scripts/ci/check_mutants.sh
set -eu

ALLOWED_SURVIVORS=1

uv run mutmut run
survivors=$(uv run mutmut results | grep -c ': survived' || true)

echo "surviving mutants: $survivors (allowed: $ALLOWED_SURVIVORS)"
if [ "$survivors" -gt "$ALLOWED_SURVIVORS" ]; then
    uv run mutmut results | grep ': survived'
    exit 1
fi
