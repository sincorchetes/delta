import json

import pytest

from delta.domain.backup_job import BackupJob
from delta.domain.errors import (
    EngineError,
    PassphraseError,
    RepositoryLocked,
    RepositoryNotFound,
)
from delta.domain.repository import Repository
from delta.domain.retention import RetentionPolicy
from delta.infrastructure import borg_commands as commands
from delta.domain.progress import ProgressEvent
from delta.infrastructure.borg_parsing import error_for, parse_progress, parse_snapshots

REPO = Repository("/srv/repo")


def test_create_argv_has_excludes_and_sources():
    job = BackupJob("j", ("/home/a", "/etc"), excludes=("*.tmp",))
    assert commands.create(REPO, "now", job) == [
        "borg", "create", "--json", "--stats", "--progress", "--log-json",
        "--checkpoint-interval=300", "--exclude", "*.tmp", "/srv/repo::now", "/home/a", "/etc",
    ]


def test_parse_progress_reads_archive_progress():
    line = json.dumps({"type": "archive_progress", "nfiles": 3, "original_size": 99, "path": "/a"})
    assert parse_progress(line) == ProgressEvent(3, 99, "/a")


@pytest.mark.parametrize("line", [
    "garbage",
    "[]",
    json.dumps({"type": "log_message", "message": "x"}),
    json.dumps({"type": "archive_progress", "finished": True}),
])
def test_parse_progress_ignores_other_lines(line):
    assert parse_progress(line) is None


def test_error_for_understands_log_json():
    line = json.dumps({"type": "log_message", "levelname": "ERROR", "message": "Repository /x does not exist."})
    assert type(error_for(2, line)) is RepositoryNotFound


def test_mounting_stays_in_the_foreground_so_the_process_is_ours_to_stop():
    assert commands.mount(Repository("/r"), "monday", "/m") == ["borg", "mount", "-f", "/r::monday", "/m"]


def test_unmounting_is_lazy_so_an_open_file_cannot_keep_the_folder():
    assert commands.lazy_unmount("/m") == ["fusermount3", "-u", "-z", "/m"]


def test_extract_strips_leading_slash():
    assert commands.extract(REPO, "a", ("/home/x",))[-1] == "home/x"


def test_prune_argv_from_policy():
    argv = commands.prune(REPO, RetentionPolicy(1, 2, 3, 4))
    assert argv == [
        "borg", "prune", "--keep-hourly", "1", "--keep-daily", "2",
        "--keep-weekly", "3", "--keep-monthly", "4", "/srv/repo",
    ]


def test_prune_refuses_empty_policy():
    with pytest.raises(ValueError):
        commands.prune(REPO, RetentionPolicy(0, 0, 0, 0))


def test_parse_snapshots_sorted_oldest_first():
    out = json.dumps({"archives": [
        {"id": "b", "name": "n2", "time": "2026-11-09T11:00:00.000000"},
        {"id": "a", "name": "n1", "time": "2026-11-09T10:00:00.000000"},
    ]})
    assert [s.name for s in parse_snapshots(out)] == ["n1", "n2"]


def test_json_glued_after_a_prompt_on_the_same_line_is_still_unwrapped():
    from delta.infrastructure.borg_parsing import log_messages

    glued = (
        "Warning: Password input may be echoed.\n"
        'Enter passphrase for key /r: {"type": "log_message", "levelname": "ERROR", '
        '"message": "Cannot acquire a passphrase."}'
    )
    text = log_messages(glued)
    assert "Cannot acquire a passphrase." in text
    assert '"type"' not in text and "{" not in text


def test_a_plain_line_that_merely_mentions_json_is_kept():
    from delta.infrastructure.borg_parsing import log_messages

    assert log_messages('see {"type" docs') == 'see {"type" docs'


def test_partial_checkpoint_archives_are_never_offered_as_snapshots():
    out = json.dumps({"archives": [
        {"id": "a", "name": "2026-11-10T12-00-00", "time": "2026-11-10T12:00:00.000000"},
        {"id": "b", "name": "2026-11-10T13-00-00.checkpoint", "time": "2026-11-10T13:05:00.000000"},
        {"id": "c", "name": "2026-11-10T13-00-00.checkpoint.1", "time": "2026-11-10T13:10:00.000000"},
        {"id": "d", "name": "my.checkpoint.notes", "time": "2026-11-10T14:00:00.000000"},
    ]})
    assert [s.name for s in parse_snapshots(out)] == ["2026-11-10T12-00-00", "my.checkpoint.notes"]


@pytest.mark.parametrize("bad", ["not json", "{}", '{"archives": [{"id": 1}]}'])
def test_parse_snapshots_rejects_malformed(bad):
    with pytest.raises(EngineError):
        parse_snapshots(bad)


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("Repository /x does not exist.", RepositoryNotFound),
        ("Failed to create/acquire the lock /x/lock.exclusive (timeout).", RepositoryLocked),
        ("passphrase supplied in BORG_PASSPHRASE is incorrect.", PassphraseError),
        ("boom", EngineError),
    ],
)
def test_error_mapping(stderr, expected):
    assert type(error_for(2, stderr)) is expected
