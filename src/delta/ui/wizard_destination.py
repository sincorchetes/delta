"""The destination page: a folder or a drive on this computer."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from delta.i18n import _
from delta.ui.drives import removable_drives
from delta.ui.wizard import WizardModel
from delta.ui.wizard_base import Changed, Page, choose_folder


class DestinationPage(Page):
    """Backups stay on this computer: a folder, or one of the connected drives."""

    def __init__(self, model: WizardModel, window, changed: Changed) -> None:
        super().__init__(model, window, changed)
        self._local_group = Adw.PreferencesGroup(
            title=_("Where should backups go?"),
            description=_("Pick a folder or a drive on this computer. A folder that does not exist yet is created."),
        )
        self._path = Adw.EntryRow(title=_("Folder"))
        self._path.set_text(model.destination)
        self._path.connect("changed", self._on_path)
        choose = Gtk.Button(label=_("Choose…"), valign=Gtk.Align.CENTER)
        choose.connect("clicked", self._on_choose)
        self._path.add_suffix(choose)
        self._local_group.add(self._path)
        self.add(self._local_group)

        drives = removable_drives(Gio.VolumeMonitor.get().get_mounts())
        if drives:
            group = Adw.PreferencesGroup(
                title=_("Connected drives"),
                description=_("Removable drives. Backups go in a folder called “delta-backups”."),
            )
            for drive in drives:
                group.add(self._drive_row(drive))
            self.add(group)
        self._finish_layout()

    def _drive_row(self, drive) -> Adw.ActionRow:
        row = Adw.ActionRow(
            title=GLib.markup_escape_text(drive.name),
            subtitle=GLib.markup_escape_text(drive.mount_point),
        )
        use = Gtk.Button(label=_("Use"), valign=Gtk.Align.CENTER)
        use.connect("clicked", self._on_use_drive, drive)
        row.add_suffix(use)
        return row

    def _on_path(self, row) -> None:
        self._model.destination = row.get_text()
        self._changed()

    def _on_choose(self, button) -> None:
        choose_folder(
            self._window, _("Choose a folder for your backups"), self._path.set_text, self._model.chooser_start()
        )

    def _on_use_drive(self, button, drive) -> None:
        self._path.set_text(drive.suggested_folder)
