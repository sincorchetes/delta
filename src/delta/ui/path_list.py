"""A group of rows listing paths, with buttons to add folders (or files) and remove them."""

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from delta.i18n import _
from delta.ui.a11y import named
from delta.ui.preferences import add_path, remove_path
from delta.ui.wizard_base import choose_file, choose_folder, flat_icon_button

Check = Callable[[str], str | None]


class PathListGroup(Adw.PreferencesGroup):
    def __init__(
        self,
        window,
        title: str,
        description: str,
        empty_text: str,
        on_changed: Callable[[tuple[str, ...]], None],
        on_problem: Callable[[str], None],
        allow_files: bool = False,
        check: Check | None = None,
    ) -> None:
        super().__init__(title=title, description=description)
        self._window, self._empty_text = window, empty_text
        self._on_changed, self._on_problem, self._check = on_changed, on_problem, check
        self._paths: tuple[str, ...] = ()
        self._rows: list[Adw.ActionRow] = []

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        folder = Gtk.Button(label=_("Add folder…"), valign=Gtk.Align.CENTER)
        folder.connect("clicked", lambda button: choose_folder(window, title, self._add))
        buttons.append(folder)
        if allow_files:
            file = Gtk.Button(label=_("Add file…"), valign=Gtk.Align.CENTER)
            file.connect("clicked", lambda button: choose_file(window, title, self._add))
            buttons.append(file)
        self.set_header_suffix(buttons)
        self._rebuild()

    @property
    def paths(self) -> tuple[str, ...]:
        return self._paths

    def set_paths(self, paths: tuple[str, ...]) -> None:
        self._paths = paths
        self._rebuild()

    def _add(self, path: str) -> None:
        problem = self._check(path) if self._check else None
        if problem:
            self._on_problem(problem)
            return
        updated = add_path(self._paths, path)
        if updated != self._paths:
            self.set_paths(updated)
            self._on_changed(updated)

    def _remove(self, button, path: str) -> None:
        updated = remove_path(self._paths, path)
        self.set_paths(updated)
        self._on_changed(updated)

    def _rebuild(self) -> None:
        for row in self._rows:
            self.remove(row)
        self._rows = []
        if not self._paths:
            row = Adw.ActionRow(title=GLib.markup_escape_text(self._empty_text))
            row.set_sensitive(False)
            self.add(row)
            self._rows.append(row)
            return
        for path in self._paths:
            row = Adw.ActionRow(title=GLib.markup_escape_text(path))
            remove = flat_icon_button("list-remove-symbolic", _("Remove"))
            named(remove, _("Remove {name}").format(name=path))
            remove.connect("clicked", self._remove, path)
            row.add_suffix(remove)
            self.add(row)
            self._rows.append(row)
