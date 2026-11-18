#!/bin/sh
# Publishes the package of a tag to the openSUSE Build Service: the spec, the dsc, the service and debian.tar.gz.
# Runs as root in an openSUSE container. The sources come from the checkout of the tag; OBS downloads the tarball
# itself (packaging/obs/_service).
# Usage: publish_obs.sh vX.Y.Z
# Environment: OBS_USER and OBS_SSH_PRIVATE_KEY (required), DRY_RUN=1 (everything but the commit).
set -eu

tag=${1:?usage: publish_obs.sh vX.Y.Z}
version=${tag#v}
here=$(cd "$(dirname "$0")/../.." && pwd)
project=home:sincorchetes:delta
package=delta-backup
api=https://api.opensuse.org

fail() { echo "publish_obs.sh: $*" >&2; exit 1; }

grep -q "^Version:  *$version\$" "$here/packaging/rpm/delta-backup.spec" || fail "the spec is not at $version"
grep -q "^Version: $version-" "$here/packaging/obs/delta-backup.dsc" || fail "the dsc is not at $version"
[ -n "${OBS_USER:-}" ] || fail "OBS_USER is not set"
[ -n "${OBS_SSH_PRIVATE_KEY:-}" ] || fail "OBS_SSH_PRIVATE_KEY is not set"

zypper --non-interactive install --no-recommends osc tar gzip >/dev/null

install -d -m 700 /root/.ssh
printf '%s\n' "$OBS_SSH_PRIVATE_KEY" > /root/.ssh/obs
chmod 600 /root/.ssh/obs
cat > /root/.oscrc <<EOF
[general]
apiurl = $api

[$api]
user = $OBS_USER
sshkey = /root/.ssh/obs
EOF
chmod 600 /root/.oscrc

mkdir -p /work && cd /work
osc checkout "$project" "$package"
cd "$project/$package"

cp "$here/packaging/rpm/delta-backup.spec" "$here/packaging/obs/_service" "$here/packaging/obs/delta-backup.dsc" .
tar --owner=0 --group=0 --exclude=debian/source -czf debian.tar.gz -C "$here" debian

osc status
if [ -z "$(osc status)" ]; then
    echo "OBS already has $version"
    exit 0
fi

if [ "${DRY_RUN:-0}" = 1 ]; then
    echo "Dry run: not committed"
    exit 0
fi
osc commit -m "Delta $version"
osc results
