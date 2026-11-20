"""With Borg for real: names that break careless code survive a backup, the listings, a search and a restore."""

import shutil

import pytest

from delta.domain.backup_job import BackupJob
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner

pytestmark = pytest.mark.skipif(shutil.which("borg") is None, reason="borg not installed")

HOSTILE = [
    "with space.txt",
    "  leading and trailing  ",
    "-starts-with-a-dash",
    "--looks-like-an-option",
    "quote'single.txt",
    'quote"double.txt',
    "back\\slash.txt",
    "star*.txt",
    "question?.txt",
    "[brackets].txt",
    "{braces}.txt",
    "colon: semicolon;.txt",
    "pp:looks-like-a-pattern",
    "re:looks-like-a-regex",
    "dollar$HOME.txt",
    "`backtick`.txt",
    "percent%20.txt",
    "tab\there.txt",
    "línea-ñandú-日本語.txt",
    "emoji-🙂.txt",
    "x" * 200,
]


@pytest.fixture
def world(tmp_path):
    runner = BorgRunner(env={"BORG_PASSPHRASE": "x", "BORG_BASE_DIR": str(tmp_path / "borg-home")})
    repo = Repository(str(tmp_path / "repo"))
    runner.init(repo)
    root = tmp_path / "data"
    root.mkdir()
    for index, name in enumerate(HOSTILE):
        (root / name).write_text(f"content {index}")
    (root / "folder with spaces").mkdir()
    (root / "folder with spaces" / "inner [1].txt").write_text("inside")
    snapshot = runner.create(repo, BackupJob("j", (str(root),)), "snap")
    return runner, repo, root, snapshot, tmp_path


def test_every_name_is_listed_as_it_was(world):
    runner, repo, root, snapshot, _tmp = world

    names = {entry.name for entry in runner.list_folder(repo, snapshot, str(root))}

    assert names == {*HOSTILE, "folder with spaces"}


def test_every_name_has_its_own_entry_with_its_size(world):
    runner, repo, root, snapshot, _tmp = world

    for index, name in enumerate(HOSTILE):
        entry = runner.file_entry(repo, snapshot, f"{root}/{name}")
        assert entry is not None and entry.size == len(f"content {index}"), name


def test_what_is_inside_a_folder_with_odd_names_is_listed(world):
    runner, repo, root, snapshot, _tmp = world

    inner = runner.list_folder(repo, snapshot, f"{root}/folder with spaces")

    assert [entry.name for entry in inner] == ["inner [1].txt"]


def test_a_search_finds_names_with_characters_that_mean_something_to_a_pattern(world):
    runner, repo, root, snapshot, _tmp = world

    found = {entry.name for entry in runner.search_folder(repo, snapshot, str(root), "[1]", 100)}
    assert found == {"folder with spaces/inner [1].txt"}

    stars = {entry.name for entry in runner.search_folder(repo, snapshot, str(root), "*", 100)}
    assert stars == {"star*.txt"}


def test_every_file_comes_back_with_its_content(world):
    runner, repo, root, snapshot, tmp_path = world
    out = tmp_path / "restored"
    out.mkdir()

    runner.extract(repo, snapshot, tuple(f"{root}/{name}" for name in HOSTILE), str(out))

    base = out / str(root).lstrip("/")
    for index, name in enumerate(HOSTILE):
        assert (base / name).read_text() == f"content {index}", name


def test_restoring_one_odd_name_does_not_bring_its_lookalikes(world):
    runner, repo, root, snapshot, tmp_path = world
    out = tmp_path / "one"
    out.mkdir()

    runner.extract(repo, snapshot, (f"{root}/star*.txt",), str(out))

    base = out / str(root).lstrip("/")
    assert [path.name for path in base.iterdir()] == ["star*.txt"]
