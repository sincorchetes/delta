from datetime import datetime

import pytest

from delta.application.snapshots import snapshot_name
from delta.domain.errors import SnapshotNotFound
from delta.domain.repository import Repository
from delta.domain.snapshot import Snapshot


class Engine:
    def __init__(self, *snapshots):
        self.snapshots = snapshots
        self.asked = 0

    def list_snapshots(self, repo):
        self.asked += 1
        return list(self.snapshots)


WHEN = datetime(2026, 1, 1)
ENGINE = Engine(Snapshot("id-1", "2026-01-01T10-00", WHEN), Snapshot("id-2", "2026-01-02T10-00", WHEN))
REPO = Repository("/r")


def test_a_snapshot_is_found_by_its_name():
    assert snapshot_name(ENGINE, REPO, "2026-01-02T10-00") == "2026-01-02T10-00"


def test_a_snapshot_is_found_by_its_id_and_comes_back_as_its_name():
    assert snapshot_name(ENGINE, REPO, "id-1") == "2026-01-01T10-00"


def test_one_that_is_gone_is_reported_not_guessed():
    with pytest.raises(SnapshotNotFound):
        snapshot_name(ENGINE, REPO, "pruned-meanwhile")


def test_the_user_is_told_in_plain_words_not_given_the_snapshot_name():
    with pytest.raises(SnapshotNotFound, match="no longer exists") as caught:
        snapshot_name(ENGINE, REPO, "2026-01-03T10-00")

    assert "2026-01-03" not in str(caught.value)


def test_an_id_is_never_taken_for_a_name_that_merely_contains_it():
    with pytest.raises(SnapshotNotFound):
        snapshot_name(ENGINE, REPO, "id")


def test_a_repository_with_no_snapshots_has_nothing_to_find():
    with pytest.raises(SnapshotNotFound):
        snapshot_name(Engine(), REPO, "anything")
