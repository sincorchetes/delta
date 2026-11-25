"""The pages of the setup wizard, against a stand-in daemon client."""

from types import SimpleNamespace
from gtk_helpers import of_type
from gi.repository import Adw, Gio, GLib, Gtk
from delta.ui import wizard_pages
from delta.ui.wizard import Protection
from wizard_support import SaveDialog, folders_page, recovery_page, summary_page


def test_with_no_folders_the_whole_personal_folder_is_shown_and_cannot_be_changed():
    page, _model, _changes = folders_page()

    rows = of_type(page._list, Adw.ActionRow)
    assert len(rows) == 1 and not rows[0].get_sensitive()


def test_adding_a_folder_lists_it_once():
    page, chosen, changes = folders_page()

    page._add("/home/u/docs")
    page._add("/home/u/docs")

    assert chosen.folders == ("/home/u/docs",) and len(of_type(page._list, Adw.ActionRow)) == 1
    assert len(changes) == 2


def test_removing_a_folder_goes_back_to_the_whole_personal_folder():
    page, chosen, _changes = folders_page(folders=("/home/u/docs",))

    of_type(page._list, Gtk.Button)[0].emit("clicked")

    assert chosen.folders == () and not of_type(page._list, Adw.ActionRow)[0].get_sensitive()


def test_the_add_button_opens_the_folder_chooser(monkeypatch):
    page, chosen, _changes = folders_page()
    monkeypatch.setattr(wizard_pages, "choose_folder", lambda window, title, on_chosen: on_chosen("/home/u/music"))

    page._on_add(None)

    assert chosen.folders == ("/home/u/music",)


def test_copying_the_key_puts_it_on_the_clipboard_but_does_not_count_as_saving_it():
    page, chosen, _changes = recovery_page()

    page._on_copy(None)

    assert page.clipboard.content is not None and chosen.recovery_saved is False


def test_the_switch_says_the_key_is_saved():
    page, chosen, changes = recovery_page()

    page._saved.set_active(True)

    assert chosen.recovery_saved is True and changes == [True]


def test_choosing_an_own_passphrase_swaps_the_key_for_two_entries():
    page, chosen, _changes = recovery_page()

    page._own.set_active(True)
    page._passphrase.set_text("correct horse")
    page._confirmation.set_text("correct horse")

    assert chosen.protection is Protection.OWN and not page._key_group.get_visible()
    assert page._passphrase.get_visible() and chosen.own_passphrase == chosen.own_confirmation == "correct horse"

    page._own.set_active(False)
    assert chosen.protection is Protection.GENERATED and page._key_group.get_visible()


def test_saving_the_key_to_a_file_counts_as_saving_it(monkeypatch, tmp_path):
    page, chosen, _changes = recovery_page()
    dialogs = []
    monkeypatch.setattr(
        wizard_pages,
        "Gtk",
        SimpleNamespace(FileDialog=lambda **kwargs: dialogs.append(SaveDialog(**kwargs)) or dialogs[-1]),
    )

    page._on_save(None)
    target = tmp_path / "key.txt"
    dialogs[0].callback(dialogs[0], Gio.File.new_for_path(str(target)))

    assert dialogs[0].initial_name == "delta-recovery-key.txt"
    assert target.read_text() == "AAAAA-BBBBB\n" and chosen.recovery_saved is True
    assert (target.stat().st_mode & 0o077) == 0  # private


def test_dismissing_the_save_dialog_changes_nothing():
    page, chosen, _changes = recovery_page()

    page._on_save_chosen(SaveDialog("t", "n"), GLib.Error("dismissed", domain="test", code=1))

    assert chosen.recovery_saved is False


def test_a_file_that_cannot_be_written_is_reported_and_does_not_count():
    page, chosen, _changes = recovery_page()

    page._on_save_chosen(SaveDialog("t", "n"), Gio.File.new_for_path("/nonexistent-folder/key.txt"))

    assert chosen.recovery_saved is False and page._problems.get_visible()


def test_the_summary_lists_what_will_be_done_and_refreshes_without_piling_up():
    page, _chosen = summary_page()

    page.refresh()
    page.refresh()

    assert len(page._rows) == 3
    assert any("/media/disk/delta-backups" in (row.get_subtitle() or "") for row in page._rows)


def test_the_existing_repository_can_be_offered_used_and_hidden_again():
    page, _chosen = summary_page()
    used = []

    page.offer_existing(used.append)
    assert page._existing.get_visible() and not page._existing_button.get_sensitive()
    page._existing_passphrase.set_text("secret")
    page._existing_button.emit("clicked")
    page.offer_existing(used.append)  # offering again keeps what was typed
    page.hide_existing()

    assert used == ["secret"] and not page._existing.get_visible()
    assert page._existing_passphrase.get_text() == "secret"


def test_using_the_existing_repository_before_it_is_offered_does_nothing():
    page, _chosen = summary_page()

    page._on_use_clicked(None)


def test_being_busy_shows_the_spinner_and_freezes_the_existing_group():
    page, _chosen = summary_page()

    page.set_busy(True)
    assert page._busy.get_visible() and not page._existing.get_sensitive()

    page.set_busy(False)
    assert not page._busy.get_visible() and page._existing.get_sensitive()
