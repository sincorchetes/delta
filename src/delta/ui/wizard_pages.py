"""Folders, recovery key and summary pages (thin GTK over WizardModel; rules live in wizard.py)."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from delta.i18n import _
from delta.ui.a11y import named
from delta.ui.wizard import Protection, WizardModel
from delta.ui.wizard_base import Changed, Page, choose_folder, flat_icon_button


class FoldersPage(Page):
    def __init__(self, model: WizardModel, window, changed: Changed) -> None:
        super().__init__(model, window, changed)
        group = Adw.PreferencesGroup(
            title=_("What should be backed up?"),
            description=_("Leave the list empty to back up your whole personal folder."),
        )
        self._list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self._list.add_css_class("boxed-list")
        group.add(self._list)
        add = Gtk.Button(label=_("Add folder…"), halign=Gtk.Align.CENTER, margin_top=12)
        add.connect("clicked", self._on_add)
        group.add(add)
        self.add(group)
        self._finish_layout()
        self.refresh()

    def refresh(self) -> None:
        child = self._list.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self._list.remove(child)
            child = following
        if not self._model.folders:
            row = Adw.ActionRow(
                title=_("Your personal folder"), subtitle=_("Everything in your home folder")
            )
            row.set_sensitive(False)
            self._list.append(row)
            return
        for folder in self._model.folders:
            row = Adw.ActionRow(title=GLib.markup_escape_text(folder))
            remove = flat_icon_button("list-remove-symbolic", _("Remove"))
            named(remove, _("Remove {name}").format(name=folder))
            remove.connect("clicked", self._on_remove, folder)
            row.add_suffix(remove)
            self._list.append(row)

    def _on_add(self, button) -> None:
        choose_folder(self._window, _("Choose a folder to back up"), self._add)

    def _add(self, path: str) -> None:
        if path not in self._model.folders:
            self._model.folders = (*self._model.folders, path)
        self.refresh()
        self._changed()

    def _on_remove(self, button, folder: str) -> None:
        self._model.folders = tuple(item for item in self._model.folders if item != folder)
        self.refresh()
        self._changed()


class RecoveryPage(Page):
    def __init__(self, model: WizardModel, window, changed: Changed) -> None:
        super().__init__(model, window, changed)
        self._key_group = Adw.PreferencesGroup(
            title=_("Your recovery key"),
            description=_(
                "Delta protects your backups with a key kept in your keyring. If you ever "
                "lose access to it, this recovery key is the only way to read them. Keep it "
                "somewhere safe, away from this computer."
            ),
        )
        key = Gtk.Label(label=model.recovery_key, selectable=True, margin_top=12, margin_bottom=12)
        key.add_css_class("title-2")
        key.add_css_class("monospace")
        self._key_group.add(key)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.CENTER)
        copy = Gtk.Button(label=_("Copy"))
        copy.connect("clicked", self._on_copy)
        save = Gtk.Button(label=_("Save to a file…"))
        save.connect("clicked", self._on_save)
        actions.append(copy)
        actions.append(save)
        self._key_group.add(actions)

        self._saved = Adw.SwitchRow(
            title=_("I have saved my recovery key"),
            subtitle=_("Or I accept that I could lose access to my backups without it."),
        )
        self._saved.connect("notify::active", self._on_saved)
        self._key_group.add(self._saved)
        self.add(self._key_group)

        own_group = Adw.PreferencesGroup()
        self._own = Adw.SwitchRow(
            title=_("Use my own passphrase instead"),
            subtitle=_("You will need it to restore your files, so do not lose it."),
        )
        self._own.connect("notify::active", self._on_own)
        self._passphrase = Adw.PasswordEntryRow(title=_("Passphrase"), visible=False)
        self._confirmation = Adw.PasswordEntryRow(title=_("Repeat the passphrase"), visible=False)
        self._passphrase.connect("changed", self._on_passphrase)
        self._confirmation.connect("changed", self._on_passphrase)
        for row in (self._own, self._passphrase, self._confirmation):
            own_group.add(row)
        self.add(own_group)
        self._finish_layout()

    def _on_copy(self, button) -> None:
        provider = Gdk.ContentProvider.new_for_value(GObject.Value(str, self._model.recovery_key))
        self.get_clipboard().set_content(provider)
        # Copying is not saving: only a written file or the explicit switch counts.

    def _on_save(self, button) -> None:
        dialog = Gtk.FileDialog(title=_("Save your recovery key"), initial_name="delta-recovery-key.txt")
        dialog.save(self._window, None, self._on_save_chosen)

    def _on_save_chosen(self, dialog, result) -> None:
        try:
            target = dialog.save_finish(result)
        except GLib.Error:
            return  # dismissed
        try:
            text = f"{self._model.recovery_key}\n"
            target.replace_contents(text.encode(), None, False, Gio.FileCreateFlags.PRIVATE, None)
        except GLib.Error as err:
            self.show_problems([err.message])
            return
        self._saved.set_active(True)

    def _on_saved(self, row, _pspec) -> None:
        self._model.recovery_saved = row.get_active()
        self._changed()

    def _on_own(self, row, _pspec) -> None:
        own = row.get_active()
        self._model.protection = Protection.OWN if own else Protection.GENERATED
        self._key_group.set_visible(not own)
        self._passphrase.set_visible(own)
        self._confirmation.set_visible(own)
        self._changed()

    def _on_passphrase(self, row) -> None:
        self._model.own_passphrase = self._passphrase.get_text()
        self._model.own_confirmation = self._confirmation.get_text()
        self._changed()


class SummaryPage(Page):
    def __init__(self, model: WizardModel, window, changed: Changed) -> None:
        super().__init__(model, window, changed)
        self._group = Adw.PreferencesGroup(
            title=_("Ready to go"),
            description=_("Delta will create your backup destination and start protecting your files."),
        )
        self._rows: list[Adw.ActionRow] = []
        self._on_use = None
        self.add(self._group)

        self._existing = Adw.PreferencesGroup(
            title=_("Use the existing repository"),
            description=_(
                "There is already a backup repository there. Enter its passphrase to keep "
                "using it; nothing in it will be erased."
            ),
            visible=False,
        )
        self._existing_passphrase = Adw.PasswordEntryRow(title=_("Repository passphrase"))
        self._existing_passphrase.connect("changed", self._on_existing_changed)
        self._existing_button = Gtk.Button(
            label=_("Use this repository"), halign=Gtk.Align.CENTER, margin_top=12, sensitive=False
        )
        self._existing_button.add_css_class("suggested-action")
        self._existing_button.connect("clicked", self._on_use_clicked)
        self._existing.add(self._existing_passphrase)
        self._existing.add(self._existing_button)
        self.add(self._existing)

        busy_group = Adw.PreferencesGroup()
        self._busy = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.CENTER)
        self._busy.set_visible(False)
        self._busy.append(Gtk.Spinner(spinning=True, accessible_role=Gtk.AccessibleRole.PRESENTATION))  # the label says it
        self._busy.append(Gtk.Label(label=_("Setting up your backups…")))
        busy_group.add(self._busy)
        self.add(busy_group)
        self._finish_layout()

    def refresh(self) -> None:
        self._group.set_description(
            _("Delta will keep using the backups that are there.")
            if self._model.reuses_repository
            else _("Delta will create your backup destination and start protecting your files.")
        )
        for row in self._rows:
            self._group.remove(row)
        self._rows = []
        for label, value in self._model.summary():
            row = Adw.ActionRow(
                title=GLib.markup_escape_text(label), subtitle=GLib.markup_escape_text(value)
            )
            self._group.add(row)
            self._rows.append(row)

    def _on_existing_changed(self, row) -> None:
        self._existing_button.set_sensitive(bool(row.get_text()))

    def _on_use_clicked(self, button) -> None:
        if self._on_use is not None:
            self._on_use(self._existing_passphrase.get_text())

    def offer_existing(self, on_use) -> None:
        """Show the way out when the destination already holds a repository."""
        self._on_use = on_use
        if not self._existing.get_visible():
            self._existing_passphrase.set_text("")
        self._existing.set_visible(True)

    def hide_existing(self) -> None:
        self._existing.set_visible(False)

    def set_busy(self, busy: bool) -> None:
        self._busy.set_visible(busy)
        self._existing.set_sensitive(not busy)
