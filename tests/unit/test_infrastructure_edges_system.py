"""The adapters' contact with the system: notifications, the app launcher, systemd, the journal and what borg said."""

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from gi.repository import Gio, GLib

from delta.domain.errors import EngineError, SchedulerError
from delta.domain.notification import Notification, NotificationKind
from delta.domain.repository import Repository
from delta.infrastructure import gio_notifier, listing_cache, systemd_scheduler, ui_launcher
from delta.infrastructure.borg_parsing import parse_folder_listing, parse_folder_tree
from delta.infrastructure.borg_runner import BorgRunner
from delta.infrastructure.file_job_journal import FileJobJournal, default_state_dir


def glib_error(message="it failed"):
    return GLib.Error(message, domain="test", code=1)


# --- notifications -------------------------------------------------------------------------------


class Application:
    def __init__(self):
        self.actions, self.sent = [], []

    def add_action(self, action):
        self.actions.append(action)

    def send_notification(self, notification_id, message):
        self.sent.append((notification_id, message))


def test_a_notification_is_handed_to_the_main_loop_already_rendered(monkeypatch):
    queued = []
    monkeypatch.setattr(gio_notifier, "GLib", SimpleNamespace(idle_add=lambda *args: queued.append(args)))
    notifier = gio_notifier.GioNotifier(Application())

    notification = Notification(NotificationKind.BACKUP_SUCCEEDED, "")
    notifier.notify(notification)

    assert queued == [(notifier._send, *gio_notifier.render(notification))]


@pytest.mark.parametrize("opens_ui", [False, True])
def test_a_notification_is_sent_under_one_id_so_the_result_replaces_the_progress(opens_ui):
    application = Application()
    notifier = gio_notifier.GioNotifier(application, (lambda: None) if opens_ui else None)

    again = notifier._send("Backup complete", "Safe.", Gio.NotificationPriority.LOW)

    assert again is False
    assert [sent[0] for sent in application.sent] == [gio_notifier.NOTIFICATION_ID]
    assert len(application.actions) == (1 if opens_ui else 0)


# --- opening the app -----------------------------------------------------------------------------


def with_desktop_entry(monkeypatch, info):
    monkeypatch.setattr(ui_launcher, "Gio", SimpleNamespace(DesktopAppInfo=SimpleNamespace(new=lambda desktop_id: info)))


def test_the_app_is_launched_from_its_desktop_entry(monkeypatch):
    launched = []
    with_desktop_entry(monkeypatch, SimpleNamespace(launch=lambda files, context: launched.append(files)))

    ui_launcher.open_ui()

    assert launched == [[]]


def test_a_missing_desktop_entry_is_logged_not_raised(monkeypatch, caplog):
    with_desktop_entry(monkeypatch, None)

    with caplog.at_level(logging.WARNING):
        ui_launcher.open_ui()

    assert "is not installed" in caplog.text


def test_an_app_that_cannot_be_launched_is_logged_not_raised(monkeypatch, caplog):
    def refuse(files, context):
        raise glib_error("no display")

    with_desktop_entry(monkeypatch, SimpleNamespace(launch=refuse))

    with caplog.at_level(logging.WARNING):
        ui_launcher.open_ui()

    assert "no display" in caplog.text


# --- systemd -------------------------------------------------------------------------------------


def with_systemctl(monkeypatch, spawn):
    monkeypatch.setattr(
        systemd_scheduler,
        "Gio",
        SimpleNamespace(Subprocess=SimpleNamespace(new=spawn), SubprocessFlags=Gio.SubprocessFlags),
    )


def process(stdout="", stderr="", successful=True):
    return SimpleNamespace(
        communicate_utf8=lambda *args: (None, stdout, stderr), get_successful=lambda: successful
    )


def test_systemctl_output_is_returned(monkeypatch):
    with_systemctl(monkeypatch, lambda argv, flags: process(stdout="@1731264000\n"))

    assert systemd_scheduler.read_systemctl(["show"]) == "@1731264000\n"


def test_a_missing_output_is_an_empty_string(monkeypatch):
    with_systemctl(monkeypatch, lambda argv, flags: process(stdout=None))

    assert systemd_scheduler.read_systemctl(["show"]) == ""


def test_a_systemctl_that_cannot_start_is_a_scheduler_error(monkeypatch):
    def cannot_start(argv, flags):
        raise glib_error("No such file or directory")

    with_systemctl(monkeypatch, cannot_start)

    with pytest.raises(SchedulerError, match="cannot run systemctl"):
        systemd_scheduler.read_systemctl(["show"])


def test_a_failing_systemctl_says_why_or_what_it_was_asked(monkeypatch):
    with_systemctl(monkeypatch, lambda argv, flags: process(stderr="Unit not found.\n", successful=False))
    with pytest.raises(SchedulerError, match="Unit not found"):
        systemd_scheduler.run_systemctl(["enable", "delta.timer"])

    with_systemctl(monkeypatch, lambda argv, flags: process(successful=False))
    with pytest.raises(SchedulerError, match="systemctl enable delta.timer failed"):
        systemd_scheduler.run_systemctl(["enable", "delta.timer"])


# --- the journal ---------------------------------------------------------------------------------


def test_the_journal_lives_under_the_state_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    assert default_state_dir() == tmp_path / "delta"


def test_without_a_state_folder_the_journal_goes_under_the_home_folder(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert default_state_dir() == Path(tmp_path) / ".local" / "state" / "delta"


def test_a_backup_that_began_and_did_not_end_was_interrupted(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    journal = FileJobJournal()

    assert journal.was_interrupted() is False
    journal.begin()
    assert journal.was_interrupted() is True
    journal.end()
    assert journal.was_interrupted() is False


# --- what borg said ------------------------------------------------------------------------------


def entry(path, kind="-", size=1, mtime="2026-01-01T00:00:00.000000"):
    return json.dumps({"path": path, "type": kind, "size": size, "mtime": mtime})


def test_a_listing_line_that_is_not_an_entry_is_skipped_when_cutting_a_folder_out():
    listing = "\n".join(["not json", entry("home/u/dir/a"), entry("home/u/other/b")])

    assert listing_cache._cut(listing, "/home/u/dir") == entry("home/u/dir/a")


def test_a_path_with_nothing_after_the_folder_name_is_not_an_entry():
    listing = "\n".join([entry("home/u/dir//ghost"), entry("home/u/dir/real")])

    assert [e.name for e in parse_folder_listing(listing, "/home/u/dir")] == ["real"]


def test_a_tree_listing_that_is_not_borg_output_is_an_engine_error():
    with pytest.raises(EngineError):
        parse_folder_tree("not json", "/home/u/dir")


def test_borg_that_cannot_be_read_while_running_is_an_engine_error(monkeypatch):
    class Process:
        def communicate_utf8(self, *args):
            raise glib_error("pipe broke")

    runner = BorgRunner()
    monkeypatch.setattr(runner, "launcher", lambda repo, cwd: SimpleNamespace(spawnv=lambda argv: Process()))

    with pytest.raises(EngineError, match="pipe broke"):
        runner._run(["borg", "list"], Repository("/r"))
    assert runner._running == set()
