
import os

import pytest

from delta.domain.errors import DeltaError, InvalidPath, SnapshotNotFound
from restore_beside_support import FakeEngine, read, scratch_left, service


@pytest.fixture
def home(tmp_path):
    root = tmp_path / "home"
    (root / "docs").mkdir(parents=True)
    return root


def test_copy_goes_beside_the_original_and_never_touches_it(home):
    doc = home / "docs" / "doc.txt"
    doc.write_text("new")
    engine = FakeEngine(files={str(doc): "old"})

    placed = service(home, engine).restore_beside("first", str(doc), replace=False)

    assert placed == str(home / "docs" / "doc (restored 2026-11-10).txt")
    assert read(placed) == "old"
    assert doc.read_text() == "new"
    assert scratch_left(home / "docs") == []


def test_a_second_copy_never_overwrites_the_first(home):
    doc = home / "docs" / "doc.txt"
    doc.write_text("new")
    restore = service(home, FakeEngine(files={str(doc): "old"}))

    first = restore.restore_beside("first", str(doc), replace=False)
    second = restore.restore_beside("first", str(doc), replace=False)

    assert first != second
    assert second == str(home / "docs" / "doc (restored 2026-11-10) 2.txt")  # next to the original, not in the working directory
    assert read(first) == read(second) == "old"


def test_a_deleted_file_can_be_restored_as_a_copy(home):
    gone = home / "docs" / "gone.txt"
    restore = service(home, FakeEngine(files={str(gone): "precious"}))

    placed = restore.restore_beside("first", str(gone), replace=False)

    assert read(placed) == "precious"
    assert not gone.exists()


def test_a_folder_copy_keeps_its_dots_instead_of_splitting_an_extension(home):
    project = home / "docs" / "proj.v2"
    project.mkdir()
    (project / "a.txt").write_text("current")
    restore = service(home, FakeEngine(folders={str(project): {"a.txt": "old", "sub/b.txt": "b"}}))

    placed = restore.restore_beside("first", str(project), replace=False)

    assert placed == str(home / "docs" / "proj.v2 (restored 2026-11-10)")
    assert read(os.path.join(placed, "a.txt")) == "old"
    assert read(os.path.join(placed, "sub", "b.txt")) == "b"
    assert (project / "a.txt").read_text() == "current"


def test_replace_swaps_in_the_old_version_and_keeps_the_current_one(home):
    doc = home / "docs" / "doc.txt"
    doc.write_text("new")

    placed = service(home, FakeEngine(files={str(doc): "old"})).restore_beside(
        "first", str(doc), replace=True
    )

    kept = home / "docs" / "doc (before restore 2026-11-10 13-05-00).txt"
    assert placed == str(doc) and doc.read_text() == "old"
    assert kept.read_text() == "new"
    assert scratch_left(home / "docs") == []


def test_replace_without_a_current_file_just_restores_it(home):
    gone = home / "docs" / "gone.txt"

    placed = service(home, FakeEngine(files={str(gone): "old"})).restore_beside(
        "first", str(gone), replace=True
    )

    assert read(placed) == "old"
    assert os.listdir(home / "docs") == ["gone.txt"]


def test_a_failure_halfway_puts_the_current_version_back(home, monkeypatch):
    doc = home / "docs" / "doc.txt"
    doc.write_text("new")
    real_rename, calls = os.rename, []

    def flaky(source, destination):
        calls.append((source, destination))
        if len(calls) == 2:  # moving the restored version into place
            raise OSError("disk went away")
        real_rename(source, destination)

    monkeypatch.setattr("delta.application.restore_service.os.rename", flaky)

    with pytest.raises(DeltaError, match="disk went away"):
        service(home, FakeEngine(files={str(doc): "old"})).restore_beside(
            "first", str(doc), replace=True
        )

    assert doc.read_text() == "new"
    assert scratch_left(home / "docs") == []


def test_a_path_missing_from_the_snapshot_is_reported_and_leaves_no_litter(home):
    doc = home / "docs" / "doc.txt"
    doc.write_text("new")

    with pytest.raises(SnapshotNotFound):
        service(home, FakeEngine()).restore_beside("first", str(doc), replace=False)

    assert os.listdir(home / "docs") == ["doc.txt"]


def test_restoring_beside_from_an_unknown_snapshot_is_reported(home):
    with pytest.raises(SnapshotNotFound):
        service(home, FakeEngine()).restore_beside("nope", str(home / "docs" / "x"), replace=False)


def test_a_folder_deleted_with_its_file_is_made_again_for_the_copy(home):
    gone = home / "deleted-folder" / "deeper" / "x.txt"
    restore = service(home, FakeEngine(files={str(gone): "precious"}))

    placed = restore.restore_beside("first", str(gone), replace=False)

    assert read(placed) == "precious" and os.path.dirname(placed) == str(gone.parent)
    assert not scratch_left(gone.parent)


def test_replacing_something_deleted_puts_it_back_under_its_own_name(home):
    gone = home / "deleted-folder" / "x.txt"
    restore = service(home, FakeEngine(files={str(gone): "precious"}))

    placed = restore.restore_beside("first", str(gone), replace=True)

    assert placed == str(gone) and read(gone) == "precious"
    assert os.listdir(gone.parent) == ["x.txt"]  # nothing was set aside: there was nothing there


def test_a_failed_restore_leaves_no_empty_folders_behind(home):
    gone = home / "deleted-folder" / "deeper" / "x.txt"

    with pytest.raises(SnapshotNotFound):
        service(home, FakeEngine()).restore_beside("first", str(gone), replace=False)  # not in the snapshot

    assert not (home / "deleted-folder").exists()


def test_folders_that_already_existed_are_never_removed_after_a_failure(home):
    with pytest.raises(SnapshotNotFound):
        service(home, FakeEngine()).restore_beside("first", str(home / "docs" / "x.txt"), replace=False)

    assert (home / "docs").is_dir()


def test_nothing_is_created_outside_home(home, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (home / "link").symlink_to(outside)

    with pytest.raises(InvalidPath):
        service(home, FakeEngine(files={})).restore_beside("first", str(home / "link" / "sub" / "x.txt"), replace=False)

    assert not (outside / "sub").exists()


@pytest.mark.parametrize(
    "bad",
    ["relative/path", "{home}/docs/../../etc/passwd", "/etc/passwd", "{home}"],
)
def test_unsafe_paths_are_refused_before_any_work(home, bad):
    with pytest.raises(InvalidPath):
        service(home, FakeEngine()).prepare_in_place(bad.format(home=home))


def test_a_folder_symlink_escaping_home_is_refused(home, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (home / "link").symlink_to(outside)

    with pytest.raises(InvalidPath):
        service(home, FakeEngine()).prepare_in_place(str(home / "link" / "x.txt"))


def test_a_normal_path_in_home_is_accepted(home):
    path = str(home / "docs" / "doc.txt")
    assert service(home, FakeEngine()).prepare_in_place(path) == path
