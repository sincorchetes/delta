"""What a mutation run showed nothing watched in the words and edges of each refusal."""


import pytest

from delta.domain.backup_job import BackupJob
from delta.domain.errors import InvalidPath
from delta.domain.paths import validate_in_home, validate_restore
from delta.domain.repository import Repository
from delta.domain.retention import RetentionPolicy
from delta.domain.schedule import Schedule
from delta.ui.wizard import (
    MIN_OWN_PASSPHRASE,
    PathState,
    Protection,
    Step,
    WizardModel,
    check_destination,
    check_folders,
    check_passphrase,
)

# --- what a refusal says, and which rule refuses -----------------------------------------------------


@pytest.mark.parametrize(
    ("source", "target", "message"),
    [
        ("rel/a", "/home/u/t", "source must be an absolute path"),
        ("/home/u/a", "t", "target must be an absolute path"),
        ("/home/u/a", "/home/u/a/../b", "target must not contain '..'"),  # it would land inside home: still refused
        ("/home/u/docs/../a", "/home/u/t", "source must not contain '..'"),
        ("/etc/passwd", "/home/u/t", "source must be inside /home/u"),
        ("/home/u/a", "/tmp/x", "target must be inside /home/u"),
    ],
)
def test_a_refused_restore_names_the_path_and_the_rule(source, target, message):
    with pytest.raises(InvalidPath, match=message):
        validate_restore(source, target, "/home/u")


def test_a_path_outside_home_is_refused_by_name():
    with pytest.raises(InvalidPath, match="path must be inside /home/u"):
        validate_in_home("/etc/passwd", "/home/u")


def test_the_domain_says_what_is_wrong():
    with pytest.raises(ValueError, match="at least one source"):
        BackupJob("j", ())
    job = BackupJob("j", ("/home",))
    with pytest.raises(ValueError, match="cannot go from pending to succeeded"):
        job.succeed()
    with pytest.raises(ValueError, match="must not be empty"):
        Repository("")
    with pytest.raises(ValueError, match="must be an absolute path"):
        Repository("relative")
    with pytest.raises(ValueError, match="keep_daily must not be negative"):
        RetentionPolicy(keep_daily=-1)
    with pytest.raises(ValueError, match="invalid calendar expression"):
        Schedule("hourly\nExecStart=/bin/sh")


# --- the setup wizard's rules, at their edges --------------------------------------------------------

HOME = "/home/user"


def anywhere(state=PathState.NOT_EMPTY):
    return lambda path: state


def test_a_passphrase_of_exactly_the_minimum_length_is_accepted_and_one_less_is_not():
    assert check_passphrase("x" * MIN_OWN_PASSPHRASE, "x" * MIN_OWN_PASSPHRASE) is None
    assert check_passphrase("x" * (MIN_OWN_PASSPHRASE - 1), "x" * (MIN_OWN_PASSPHRASE - 1))


def test_a_lone_tilde_is_the_home_folder_and_a_trailing_slash_is_dropped():
    assert check_folders(("~",), HOME, anywhere()) == ((HOME,), [])
    assert check_destination("~/Backups//", HOME, lambda path: PathState.MISSING) == (f"{HOME}/Backups", None)
    assert check_destination("///", HOME, anywhere())[1] == "Choose a folder, not the whole disk."


def test_one_bad_folder_does_not_stop_the_rest_from_being_read():
    inspect = lambda path: PathState.MISSING if path.endswith("missing") else PathState.NOT_EMPTY  # noqa: E731

    folders, problems = check_folders(("relative", "~/missing", "~/Pictures"), HOME, inspect)

    assert folders == (f"{HOME}/Pictures",) and len(problems) == 2


def test_going_back_says_whether_it_moved():
    wizard = WizardModel(home=HOME, inspect=anywhere(), step=Step.FOLDERS)

    assert wizard.back() is True and wizard.step is Step.DESTINATION
    assert wizard.back() is False


def test_the_final_request_checks_every_step_whichever_one_the_wizard_is_on():
    wizard = WizardModel(home=HOME, inspect=lambda path: PathState.MISSING, destination="~/Backups", recovery_key="K")

    with pytest.raises(ValueError, match="recovery key"):
        wizard.request()


def test_the_request_and_the_folder_step_use_the_home_folder_and_the_disk_inspector():
    wizard = WizardModel(
        home=HOME,
        inspect=lambda path: PathState.MISSING if path.endswith("Backups") else PathState.NOT_EMPTY,
        destination="~/Backups", folders=("~/Pictures",), recovery_saved=True, recovery_key="K",
    )

    assert wizard.errors(Step.FOLDERS) == []
    assert wizard.request().folders == (f"{HOME}/Pictures",)


def test_the_summary_names_the_protection_chosen():
    own = WizardModel(home=HOME, inspect=anywhere(), protection=Protection.OWN)
    generated = WizardModel(home=HOME, inspect=anywhere())

    assert dict(own.summary())["Protection"] == "Your own passphrase"
    assert dict(generated.summary())["Protection"] == "Recovery key, saved by you"
