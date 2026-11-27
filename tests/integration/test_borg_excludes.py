"""The user's exclusions reach borg as `pp:` paths: exact subtree, never a wildcard."""

import shutil

import pytest

from delta.application.backup_service import BackupService
from delta.daemon.composition import resolve_excludes
from delta.domain.backup_job import BackupJob
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner

pytestmark = pytest.mark.skipif(shutil.which("borg") is None, reason="borg not installed")


@pytest.fixture
def world(tmp_path):
    runner = BorgRunner(
        env={"BORG_PASSPHRASE": "x", "BORG_BASE_DIR": str(tmp_path / "borg-home")}
    )
    repo = Repository(str(tmp_path / "repo"))
    runner.init(repo)
    root = tmp_path / "data"
    root.mkdir()
    return runner, repo, root, tmp_path


def backed_up(runner, repo, root, tmp_path, excluded):
    job = BackupJob("j", (str(root),), resolve_excludes(tuple(map(str, excluded)), str(tmp_path / "home")))
    name = runner.create(repo, job, "snap")
    listing = runner.list_snapshots(repo)
    assert [s.name for s in listing] == [name]
    dest = tmp_path / "out"
    dest.mkdir()
    runner.extract(repo, name, (str(root),), str(dest))
    base = dest / str(root).lstrip("/")
    return {p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()}


def test_an_excluded_folder_is_skipped_with_everything_inside_but_not_its_neighbours(world):
    runner, repo, root, tmp_path = world
    (root / "skip" / "deep").mkdir(parents=True)
    (root / "skip" / "deep" / "f").write_text("x")
    (root / "skipper").mkdir()
    (root / "skipper" / "f").write_text("keep: only a similar name")
    (root / "keep.txt").write_text("keep")

    files = backed_up(runner, repo, root, tmp_path, [root / "skip"])

    assert files == {"skipper/f", "keep.txt"}


def test_wildcard_characters_in_a_name_exclude_only_that_name(world):
    runner, repo, root, tmp_path = world
    (root / "[1]").mkdir()
    (root / "[1]" / "f").write_text("skip")
    (root / "1").mkdir()
    (root / "1" / "f").write_text("keep: a wildcard would have matched this")
    (root / "star").mkdir()
    (root / "star" / "f").write_text("keep")
    (root / "*").mkdir()
    (root / "*" / "f").write_text("skip")

    files = backed_up(runner, repo, root, tmp_path, [root / "[1]", root / "*"])

    assert files == {"1/f", "star/f"}


def test_a_repository_inside_the_sources_is_not_copied_into_itself(tmp_path):
    runner = BorgRunner(env={"BORG_PASSPHRASE": "x", "BORG_BASE_DIR": str(tmp_path / "borg-home")})
    home = tmp_path / "home"
    (home / "Backups").mkdir(parents=True)
    repo = Repository(str(home / "Backups" / "repo"))
    runner.init(repo)
    (home / "notes.txt").write_text("keep")
    (home / "Backups" / "readme.txt").write_text("keep: beside the repository, not inside it")

    job = BackupService(runner, repo, (str(home),)).new_job()
    name = runner.create(repo, job, "snap")

    dest = tmp_path / "out"
    dest.mkdir()
    runner.extract(repo, name, (str(home),), str(dest))
    base = dest / str(home).lstrip("/")
    files = {p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()}
    assert files == {"notes.txt", "Backups/readme.txt"}


def test_an_excluded_single_file_is_skipped(world):
    runner, repo, root, tmp_path = world
    (root / "secret.txt").write_text("skip")
    (root / "notes.txt").write_text("keep")

    assert backed_up(runner, repo, root, tmp_path, [root / "secret.txt"]) == {"notes.txt"}


def test_the_cache_of_a_flatpak_app_is_skipped_but_not_its_data(world):
    runner, repo, _, tmp_path = world
    home = tmp_path / "home"
    for folder in (".cache/x", ".var/app/org.x.App/cache/deep", ".var/app/org.x.App/data", ".var/app/org.x.App/cached"):
        (home / folder).mkdir(parents=True)
        (home / folder / "f").write_text("x")

    files = backed_up(runner, repo, home, tmp_path, [])

    assert files == {".var/app/org.x.App/data/f", ".var/app/org.x.App/cached/f"}
