#!/bin/sh
# Installs Delta from the openSUSE Build Service repository of a distribution, as its page says to, and runs a real backup and a
# real restore with it (package_smoke.py). Meant for a clean container of that distribution, as root.
#
#   package_smoke.sh KIND OBS_DIRECTORY [EXPECTED_VERSION]
#     KIND               fedora | el (Rocky, AlmaLinux) | suse | deb (Debian, Ubuntu)
#     OBS_DIRECTORY      the name of the repository: Fedora_44, RockyLinux_10, openSUSE_Tumbleweed, Debian_13, xUbuntu_26.04...
#     EXPECTED_VERSION   after a release: keep trying until the repository has this version (OBS builds it after the tag),
#                        for up to WAIT_MINUTES (default 180). Without it, whatever the repository has.
set -eu

kind=${1:?usage: package_smoke.sh KIND OBS_DIRECTORY [EXPECTED_VERSION]}
directory=${2:?usage: package_smoke.sh KIND OBS_DIRECTORY [EXPECTED_VERSION]}
expected=${3:-}
wait_minutes=${WAIT_MINUTES:-180}
base=https://download.opensuse.org/repositories/home:/sincorchetes:/delta/$directory

installed_version() {
    case $kind in
        deb) dpkg-query -W -f='${Version}\n' delta-backup 2> /dev/null || true ;;
        *) rpm -q --qf '%{VERSION}\n' delta-backup 2> /dev/null | grep -v "not installed" || true ;;
    esac
}

prepare() {
    case $kind in
        fedora)
            dnf -y install dnf-plugins-core ca-certificates
            dnf config-manager addrepo --from-repofile="$base/home:sincorchetes:delta.repo"
            ;;
        el)
            dnf -y install epel-release dnf-plugins-core ca-certificates
            dnf config-manager --add-repo "$base/home:sincorchetes:delta.repo"
            ;;
        suse)
            zypper -n install ca-certificates
            zypper -n addrepo "$base/home:sincorchetes:delta.repo"
            ;;
        deb)
            export DEBIAN_FRONTEND=noninteractive
            apt-get update
            apt-get -y install curl gnupg ca-certificates
            install -d /etc/apt/keyrings
            curl -fsSL "$base/Release.key" | gpg --dearmor -o /etc/apt/keyrings/delta.gpg
            echo "deb [signed-by=/etc/apt/keyrings/delta.gpg] $base/ /" > /etc/apt/sources.list.d/delta.list
            ;;
    esac
}

install_package() {
    case $kind in
        fedora | el) dnf clean all && dnf -y install delta-backup dbus-daemon gnome-keyring ;;
        suse) zypper -n --gpg-auto-import-keys refresh && zypper -n install delta-backup dbus-1-daemon gnome-keyring ;;
        deb) apt-get update && apt-get -y install delta-backup dbus gnome-keyring ;;
    esac
}

prepare
deadline=$(( $(date +%s) + wait_minutes * 60 ))
while :; do
    if ! install_package && [ -z "$expected" ]; then
        echo "::error::the package could not be installed from the repository"
        exit 1
    fi
    have=$(installed_version)
    if [ -n "$have" ] && { [ -z "$expected" ] || case $have in "$expected"*) true ;; *) false ;; esac; }; then
        break
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
        echo "::error::the repository has '${have:-nothing}' and not '$expected' after $wait_minutes minutes"
        exit 1
    fi
    echo "the repository has '${have:-nothing}', waiting for '$expected' (the Build Service is still building it)"
    sleep 120
done
echo "installed delta-backup $have"

python3 "$(dirname "$0")/package_smoke.py" /usr
