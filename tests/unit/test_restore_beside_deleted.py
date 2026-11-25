"""Putting back everything that is gone in one go, and replacing something that is already exactly that."""

import os

import pytest

from delta.domain.errors import InvalidPath, SnapshotNotFound
from restore_beside_support import FakeEngine, read, scratch_left, service


@pytest.fixture
def home(tmp_path):
    root = tmp_path / "home"
    (root / "docs").mkdir(parents=True)
    return root


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
