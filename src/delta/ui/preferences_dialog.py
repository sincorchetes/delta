"""The preferences: every change is saved at once to GSettings, which the daemon follows."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from delta.i18n import _
from delta.ui.a11y import named
from delta.ui.path_list import PathListGroup
from delta.ui.wizard_window import SetupWizard
from delta.ui.preferences import (
    ComboModel,
    exclusion_problem,
    retention_description,
    retention_model,
    retention_presets,
    retention_values,
    schedule_model,
    schedule_value,
)

KEEP_KEYS = ("keep-hourly", "keep-daily", "keep-weekly", "keep-monthly")


def _combo(title: str, model: ComboModel) -> Adw.ComboRow:
    row = Adw.ComboRow(title=title, model=Gtk.StringList.new(list(model.labels)))
    row.set_selected(model.selected)
    return row


class PreferencesDialog(Adw.PreferencesDialog):
    def __init__(self, settings, home: str, parent, client=None) -> None:
        super().__init__(title=_("Preferences"), content_width=620, content_height=760)
        self._settings, self._home, self._parent, self._client = settings, home, parent, client
        page = Adw.PreferencesPage()
        page.add(self._destination_group())
        page.add(self._schedule_group())
        page.add(self._retention_group())
        page.add(self._sources_group())
        page.add(self._exclusions_group())
        self.add(page)

    # -- where and when ---------------------------------------------------------------

    def _destination_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title=_("Destination"))
        location = self._settings.get_string("repository-location")
        self._location_row = Adw.ActionRow(
            title=_("Backups are kept in"),
            subtitle=GLib.markup_escape_text(location or _("Not set up yet")),
        )
        self._location_row.set_subtitle_selectable(True)
        if self._client is not None and location:
            change = Gtk.Button(label=_("Change…"), valign=Gtk.Align.CENTER)
            change.connect("clicked", self._on_change_destination, self._client)
            self._location_row.add_suffix(change)
        group.add(self._location_row)
        return group

    def _on_change_destination(self, button, client) -> None:
        """The backups already made stay where they are; what is backed up and how long it is kept do not change."""
        SetupWizard(self._parent, client, self._settings, self._show_destination, change=True).present()

    def _show_destination(self) -> None:
        location = self._settings.get_string("repository-location")
        self._location_row.set_subtitle(GLib.markup_escape_text(location))

    def _schedule_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title=_("Schedule"))
        self._schedule = _combo(
            _("Back up automatically"), schedule_model(self._settings.get_string("schedule"))
        )
        self._schedule.connect("notify::selected", self._on_schedule)
        group.add(self._schedule)

        return group

    def _retention_group(self) -> Adw.PreferencesGroup:
        """Radio rows, so what each option means is visible before choosing, not after."""
        group = Adw.PreferencesGroup(
            title=_("Keep old backups"),
            description=_("Older backups are removed to save space. Pick how much history to keep."),
        )
        values = tuple(self._settings.get_int(key) for key in KEEP_KEYS)
        model = retention_model(values)
        presets = retention_presets()
        first = None
        for index, preset in enumerate(presets):
            check = named(Gtk.CheckButton(valign=Gtk.Align.CENTER), preset.label)
            if first is None:
                first = check
            else:
                check.set_group(first)
            check.set_active(index == model.selected)
            check.connect("toggled", self._on_preset, index)
            row = Adw.ActionRow(title=preset.label, subtitle=preset.description)
            row.add_prefix(check)
            row.set_activatable_widget(check)
            group.add(row)
        if model.has_custom:
            check = named(
                Gtk.CheckButton(valign=Gtk.Align.CENTER, active=True, sensitive=False), model.labels[model.selected]
            )
            check.set_group(first)
            row = Adw.ActionRow(
                title=model.labels[model.selected],
                subtitle=retention_description(model.selected),
            )
            row.add_prefix(check)
            group.add(row)
        return group

    def _on_schedule(self, row, _pspec) -> None:
        value = schedule_value(row.get_selected())
        if value is not None and value != self._settings.get_string("schedule"):
            self._settings.set_string("schedule", value)

    def _on_preset(self, check, index: int) -> None:
        values = retention_values(index)
        if not check.get_active() or values is None:
            return
        for key, value in zip(KEEP_KEYS, values):
            if self._settings.get_int(key) != value:
                self._settings.set_int(key, value)

    # -- what ---------------------------------------------------------------------------

    def _sources_group(self) -> PathListGroup:
        self._sources = PathListGroup(
            self._parent,
            _("Folders to back up"),
            _("Leave the list empty to back up your whole personal folder."),
            _("Your personal folder"),
            lambda paths: self._settings.set_strv("backup-sources", list(paths)),
            self._tell,
        )
        self._sources.set_paths(tuple(self._settings.get_strv("backup-sources")))
        return self._sources

    def _exclusions_group(self) -> PathListGroup:
        self._exclusions = PathListGroup(
            self._parent,
            _("Skip these"),
            _("They are not backed up, nor is anything inside them. The cache and the trash are always skipped."),
            _("Nothing else is skipped"),
            lambda paths: self._settings.set_strv("excluded-paths", list(paths)),
            self._tell,
            allow_files=True,
            check=lambda path: exclusion_problem(path, self._sources.paths, self._home),
        )
        self._exclusions.set_paths(tuple(self._settings.get_strv("excluded-paths")))
        return self._exclusions

    def _tell(self, message: str) -> None:
        self.add_toast(Adw.Toast.new(GLib.markup_escape_text(message)))
