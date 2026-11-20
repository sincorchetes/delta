"""Another repository in the place of the one Delta made is noticed, whatever drive or folder it is on."""

import json

import pytest

from delta.application.backup_service import BackupService
from delta.application.repository_setup import RepositorySetup
from delta.domain.backup_job import JobState
from delta.domain.destination import DestinationState
from delta.domain.errors import DeltaError, DestinationUnavailable, EngineError, PassphraseError
from delta.domain.repository import Repository
from delta.infrastructure import borg_commands as commands
from delta.infrastructure import settings
from delta.infrastructure.borg_parsing import parse_repository_id
from delta.infrastructure.borg_runner import BorgRunner

REPO = Repository("/media/disk/delta")
MINE, OTHER = "a" * 64, "b" * 64


class Identity:
    def __init__(self, expected=""):
        self.value, self.remembered = expected, []

    def expected(self):
        return self.value

    def remember(self, repo_id):
        self.remembered.append(repo_id)
        self.value = repo_id


class Engine:
    def __init__(self, found=MINE, error=None, snapshots=None):
        self.found, self.error, self.created, self.asked = found, error, 0, []
        self.snapshots = snapshots or []

    def repository_id(self, repo):
        self.asked.append(repo)
        if isinstance(self.found, Exception):
            raise self.found
        return self.found

    def create(self, repo, job, name=None, on_progress=None):
        self.created += 1
        if self.error:
            raise self.error
        return "archive"

    def list_snapshots(self, repo):
        return self.snapshots

    def init(self, repo):
        pass


def backup(engine, identity):
    return BackupService(engine, REPO, ("/home",), identity=identity)


# --- the engine's line, its answer, and the runner ------------------------------------------------------


def test_the_identifier_is_asked_with_the_cheapest_listing():
    assert commands.repository_id(REPO) == ["borg", "list", "--json", "--last", "1", "/media/disk/delta"]


def test_the_identifier_is_read_from_the_repository_part_of_the_answer():
    answer = json.dumps({"archives": [], "repository": {"id": MINE, "location": "/x"}, "encryption": {}})

    assert parse_repository_id(answer) == MINE


@pytest.mark.parametrize("answer", ["", "garbage", "[]", "{}", '{"repository": {}}', '{"repository": null}'])
def test_an_answer_without_an_identifier_is_an_error_of_the_engine(answer):
    with pytest.raises(EngineError, match="unexpected borg list output"):
        parse_repository_id(answer)


def test_the_runner_gives_the_identifier_its_engine_printed(monkeypatch):
    runner = BorgRunner(env={})
    asked = []

    def run(argv, repo, **kwargs):
        asked.append((argv, repo))
        return json.dumps({"repository": {"id": OTHER}})

    monkeypatch.setattr(runner, "_run", run)

    assert runner.repository_id(REPO) == OTHER
    assert asked == [(commands.repository_id(REPO), REPO)]


# --- the settings keep it ---------------------------------------------------------------------------------


class Stored:
    def __init__(self, **values):
        self.values, self.written = values, {}

    def get_string(self, key):
        return self.values.get(key, "")

    def set_string(self, key, value):
        self.written[key] = value


def test_the_identifier_is_kept_in_the_settings_and_read_back(monkeypatch):
    stored = Stored(**{"repository-id": MINE})
    monkeypatch.setattr(settings, "open_settings", lambda: stored)

    assert settings.SettingsRepositoryIdentity().expected() == MINE
    settings.SettingsRepositoryIdentity().remember(OTHER)
    assert stored.written == {"repository-id": OTHER}


def test_without_the_settings_there_is_nothing_to_compare_with_and_nothing_to_keep(monkeypatch):
    monkeypatch.setattr(settings, "open_settings", lambda: None)

    assert settings.SettingsRepositoryIdentity().expected() == ""
    settings.SettingsRepositoryIdentity().remember(MINE)  # does nothing, and does not fail


# --- a backup: the same repository, another one, or the first time --------------------------------------


def test_the_repository_that_was_made_is_backed_up_as_usual():
    engine, identity = Engine(found=MINE), Identity(MINE)
    job = backup(engine, identity).new_job()

    backup(engine, identity).run(job)

    assert job.state is JobState.SUCCEEDED and engine.created == 1 and identity.remembered == []


def test_another_repository_in_its_place_makes_the_backup_wait_and_writes_nothing_in_it():
    engine, identity = Engine(found=OTHER), Identity(MINE)
    service = backup(engine, identity)
    job = service.new_job()

    service.run(job)

    assert job.state is JobState.UNAVAILABLE and engine.created == 0
    assert job.unavailable.state is DestinationState.OTHER_REPOSITORY and job.unavailable.location == REPO.location
    assert identity.value == MINE  # it does not take the other one for its own


def test_the_first_time_there_is_nothing_to_compare_with_so_what_is_there_is_learnt():
    engine, identity = Engine(found=MINE), Identity("")
    service = backup(engine, identity)
    job = service.new_job()

    service.run(job)

    assert job.state is JobState.SUCCEEDED and identity.remembered == [MINE]


def test_what_cannot_be_read_is_left_for_the_engine_to_say_when_it_makes_the_backup():
    engine, identity = Engine(found=PassphraseError("The passphrase is incorrect.")), Identity(MINE)
    service = backup(engine, identity)

    assert service.cannot_back_up() is None
    job = service.new_job()
    service.run(job)

    assert job.state is JobState.SUCCEEDED and engine.created == 1  # (its own create is what would say it)


def test_without_an_identity_nothing_is_compared_and_the_engine_is_not_asked():
    engine = Engine(found=OTHER)
    service = BackupService(engine, REPO, ("/home",))

    assert service.cannot_back_up() is None and engine.asked == []


def test_without_a_repository_there_is_nothing_to_compare():
    engine = Engine(found=OTHER)

    assert BackupService(engine, None, ("/home",), identity=Identity(MINE)).cannot_back_up() is None
    assert engine.asked == []


def test_the_caller_that_has_just_asked_is_not_asked_again():
    engine, identity = Engine(found=MINE), Identity(MINE)
    service = backup(engine, identity)
    job = service.new_job()

    assert service.cannot_back_up() is None
    service.run(job, checked=True)

    assert engine.asked == [REPO]  # once, by `cannot_back_up`, and not again by `run`


def test_a_place_that_cannot_be_used_is_said_before_the_repository_is_looked_at():
    class Gone:
        def state(self, repo, out_of_space=False):
            return DestinationState.MISSING

    engine = Engine(found=OTHER)
    service = BackupService(engine, REPO, ("/home",), destination=Gone(), identity=Identity(MINE))

    assert service.cannot_back_up().state is DestinationState.MISSING and engine.asked == []


def test_after_a_failure_only_the_place_is_asked_again_not_the_repository():
    engine, identity = Engine(found=MINE, error=EngineError("Input/output error")), Identity(MINE)
    service = backup(engine, identity)
    job = service.new_job()

    service.run(job)

    assert job.state is JobState.FAILED and engine.asked == [REPO]


# --- what makes or adopts a repository remembers it ------------------------------------------------------


class Store:
    def __init__(self):
        self.items = {}

    def get(self, key):
        return self.items.get(key)

    def set(self, key, value):
        self.items[key] = value

    def delete(self, key):
        self.items.pop(key, None)


def test_a_repository_that_is_made_is_remembered():
    identity = Identity()

    RepositorySetup(Engine(found=MINE), Store(), identity).create(REPO, "pass")

    assert identity.remembered == [MINE]


def test_a_repository_that_is_adopted_is_remembered_in_the_place_of_the_one_before():
    identity = Identity(MINE)

    RepositorySetup(Engine(found=OTHER), Store(), identity).adopt(REPO, "pass")

    assert identity.value == OTHER


def test_when_its_identifier_cannot_be_read_it_is_forgotten_so_the_first_backup_learns_it():
    identity = Identity(MINE)

    RepositorySetup(Engine(found=EngineError("boom")), Store(), identity).create(REPO, "pass")

    assert identity.value == ""


def test_a_repository_that_fails_to_be_made_or_adopted_is_not_remembered():
    class Failing(Engine):
        def init(self, repo):
            raise EngineError("no")

        def list_snapshots(self, repo):
            raise PassphraseError("wrong")

    identity = Identity(MINE)

    with pytest.raises(DeltaError):
        RepositorySetup(Failing(), Store(), identity).create(REPO, "pass")
    with pytest.raises(DeltaError):
        RepositorySetup(Failing(), Store(), identity).adopt(REPO, "pass")

    assert identity.remembered == [] and identity.value == MINE


def test_without_an_identity_making_and_adopting_work_as_before():
    RepositorySetup(Engine(), Store()).create(REPO, "pass")
    RepositorySetup(Engine(), Store()).adopt(REPO, "pass")


# --- told as its own cause ----------------------------------------------------------------------------------


def test_this_cause_has_its_own_message_and_hint():
    error = DestinationUnavailable("/media/disk/delta", DestinationState.OTHER_REPOSITORY)

    assert str(error) == "The repository at /media/disk/delta is not the one your backups were made in"
    assert error.hint == (
        "Connect the drive that holds your backups. If this repository is the right one, "
        "choose it again in the preferences, with its passphrase."
    )
