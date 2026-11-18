"""Creates an encrypted repository, always registering its passphrase in the keyring."""

import secrets

from delta.application.ports import BackupEngine, SecretStore
from delta.application.snapshot_service import newest_timestamp
from delta.domain.repository import Encryption, Repository


def generate_passphrase() -> str:
    return secrets.token_urlsafe(32)


class RepositorySetup:
    def __init__(self, engine: BackupEngine, store: SecretStore) -> None:
        self._engine = engine
        self._store = store

    def create(self, repo: Repository, passphrase: str | None = None) -> None:
        """Store the passphrase (generated if none given), then `borg init`.

        If init fails, the keyring is restored to its previous state so no
        orphan secret is left behind.
        """
        if repo.encryption is Encryption.NONE:
            raise ValueError("repositories must be encrypted")
        previous = self._store.get(repo.location)
        self._store.set(repo.location, passphrase or generate_passphrase())
        try:
            self._engine.init(repo)
        except Exception:
            self._restore(repo.location, previous)
            raise

    def adopt(self, repo: Repository, passphrase: str) -> int:
        """Use a repository that already exists: it must open with this passphrase.

        Never runs `borg init`. The keyring is restored if the repository does not open.
        Returns when its newest snapshot was made (epoch seconds, 0 if empty).
        """
        if repo.encryption is Encryption.NONE:
            raise ValueError("repositories must be encrypted")
        if not passphrase:
            raise ValueError("an existing repository needs its passphrase")
        previous = self._store.get(repo.location)
        self._store.set(repo.location, passphrase)
        try:
            return newest_timestamp(self._engine.list_snapshots(repo))
        except Exception:
            self._restore(repo.location, previous)
            raise

    def _restore(self, key: str, previous: str | None) -> None:
        if previous is None:
            self._store.delete(key)
        else:
            self._store.set(key, previous)
