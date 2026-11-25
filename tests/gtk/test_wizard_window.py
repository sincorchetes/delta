"""The window that walks the setup wizard, and the wizard that changes the destination."""

from delta.ui.wizard import PathState, Step
from delta.ui.wizard_window import SetupWizard
from wizard_support import go_to_the_summary
from wizard_support import change, setup  # noqa: F401  (fixtures)


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


def test_changing_the_destination_is_a_wizard_of_its_own_with_no_folders_step(change):
    wizard = change.wizard
    wizard._model.destination = change.destination
    wizard._model.recovery_saved = True

    assert wizard.get_title() == "Change where backups are kept"
    wizard._on_next(None)
    wizard._on_next(None)
    assert wizard._model.step is Step.SUMMARY
    assert wizard._next.get_label() == "Use this destination" and wizard._back.get_sensitive()
    wizard._on_back(None)
    assert wizard._model.step is Step.RECOVERY and wizard._next.get_label() == "Next"


def test_the_first_page_of_a_change_cannot_go_back(change):
    assert not change.wizard._back.get_sensitive()


def test_a_changed_destination_leaves_the_folders_to_back_up_alone(change):
    wizard = change.wizard
    wizard._model.destination = change.destination
    wizard._model.recovery_saved = True
    wizard._on_next(None)
    wizard._on_next(None)
    wizard._on_next(None)
    change.client.answer("create_repository", "job", None)

    change.client.subscriptions["on_backup_finished"]("job", True, "")

    assert change.done == 1 and change.settings.written == []


def test_a_folder_with_a_repository_is_reopened_with_its_passphrase_instead_of_created(setup):
    wizard = setup.wizard
    wizard._model.inspect = lambda path: PathState.REPOSITORY
    wizard._model.destination = setup.destination
    wizard._model.folders = ("/home/u/docs",)
    wizard._model.inspect = lambda path: PathState.REPOSITORY if path == setup.destination else PathState.NOT_EMPTY

    wizard._on_next(None)
    wizard._on_next(None)

    summary = wizard._pages[Step.SUMMARY]
    assert wizard._model.step is Step.SUMMARY  # no recovery key to save: it has its own passphrase
    assert summary._existing.get_visible() and not wizard._next.get_visible()
    summary._existing_passphrase.set_text("old passphrase")
    summary._existing_button.emit("clicked")
    assert setup.client.asked("use_repository") == [(setup.destination, "old passphrase")]
    assert setup.client.asked("create_repository") == []

    setup.client.answer("use_repository", "job", None)
    setup.client.subscriptions["on_backup_finished"]("job", True, "")
    assert setup.done == 1 and setup.settings.written == [("backup-sources", ["/home/u/docs"])]


def test_going_back_from_a_repository_to_a_new_folder_creates_again(setup):
    wizard = setup.wizard
    wizard._model.destination = setup.destination
    wizard._model.inspect = lambda path: PathState.REPOSITORY if path == setup.destination else PathState.NOT_EMPTY
    wizard._on_next(None)
    wizard._on_next(None)
    wizard._on_back(None)
    wizard._on_back(None)

    wizard._model.inspect = lambda path: PathState.MISSING
    wizard._model.recovery_saved = True
    for _step in range(3):
        wizard._on_next(None)

    assert wizard._next.get_visible() and not wizard._pages[Step.SUMMARY]._existing.get_visible()
