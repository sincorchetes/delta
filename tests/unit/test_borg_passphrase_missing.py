import pytest

from delta.domain.backup_job import BackupJob
from delta.domain.errors import EngineError, PassphraseError
from delta.domain.repository import Repository
from delta.domain.retention import RetentionPolicy
from delta.infrastructure.borg_runner import BorgRunner

REPO = Repository("/backups/repo")


class Store:
    def __init__(self, secret=None):
        self.secret = secret

    def get(self, key):
        return self.secret


def runner(store, env=None):
    # A binary that cannot exist: reaching it proves borg would have been launched.
    return BorgRunner(env=env, binary="delta-no-such-borg", secrets=store)


OPERATIONS = {
    "list": lambda r: r.list_snapshots(REPO),
    "entry": lambda r: r.file_entry(REPO, "first", "/home/a"),
    "extract": lambda r: r.extract(REPO, "first", ("/home/a",), "/tmp"),
    "prune": lambda r: r.prune(REPO, RetentionPolicy()),
    "create": lambda r: r.create(REPO, BackupJob("j", ("/home",))),
}


@pytest.mark.parametrize("operation", sorted(OPERATIONS))
def test_a_missing_passphrase_stops_before_borg_is_launched(operation):
    with pytest.raises(PassphraseError, match="keyring"):
        OPERATIONS[operation](runner(Store(None)))


@pytest.mark.parametrize("variable", ["BORG_PASSPHRASE", "BORG_PASSCOMMAND"])
def test_a_development_override_still_lets_borg_run(variable):
    with pytest.raises(EngineError, match="cannot run"):
        runner(Store(None), env={variable: "x"}).list_snapshots(REPO)


def test_a_passphrase_in_the_keyring_lets_borg_run():
    with pytest.raises(EngineError, match="cannot run"):
        runner(Store("secret")).list_snapshots(REPO)
