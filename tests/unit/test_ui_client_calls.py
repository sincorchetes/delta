"""What the GTK app's D-Bus client sends and how it hands answers back, against a stand-in connection."""

from types import SimpleNamespace

import pytest
from gi.repository import GLib

from delta.ui import disk_watch
from delta.ui.client import INTERFACE, PROPERTIES, DeltaClient


class Connection:
    def __init__(self):
        self.calls, self.syncs, self.subscribed, self.unsubscribed = [], [], [], []
        self.reply = GLib.Variant("(aa{sv})", ([],))
        self.sync_error = None

    def call(self, bus_name, path, interface, method, parameters, reply_type, flags, timeout, cancellable, callback):
        self.calls.append((interface, method, parameters and parameters.unpack(), callback))

    def call_finish(self, result):
        if isinstance(result, GLib.Error):
            raise result
        return self.reply

    def call_sync(self, bus_name, path, interface, method, parameters, reply_type, flags, timeout, cancellable):
        if self.sync_error:
            raise self.sync_error
        self.syncs.append(method)

    def signal_subscribe(self, bus_name, interface, signal, path, arg0, flags, callback):
        self.subscribed.append((signal, callback))
        return 42

    def signal_unsubscribe(self, subscription):
        self.unsubscribed.append(subscription)


@pytest.fixture
def connection():
    return Connection()


@pytest.mark.parametrize(
    ("call", "interface", "method", "sent"),
    [
        (lambda c, r: c.read_state(r), PROPERTIES, "GetAll", (INTERFACE,)),
        (lambda c, r: c.list_snapshots(r), INTERFACE, "ListSnapshots", None),
        (lambda c, r: c.list_versions("/home/u/a", r), INTERFACE, "ListVersions", ("/home/u/a",)),
        (lambda c, r: c.list_folder("s", "/home/u", r), INTERFACE, "ListFolder", ("s", "/home/u")),
        (lambda c, r: c.search_folder("s", "/home/u", "q", r), INTERFACE, "SearchFolder", ("s", "/home/u", "q")),
        (lambda c, r: c.list_deleted("s", "/home/u", r), INTERFACE, "ListDeleted", ("s", "/home/u")),
        (lambda c, r: c.list_changed("s", "/home/u", r), INTERFACE, "ListChanged", ("s", "/home/u")),
        (lambda c, r: c.restore_deleted("s", "/home/u", r), INTERFACE, "RestoreDeleted", ("s", "/home/u")),
        (lambda c, r: c.restore_as_copy("s", "/home/u/a", r), INTERFACE, "RestoreAsCopy", ("s", "/home/u/a")),
        (lambda c, r: c.restore_replace("s", "/home/u/a", r), INTERFACE, "RestoreReplace", ("s", "/home/u/a")),
        (lambda c, r: c.preview_version("s", "/home/u/a", r), INTERFACE, "PreviewVersion", ("s", "/home/u/a")),
        (lambda c, r: c.mount_snapshot("s", r), INTERFACE, "MountSnapshot", ("s",)),
        (lambda c, r: c.unmount_snapshot(r), INTERFACE, "UnmountSnapshot", None),
        (lambda c, r: c.create_backup(r), INTERFACE, "CreateBackup", None),
        (lambda c, r: c.create_repository("/r", "pw", r), INTERFACE, "CreateRepository", ("/r", "pw")),
        (lambda c, r: c.unlock_repository(r), INTERFACE, "UnlockRepository", None),
        (lambda c, r: c.check_repository(r), INTERFACE, "CheckRepository", None),
        (lambda c, r: c.cancel_check(r), INTERFACE, "CancelCheck", None),
        (lambda c, r: c.use_repository("/r", "pw", r), INTERFACE, "UseRepository", ("/r", "pw")),
    ],
)
def test_each_request_names_its_method_and_hands_the_answer_to_the_caller(connection, call, interface, method, sent):
    answers = []
    connection.reply = GLib.Variant("(a{sv})", ({},)) if method == "GetAll" else GLib.Variant("(s)", ("job",))
    if method.startswith("List") or method == "ListSnapshots":
        connection.reply = GLib.Variant("(aa{sv})", ([],))

    call(DeltaClient(connection), lambda value, error: answers.append((value, error)))

    assert connection.calls[0][:3] == (interface, method, sent)
    connection.calls[0][3](connection, "result")
    assert len(answers) == 1 and answers[0][1] is None


def test_a_daemon_error_reaches_the_caller_as_plain_text(connection):
    answers = []
    DeltaClient(connection).create_backup(lambda value, error: answers.append((value, error)))
    failure = GLib.Error("GDBus.Error:io.github.sincorchetes.Delta.Service1.Error.Busy: another job is already running", domain="d", code=1)

    connection.calls[0][3](connection, failure)

    assert answers == [(None, "another job is already running")]


def test_the_signals_are_followed_and_can_be_dropped(connection):
    heard = []
    client = DeltaClient(connection)

    assert client.on_backup_finished(lambda *args: heard.append(("finished", args))) == 42
    assert client.on_progress(lambda *args: heard.append(("progress", args))) == 42
    finished, progress = (callback for _signal, callback in connection.subscribed)
    finished(None, None, None, None, None, GLib.Variant("(sbs)", ("job", True, "ok")))
    progress(None, None, None, None, None, GLib.Variant("(sds)", ("job", -1.0, "/home/u/a")))
    client.unsubscribe(42)

    assert heard == [("finished", ("job", True, "ok")), ("progress", ("job", -1.0, "/home/u/a"))]
    assert connection.unsubscribed == [42]


def test_closing_when_nothing_was_open_answers_with_no_job(connection):
    answers = []
    connection.reply = GLib.Variant("(s)", ("",))

    DeltaClient(connection).unmount_snapshot(lambda value, error: answers.append((value, error)))
    connection.calls[0][3](connection, "result")

    assert answers == [(None, None)]


def test_the_daemon_closing_a_backup_is_followed(connection):
    heard = []

    DeltaClient(connection).on_snapshot_closed(heard.append)
    connection.subscribed[0][1](None, None, None, None, None, GLib.Variant("(s)", ("sleep-or-lock",)))

    assert connection.subscribed[0][0] == "SnapshotClosed" and heard == ["sleep-or-lock"]


def test_previews_are_cleared_and_a_missing_daemon_is_no_problem(connection):
    client = DeltaClient(connection)

    client.clear_previews()
    connection.sync_error = GLib.Error("no daemon", domain="d", code=1)
    client.clear_previews()

    assert connection.syncs == ["ClearPreviews"]


def test_a_folder_that_cannot_be_followed_is_left_alone(monkeypatch):
    def cannot_follow(path):
        raise GLib.Error("not supported", domain="d", code=1)

    monkeypatch.setattr(
        disk_watch,
        "Gio",
        SimpleNamespace(
            File=SimpleNamespace(new_for_path=cannot_follow),
            FileMonitorFlags=SimpleNamespace(WATCH_MOVES=0),
        ),
    )
    watch = disk_watch.DiskWatch(lambda: None)

    watch.watch("/somewhere")

    assert watch._monitor is None
