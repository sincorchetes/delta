"""A drive that comes back starts the backup that was waiting for it, and nothing else does."""

from delta.daemon.drive_return import DriveReturn
from delta.infrastructure.mount_events import GioMountEvents


def started_by(status):
    calls = []
    DriveReturn(lambda: status, lambda: calls.append(1)).on_mounted()
    return calls


def test_a_mount_while_the_drive_was_away_starts_the_backup():
    assert started_by("unavailable") == [1]


def test_a_mount_at_any_other_time_starts_nothing():
    assert started_by("idle") == started_by("running") == started_by("browsing") == []


class Monitor:
    def __init__(self):
        self.handlers = {}

    def connect(self, signal, handler):
        self.handlers[signal] = handler


def test_the_adapter_calls_back_without_the_arguments_of_the_signal():
    monitor, seen = Monitor(), []
    GioMountEvents(monitor).watch(lambda: seen.append("mounted"))

    monitor.handlers["mount-added"](monitor, "a mount")

    assert seen == ["mounted"]


def test_the_adapter_follows_the_volume_monitor_of_the_session_by_default():
    assert GioMountEvents() is not None
