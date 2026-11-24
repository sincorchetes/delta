%global forgeurl https://github.com/sincorchetes/delta
%global appid io.github.sincorchetes.Delta

Name:           delta-backup
Version:        0.3.0
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
# The preview of a video or audio plays through GStreamer, and GTK stops the whole program when its plugins are missing.
%if 0%{?suse_version}
Recommends:     gstreamer-plugins-base
Recommends:     gstreamer-plugins-good
%else
Recommends:     gstreamer1-plugins-base
Recommends:     gstreamer1-plugins-good
%endif

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
# openSUSE's find_lang already lists the help pages in delta.lang, so only the other distributions list them here.
# openSUSE's build also fails on a directory that no package owns: these belong to the icon themes and to
# nautilus-python, which Delta does not depend on, so it owns them too (two packages may own the same directory).
%if 0%{?suse_version}
%dir %{_datadir}/icons/hicolor
%dir %{_datadir}/icons/hicolor/scalable
%dir %{_datadir}/icons/hicolor/scalable/apps
%dir %{_datadir}/icons/hicolor/symbolic
%dir %{_datadir}/icons/hicolor/symbolic/apps
%dir %{_datadir}/nautilus-python
%dir %{_datadir}/nautilus-python/extensions
%else
%{_datadir}/help/C/delta/
%lang(es) %{_datadir}/help/es/delta/
%endif
%{_userunitdir}/delta.service
%{_userunitdir}/delta-backup.service
%{_userunitdir}/delta.timer

%changelog
* Tue Nov 24 2026 Álvaro Castillo <sincorchetes@gmail.com> - 0.3.0-1
- The window learns that the drive is gone without waiting for a backup: the daemon looks at the place in the background
- A drive that fails while it is written to, or goes read-only in the middle of a backup, is told for what it is, and a crash of Borg is told in one line
- Unlocking checks the place first; a destination that is not usable is logged as information; the wizard chooser opens where you were; the history says why it is short

* Fri Nov 20 2026 Álvaro Castillo <sincorchetes@gmail.com> - 0.2.0-1
- Another repository in the place of the one Delta made is noticed: nothing is written in it and the window says so
- The wizard no longer refuses the place where the backups already are, so that a repository can be accepted on purpose

* Fri Nov 20 2026 Álvaro Castillo <sincorchetes@gmail.com> - 0.1.3-1
- The daemon starts on a GLib without GLibUnix.signal_add (it died at startup on Fedora 43, Debian 13 and Enterprise Linux 10)
- A destination that cannot be used (drive not connected, another drive, full, read-only, no permission) is told apart from a failed backup
- Change where backups are kept from the preferences

* Thu Nov 19 2026 Álvaro Castillo <sincorchetes@gmail.com> - 0.1.2-1
- The backup repository is never copied into itself

* Wed Nov 18 2026 Álvaro Castillo <sincorchetes@gmail.com> - 0.1.1-1
- No change to the code: packaging and documentation

* Tue Nov 17 2026 Álvaro Castillo <sincorchetes@gmail.com> - 0.1.0-1
- First package
