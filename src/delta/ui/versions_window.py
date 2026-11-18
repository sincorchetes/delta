"""Previous versions of one file or folder, as a timeline: see a version, restore it, or replace the current one."""

import os
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, Gio, GLib, Gtk, Pango

from delta.i18n import _
from delta.ui.a11y import loading_spinner, tipped
from delta.ui.browse_folder import BrowseFolder
from delta.ui.button_row import button_row
from delta.ui.client import DeltaClient
from delta.ui.folder_browser import FolderBrowser
from delta.ui.job_tracker import JobTracker
from delta.ui.preview_pane import PreviewPane
from delta.ui.restore_batch import RestoreBatch, summary
from delta.ui.restore_deleted import RestoreDeleted, confirm_replace
from delta.ui.shortcuts import install as install_shortcuts
from delta.ui.status import summarise
from delta.ui.timeline import Timeline
from delta.ui.version_preview import Target, VersionPreviewer
from delta.ui.versions import VersionRow, build_versions


class VersionsWindow(Adw.Window):
    def __init__(self, application, client: DeltaClient, path: str) -> None:
        super().__init__(application=application, title=_("Previous versions"), default_width=860, default_height=600)
        self._client, self._path = client, path
        self._inner: Target | None = None  # a file opened from inside a folder version
        self._timeline = Timeline(self._on_version_chosen, lambda: self._on_open(None))
        self._tracker = JobTracker()
        self._pane = PreviewPane()
        self._previewer = VersionPreviewer(client, self._tracker, self._pane, self, self._current, self._sync, self._toast)
        self._browser = FolderBrowser(client, self._on_inner_file, self._sync, self._on_row_restore, self._on_restore_deleted)
        self._deleted = RestoreDeleted(client, self._tracker, self, self._toast, self._sync, self._after_deleted)
        self._folder = BrowseFolder(client, self._tracker, self._toast, self._sync, self._show_in_files)

        title = Adw.WindowTitle(title=_("Previous versions"), subtitle=GLib.markup_escape_text(os.path.basename(path)))
        header = Adw.HeaderBar(title_widget=title)

        self._copy = Gtk.Button(label=_("Restore as a copy"))
        self._copy.add_css_class("suggested-action")
        self._copy.connect("clicked", self._on_copy)
        self._replace = Gtk.Button(label=_("Replace the current version…"))
        self._replace.connect("clicked", self._on_replace)
        self._open = Gtk.Button(label=_("Open"))
        self._open.connect("clicked", self._on_open)
        actions = button_row((self._replace, self._open, self._folder.button, self._copy))

        self._back = tipped(Gtk.Button(icon_name="go-previous-symbolic"), _("Back"))
        self._back.connect("clicked", self._on_back)
        self._where = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.START)
        self._bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, margin_start=12, margin_end=12, margin_top=12, visible=False)
        self._bar.append(self._back)
        self._bar.append(self._where)
        self._shown = Gtk.Stack(hexpand=True, vexpand=True)  # a file or message, or a folder to browse
        self._shown.add_named(self._pane, "preview")
        self._shown.add_named(self._browser, "browser")

        stage = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        for part in (self._bar, self._shown, actions):
            stage.append(part)
        listing = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        for part in (stage, Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), self._timeline):
            listing.append(part)

        self._empty = Adw.StatusPage(icon_name="document-open-recent-symbolic")
        self._stack = Gtk.Stack()
        self._stack.add_named(loading_spinner(halign=Gtk.Align.CENTER), "loading")
        self._stack.add_named(listing, "list")
        self._stack.add_named(self._empty, "empty")

        self._toasts = Adw.ToastOverlay(child=self._stack)
        toolbar = Adw.ToolbarView(content=self._toasts)
        toolbar.add_top_bar(header)
        self.set_content(toolbar)

        self._subscription = client.on_backup_finished(self._tracker.on_finished)
        self.connect("close-request", self._on_close)
        self.connect("notify::is-active", self._on_active)
        install_shortcuts(self, {
            "search": self._browser.focus_search,
            "back": lambda: self._on_back(None),
            "older": lambda: self._timeline.step(1),
            "newer": lambda: self._timeline.step(-1),
            "escape": self._browser.escape,
        })
        self._sync()
        self._stack.set_visible_child_name("loading")
        client.list_versions(path, self._on_versions)

    # -- listing ------------------------------------------------------------------------

    def _on_versions(self, rows, error) -> None:
        if error:
            self._show_empty(_("Could not read the backups"), summarise(error))
            return
        versions = build_versions(rows, datetime.now())
        if not versions:
            self._show_empty(_("No earlier versions"), _("This item is not in any backup yet."))
            return
        self._stack.set_visible_child_name("list")
        self._timeline.fill(versions)

    def _show_empty(self, title: str, detail: str) -> None:
        self._empty.set_title(title)
        self._empty.set_description(GLib.markup_escape_text(detail))
        self._stack.set_visible_child_name("empty")

    def _selected(self) -> VersionRow | None:
        return self._timeline.selected

    def _current(self) -> Target | None:
        """What the stage shows and the buttons act on.

        A file opened from a folder; else the folder being browsed (the one the bar names, which is
        a subfolder once the user has gone into one); else the chosen version of the opened item.
        """
        if self._inner is not None:
            return self._inner
        version = self._selected()
        if version is None:
            return None
        folder = self._browser.folder if version.is_dir else ""
        return Target(version.snapshot, folder or self._path, version.size, version.is_dir)

    def _on_version_chosen(self, version: VersionRow | None) -> None:
        self._inner = None
        if version is not None and version.is_dir:
            self._shown.set_visible_child_name("browser")
            self._browser.open(version.snapshot, self._path)
        elif version is not None:
            self._shown.set_visible_child_name("preview")
            self._previewer.show(self._current())
        self._sync()

    def _restore_targets(self) -> list[Target]:
        """What the restore buttons act on: the items ticked, else what is in view (nothing, if the
        folder is in selection mode and nothing is ticked, rather than the whole folder)."""
        version = self._selected()
        if version is not None and self._inner is None and self._browser.selecting:
            return [Target(version.snapshot, path, 0) for path in self._browser.selected_paths()]
        current = self._current()
        return [] if current is None else [current]

    def _sync(self) -> None:
        free = not self._tracker.busy
        targets = self._restore_targets()
        many = len(targets) > 1
        self._copy.set_sensitive(bool(targets) and free)
        self._replace.set_sensitive(bool(targets) and free)
        self._open.set_sensitive(self._current() is not None and free)
        self._browser.set_busy(not free)
        self._folder.sync(self._current())
        self._copy.set_label(_("Restore {n} as copies").format(n=len(targets)) if many else _("Restore as a copy"))
        self._replace.set_label(
            _("Replace {n} current versions…").format(n=len(targets)) if many else _("Replace the current version…")
        )
        self._sync_bar()

    # -- inside a folder ----------------------------------------------------------------

    def _sync_bar(self) -> None:
        version = self._selected()
        self._bar.set_visible(version is not None and version.is_dir)
        if not self._bar.get_visible():
            return
        shown = self._inner.path if self._inner is not None else (self._browser.folder or self._path)
        self._back.set_sensitive(self._inner is not None or self._browser.can_go_up)
        self._where.set_label(os.path.relpath(shown, os.path.dirname(self._path)))

    def _on_inner_file(self, path: str, size: int) -> None:
        version = self._selected()
        if version is None:
            return
        self._inner = Target(version.snapshot, path, size)
        self._shown.set_visible_child_name("preview")
        self._previewer.show(self._inner)
        self._sync()

    def _on_back(self, button) -> None:
        if self._inner is not None:
            self._inner = None
            self._pane.stop_media()
            self._shown.set_visible_child_name("browser")
        else:
            self._browser.go_up()
        self._sync()

    # -- looking ------------------------------------------------------------------------

    def _on_open(self, button) -> None:
        target = self._current()
        if target is not None and not self._tracker.busy:
            self._previewer.open_outside(target)

    # -- restoring ----------------------------------------------------------------------

    def _on_copy(self, button) -> None:
        self._restore(replace=False)

    def _on_replace(self, button) -> None:
        confirm_replace(self, len(self._restore_targets()), lambda: self._restore(replace=True))

    def _restore(self, replace: bool) -> None:
        targets = self._restore_targets()
        if not targets or self._tracker.busy:
            return
        if self._browser.selecting and self._inner is None:
            # A deleted item always goes back under its own name: as a copy it would stay deleted
            # and the row would look untouched.
            deleted = dict(self._browser.selected_items())
            items = [(t.path, replace or deleted.get(t.path, False)) for t in targets]
        else:
            items = [(t.path, replace) for t in targets]
        self._start_batch(targets[0].snapshot, items)

    def _on_row_restore(self, paths: list[str], in_place: bool) -> None:
        """The button on a row: no confirmation, because it never overwrites anything. A deleted item
        goes back under its own name (nothing is there to set aside); the rest is restored as a copy."""
        version = self._selected()
        if version is not None and not self._tracker.busy:
            self._start_batch(version.snapshot, [(path, in_place) for path in paths])

    def _start_batch(self, snapshot: str, items: list[tuple[str, bool]]) -> None:
        in_place = len(items) == 1 and items[0][1]  # only one item is named in the toast
        RestoreBatch(
            self._client, self._tracker, snapshot, items,
            lambda restored, failures, done: self._on_restored(restored, failures, done, in_place),
        ).start()
        self._sync()

    def _on_restored(self, restored: list[str], failures: list[str], done: list[str], in_place: bool) -> None:
        self._sync()
        self._previewer.drain()
        version = self._selected()
        if version is not None and version.is_dir:
            self._browser.mark_restored(done)  # the rows say "Restored", and nothing stays ticked
            self._browser.refresh_all()  # and the folders that held them no longer say "changed inside"
        toast = Adw.Toast.new(GLib.markup_escape_text(summary(restored, failures, in_place)))
        if restored:
            toast.set_button_label(_("Show in Files"))
            toast.connect("button-clicked", lambda t: self._show_in_files(restored[0]))
        self._toasts.add_toast(toast)

    # -- everything that was deleted ------------------------------------------------------

    def _on_restore_deleted(self) -> None:
        version = self._selected()
        if version is not None:
            self._deleted.start(version.snapshot, self._browser.folder)

    def _after_deleted(self) -> None:
        self._previewer.drain()
        version = self._selected()
        if version is not None and version.is_dir:
            self._browser.refresh_all()  # what came back is no longer "deleted", nor does it make a folder "changed"

    def _show_in_files(self, path: str) -> None:
        Gtk.FileLauncher.new(Gio.File.new_for_path(path)).open_containing_folder(self, None, None)

    def _toast(self, message: str) -> None:
        self._toasts.add_toast(Adw.Toast.new(GLib.markup_escape_text(message)))

    def _on_active(self, window, pspec) -> None:
        """Back from another window (Files, say): what was deleted there must show here."""
        version = self._selected()
        if self.is_active() and version is not None and version.is_dir:
            self._browser.refresh_all()

    def _on_close(self, window) -> bool:
        self._client.unsubscribe(self._subscription)
        self._pane.stop_media()
        self._browser.close()
        self._previewer.close()
        self._folder.close()
        self._client.clear_previews()
        return False
