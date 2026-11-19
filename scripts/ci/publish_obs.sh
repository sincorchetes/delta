#!/bin/sh
# Publishes a tag to the openSUSE Build Service. OBS fetches the sources itself (its source service, `_service`, reads
# the branch `release` of this repository), so this only moves that branch to the tag and asks OBS to run the service
# with a token bound to that one package.
# Run it inside a checkout of the tag, with permission to push to origin.
# Usage: publish_obs.sh vX.Y.Z
# Environment: OBS_TOKEN (type service, for the package delta-backup), DRY_RUN=1 (touches neither the branch nor OBS).
set -eu

tag=${1:?usage: publish_obs.sh vX.Y.Z}

if [ -z "${OBS_TOKEN:-}" ]; then
    echo "::notice::OBS_TOKEN is not set, so OBS is published by hand (packaging/obs/README.md)"
    exit 0
fi

commit=$(git rev-parse "refs/tags/$tag^{commit}")
echo "The branch release goes to $tag ($commit)"

if [ "${DRY_RUN:-0}" = 1 ]; then
    echo "Dry run: neither the branch nor OBS was touched"
    exit 0
fi

git push --force origin "$commit:refs/heads/release"

response=$(curl -sS --fail -X POST -H "Authorization: Token $OBS_TOKEN" https://api.opensuse.org/trigger/runservice)
echo "$response"
case "$response" in
    *'status code="ok"'*) echo "OBS runs the source service for $tag" ;;
    *) echo "publish_obs.sh: OBS did not accept the trigger" >&2; exit 1 ;;
esac
