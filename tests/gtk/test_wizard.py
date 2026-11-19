"""The setup wizard: its pages and the window that walks them, against a stand-in daemon client."""

from types import SimpleNamespace

import pytest
from gtk_helpers import of_type
from gi.repository import Adw, Gio, GLib, Gtk

from delta.ui import wizard_pages
from delta.ui.wizard import PathState, Protection, Step, WizardModel
from delta.ui.wizard_pages import FoldersPage, RecoveryPage, SummaryPage
from delta.ui.wizard_window import SetupWizard

HOME = "/home/u"


def model(**fields):
    return WizardModel(home=HOME, inspect=lambda path: PathState.MISSING, recovery_key="AAAAA-BBBBB", **fields)


# --- the folders page ----------------------------------------------------------------------------


def folders_page(**fields):
    chosen = model(**fields)
    changes = []
    return FoldersPage(chosen, None, lambda: changes.append(chosen.folders)), chosen, changes


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


# --- the recovery page ---------------------------------------------------------------------------


class Clipboard:
    def __init__(self):
        self.content = None

    def set_content(self, provider):
        self.content = provider


def recovery_page():
    chosen = model()
    changes = []
    page = RecoveryPage(chosen, None, lambda: changes.append(True))
    page.clipboard = Clipboard()
    page.get_clipboard = lambda: page.clipboard
    return page, chosen, changes


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


class SaveDialog:
    def __init__(self, title, initial_name):
        self.title, self.initial_name = title, initial_name
        self.callback = None

    def save(self, window, cancellable, callback):
        self.callback = callback

    def save_finish(self, result):
        if isinstance(result, GLib.Error):
            raise result
        return result


def test_saving_the_key_to_a_file_counts_as_saving_it(monkeypatch, tmp_path):
    page, chosen, _changes = recovery_page()
    dialogs = []
    monkeypatch.setattr(
        wizard_pages, "Gtk", SimpleNamespace(FileDialog=lambda **kwargs: dialogs.append(SaveDialog(**kwargs)) or dialogs[-1])
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


# --- the summary page ----------------------------------------------------------------------------


def summary_page():
    chosen = model(destination="/media/disk/delta-backups", recovery_saved=True)
    return SummaryPage(chosen, None, lambda: None), chosen


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


# --- the wizard window ---------------------------------------------------------------------------


class Settings:
    def __init__(self):
        self.written = []

    def set_strv(self, key, value):
        self.written.append((key, value))


@pytest.fixture
def setup(client, tmp_path):
    seen = SimpleNamespace(done=0, settings=Settings(), client=client)
    seen.wizard = SetupWizard(None, client, seen.settings, lambda: setattr(seen, "done", seen.done + 1))
    seen.destination = str(tmp_path / "delta-backups")
    return seen


def go_to_the_summary(seen):
    seen.wizard._model.destination = seen.destination
    seen.wizard._model.recovery_saved = True
    for _step in range(3):
        seen.wizard._on_next(None)
    assert seen.wizard._model.step is Step.SUMMARY


def test_the_wizard_starts_at_the_destination_and_cannot_go_on_until_it_is_chosen(setup):
    wizard = setup.wizard

    assert wizard._model.step is Step.DESTINATION
    assert not wizard._back.get_sensitive() and not wizard._next.get_sensitive()

    wizard._on_back(None)
    wizard._on_next(None)
    assert wizard._model.step is Step.DESTINATION


def test_the_wizard_walks_to_the_summary_and_back(setup):
    go_to_the_summary(setup)
    wizard = setup.wizard

    assert wizard._next.get_label() == "Create backups" and wizard._back.get_sensitive()
    wizard._on_back(None)
    assert wizard._model.step is Step.RECOVERY and wizard._next.get_label() == "Next"


def test_typing_a_destination_makes_the_problems_visible_once_the_step_was_touched(setup):
    wizard = setup.wizard

    wizard._pages[Step.DESTINATION]._path.set_text("relative/path")

    assert wizard._pages[Step.DESTINATION]._problems.get_visible() and not wizard._next.get_sensitive()


def test_creating_the_repository_sends_the_choices_and_waits(setup):
    go_to_the_summary(setup)

    setup.wizard._on_next(None)

    assert setup.client.asked("create_repository") == [(setup.destination, setup.wizard._model.recovery_key)]
    assert setup.wizard._busy and not setup.wizard._next.get_sensitive()


def test_a_finished_job_closes_the_wizard_and_saves_the_chosen_folders(setup):
    go_to_the_summary(setup)
    setup.wizard._model.inspect = lambda path: PathState.MISSING if path == setup.destination else PathState.NOT_EMPTY
    setup.wizard._model.folders = ("/home/u/docs",)
    setup.wizard._on_next(None)
    setup.client.answer("create_repository", "job", None)

    setup.client.subscriptions["on_backup_finished"]("job", True, "")

    assert setup.done == 1 and setup.settings.written == [("backup-sources", ["/home/u/docs"])]
    assert setup.wizard._model.own_passphrase == ""


def test_a_result_that_arrives_before_the_reply_is_not_lost(setup):
    go_to_the_summary(setup)
    setup.wizard._on_next(None)

    setup.client.subscriptions["on_backup_finished"]("job", True, "")
    assert setup.done == 0
    setup.client.answer("create_repository", "job", None)

    assert setup.done == 1


def test_a_result_for_another_job_is_ignored(setup):
    go_to_the_summary(setup)
    setup.wizard._on_next(None)
    setup.client.answer("create_repository", "job", None)

    setup.client.subscriptions["on_backup_finished"]("someone-else", True, "")

    assert setup.done == 0


def test_without_settings_finishing_still_works(client, tmp_path):
    done = []
    wizard = SetupWizard(None, client, None, lambda: done.append(True))
    wizard._model.destination = str(tmp_path / "delta-backups")
    wizard._model.recovery_saved = True
    for _step in range(4):
        wizard._on_next(None)
    client.answer("create_repository", "job", None)

    client.subscriptions["on_backup_finished"]("job", True, "")

    assert done == [True]


def test_a_failure_is_shown_and_the_wizard_can_try_again(setup):
    go_to_the_summary(setup)
    setup.wizard._on_next(None)

    setup.client.answer("create_repository", None, "disk full")

    summary = setup.wizard._pages[Step.SUMMARY]
    assert not setup.wizard._busy and summary._problems.get_text() == "disk full"
    assert not summary._existing.get_visible()


def test_a_failed_job_is_shown_the_same_way(setup):
    go_to_the_summary(setup)
    setup.wizard._on_next(None)
    setup.client.answer("create_repository", "job", None)

    setup.client.subscriptions["on_backup_finished"]("job", False, "disk full")

    assert setup.wizard._pages[Step.SUMMARY]._problems.get_text() == "disk full"


def test_a_repository_that_is_already_there_can_be_used_with_its_passphrase(setup):
    go_to_the_summary(setup)
    setup.wizard._on_next(None)
    setup.client.answer("create_repository", None, "A repository already exists at /x.")
    summary = setup.wizard._pages[Step.SUMMARY]
    assert summary._existing.get_visible()

    summary._existing_passphrase.set_text("old passphrase")
    summary._existing_button.emit("clicked")
    assert setup.client.asked("use_repository") == [(setup.destination, "old passphrase")]

    setup.client.answer("use_repository", None, "The passphrase is incorrect.")
    assert summary._existing.get_visible()  # a wrong passphrase can be retried


def test_using_an_existing_repository_without_a_request_does_nothing(setup):
    setup.wizard._use_existing("secret")

    assert setup.client.asked("use_repository") == []


def test_closing_the_wizard_lets_go_of_the_signal(setup):
    assert setup.wizard._on_close(setup.wizard) is False

    assert setup.client.unsubscribed == [1]
