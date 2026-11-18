"""Shared bits of the wizard pages."""

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from delta.ui.a11y import tipped
from delta.ui.wizard import WizardModel

Changed = Callable[[], None]


def flat_icon_button(icon: str, tooltip: str) -> Gtk.Button:
    button = Gtk.Button(icon_name=icon, valign=Gtk.Align.CENTER)
    button.add_css_class("flat")
    return tipped(button, tooltip)


def choose_folder(window, title: str, on_chosen: Callable[[str], None]) -> None:
    def finished(dialog, result) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return  # dismissed
        if folder.get_path():
            on_chosen(folder.get_path())

    Gtk.FileDialog(title=title).select_folder(window, None, finished)


def choose_file(window, title: str, on_chosen: Callable[[str], None]) -> None:
    def finished(dialog, result) -> None:
        try:
            chosen = dialog.open_finish(result)
        except GLib.Error:
            return  # dismissed
        if chosen.get_path():
            on_chosen(chosen.get_path())

    Gtk.FileDialog(title=title).open(window, None, finished)


class Page(Adw.PreferencesPage):
    """A page that can show the model's problems for its step."""

    def __init__(self, model: WizardModel, window, changed: Changed) -> None:
        super().__init__()
        self._model, self._window, self._changed = model, window, changed
        self._problems = Gtk.Label(wrap=True, xalign=0, visible=False)
        self._problems.add_css_class("error")

    def _finish_layout(self) -> None:
        group = Adw.PreferencesGroup()
        group.add(self._problems)
        self.add(group)

    def show_problems(self, problems: list[str]) -> None:
        self._problems.set_text("\n".join(problems))
        self._problems.set_visible(bool(problems))
