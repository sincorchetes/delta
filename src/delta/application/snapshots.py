"""Finding a snapshot by the reference a client gives: its id or its name."""

from delta.application.ports import SnapshotSource
from delta.domain.errors import SnapshotNotFound
from delta.domain.repository import Repository
from delta.i18n import _


def snapshot_name(engine: SnapshotSource, repo: Repository, reference: str) -> str:
    """The name of the snapshot `reference` (its id or its name) points to.

    Raises SnapshotNotFound when there is none: it may have been pruned since the client saw it.
    """
    for item in engine.list_snapshots(repo):
        if reference in (item.id, item.name):
            return item.name
    raise SnapshotNotFound(
        _("That backup no longer exists: a newer one may have replaced it. Reopen the window to see the current ones.")
    )
