"""Who made Delta, under which license, and what it stands on. No GTK: only data."""

from dataclasses import dataclass

AUTHOR = "Álvaro Castillo"
WEBSITE = "https://sincorchetes.tech"
CO_AUTHOR = "Claude (Anthropic)"
CO_AUTHOR_URL = "https://claude.ai"
REPOSITORY = "https://github.com/sincorchetes/delta"
DOCUMENTATION = "https://delta.sincorchetes.tech"
COPYRIGHT = "© 2026 Álvaro Castillo"
LICENSE = "GPL-3.0-or-later"


@dataclass(frozen=True)
class Component:
    name: str
    license: str  # an SPDX expression, as the project declares it
    url: str


# What a native install uses while it runs. The full list, with what the code was built and tested
# with, is THIRD_PARTY_LICENSES.md.
RUNTIME = (
    Component("GTK 4", "LGPL-2.1-or-later", "https://www.gtk.org"),
    Component("libadwaita", "LGPL-2.1-or-later", "https://gnome.pages.gitlab.gnome.org/libadwaita/"),
    Component("GLib and GIO", "LGPL-2.1-or-later", "https://gitlab.gnome.org/GNOME/glib"),
    Component("GStreamer", "LGPL-2.1-or-later", "https://gstreamer.freedesktop.org"),
    Component("libsecret", "LGPL-2.1-or-later", "https://gitlab.gnome.org/GNOME/libsecret"),
    Component("systemd", "LGPL-2.1-or-later", "https://systemd.io"),
    Component("PyGObject", "LGPL-2.1-or-later", "https://pygobject.gnome.org"),
    Component("pycairo", "LGPL-2.1-only OR MPL-1.1", "https://pycairo.readthedocs.io"),
    Component("Python", "PSF-2.0", "https://www.python.org"),
    Component("BorgBackup", "BSD-3-Clause", "https://www.borgbackup.org"),
    Component("nautilus-python", "GPL-2.0-or-later", "https://gitlab.gnome.org/GNOME/nautilus-python"),
)
