import os

import pytest

from delta.ui.disk import inspect_path
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
        assert inspect_path(str(locked)) is PathState.NOT_EMPTY
    finally:
        locked.chmod(0o700)
