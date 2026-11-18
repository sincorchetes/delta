"""Details of restoring that a mutation run showed nothing was watching."""

import os

from delta.application import restore_service
from delta.application.restore_service import RestoreService
from delta.domain.repository import Repository
from delta.domain.snapshot import Snapshot
from datetime import datetime


def same_time(*paths):
    for path in paths:
        os.utime(path, (1_700_000_000, 1_700_000_000))


# --- when two files count as the same --------------------------------------------------------------


def test_identical_files_are_the_same(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_text("same bytes")
    b.write_text("same bytes")

    assert restore_service._same_file(str(a), str(b)) is True


def test_files_of_the_same_size_and_date_but_other_bytes_are_not_the_same(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_text("aaaa")
    b.write_text("bbbb")
    same_time(a, b)

    assert not restore_service._same_file(str(a), str(b))


def test_a_link_is_never_the_same_as_the_file_it_points_to(tmp_path):
    target, link = tmp_path / "target", tmp_path / "link"
    target.write_text("same bytes")
    link.symlink_to(target)

    assert not restore_service._same_file(str(target), str(link))
    assert not restore_service._same_file(str(link), str(target))


def test_a_folder_is_never_the_same_as_anything(tmp_path):
    folder, other = tmp_path / "folder", tmp_path / "other"
    folder.mkdir()
    other.mkdir()

    assert not restore_service._same_file(str(folder), str(other))


# --- what the service hands back ---------------------------------------------------------------------


class Engine:
    def __init__(self):
        self.calls = []

    def list_snapshots(self, repo):
        return [Snapshot("id1", "first", datetime(2026, 1, 1))]

    def extract(self, repo, snapshot, paths, destination):
        self.calls.append(len(paths))
        for path in paths:
            target = os.path.join(destination, path.lstrip("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w") as handle:
                handle.write("back")


def test_prepare_returns_both_paths_cleaned_up():
    service = RestoreService(Engine(), Repository("/r"), "/home/u", resolve=lambda path: path)

    assert service.prepare("/home/u//docs/a.txt/", "/home/u/./target") == ("/home/u/docs/a.txt", "/home/u/target")


def test_every_job_gets_its_own_identifier():
    ids = {RestoreService.new_job_id() for _ in range(50)}

    assert len(ids) == 50 and all(len(job) == 32 and int(job, 16) >= 0 for job in ids)


def test_what_was_deleted_is_extracted_in_batches_of_five_hundred(tmp_path):
    home = tmp_path / "home"
    (home / "docs").mkdir(parents=True)
    engine = Engine()
    service = RestoreService(engine, Repository("/r"), str(home))

    restored = service.place_missing("first", [str(home / "docs" / f"f{n}.txt") for n in range(1201)])

    assert engine.calls == [500, 500, 201] and len(restored) == 1201
