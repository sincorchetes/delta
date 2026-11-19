#!/bin/sh
# Installs what building and testing Delta needs, from the distribution's own packages: its Python, `python3-gobject`,
# GTK, libadwaita, BorgBackup. No uv and nothing from PyPI, so it checks what a user of the distribution's package gets.
#
# Used by the per-distribution jobs of .github/workflows/distros.yml inside a container, and a plain list of what each
# family calls things, for whoever writes a package. Run as root: `sh scripts/ci/install-deps.sh`.
set -eu

. /etc/os-release

case "$ID" in
    fedora)
        # The preview of a video or audio plays through GStreamer, and GTK aborts the whole process when it cannot find
        # what it needs (the plugins, a GL library): a desktop has them, a minimal container does not.
        dnf install -y --setopt=install_weak_deps=False \
            git meson ninja-build glib2-devel dbus-daemon \
            python3 python3-gobject python3-pytest python3-dbusmock \
            libsecret gnome-keyring gtk4 libadwaita gobject-introspection gettext borgbackup fuse3 \
            gstreamer1-plugins-base gstreamer1-plugins-good mesa-libGLES \
            xorg-x11-server-Xvfb appstream desktop-file-utils
        ;;
    almalinux | rocky)
        # Enterprise Linux: the development files are in CRB, borg and the test tools in EPEL, python3-dbusmock in the
        # repository `devel` of Rocky and AlmaLinux (Rocky defines it but does not enable it; AlmaLinux ships its definition
        # in a package of its own).
        dnf install -y dnf-plugins-core epel-release
        dnf config-manager --set-enabled crb
        if [ "$ID" = almalinux ]; then
            dnf install -y almalinux-release-devel || echo "warning: no package almalinux-release-devel"
        fi
        dnf config-manager --set-enabled devel || echo "warning: no repository called devel"
        dnf install -y --setopt=install_weak_deps=False \
            git meson ninja-build glib2-devel dbus-daemon \
            python3 python3-gobject python3-pytest \
            libsecret gnome-keyring gtk4 libadwaita gobject-introspection gettext fuse3 desktop-file-utils
        # Not in every release: the build goes on without them and the checks that need them say so. One at a time, because
        # dnf installs none of a list when one of them does not exist (Enterprise Linux 10 has no Xvfb; xwayland-run, with
        # weston from EPEL, brings xwfb-run, which stands in for xvfb-run).
        for package in borgbackup python3-dbusmock xorg-x11-server-Xvfb xwayland-run weston appstream; do
            dnf install -y "$package" || echo "warning: $package is not available"
        done
        ;;
    arch)
        pacman -Syu --noconfirm --needed \
            git meson ninja glib2 dbus \
            python python-gobject python-pytest python-dbusmock \
            libsecret gnome-keyring gtk4 libadwaita gettext borg fuse3 \
            xorg-server-xvfb appstream desktop-file-utils
        ;;
    opensuse-tumbleweed | opensuse-leap)
        zypper --non-interactive install --no-recommends \
            git meson ninja glib2-devel dbus-1-daemon \
            python3 python3-gobject python3-gobject-Gdk python3-pytest python3-dbusmock \
            libsecret-1-0 gnome-keyring typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1 typelib-1_0-Secret-1 \
            gettext-tools borgbackup fuse3 xorg-x11-server-Xvfb xvfb-run AppStream desktop-file-utils
        ;;
    ubuntu | debian)
        export DEBIAN_FRONTEND=noninteractive
        apt-get update
        apt-get install -y --no-install-recommends \
            git ca-certificates meson ninja-build libglib2.0-bin libglib2.0-dev dbus gnome-keyring \
            python3 python3-gi python3-pytest python3-dbusmock \
            gir1.2-secret-1 gir1.2-gtk-4.0 gir1.2-adw-1 gettext borgbackup fuse3 \
            gstreamer1.0-plugins-base gstreamer1.0-plugins-good libgles2 \
            xvfb xauth appstream desktop-file-utils
        ;;
    *)
        echo "unsupported distribution: $ID" >&2
        exit 1
        ;;
esac
