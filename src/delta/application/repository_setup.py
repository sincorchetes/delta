"""Creates an encrypted repository, always registering its passphrase in the keyring."""

import secrets

from delta.application.ports import BackupEngine, RepositoryIdentity, SecretStore
from delta.application.snapshot_service import newest_timestamp
from delta.domain.errors import DeltaError
from delta.domain.repository import Encryption, Repository


def generate_passphrase() -> str:
    return secrets.token_urlsafe(32)


class RepositorySetup:
    def __init__(self, engine: BackupEngine, store: SecretStore, identity: RepositoryIdentity | None = None) -> None:
        self._engine = engine
        self._store = store
        self._identity = identity

    def _remember(self, repo: Repository) -> None:
        """What identifies the repository, so that another one in its place is noticed. If it cannot be read now, the first
        backup learns it."""
        if self._identity is None:
            return
        try:
            self._identity.remember(self._engine.repository_id(repo))
        except DeltaError:
            self._identity.remember("")

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
        self._remember(repo)

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
            newest = newest_timestamp(self._engine.list_snapshots(repo))
        except Exception:
            self._restore(repo.location, previous)
            raise
        self._remember(repo)
        return newest

    def _restore(self, key: str, previous: str | None) -> None:
        if previous is None:
            self._store.delete(key)
        else:
            self._store.set(key, previous)
