%global forgeurl https://github.com/sincorchetes/delta
%global appid io.github.sincorchetes.Delta

Name:           delta-backup
Version:        0.1.0
Release:        1%{?dist}
Summary:        Time travel for your files in GNOME, with BorgBackup
License:        GPL-3.0-or-later
URL:            https://delta.sincorchetes.tech
Source0:        %{forgeurl}/archive/v%{version}/delta-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  meson >= 1.0
BuildRequires:  glib2-devel
BuildRequires:  python3-devel
BuildRequires:  systemd-rpm-macros
BuildRequires:  desktop-file-utils
%if 0%{?suse_version}
BuildRequires:  gettext-tools
BuildRequires:  AppStream

Requires:       python3-gobject
Requires:       python3-gobject-Gdk
Requires:       typelib-1_0-Gtk-4_0
Requires:       typelib-1_0-Adw-1
Requires:       typelib-1_0-Secret-1
%else
BuildRequires:  gettext
BuildRequires:  appstream

Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       libsecret
%endif
Requires:       borgbackup
# `borg mount` (browsing a copy as a folder) needs FUSE.
Requires:       fuse3
%if ! 0%{?suse_version}
Recommends:     nautilus-python
%endif
Recommends:     gnome-keyring
Recommends:     yelp

%description
Delta shows how a file or a folder looked on any day, from Nautilus or its own
window, and restores it. Copies are made by BorgBackup (incremental,
deduplicated and encrypted) and stay on this computer, in a folder or on a
connected drive. Passwords are kept in the GNOME secret service and the
schedule runs with systemd user timers.

%prep
%autosetup -n delta-%{version}

%build
%meson
%meson_build

%install
%meson_install
# The scripts name the interpreter itself: no dependency on /usr/bin/env where the shebang is not rewritten.
sed -i '1s|^#!.*|#!%{__python3}|' %{buildroot}%{_bindir}/delta-ui %{buildroot}%{_libexecdir}/delta-daemon
%find_lang delta

%check
%meson_test

%files -f delta.lang
%license LICENSE THIRD_PARTY_LICENSES.md
%doc docs/security.md docs/dbus-api.md
%{_bindir}/delta-ui
%{_libexecdir}/delta-daemon
%{python3_sitelib}/delta/
%{_datadir}/nautilus-python/extensions/delta_extension.py
%{_datadir}/applications/%{appid}.desktop
%{_datadir}/applications/%{appid}.Daemon.desktop
%{_datadir}/applications/%{appid}.Versions.desktop
%{_datadir}/dbus-1/services/%{appid}.Service1.service
%{_datadir}/glib-2.0/schemas/%{appid}.gschema.xml
%{_datadir}/metainfo/%{appid}.metainfo.xml
%{_datadir}/icons/hicolor/scalable/apps/%{appid}.svg
%{_datadir}/icons/hicolor/symbolic/apps/%{appid}-symbolic.svg
%if ! 0%{?suse_version}
# openSUSE's find_lang already lists the help pages in delta.lang.
%{_datadir}/help/C/delta/
%lang(es) %{_datadir}/help/es/delta/
%endif
%{_userunitdir}/delta.service
%{_userunitdir}/delta-backup.service
%{_userunitdir}/delta.timer

%changelog
* Tue Nov 17 2026 Álvaro Castillo <sincorchetes@gmail.com> - 0.1.0-1
- First package
