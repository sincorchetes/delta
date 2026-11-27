"""Delta's Nautilus extension: "Restore Previous Version…" and the backup state of each file.

This runs inside Nautilus, with nautilus-python's own interpreter. So it imports only the
standard library and PyGObject (never the `delta` package) and keeps all real work in the Delta
app, which it opens through a desktop entry. The only thing it asks the daemon is when the last
backup was (a cheap D-Bus property, cached), to tell which files changed since.
"""

import fnmatch
import gettext
import glob
import os
import time
from dataclasses import dataclass

import gi

for _version in ("4.1", "4.0"):  # the GTK 4 API; newest first
    try:
        gi.require_version("Nautilus", _version)
        break
    except ValueError:
        continue
else:
    raise ImportError("no GTK 4 Nautilus extension API (Nautilus-4.x) is installed")
from gi.repository import Gio, GLib, GObject, Nautilus

VERSIONS_DESKTOP_ID = "io.github.sincorchetes.Delta.Versions.desktop"
DOMAIN = "delta"
FLATPAK_APP_ID = "io.github.sincorchetes.Delta"
SCHEMA_ID = "io.github.sincorchetes.Delta"
LOCATION_KEY = "repository-location"
BUS_NAME, OBJECT_PATH, INTERFACE = "io.github.sincorchetes.Delta.Service1", "/io/github/sincorchetes/Delta/Service1", "io.github.sincorchetes.Delta.Service1"
DAEMON_TIMEOUT_MS = 300  # Nautilus waits for this: never long
REFRESH_SECONDS = 30
ATTRIBUTE = "delta_backup"
SAVED, PENDING = "saved", "pending"
PENDING_EMBLEM = "emblem-synchronizing"
# What the daemon never backs up on its own (daemon/composition.py DEFAULT_EXCLUDES).
DEFAULT_EXCLUDES = (".cache", ".local/share/Trash", ".var/app/*/cache")


def flatpak_share_dirs(user_data_dir=None) -> list[str]:
    """The `share` folder of a Flatpak install of Delta, which Nautilus can read from outside the sandbox.

    The Flatpak keeps its catalogues in the application itself (`separate-locales: false` in its manifest), because
    a separate locale extension is a place this file cannot know where to look. The user's install comes first.
    """
    user_data_dir = user_data_dir or GLib.get_user_data_dir()
    return [
        os.path.join(root, "app", FLATPAK_APP_ID, "current", "active", "files", "share")
        for root in (os.path.join(user_data_dir, "flatpak"), "/var/lib/flatpak")
    ]


def translations(data_dirs=None, languages=None) -> gettext.NullTranslations:
    """Delta's catalogue from the first XDG data directory that has one (then a Flatpak's); English otherwise."""
    if data_dirs is None:
        data_dirs = [GLib.get_user_data_dir(), *GLib.get_system_data_dirs(), *flatpak_share_dirs()]
    for base in data_dirs:
        try:
            return gettext.translation(DOMAIN, os.path.join(base, "locale"), languages=languages)
        except OSError:
            continue
    return gettext.NullTranslations()


def is_restorable(path, home) -> bool:
    """A path inside the user's home folder: the only place the daemon will restore into."""
    if not path:
        return False
    return os.path.normpath(path).startswith(os.path.normpath(home) + os.sep)


def repository_location(source=None) -> str | None:
    """The repository Delta is set up with ("" when none), or None when Delta's settings are not
    installed here, so there is no way to tell."""
    source = source or Gio.SettingsSchemaSource.get_default()
    schema = source.lookup(SCHEMA_ID, True) if source is not None else None
    if schema is None:
        return None
    return Gio.Settings.new_full(schema, None, None).get_string(LOCATION_KEY)


def has_backups(location: str | None) -> bool:
    """False only when Delta is known to have no repository: a menu entry would lead nowhere.

    If the settings cannot be read the entry is shown anyway, and the window explains.
    """
    if location is None:
        return True
    return bool(location.strip())


@dataclass(frozen=True)
class BackupInfo:
    last_backup: int  # epoch seconds; 0 when there has been none
    sources: tuple[str, ...]  # folders chosen for backup; empty means the whole home folder
    excludes: tuple[str, ...]  # paths the user chose to skip


def _expand(path: str, home: str) -> str:
    return home + path[1:] if path == "~" or path.startswith("~/") else path


def _within(path: str, folder: str) -> bool:
    return path == folder or path.startswith(folder.rstrip("/") + "/")


def _skipped_by_default(path: str, home: str) -> bool:
    """Borg's own matching: `*` also crosses folders, and a folder takes what is inside it."""
    return any(
        fnmatch.fnmatchcase(path, f"{glob.escape(home)}/{relative}{inside}")
        for relative in DEFAULT_EXCLUDES
        for inside in ("", "/*")
    )


def is_covered(path: str, home: str, info: BackupInfo) -> bool:
    """Whether the backup takes this file: inside a chosen folder and not in a skipped one."""
    roots = [_expand(s, home) for s in info.sources]
    roots = [r for r in roots if r.startswith("/")] or [home]
    if not any(_within(path, root) for root in roots):
        return False
    skipped = [e for e in (_expand(e, home) for e in info.excludes) if e.startswith("/")]
    return not (_skipped_by_default(path, home) or any(_within(path, folder) for folder in skipped))


def backup_status(path: str, changed_at: float, info: BackupInfo, home: str) -> str | None:
    """SAVED when the file has not changed since the last backup, PENDING when it has (or when
    there has been no backup yet), None when the backup does not cover it at all."""
    if not is_covered(path, home, info):
        return None
    return SAVED if info.last_backup and int(changed_at) <= info.last_backup else PENDING


def _daemon_last_backup() -> int | None:
    """When the last backup finished, or None if the daemon is not running (it is never started
    just for this: Nautilus must not wait on it)."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = bus.call_sync(
            BUS_NAME, OBJECT_PATH, "org.freedesktop.DBus.Properties", "Get",
            GLib.Variant("(ss)", (INTERFACE, "LastBackup")), GLib.VariantType("(v)"),
            Gio.DBusCallFlags.NO_AUTO_START, DAEMON_TIMEOUT_MS, None,
        )
        return int(reply.unpack()[0])
    except GLib.Error:
        return None


def read_backup_state() -> BackupInfo | None:
    """None when it cannot be told: no settings, no repository, or no daemon to ask."""
    source = Gio.SettingsSchemaSource.get_default()
    schema = source.lookup(SCHEMA_ID, True) if source is not None else None
    if schema is None:
        return None
    settings = Gio.Settings.new_full(schema, None, None)
    if not has_backups(settings.get_string(LOCATION_KEY)):
        return None
    last = _daemon_last_backup()
    if last is None:
        return None
    return BackupInfo(last, tuple(settings.get_strv("backup-sources")), tuple(settings.get_strv("excluded-paths")))


class BackupState:
    """`read()` is slowish (settings and a D-Bus call) and Nautilus asks once per visible file."""

    def __init__(self, read=None, clock=time.monotonic) -> None:
        self._read, self._clock = read or read_backup_state, clock
        self._info: BackupInfo | None = None
        self._at: float | None = None

    def get(self) -> BackupInfo | None:
        now = self._clock()
        if self._at is None or now - self._at >= REFRESH_SECONDS:
            self._info, self._at = self._read(), now
        return self._info


def launch_versions(path) -> None:
    info = Gio.DesktopAppInfo.new(VERSIONS_DESKTOP_ID)
    if info is None:
        return
    try:
        info.launch([Gio.File.new_for_path(path)], None)
    except GLib.Error:
        pass  # nothing useful to show inside Nautilus; the app reports its own problems


class DeltaMenuProvider(GObject.GObject, Nautilus.MenuProvider):
    def __init__(self) -> None:
        super().__init__()
        self._gettext = translations().gettext

    def get_file_items(self, *args):
        files = args[-1]  # Nautilus 4 passes (files); older releases passed (window, files)
        if len(files) != 1:
            return []
        return self._items_for(files[0], "Delta::RestorePreviousVersion")

    def get_background_items(self, *args):
        """Right click on the empty space of a folder: its own previous versions."""
        # (folder); older releases passed (window, folder). Nautilus keys each entry's action by
        # its name, so this one must differ from the file entry or the two would run each other's.
        return self._items_for(args[-1], "Delta::RestorePreviousVersionHere", browsable_home=True)

    def _items_for(self, selected, name, browsable_home=False):
        """The home folder itself is browsed (what was deleted in it is recovered), never replaced as a whole."""
        if selected is None or selected.get_uri_scheme() != "file":
            return []
        location = selected.get_location()
        path = location.get_path() if location is not None else None
        home = GLib.get_home_dir()
        is_home = bool(path) and browsable_home and os.path.normpath(path) == os.path.normpath(home)
        if not (is_home or is_restorable(path, home)) or not has_backups(repository_location()):
            return []
        _ = self._gettext  # named `_` so xgettext finds the string below
        entry = Nautilus.MenuItem(
            name=name,
            label=_("Restore Previous Version…"),
        )
        entry.connect("activate", self._on_activate, path)
        return [entry]

    def _on_activate(self, menu_item, path) -> None:
        launch_versions(path)


class DeltaInfoProvider(GObject.GObject, Nautilus.InfoProvider, Nautilus.ColumnProvider):
    """A «Backup» column, and an emblem on the files that changed since the last backup.

    Only what the settings and one cached property can tell: borg is never asked about a file.
    """

    def __init__(self, state=None) -> None:
        super().__init__()
        self._gettext = translations().gettext
        self._state = state or BackupState()

    def get_columns(self):
        _ = self._gettext
        return [
            Nautilus.Column(
                name="Delta::Backup",
                attribute=ATTRIBUTE,
                label=_("Backup"),
                description=_("Whether the file is in the latest backup"),
            )
        ]

    def update_file_info(self, file) -> None:
        if file.get_uri_scheme() != "file" or file.is_directory():
            return
        location = file.get_location()
        path = location.get_path() if location is not None else None
        home = GLib.get_home_dir()
        if path is None or not is_restorable(path, home):
            return
        info = self._state.get()
        if info is None:
            return
        try:
            stat = os.stat(path)
        except OSError:
            return
        status = backup_status(path, max(stat.st_mtime, stat.st_ctime), info, home)
        if status is None:
            return
        _ = self._gettext
        labels = {SAVED: _("In the latest backup"), PENDING: _("Changed since the last backup")}
        file.add_string_attribute(ATTRIBUTE, labels[status])
        if status == PENDING:
            file.add_emblem(PENDING_EMBLEM)
