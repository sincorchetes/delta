#!/bin/sh
# Installs what building and testing Delta needs, from the distribution's own packages.
#
# Used by the per-distribution CI jobs (.github/workflows/ci.yml) inside a container, and a plain list of
# what each family calls things, for whoever writes a package. Run as root: `sh scripts/ci/install-deps.sh`.
set -eu

. /etc/os-release

case "$ID" in
    fedora)
        dnf install -y --setopt=install_weak_deps=False \
            git curl meson ninja-build gcc pkgconf-pkg-config patchelf \
            glib2-devel gobject-introspection-devel cairo-devel dbus-devel dbus-daemon \
            libsecret gnome-keyring gtk4 libadwaita gettext borgbackup fuse3 \
            python3 python3-devel xorg-x11-server-Xvfb appstream desktop-file-utils
        ;;
    almalinux | rocky)
        # Enterprise Linux: the development files are in CRB, borg and patchelf in EPEL.
        dnf install -y dnf-plugins-core epel-release
        dnf config-manager --set-enabled crb
        dnf install -y --setopt=install_weak_deps=False \
            git curl meson ninja-build gcc pkgconf-pkg-config \
            glib2-devel gobject-introspection-devel cairo-devel dbus-devel dbus-daemon \
            libsecret gnome-keyring gtk4 libadwaita gettext fuse3 \
            python3 python3-devel desktop-file-utils
        # Not in every release: the build goes on without them and the checks that need them say so.
        dnf install -y borgbackup patchelf xorg-x11-server-Xvfb appstream || echo "warning: some optional packages are missing"
        ;;
    arch)
        pacman -Syu --noconfirm --needed \
            git curl meson ninja gcc pkgconf patchelf \
            glib2 gobject-introspection cairo dbus libsecret gnome-keyring gtk4 libadwaita gettext borg fuse3 \
            python xorg-server-xvfb appstream desktop-file-utils
        ;;
    opensuse-tumbleweed | opensuse-leap)
        zypper --non-interactive install --no-recommends \
            git curl meson ninja gcc pkgconf-pkg-config patchelf \
            glib2-devel gobject-introspection-devel cairo-devel dbus-1-devel dbus-1-daemon \
            libsecret-1-0 gnome-keyring gtk4-tools libadwaita-devel typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1 typelib-1_0-Secret-1 \
            gettext-tools borgbackup fuse3 python3 python3-devel xorg-x11-server-Xvfb xvfb-run AppStream desktop-file-utils
        ;;
    ubuntu | debian)
        export DEBIAN_FRONTEND=noninteractive
        apt-get update
        # PyGObject 3.52+ builds against girepository-2.0 (GLib 2.80+); the older name is the fallback.
        if apt-cache show libgirepository-2.0-dev > /dev/null 2>&1; then gi=libgirepository-2.0-dev; else gi=libgirepository1.0-dev; fi
        apt-get install -y --no-install-recommends \
            git curl ca-certificates meson ninja-build gcc pkg-config patchelf \
            libglib2.0-dev "$gi" libcairo2-dev libdbus-1-dev dbus gnome-keyring \
            gir1.2-secret-1 gir1.2-gtk-4.0 gir1.2-adw-1 gettext borgbackup fuse3 \
            python3 python3-dev python3-venv xvfb xauth appstream desktop-file-utils
        ;;
    *)
        echo "unsupported distribution: $ID" >&2
        exit 1
        ;;
esac
