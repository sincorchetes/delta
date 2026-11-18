#!/bin/sh
# Publishes the PKGBUILD of a tag to the AUR: the real checksum, .SRCINFO, a commit and the push.
# Runs as root in an Arch Linux container (it creates the user that makepkg needs).
# Usage: publish_aur.sh vX.Y.Z
# Environment: AUR_SSH_PRIVATE_KEY (required), AUR_GIT_NAME, AUR_GIT_EMAIL, DRY_RUN=1 (everything but the push),
# SOURCE_DIR (a checkout of the tag; by default the one this script is in). The pinned host keys always come from
# this script's own checkout, so an old tag cannot bring its own.
set -eu

tag=${1:?usage: publish_aur.sh vX.Y.Z}
version=${tag#v}
here=$(cd "$(dirname "$0")/../.." && pwd)
source_dir=${SOURCE_DIR:-$here}
known_hosts=$here/scripts/ci/aur_known_hosts
work=/work/aur

fail() { echo "publish_aur.sh: $*" >&2; exit 1; }

grep -q "^pkgver=$version\$" "$source_dir/packaging/arch/PKGBUILD" || fail "pkgver of the PKGBUILD is not $version"
[ -s "$known_hosts" ] || fail "scripts/ci/aur_known_hosts is empty: the host keys of the AUR have to be pinned there"
[ -n "${AUR_SSH_PRIVATE_KEY:-}" ] || fail "AUR_SSH_PRIVATE_KEY is not set"

pacman -Sy --noconfirm --needed pacman-contrib base-devel git openssh >/dev/null

install -d -m 700 /root/.ssh
printf '%s\n' "$AUR_SSH_PRIVATE_KEY" > /root/.ssh/aur
chmod 600 /root/.ssh/aur
ssh-keygen -y -f /root/.ssh/aur > /root/.ssh/aur.pub </dev/null ||
    fail "AUR_SSH_PRIVATE_KEY is not a usable private key: it needs its BEGIN and END lines whole, and no passphrase"
echo "The key of the CI is $(ssh-keygen -lf /root/.ssh/aur.pub): it has to be one of the fingerprints in the AUR account"
cp "$known_hosts" /root/.ssh/known_hosts
export GIT_SSH_COMMAND="ssh -i /root/.ssh/aur -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes"

git clone ssh://aur@aur.archlinux.org/delta-backup.git "$work"
cp "$source_dir/packaging/arch/PKGBUILD" "$work/PKGBUILD"

useradd -m builder
chown -R builder "$work"
su builder -c "cd $work && updpkgsums && makepkg --printsrcinfo > .SRCINFO"
chown -R root "$work"

cd "$work"
git config --global --add safe.directory "$work"

# Only the two files of the package count: updpkgsums leaves the tarball it downloaded beside them.
git add PKGBUILD .SRCINFO
if git diff --cached --quiet; then
    echo "The AUR already has this PKGBUILD for $version"
    exit 0
fi

git config user.name "${AUR_GIT_NAME:?AUR_GIT_NAME is not set}"
git config user.email "${AUR_GIT_EMAIL:?AUR_GIT_EMAIL is not set}"
git commit -q -m "Update to $version"
git show --stat HEAD

if [ "${DRY_RUN:-0}" = 1 ]; then
    echo "Dry run: not pushed"
    exit 0
fi
git push origin HEAD:master
