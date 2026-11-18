"""One row of the folder browser: its name and date, how it compares with now, and what can be done."""

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from delta.i18n import _
from delta.ui.a11y import decorative_icon, named
from delta.ui.folder_listing import Change, FolderRow, change_label, row_titles
from delta.ui.preview_kind import icon_for

TAG_STYLE = {
    Change.DELETED: "error",
    Change.MODIFIED: "warning",
    Change.INSIDE: "warning",
    Change.UNCHANGED: "",  # not dimmed: it is information, and dimmed text fails the contrast minimum
}


def cap_notice_row(cap: int) -> Adw.ActionRow:
    """Shown under the results of a search that hit the limit."""
    return Adw.ActionRow(
        title=_("Showing the first {n} matches").format(n=cap),
        subtitle=_("Type more of the name to narrow them down."),
        activatable=False,
    )


def build_row(
    entry: FolderRow,
    selecting: bool,
    checked: bool,
    on_toggle: Callable[[bool], None],
    on_restore: Callable[[], None],
    restored: bool = False,
) -> tuple[Adw.ActionRow, Gtk.CheckButton | None]:
    title, subtitle = row_titles(entry)
    row = Adw.ActionRow(
        title=GLib.markup_escape_text(title), subtitle=GLib.markup_escape_text(subtitle), activatable=True
    )
    check = None
    same = entry.change is Change.UNCHANGED  # identical to what is there now: nothing to restore
    if selecting:
        check = Gtk.CheckButton(active=checked and not same, valign=Gtk.Align.CENTER, sensitive=not same)
        named(check, _("Select {name}").format(name=title))
        check.connect("toggled", lambda button: on_toggle(button.get_active()))
        row.add_prefix(check)
    mime = Gio.content_type_guess(title, None)[0] or ""
    row.add_prefix(decorative_icon("folder-symbolic" if entry.is_dir else icon_for(mime)))

    # Once restored in this window the row says so, whatever it was before: otherwise a click that
    # worked looks like a click that did nothing, and the user presses it again.
    label = _("Restored") if restored else change_label(entry.change)
    if label:
        tag = Gtk.Label(label=label, valign=Gtk.Align.CENTER)
        tag.add_css_class("caption")
        style = "success" if restored else TAG_STYLE[entry.change]
        if style:
            tag.add_css_class(style)
        row.add_suffix(tag)
    # A deleted item goes back under its own name; anything else, beside what is there. What is
    # identical to today's cannot be restored at all: a copy of it would only be clutter.
    if same:
        tip = _("The same as the current one: nothing to restore")
    elif entry.change is Change.DELETED:
        tip = _("Put it back")
    else:
        tip = _("Restore as a copy")
    restore = Gtk.Button(
        icon_name="document-revert-symbolic", valign=Gtk.Align.CENTER, tooltip_text=tip, sensitive=not same
    )
    restore.add_css_class("flat")
    named(restore, _("{action}: {name}").format(action=tip, name=title))  # every row has one: say which
    restore.connect("clicked", lambda button: on_restore())
    row.add_suffix(restore)
    if entry.is_dir:
        row.add_suffix(decorative_icon("go-next-symbolic"))
    return row, check
