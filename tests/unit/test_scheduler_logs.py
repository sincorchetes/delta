"""What the schedulers and the reloader say when something goes wrong or right: the facts, with their cause."""

import logging

from delta.daemon.config_reloader import ConfigReloader
from delta.domain.errors import SchedulerError
from delta.infrastructure.background_scheduler import BackgroundScheduler


class Inner:
    def apply(self, schedule):
        pass


class Portal:
    def __init__(self):
        self.asked = 0

    def request(self, answered):
        self.asked += 1


def messages(caplog, logger):
    return [record.getMessage() for record in caplog.records if record.name == logger]


def test_the_background_scheduler_has_not_asked_the_portal_until_a_schedule_is_applied():
    scheduler = BackgroundScheduler(Inner(), Portal())

    assert scheduler._asked is False


def test_the_answer_of_the_portal_is_logged_as_good_news_or_as_a_warning(caplog):
    with caplog.at_level(logging.INFO, logger="delta.infrastructure.background_scheduler"):
        BackgroundScheduler._answered(True)
        BackgroundScheduler._answered(False)

    assert messages(caplog, "delta.infrastructure.background_scheduler") == [
        "Delta may run in the background and starts at login",
        "Delta may not run in the background: scheduled backups only happen while it is open",
    ]


def test_a_schedule_that_cannot_be_applied_is_logged_with_the_reason(caplog):
    class Settings:
        def connect(self, signal, handler):
            pass

        def get_string(self, key):
            return "daily"

    class Broken:
        def apply(self, schedule):
            raise SchedulerError("no systemd")

    reloader = ConfigReloader(Settings(), None, lambda: None, Broken(), lambda: True)

    with caplog.at_level(logging.WARNING, logger="delta.daemon.config_reloader"):
        reloader.apply_schedule()

    assert messages(caplog, "delta.daemon.config_reloader") == ["cannot apply backup schedule: no systemd"]
