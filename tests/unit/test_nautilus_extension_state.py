"""The backup state of a file: the column and the emblem of the extension."""

import time
import pytest
from nautilus_extension_support import FakeClock, FileInfo, HOME, backup_info, info_for
from nautilus_extension_support import extension, home  # noqa: F401  (fixtures)


@pytest.mark.parametrize(
    ("path", "sources", "excludes", "covered"),
    [
        ("/home/ana/Documents/a.txt", (), (), True),  # no folders chosen: the whole home folder
        ("/home/ana/.cache/x/y", (), (), False),  # what the daemon never backs up
        ("/home/ana/.local/share/Trash/files/old", (), (), False),
        ("/home/ana/.var/app/org.x.App/cache/y", (), (), False),  # the cache of a Flatpak app
        ("/home/ana/.var/app/org.x.App/data/y", (), (), True),  # its data is backed up
        ("/home/ana/.var/app/org.x.App/cached", (), (), True),  # a similar name
        ("/home/ana/Pictures/me.jpg", ("~/Pictures",), (), True),
        ("/home/ana/Documents/a.txt", ("~/Pictures",), (), False),  # outside the chosen folders
        ("/home/ana/Picturesque/a.txt", ("~/Pictures",), (), False),  # a sibling, not inside
        ("/home/ana/Pictures/Screenshots/a.png", ("~/Pictures",), ("/home/ana/Pictures/Screenshots",), False),
        ("/home/ana/Pictures/Screenshots/a.png", ("~/Pictures",), ("~/Pictures/Screenshots",), False),
        ("/home/ana/Pictures/ScreenshotsOld/a.png", ("~/Pictures",), ("~/Pictures/Screenshots",), True),
        ("/home/ana/Documents/a.txt", ("relative/dir",), (), True),  # an invalid source is dropped
    ],
)
def test_the_backup_covers_the_chosen_folders_minus_the_skipped_ones(extension, path, sources, excludes, covered):
    assert extension.is_covered(path, HOME, backup_info(extension, sources=sources, excludes=excludes)) is covered


def test_a_file_unchanged_since_the_last_backup_is_saved(extension):
    info = backup_info(extension, last=1000)
    assert extension.backup_status("/home/ana/a.txt", 900, info, HOME) == extension.SAVED
    assert extension.backup_status("/home/ana/a.txt", 1000.4, info, HOME) == extension.SAVED


def test_a_file_changed_after_the_last_backup_is_pending(extension):
    assert (
        extension.backup_status("/home/ana/a.txt", 1001, backup_info(extension, last=1000), HOME) == extension.PENDING
    )


def test_before_the_first_backup_everything_covered_is_pending(extension):
    assert extension.backup_status("/home/ana/a.txt", 5, backup_info(extension, last=0), HOME) == extension.PENDING


def test_a_file_the_backup_skips_has_no_state(extension):
    assert extension.backup_status("/home/ana/.cache/a", 5, backup_info(extension), HOME) is None


def test_the_state_is_read_once_per_refresh_period_not_once_per_file(extension):
    reads, clock = [], FakeClock()
    state = extension.BackupState(read=lambda: reads.append(1) or backup_info(extension), clock=clock)

    for _ in range(50):  # Nautilus asks for every visible file
        state.get()
    assert len(reads) == 1

    clock.now += extension.REFRESH_SECONDS - 1
    state.get()
    assert len(reads) == 1

    clock.now += 1
    state.get()
    assert len(reads) == 2


def test_an_unknown_state_is_kept_for_the_period_too(extension):
    reads, clock = [], FakeClock()
    state = extension.BackupState(read=lambda: reads.append(1), clock=clock)  # always None
    state.get()
    state.get()
    assert len(reads) == 1


def test_there_is_one_backup_column(extension):
    (column,) = info_for(extension, None).get_columns()
    assert column.attribute == "delta_backup" and column.name == "Delta::Backup"
    assert column.label == "Backup"


def test_a_file_changed_since_the_last_backup_gets_the_emblem_and_the_column_text(extension, home):
    file = FileInfo(str(home / "Documents" / "a.txt"))

    info_for(extension, backup_info(extension, last=1)).update_file_info(file)

    assert file.attributes == {"delta_backup": "Changed since the last backup"}
    assert file.emblems == [extension.PENDING_EMBLEM]


def test_a_saved_file_only_gets_the_column_text(extension, home):
    file = FileInfo(str(home / "Documents" / "a.txt"))
    future = int(time.time()) + 1000

    info_for(extension, backup_info(extension, last=future)).update_file_info(file)

    assert file.attributes == {"delta_backup": "In the latest backup"}
    assert file.emblems == []


@pytest.mark.parametrize(
    "build",
    [
        lambda home: FileInfo(str(home / "Documents"), directory=True),
        lambda home: FileInfo(str(home / "Documents" / "a.txt"), scheme="sftp"),
        lambda home: FileInfo("/etc/passwd"),
        lambda home: FileInfo(str(home / "Documents" / "missing.txt")),
        lambda home: FileInfo(None),
    ],
    ids=["folder", "not a local file", "outside home", "vanished", "no path"],
)
def test_things_with_no_file_state_are_left_alone(extension, home, build):
    file = build(home)

    info_for(extension, backup_info(extension, last=1)).update_file_info(file)

    assert file.attributes == {} and file.emblems == []


def test_when_the_state_is_unknown_nothing_is_marked(extension, home):
    """No repository, no settings or the daemon is not running: say nothing rather than guess."""
    file = FileInfo(str(home / "Documents" / "a.txt"))

    info_for(extension, None).update_file_info(file)

    assert file.attributes == {} and file.emblems == []


def test_a_skipped_folder_is_not_marked(extension, home):
    cache = home / ".cache"
    cache.mkdir()
    (cache / "x").write_text("x")
    file = FileInfo(str(cache / "x"))

    info_for(extension, backup_info(extension, last=1)).update_file_info(file)

    assert file.attributes == {} and file.emblems == []
