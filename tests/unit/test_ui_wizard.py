import re

import pytest

from delta.ui.wizard import (
    MIN_OWN_PASSPHRASE,
    PathState,
    Protection,
    Step,
    WizardModel,
    check_destination,
    check_folders,
    check_passphrase,
    generate_recovery_key,
    repository_exists,
)

HOME = "/home/user"


def test_borgs_refusal_to_overwrite_a_repository_is_recognised():
    assert repository_exists("A repository already exists at /home/me/delta.")
    assert repository_exists("a REPOSITORY ALREADY EXISTS at /x")


def test_other_failures_are_not_mistaken_for_an_existing_repository():
    assert not repository_exists("The passphrase for this repository is incorrect.")
    assert not repository_exists("")


class Disk:
    """A pretend filesystem: unknown paths do not exist."""

    def __init__(self, **states):
        self.states = {path.replace("__", "/"): state for path, state in states.items()}

    def __call__(self, path):
        return self.states.get(path, PathState.MISSING)


def model(disk=None, **fields):
    return WizardModel(home=HOME, inspect=disk or Disk(), recovery_key="AAAAA-BBBBB", **fields)


# --- recovery key -----------------------------------------------------------------------


def test_recovery_key_is_readable_and_has_no_ambiguous_characters():
    key = generate_recovery_key()
    assert re.fullmatch(r"([A-Z2-9]{5}-){5}[A-Z2-9]{5}", key)
    assert not set(key) & set("0OIL1")


def test_recovery_keys_are_not_repeated():
    assert len({generate_recovery_key() for _ in range(200)}) == 200


# --- destination ------------------------------------------------------------------------


def test_a_new_local_folder_is_accepted_and_tilde_is_expanded():
    assert check_destination("~/Backups/delta", HOME, Disk()) == ("/home/user/Backups/delta", None)


def test_an_existing_empty_folder_is_accepted():
    disk = Disk(**{"__home__user__usb": PathState.EMPTY_DIR})
    assert check_destination("/home/user/usb", HOME, disk)[0] == "/home/user/usb"


@pytest.mark.parametrize(
    ("state", "word"),
    [(PathState.NOT_EMPTY, "not empty"), (PathState.FILE, "file")],
)
def test_a_folder_that_borg_could_not_initialise_is_refused(state, word):
    location, error = check_destination("/data/x", HOME, Disk(**{"__data__x": state}))
    assert location is None and word in error


@pytest.mark.parametrize("text", ["", "   "])
def test_an_empty_destination_is_refused(text):
    assert check_destination(text, HOME, Disk())[1]


@pytest.mark.parametrize("text", ["Backups", "../Backups", "/"])
def test_relative_paths_and_the_root_are_refused(text):
    location, error = check_destination(text, HOME, Disk())
    assert location is None and error


def test_the_destination_is_what_the_user_typed():
    assert model(destination="~/Backups").destination_text() == "~/Backups"


def test_a_local_destination_lets_the_wizard_continue():
    wizard = model(destination="~/Backups")
    assert wizard.errors() == [] and wizard.can_continue()


def test_the_wizard_produces_the_request_and_summary_for_a_local_folder():
    wizard = model(destination="~/Backups", recovery_saved=True, step=Step.SUMMARY)
    assert wizard.request().location == "/home/user/Backups"
    assert dict(wizard.summary())["Destination"] == "/home/user/Backups"


# --- folders ----------------------------------------------------------------------------


def test_no_folders_means_the_whole_home_folder():
    assert check_folders((), HOME, Disk()) == ((), [])


def test_folders_are_normalised_and_deduplicated():
    disk = Disk(**{"__home__user__Pictures": PathState.NOT_EMPTY})
    folders, problems = check_folders(("~/Pictures", "/home/user//Pictures/"), HOME, disk)
    assert folders == ("/home/user/Pictures",) and problems == []


def test_each_unusable_folder_gets_its_own_message():
    disk = Disk(**{"__a__file": PathState.FILE})
    folders, problems = check_folders(("/a/file", "/missing", "relative"), HOME, disk)
    assert folders == () and len(problems) == 3


# --- passphrase -------------------------------------------------------------------------


def test_a_short_passphrase_is_refused():
    assert str(MIN_OWN_PASSPHRASE) in check_passphrase("short", "short")


def test_mismatched_confirmation_is_refused():
    assert "match" in check_passphrase("a-long-enough-one", "a-long-enough-two")


def test_a_good_passphrase_passes():
    assert check_passphrase("a-long-enough-one", "a-long-enough-one") is None


# --- the wizard flow --------------------------------------------------------------------


def test_the_wizard_walks_the_steps_in_order():
    wizard = model(destination="~/Backups")
    assert wizard.step is Step.DESTINATION

    assert wizard.next() and wizard.step is Step.FOLDERS
    assert wizard.next() and wizard.step is Step.RECOVERY


def test_it_will_not_advance_past_an_invalid_step():
    wizard = model(destination="")
    assert not wizard.next() and wizard.step is Step.DESTINATION
    assert wizard.errors()


def test_the_recovery_key_must_be_saved_or_the_risk_accepted():
    wizard = model(destination="~/Backups", step=Step.RECOVERY)
    assert not wizard.can_continue()
    assert "recovery key" in wizard.errors()[0].lower()

    wizard.recovery_saved = True

    assert wizard.can_continue() and wizard.next() and wizard.step is Step.SUMMARY


def test_choosing_your_own_passphrase_needs_no_recovery_key_but_a_good_passphrase():
    wizard = model(destination="~/B", step=Step.RECOVERY, protection=Protection.OWN)
    assert not wizard.can_continue()

    wizard.own_passphrase = wizard.own_confirmation = "my own long passphrase"

    assert wizard.can_continue()


def test_going_back_keeps_what_was_entered():
    wizard = model(destination="~/Backups")
    wizard.next()
    wizard.back()
    assert wizard.step is Step.DESTINATION and wizard.destination == "~/Backups"
    assert not wizard.back()


def test_the_last_step_cannot_advance_further():
    wizard = model(destination="~/B", recovery_saved=True, step=Step.SUMMARY)
    assert wizard.is_last and not wizard.next()


def test_the_request_carries_the_recovery_key_as_the_passphrase():
    wizard = model(destination="~/Backups", recovery_saved=True, step=Step.SUMMARY)

    request = wizard.request()

    assert request.location == "/home/user/Backups"
    assert request.folders == () and request.passphrase == "AAAAA-BBBBB"


def test_the_request_carries_the_users_own_passphrase_when_chosen():
    wizard = model(
        destination="~/Backups", protection=Protection.OWN, step=Step.SUMMARY,
        own_passphrase="my own long passphrase", own_confirmation="my own long passphrase",
    )
    assert wizard.request().passphrase == "my own long passphrase"


def test_an_incomplete_wizard_cannot_produce_a_request():
    with pytest.raises(ValueError):
        model(destination="~/Backups", step=Step.SUMMARY).request()


def test_going_back_and_breaking_an_earlier_step_blocks_the_request():
    wizard = model(destination="~/Backups", recovery_saved=True, step=Step.SUMMARY)
    wizard.destination = ""
    with pytest.raises(ValueError):
        wizard.request()


def test_the_summary_describes_destination_folders_and_protection():
    disk = Disk(**{"__home__user__Pictures": PathState.NOT_EMPTY})
    wizard = model(disk, destination="~/Backups", folders=("~/Pictures",), recovery_saved=True)

    labels = dict(wizard.summary())

    assert labels["Destination"] == "/home/user/Backups"
    assert labels["Folders"] == "/home/user/Pictures"
    assert "Recovery key" in labels["Protection"]


def test_the_summary_says_personal_folder_when_none_chosen():
    assert dict(model(destination="~/B").summary())["Folders"] == "Your personal folder"


# --- changing the destination: what is backed up stays as it is -----------------------------------


def changing(**fields):
    return WizardModel(home=HOME, inspect=lambda path: PathState.MISSING, keep_folders=True, recovery_key="AAAAA-BBBBB", **fields)


def test_changing_the_destination_skips_the_folders_step():
    model = changing(destination="/media/disk/delta", recovery_saved=True)

    assert model.steps == [Step.DESTINATION, Step.RECOVERY, Step.SUMMARY]
    assert model.next() and model.step is Step.RECOVERY
    assert model.next() and model.step is Step.SUMMARY and model.is_last
    assert model.back() and model.back() and model.step is Step.DESTINATION and not model.back()


def test_the_summary_of_a_change_does_not_list_the_folders():
    model = changing(destination="/media/disk/delta")

    assert [label for label, _value in model.summary()] == ["Destination", "Protection"]


def test_a_first_set_up_has_every_step():
    model = WizardModel(home=HOME, inspect=lambda path: PathState.MISSING)

    assert model.steps == list(Step)
