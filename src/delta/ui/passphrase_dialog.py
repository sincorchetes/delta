"""The dialog that asks for the passphrase of the backups again, when the keyring no longer has it."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from delta.i18n import _


def ask_passphrase(parent, location: str, on_answer) -> None:
    """Calls `on_answer(passphrase)` when the person gives one; cancelling, or an empty field, calls nothing."""
    dialog = Adw.AlertDialog.new(
        _("Enter the passphrase of your backups"),
        _("The passphrase of the backups in {location}. It is checked before it is kept in the keyring.").format(location=location),
    )
    entry = Gtk.PasswordEntry(show_peek_icon=True, activates_default=True)
    entry.update_property([Gtk.AccessibleProperty.LABEL], [_("Passphrase")])
    dialog.set_extra_child(entry)
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("use", _("Use passphrase"))
    dialog.set_response_appearance("use", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("use")
    dialog.set_close_response("cancel")
    dialog.choose(parent, None, lambda source, result: _answered(source, result, entry, on_answer))


def _answered(dialog, result, entry, on_answer) -> None:
    passphrase = entry.get_text()
    if dialog.choose_finish(result) == "use" and passphrase:
        on_answer(passphrase)
