import os

import pytest

from delta.ui.disk import inspect_path, is_repository, is_unmounted, unwritable
from delta.ui.wizard import PathState


def test_a_path_that_does_not_exist_is_missing(tmp_path):
    assert inspect_path(str(tmp_path / "nope")) is PathState.MISSING


def test_an_empty_folder_is_empty(tmp_path):
    assert inspect_path(str(tmp_path)) is PathState.EMPTY_DIR


def test_a_folder_with_anything_in_it_is_not_empty(tmp_path):
    (tmp_path / ".hidden").write_text("x")
    assert inspect_path(str(tmp_path)) is PathState.NOT_EMPTY


def test_a_file_is_a_file(tmp_path):
    target = tmp_path / "f"
    target.write_text("x")
    assert inspect_path(str(target)) is PathState.FILE


def test_a_dangling_symlink_is_not_treated_as_free_space(tmp_path):
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "missing")
    assert inspect_path(str(link)) is PathState.FILE


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read everything")
def test_an_unreadable_folder_is_never_offered(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        assert inspect_path(str(locked)) is PathState.NOT_WRITABLE  # never offered as a place for the repository
    finally:
        locked.chmod(0o700)


def make_repository(folder):
    folder.mkdir(exist_ok=True)
    (folder / "README").write_text("This is a Borg Backup repository.\nSee https://borgbackup.readthedocs.io/\n")
    (folder / "data").mkdir()


def test_a_folder_that_holds_a_borg_repository_is_one_to_reopen(tmp_path):
    make_repository(tmp_path / "repo")

    assert inspect_path(str(tmp_path / "repo")) is PathState.REPOSITORY


def test_a_folder_that_only_looks_like_one_is_just_not_empty(tmp_path):
    (tmp_path / "README").write_text("my notes")
    (tmp_path / "data").mkdir()

    assert inspect_path(str(tmp_path)) is PathState.NOT_EMPTY
    assert not is_repository(str(tmp_path))


def test_a_readme_without_the_data_folder_is_not_a_repository(tmp_path):
    (tmp_path / "README").write_text("This is a Borg Backup repository.")

    assert not is_repository(str(tmp_path))


def test_a_folder_without_a_readme_is_not_a_repository(tmp_path):
    assert not is_repository(str(tmp_path))


def never(path):
    return False


def mounted(*points):
    return lambda path: path in points


def test_under_the_places_where_drives_are_mounted_what_is_not_on_a_mount_is_a_drive_that_is_away():
    assert is_unmounted("/run/media/u/DISK/delta", never)
    assert is_unmounted("/media/DISK", never)
    assert is_unmounted("/media/u/DISK/a/b", never)
    assert is_unmounted("/run/media/u", never)


def test_on_a_mount_it_is_there_whatever_the_depth():
    assert not is_unmounted("/run/media/u/DISK/delta", mounted("/run/media/u/DISK"))
    assert not is_unmounted("/media/DISK", mounted("/media/DISK"))
    assert not is_unmounted("/media/u/DISK/a/b", mounted("/media/u/DISK"))


def test_anywhere_else_is_the_disk_of_the_computer(tmp_path):
    assert not is_unmounted("/home/u/Backups", never)
    assert not is_unmounted("/mnt/backups", never)
    assert not is_unmounted("/media", never)
    assert not is_unmounted(str(tmp_path))


def test_the_real_check_asks_the_system_and_a_path_under_the_media_roots_that_is_not_mounted_is_unmounted():
    assert is_unmounted("/media/delta-test-nobody-mounts-this") and inspect_path("/media/delta-test-nobody-mounts-this") is PathState.UNMOUNTED


class Usage:
    def __init__(self, flag):
        self.f_flag = flag


def test_a_folder_that_can_be_written_in_is_not_a_problem(tmp_path):
    assert unwritable(str(tmp_path), lambda path: Usage(0), lambda path, mode: True) is None


def test_a_file_system_mounted_read_only_is_a_problem_before_permissions_are(tmp_path):
    assert unwritable(str(tmp_path), lambda path: Usage(os.ST_RDONLY), lambda path, mode: False) is PathState.READ_ONLY


def test_a_folder_without_permission_to_write_is_a_problem(tmp_path):
    assert unwritable(str(tmp_path), lambda path: Usage(0), lambda path, mode: False) is PathState.NOT_WRITABLE


def test_where_a_folder_would_be_made_it_is_the_nearest_folder_that_is_there_which_counts(tmp_path):
    asked = []

    def access(path, mode):
        asked.append(path)
        return False

    assert unwritable(str(tmp_path / "not" / "yet"), lambda path: Usage(0), access) is PathState.NOT_WRITABLE
    assert asked == [str(tmp_path)]


def test_a_file_system_that_cannot_be_asked_is_judged_by_permissions_alone(tmp_path):
    def fail(path):
        raise OSError(5, "Input/output error", path)

    assert unwritable(str(tmp_path), fail, lambda path, mode: True) is None
    assert unwritable(str(tmp_path), fail, lambda path, mode: False) is PathState.NOT_WRITABLE


def test_a_path_with_no_folder_above_it_is_not_judged():
    assert unwritable("relative", lambda path: Usage(0), lambda path, mode: False) is None


def test_a_read_only_place_is_seen_by_the_wizard_before_anything_is_made_there(tmp_path, monkeypatch):
    monkeypatch.setattr("delta.ui.disk.unwritable", lambda path: PathState.READ_ONLY)

    assert inspect_path(str(tmp_path / "delta")) is PathState.READ_ONLY
