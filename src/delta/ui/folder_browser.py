"""Browse what a folder held in one version: search it, filter by what changed, pick items to restore."""

import os
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from delta.i18n import _
from delta.ui.a11y import loading_spinner, named, tipped
from delta.ui.client import DeltaClient
from delta.ui.disk_watch import DiskWatch
from delta.ui.folder_data import FolderData
from delta.ui.folder_listing import (
    SEARCH_CAP,
    Change,
    FolderRow,
    Show,
    apply_filter,
    build_folder_rows,
    empty_message,
    inside_names,
    inside_root,
    join_path,
)
from delta.ui.folder_row import build_row, cap_notice_row
from delta.ui.status import summarise

SEARCH_DELAY_MS = 350  # a search lists the whole folder in borg: wait for the typing to pause
SHOWS = (Show.ALL, Show.CHANGED, Show.DELETED)


class FolderBrowser(Gtk.Box):
    def __init__(
        self,
        client: DeltaClient,
        on_file: Callable[[str, int], None],
        on_change: Callable[[], None],
        on_restore: Callable[[list[str], bool], None],
        on_restore_deleted: Callable[[], None],
    ) -> None:
        """`on_file(path, size)`: a file was opened. `on_change()`: the place or the selection
        moved. `on_restore(paths, in_place)`: the button on a row was pressed.
        `on_restore_deleted()`: «Restore deleted…» was pressed."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, hexpand=True, vexpand=True)
        self._on_file, self._on_change, self._on_restore = on_file, on_change, on_restore
        self._data = FolderData(client, self._render, self._on_data_error)
        self._disk = DiskWatch(self.refresh_marks)
        self._restored: set[str] = set()  # names restored from this window, shown as such until we move
        self._shown: list[FolderRow] = []
        self._checks: dict[str, Gtk.CheckButton] = {}
        self._checked: set[str] = set()
        self._selecting = False
        self._muted = False  # while the controls are being reset, their signals mean nothing
        self._timer = 0  # the pause before a search is sent

        self._search = named(Gtk.SearchEntry(hexpand=True, placeholder_text=_("Search by name")), _("Search by name"))
        self._search.connect("search-changed", self._on_query)
        self._filter = named(Gtk.DropDown.new_from_strings([_("All"), _("Changed"), _("Deleted")]), _("Filter by change"))
        self._filter.set_tooltip_text(_("Show everything below this folder that changed since this version"))
        self._filter.connect("notify::selected", self._on_filter)
        self._select = tipped(Gtk.ToggleButton(icon_name="object-select-symbolic"), _("Select several items"))
        self._select.connect("toggled", self._on_select_mode)
        self._deleted = Gtk.Button(label=_("Restore deleted…"))
        self._deleted.set_tooltip_text(_("Put back everything in this folder that was deleted since this version"))
        self._deleted.connect("clicked", lambda button: on_restore_deleted())
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, margin_start=12, margin_end=12, margin_top=12)
        for widget in (self._search, self._filter, self._select, self._deleted):
            controls.append(widget)
        self.append(controls)

        self._list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self._list.add_css_class("boxed-list")
        self._list.connect("row-activated", self._on_activated)
        self._message = Adw.StatusPage(icon_name="folder-symbolic")
        self._stack = Gtk.Stack(hexpand=True, vexpand=True)
        self._stack.add_named(loading_spinner(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER), "loading")
        self._stack.add_named(
            Gtk.ScrolledWindow(child=self._list, margin_start=12, margin_end=12, margin_top=12, margin_bottom=12),
            "list",
        )
        self._stack.add_named(self._message, "message")
        self.append(self._stack)

    # -- where we are -------------------------------------------------------------------

    @property
    def folder(self) -> str:
        return self._data.folder

    @property
    def can_go_up(self) -> bool:
        return self._data.folder != self._data.root

    @property
    def selecting(self) -> bool:
        return self._selecting

    def selected_paths(self) -> list[str]:
        """What is ticked and still on screen, in the order shown."""
        return [join_path(self.folder, r.name) for r in self._shown if r.name in self._checked]

    def selected_items(self) -> list[tuple[str, bool]]:
        """(path, in_place) of what is ticked: a deleted item goes back under its own name, because a
        copy of it would leave it deleted; anything else is restored as a copy."""
        return [(join_path(self.folder, r.name), r.change is Change.DELETED) for r in self._shown if r.name in self._checked]

    def mark_restored(self, paths: list[str]) -> None:
        """Show these rows as restored and untick everything, so a second press is plainly not needed."""
        prefix = self.folder.rstrip("/") + "/"
        self._restored |= {p[len(prefix):] for p in paths if p.startswith(prefix)}
        self._checked.clear()
        self._render()

    def set_busy(self, busy: bool) -> None:
        """While a restore runs, nothing here may start another."""
        self._deleted.set_sensitive(not busy)

    def open(self, snapshot: str, root: str) -> None:
        """Start at `root` as it was in `snapshot`."""
        self._data.snapshot, self._data.root = snapshot, root
        self._navigate(root)

    def go_up(self) -> None:
        if self.can_go_up:
            self._navigate(os.path.dirname(self.folder))

    def refresh_marks(self) -> None:
        """Compare each row with the disk again: cheap, and all that a change on disk needs."""
        self._render()

    def refresh_all(self) -> None:
        """Also redo the comparison of everything below (after a restore, or coming back to the
        window), which is what the «changed inside» marks and the filters are made from."""
        self._render()
        self._data.refresh_changes()

    def focus_search(self) -> None:
        self._search.grab_focus()

    def escape(self) -> bool:
        """Clear the search, or else leave selection mode. False when there was nothing to undo."""
        if self._search.get_text():
            self._search.set_text("")
        elif self._selecting:
            self._select.set_active(False)
        else:
            return False
        return True

    def close(self) -> None:
        """The window is closing: stop following the disk."""
        self._disk.stop()
        self._cancel_timer()

    def _navigate(self, folder: str) -> None:
        self._reset_controls()
        self._disk.watch(folder)  # the marks keep up with files deleted or changed meanwhile
        self._stack.set_visible_child_name("loading")
        self._data.enter(folder)
        self._on_change()

    def _reset_controls(self) -> None:
        self._muted = True
        self._search.set_text("")
        self._filter.set_selected(0)
        self._select.set_active(False)
        self._muted = False
        self._selecting = False
        self._checked.clear()
        self._restored.clear()
        self._cancel_timer()

    def _on_data_error(self, kind: str, title: str, error: str) -> None:
        if kind == "changes" and SHOWS[self._filter.get_selected()] is Show.ALL:
            return  # only the marks on folders are missing: not worth an error page
        self._show_message(title, summarise(error), "dialog-error-symbolic")

    # -- what to list -------------------------------------------------------------------

    def _on_filter(self, dropdown, pspec) -> None:
        if not self._muted:
            self._refilter()

    def _on_query(self, entry) -> None:
        if self._muted:
            return
        self._cancel_timer()
        self._checked.clear()
        if entry.get_text().strip():
            self._timer = GLib.timeout_add(SEARCH_DELAY_MS, self._search_now)
        else:
            self._data.clear_search()
            self._refilter()

    def _search_now(self) -> bool:
        self._timer = 0
        self._stack.set_visible_child_name("loading")
        self._data.search(self._search.get_text())
        return GLib.SOURCE_REMOVE

    def _cancel_timer(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def _refilter(self) -> None:
        """Draw with the filter now chosen. A filter looks at everything below this folder, not only
        at one level, so it needs the whole comparison with the disk: choosing one asks for it
        afresh (cheap: borg is not asked again), showing what is known meanwhile."""
        if SHOWS[self._filter.get_selected()] is not Show.ALL and not self._searching() and self._data.changes is None:
            self._stack.set_visible_child_name("loading")
        self._data.refresh_changes()
        self._render()

    # -- showing it ---------------------------------------------------------------------

    def _searching(self) -> bool:
        return bool(self._search.get_text().strip())

    def _render(self) -> None:
        data, searching = self._data, self._searching()
        show = SHOWS[self._filter.get_selected()]
        if data.loading:
            return  # the folder is on its way
        source = data.hits if searching else (data.listing if show is Show.ALL else data.changes)
        if source is None:
            return  # the answer to the search or the comparison is on its way
        inside = inside_names(data.changes) if data.changes and not searching and show is Show.ALL else None
        built = build_folder_rows(source, base=self.folder, dir_sizes=not searching, inside=inside)
        self._shown = apply_filter(built, "", show)
        self._checked &= {r.name for r in self._shown if r.change is not Change.UNCHANGED}
        while (row := self._list.get_row_at_index(0)) is not None:
            self._list.remove(row)
        self._checks.clear()
        if not self._shown:
            self._show_message(*empty_message(searching, show is not Show.ALL))
            self._on_change()
            return
        for entry in self._shown:
            self._list.append(self._row_for(entry))
        if (searching or show is not Show.ALL) and len(source) >= SEARCH_CAP:
            self._list.append(cap_notice_row(SEARCH_CAP))
        self._stack.set_visible_child_name("list")
        self._on_change()

    def _row_for(self, entry: FolderRow) -> Adw.ActionRow:
        path = join_path(self.folder, entry.name)
        row, check = build_row(
            entry,
            selecting=self._selecting,
            checked=entry.name in self._checked,
            on_toggle=lambda active, name=entry.name: self._toggled(name, active),
            on_restore=lambda: self._on_restore([path], entry.change is Change.DELETED),
            restored=entry.name in self._restored and entry.change is not Change.DELETED,  # deleted again: say so
        )
        if check is not None:
            self._checks[entry.name] = check
        return row

    def _show_message(self, title: str, detail: str, icon: str) -> None:
        self._message.set_icon_name(icon)
        self._message.set_title(GLib.markup_escape_text(title))
        self._message.set_description(GLib.markup_escape_text(detail))
        self._stack.set_visible_child_name("message")

    # -- choosing -----------------------------------------------------------------------

    def _on_select_mode(self, button) -> None:
        if self._muted:
            return
        self._selecting = button.get_active()
        self._checked.clear()
        self._render()

    def _toggled(self, name: str, active: bool) -> None:
        (self._checked.add if active else self._checked.discard)(name)
        self._on_change()

    def _on_activated(self, listbox, row) -> None:
        index = row.get_index()
        if index >= len(self._shown):
            return
        entry = self._shown[index]
        if self._selecting:
            check = self._checks.get(entry.name)
            if check is not None:
                check.set_active(not check.get_active())
            return
        path = join_path(self.folder, entry.name)
        if not inside_root(path, self._data.root):
            return
        if entry.is_dir:
            self._navigate(path)
        else:
            self._on_file(path, entry.size)
