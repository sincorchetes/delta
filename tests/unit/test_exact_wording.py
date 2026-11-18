"""The exact words of each refusal and message: a mutation run showed only fragments were checked."""

import logging
import secrets
from datetime import datetime

import pytest

from delta.application.backup_notifications import BackupNotifications
from delta.application.backup_service import BackupService
from delta.application.deleted_service import DeletedService
from delta.application.preview_service import PreviewService
from delta.application.repository_setup import RepositorySetup, generate_passphrase
from delta.application.restore_service import RestoreService
from delta.application.snapshots import snapshot_name
from delta.domain.backup_job import BackupJob, JobState
from delta.domain.errors import DeltaError, EngineError, InvalidPath, SnapshotNotFound
from delta.domain.notification import Notification, NotificationKind
from delta.domain.repository import Encryption, Repository
from delta.domain.retention import RetentionPolicy
from delta.domain.snapshot import Snapshot
from delta.infrastructure import borg_commands as commands
from delta.infrastructure import borg_parsing as parsing
from delta.ui.wizard import PathState, Step, WizardModel, check_destination, check_folders, check_passphrase

REPO = Repository("/srv/repo")
HOME = "/home/user"
NO_REPOSITORY = "no repository configured"


def said(error, call, *args):
    with pytest.raises(error) as caught:
        call(*args)
    return str(caught.value)


class Engine:
    """Knows one snapshot; extracting does nothing unless told to fail."""

    def __init__(self, failure=None):
        self.failure = failure

    def list_snapshots(self, repo):
        return [Snapshot("id1", "first", datetime(2026, 1, 1))]

    def extract(self, repo, snapshot, paths, destination):
        if self.failure:
            raise self.failure


# --- the engine ----------------------------------------------------------------------------------------


def test_pruning_with_a_policy_that_keeps_nothing_is_refused_in_these_words():
    nothing = RetentionPolicy(0, 0, 0, 0)

    assert said(ValueError, commands.prune, REPO, nothing) == "refusing to prune with a policy that keeps nothing"


@pytest.mark.parametrize(
    "parse",
    [
        lambda: parsing.parse_snapshots("not json"),
        lambda: parsing.parse_file_entry("not json", "/home/u/a"),
        lambda: parsing.parse_folder_listing("not json", "/home/u"),
        lambda: parsing.parse_folder_tree("not json", "/home/u"),
        lambda: parsing.parse_folder_search("not json", "/home/u", "a", 10),
    ],
)
def test_output_borg_should_never_give_is_reported_with_what_was_wrong(parse):
    assert said(EngineError, parse) == "unexpected borg list output: Expecting value: line 1 column 1 (char 0)"


# --- the services --------------------------------------------------------------------------------------


def test_without_a_repository_every_service_says_so(tmp_path):
    restore = RestoreService(Engine(), None, HOME)
    preview = PreviewService(Engine(), None, HOME, str(tmp_path))

    assert said(DeltaError, preview.preview, "first", f"{HOME}/a") == NO_REPOSITORY
    assert said(DeltaError, restore.restore, "first", f"{HOME}/a", str(tmp_path)) == NO_REPOSITORY
    assert said(DeltaError, restore.restore_beside, "first", f"{HOME}/a", False) == NO_REPOSITORY
    assert said(DeltaError, restore.place_missing, "first", [f"{HOME}/a"]) == NO_REPOSITORY


def test_a_backup_without_a_repository_fails_saying_so():
    service = BackupService(Engine(), None, (HOME,))

    job = service.run(service.new_job())

    assert (job.state, job.message) == (JobState.FAILED, NO_REPOSITORY)


def test_restoring_into_a_folder_that_is_not_there_is_refused_in_these_words(tmp_path):
    restore = RestoreService(Engine(), REPO, HOME)

    refusal = said(InvalidPath, restore.restore, "first", f"{HOME}/a", str(tmp_path / "missing"))

    assert refusal == "target must be an existing directory"


def test_a_snapshot_that_is_gone_is_explained_without_naming_it():
    assert said(SnapshotNotFound, snapshot_name, Engine(), REPO, "pruned") == (
        "That backup no longer exists: a newer one may have replaced it. Reopen the window to see the current ones."
    )


def test_what_a_snapshot_lacks_is_named(tmp_path):
    source = str(tmp_path / "a.txt")
    restore = RestoreService(Engine(), REPO, str(tmp_path))
    preview = PreviewService(Engine(), REPO, str(tmp_path), str(tmp_path / "preview"))

    assert said(SnapshotNotFound, restore.restore_beside, "first", source, False) == source
    assert said(SnapshotNotFound, preview.preview, "first", source) == source


def test_a_disk_problem_is_passed_on_as_the_system_worded_it(tmp_path):
    engine = Engine(OSError("the disk is on fire"))
    restore = RestoreService(engine, REPO, str(tmp_path))
    preview = PreviewService(engine, REPO, str(tmp_path), str(tmp_path / "preview"))

    assert said(DeltaError, preview.preview, "first", str(tmp_path / "a")) == "the disk is on fire"
    assert said(DeltaError, restore.place_missing, "first", [str(tmp_path / "a")]) == "the disk is on fire"


def test_only_folders_inside_home_can_have_something_deleted_to_find():
    deleted = DeletedService(Engine(), REPO, HOME, RestoreService(Engine(), REPO, HOME))

    assert deleted.prepare(f"{HOME}//docs/") == f"{HOME}/docs"
    assert said(InvalidPath, deleted.prepare, "/etc") == f"path must be inside {HOME}"


def test_an_unencrypted_repository_is_refused_in_these_words():
    setup, plain = RepositorySetup(Engine(), None), Repository("/srv/repo", Encryption.NONE)

    assert said(ValueError, setup.create, plain) == "repositories must be encrypted"
    assert said(ValueError, setup.adopt, plain, "secret") == "repositories must be encrypted"
    assert said(ValueError, setup.adopt, REPO, "") == "an existing repository needs its passphrase"


def test_a_generated_passphrase_asks_for_its_32_bytes_itself(monkeypatch):
    asked = []
    monkeypatch.setattr(secrets, "token_urlsafe", lambda nbytes=None: asked.append(nbytes) or "generated")

    assert generate_passphrase() == "generated"
    assert asked == [32]  # Python's own default "is subject to change at any time"


def test_the_domain_refuses_in_these_words():
    assert said(ValueError, BackupJob, "job", ()) == "a backup job needs at least one source"
    assert said(ValueError, Repository, "") == "repository location must not be empty"
    assert said(ValueError, Repository, "relative") == "repository location must be an absolute path"


# --- notifications -------------------------------------------------------------------------------------


class Notifier:
    def __init__(self, failure=None):
        self.sent, self.failure = [], failure

    def notify(self, notification):
        if self.failure:
            raise self.failure
        self.sent.append(notification)


def test_a_repository_problem_is_notified_with_its_detail():
    notifier = Notifier()

    BackupNotifications(notifier).repository_failed("it is locked")

    assert notifier.sent == [Notification(NotificationKind.REPOSITORY_FAILED, "it is locked")]


def test_a_notification_that_cannot_be_sent_is_logged_by_name(caplog):
    with caplog.at_level(logging.ERROR):
        BackupNotifications(Notifier(RuntimeError("no bus"))).failed("detail")

    assert [record.getMessage() for record in caplog.records] == ["cannot send notification backup-failed"]


# --- the setup wizard ----------------------------------------------------------------------------------


def always(state):
    return lambda path: state


def test_each_unusable_destination_is_explained_in_these_words():
    assert check_destination("  ", HOME, always(PathState.MISSING)) == (None, "Choose where to keep your backups.")
    assert check_destination("relative", HOME, always(PathState.MISSING)) == (
        None, "Enter a full folder path, for example ~/Backups.",
    )
    assert check_destination("~/a", HOME, always(PathState.FILE)) == (None, "That path is a file, not a folder.")
    assert check_destination("~/a", HOME, always(PathState.NOT_EMPTY)) == (
        None, "That folder is not empty. Choose a new or empty folder.",
    )


def test_a_destination_keeps_its_last_letter_whatever_it_is():
    assert check_destination("~/BackupsX/", HOME, always(PathState.MISSING)) == (f"{HOME}/BackupsX", None)


def test_each_unusable_folder_is_named_as_it_was_typed():
    states = {f"{HOME}/missing": PathState.MISSING, f"{HOME}/file": PathState.FILE}

    folders, problems = check_folders(("relative", "~/missing", "~/file"), HOME, states.get)

    assert folders == ()
    assert problems == [
        "“relative” is not a full path.",
        "“~/missing” does not exist.",
        "“~/file” is a file, not a folder.",
    ]


def test_a_passphrase_is_refused_in_these_words():
    assert check_passphrase("short", "short") == "Use at least 10 characters."
    assert check_passphrase("long enough", "long enough?") == "The two passphrases do not match."


def test_an_unsaved_recovery_key_stops_the_wizard_in_these_words():
    wizard = WizardModel(home=HOME, inspect=always(PathState.MISSING), step=Step.RECOVERY)

    assert wizard.errors() == ["Save your recovery key, or confirm that you accept the risk."]


def test_the_summary_leaves_an_unusable_destination_blank_and_lists_the_folders():
    wizard = WizardModel(home=HOME, inspect=always(PathState.NOT_EMPTY), folders=("~/Pictures", "~/Music"))

    summary = dict(wizard.summary())

    assert summary["Destination"] == ""
    assert summary["Folders"] == f"{HOME}/Pictures, {HOME}/Music"
