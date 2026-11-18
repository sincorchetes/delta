import os
from datetime import datetime

import pytest

from delta.application.restore_service import SCRATCH_PREFIX, RestoreService
from delta.domain.errors import DeltaError, InvalidPath, SnapshotNotFound
from delta.domain.repository import Repository
from delta.domain.snapshot import Snapshot

NOW = datetime(2026, 11, 10, 13, 5, 0)


class FakeEngine:
    """Extracts what the 'snapshot' holds, recreating the full original path."""

    def __init__(self, files=None, folders=None):
        self.files = files or {}
        self.folders = folders or {}
        self.calls = []  # the paths of each extract call

    def list_snapshots(self, repo):
        return [Snapshot("id1", "first", NOW)]

    def extract(self, repo, snapshot, paths, destination):
        self.calls.append(paths)
        for path in paths:
            target = os.path.join(destination, path.lstrip("/"))
            if path in self.folders:
                for name, content in self.folders[path].items():
                    os.makedirs(os.path.dirname(os.path.join(target, name)), exist_ok=True)
                    with open(os.path.join(target, name), "w") as handle:
                        handle.write(content)
            elif path in self.files:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "w") as handle:
                    handle.write(self.files[path])


@pytest.fixture
def home(tmp_path):
    root = tmp_path / "home"
    (root / "docs").mkdir(parents=True)
    return root


def service(home, engine):
    return RestoreService(engine, Repository("/r"), str(home), clock=lambda: NOW)


def read(path):
    with open(path) as handle:
        return handle.read()


def scratch_left(folder):
    return [name for name in os.listdir(folder) if name.startswith(SCRATCH_PREFIX)]


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


# --- putting back everything that is gone, in one go ------------------------------------------


def put_back(home, engine, *paths, snapshot="first"):
    return service(home, engine).place_missing(snapshot, [str(p) for p in paths])


def test_deleted_files_come_back_under_their_own_names_in_a_single_extract(home):
    a, b = home / "docs" / "a.txt", home / "docs" / "b.txt"
    engine = FakeEngine(files={str(a): "A", str(b): "B"})

    placed = put_back(home, engine, a, b)

    assert placed == [str(a), str(b)] and read(a) == "A" and read(b) == "B"
    assert len(engine.calls) == 1  # not one borg call per file
    assert not scratch_left(home)


def test_a_deleted_folder_comes_back_whole_and_its_missing_parents_are_made(home):
    gone = home / "old" / "trips"
    engine = FakeEngine(folders={str(gone): {"1.jpg": "one", "raw/2.nef": "two"}})

    placed = put_back(home, engine, gone)

    assert placed == [str(gone)]
    assert read(gone / "1.jpg") == "one" and read(gone / "raw" / "2.nef") == "two"


def test_files_in_different_folders_all_come_back(home):
    a, b = home / "docs" / "a.txt", home / "gone-dir" / "deeper" / "b.txt"
    engine = FakeEngine(files={str(a): "A", str(b): "B"})

    assert put_back(home, engine, a, b) == sorted([str(a), str(b)])

    assert read(b) == "B"


def test_something_that_exists_now_is_never_overwritten(home):
    there = home / "docs" / "there.txt"
    there.write_text("current")
    gone = home / "docs" / "gone.txt"
    engine = FakeEngine(files={str(there): "old", str(gone): "back"})

    placed = put_back(home, engine, there, gone)

    assert placed == [str(gone)] and read(there) == "current"
    assert engine.calls == [(str(gone),)]  # what exists is not even extracted


def test_what_the_snapshot_lacks_is_skipped_and_leaves_no_folders_behind(home):
    missing = home / "never" / "was" / "here.txt"

    assert put_back(home, FakeEngine(), missing) == []

    assert not (home / "never").exists()


def test_an_item_made_to_exist_while_extracting_is_not_overwritten(home):
    target = home / "docs" / "race.txt"
    engine = FakeEngine(files={str(target): "from the backup"})
    original = engine.extract

    def extract_then_the_user_recreates_it(*args):
        original(*args)
        target.write_text("made meanwhile")

    engine.extract = extract_then_the_user_recreates_it

    assert put_back(home, engine, target) == []
    assert read(target) == "made meanwhile"


def test_many_paths_are_extracted_in_chunks(home, monkeypatch):
    monkeypatch.setattr("delta.application.restore_service.EXTRACT_CHUNK", 2)
    paths = [home / "docs" / f"f{n}.txt" for n in range(5)]
    engine = FakeEngine(files={str(p): "x" for p in paths})

    assert len(put_back(home, engine, *paths)) == 5

    assert [len(call) for call in engine.calls] == [2, 2, 1]


def test_a_path_outside_home_is_refused_before_anything_is_extracted(home, tmp_path):
    engine = FakeEngine()
    with pytest.raises(InvalidPath):
        put_back(home, engine, home / "docs" / "ok.txt", tmp_path / "elsewhere.txt")
    assert engine.calls == []


def test_a_folder_symlink_leading_out_of_home_is_refused(home, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (home / "link").symlink_to(outside)
    engine = FakeEngine()

    with pytest.raises(InvalidPath):
        put_back(home, engine, home / "link" / "x.txt")

    assert engine.calls == [] and not (outside / "x.txt").exists()


def test_the_same_path_twice_is_restored_once(home):
    a = home / "docs" / "a.txt"
    engine = FakeEngine(files={str(a): "A"})
    assert put_back(home, engine, a, a) == [str(a)]


def test_nothing_to_put_back_never_calls_borg(home):
    there = home / "docs" / "there.txt"
    there.write_text("x")
    engine = FakeEngine(files={str(there): "old"})

    assert put_back(home, engine, there) == []

    assert engine.calls == []


def test_putting_back_from_an_unknown_snapshot_is_reported(home):
    with pytest.raises(SnapshotNotFound):
        put_back(home, FakeEngine(), home / "docs" / "a.txt", snapshot="nope")


# --- replacing something that is already exactly that ------------------------------------------


def test_replacing_a_file_with_identical_content_sets_nothing_aside(home):
    doc = home / "docs" / "same.txt"
    doc.write_text("exactly this")

    placed = service(home, FakeEngine(files={str(doc): "exactly this"})).restore_beside(
        "first", str(doc), replace=True
    )

    assert placed == str(doc) and read(doc) == "exactly this"
    assert os.listdir(home / "docs") == ["same.txt"]  # no "(before restore …)" clutter


def test_replacing_a_file_with_different_content_still_keeps_the_current_one(home):
    doc = home / "docs" / "changed.txt"
    doc.write_text("new")

    service(home, FakeEngine(files={str(doc): "old"})).restore_beside("first", str(doc), replace=True)

    assert read(doc) == "old"
    (kept,) = [n for n in os.listdir(home / "docs") if "before restore" in n]
    assert read(home / "docs" / kept) == "new"


def test_a_same_size_but_different_file_is_not_taken_for_the_same(home):
    doc = home / "docs" / "tricky.txt"
    doc.write_text("aaaa")

    service(home, FakeEngine(files={str(doc): "bbbb"})).restore_beside("first", str(doc), replace=True)

    assert read(doc) == "bbbb"
    assert [n for n in os.listdir(home / "docs") if "before restore" in n]


def test_a_folder_is_always_set_aside_never_judged_the_same(home):
    folder = home / "docs" / "proj"
    folder.mkdir()
    (folder / "n.txt").write_text("same")

    service(home, FakeEngine(folders={str(folder): {"n.txt": "same"}})).restore_beside(
        "first", str(folder), replace=True
    )

    assert [n for n in os.listdir(home / "docs") if n.startswith("proj (before restore")]
