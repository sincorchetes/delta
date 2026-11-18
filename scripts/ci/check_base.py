"""Does this system meet the minimum base Delta supports (GNOME 46: GTK 4.10, libadwaita 1.5, Python 3.12)?

It asks for the versions and, more to the point, for the interface classes Delta really uses: a distribution
can carry a version number and still lack what the code calls. Prints a table and exits 1 if anything is missing.

    uv run python scripts/ci/check_base.py
"""

import shutil
import subprocess
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

MINIMUM = {"Python": (3, 12), "GTK": (4, 10), "libadwaita": (1, 5)}
# What the interface calls: each one arrived with the minimum above, and is absent before it.
REQUIRED_CLASSES = (
    (Adw, "AlertDialog"),
    (Adw, "AboutDialog"),
    (Adw, "PreferencesDialog"),
    (Adw, "ToolbarView"),
    (Adw, "PasswordEntryRow"),
    (Gtk, "FileDialog"),
    (Gtk, "FileLauncher"),
    (Gtk, "UriLauncher"),
)


def versions() -> dict[str, tuple[int, int]]:
    return {
        "Python": sys.version_info[:2],
        "GTK": (Gtk.get_major_version(), Gtk.get_minor_version()),
        "libadwaita": (Adw.get_major_version(), Adw.get_minor_version()),
    }


def dotted(version: tuple[int, int]) -> str:
    return ".".join(map(str, version))


def borg_version() -> str:
    if shutil.which("borg") is None:
        return "not installed"
    return subprocess.run(["borg", "--version"], capture_output=True, text=True, check=False).stdout.strip()


def main() -> int:
    failures = []
    for name, found in versions().items():
        wanted = MINIMUM[name]
        ok = found >= wanted
        print(f"{'ok  ' if ok else 'FAIL'} {name} {dotted(found)} (needs {dotted(wanted)}+)")
        if not ok:
            failures.append(name)
    for module, cls in REQUIRED_CLASSES:
        present = hasattr(module, cls)
        print(f"{'ok  ' if present else 'FAIL'} {module.__name__.split('.')[-1]}.{cls}")
        if not present:
            failures.append(cls)
    print(f"     {borg_version()}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
