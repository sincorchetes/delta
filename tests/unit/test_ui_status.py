from datetime import datetime

import pytest

from delta.ui.status import (
    Action,
    DaemonSnapshot,
    Health,
    build_status,
    describe_schedule,
    relative_time,
)

NOW = datetime(2026, 11, 10, 15, 0, 0)
EPOCH = int(NOW.timestamp())


def snapshot(**fields):
    return DaemonSnapshot(**{"repository": "/backups/repo", **fields})


@pytest.mark.parametrize(
    ("seconds_ago", "expected"),
    [
        (0, "just now"),
        (59, "just now"),
        (60, "1 minute ago"),
        (59 * 60, "59 minutes ago"),
        (3600, "1 hour ago"),
        (23 * 3600, "23 hours ago"),
        (24 * 3600, "1 day ago"),
        (5 * 24 * 3600, "5 days ago"),
    ],
)
def test_relative_time(seconds_ago, expected):
    assert relative_time(EPOCH - seconds_ago, NOW) == expected


def test_a_clock_running_behind_the_daemon_never_shows_a_negative_time():
    assert relative_time(EPOCH + 500, NOW) == "just now"


@pytest.mark.parametrize(
    ("expression", "expected"),
    [("hourly", "every hour"), ("daily", "every day"), ("weekly", "every week")],
)
def test_known_schedules_read_naturally(expression, expected):
    assert describe_schedule(expression) == expected


def test_unknown_schedule_is_shown_as_is():
    assert "*-*-* 03:00:00" in describe_schedule("*-*-* 03:00:00")


def test_unreachable_service_comes_first_and_blocks_backup():
    view = build_status(DaemonSnapshot(reachable=False), NOW)
    assert view.health is Health.UNREACHABLE and not view.can_back_up_now


def test_without_a_repository_the_user_is_asked_to_set_up():
    view = build_status(DaemonSnapshot(repository=""), NOW)
    assert view.health is Health.NOT_CONFIGURED and not view.can_back_up_now


def test_running_blocks_a_second_backup():
    view = build_status(snapshot(status="running", last_backup=EPOCH - 100), NOW)
    assert view.health is Health.RUNNING and not view.can_back_up_now


def test_an_open_backup_says_so_and_blocks_a_backup_until_it_is_closed():
    view = build_status(snapshot(status="browsing", last_backup=EPOCH - 100), NOW)

    assert view.health is Health.BROWSING and not view.can_back_up_now
    assert view.title == "A backup is open as a folder" and "close it" in view.subtitle


def test_a_failure_shows_its_reason_and_allows_trying_again():
    view = build_status(snapshot(last_error="repository locked", last_backup=EPOCH - 100), NOW)
    assert view.health is Health.FAILED
    assert view.subtitle == "repository locked" and view.can_back_up_now


def test_the_button_matches_the_situation():
    cases = {
        DaemonSnapshot(reachable=False): (Action.NONE, True),
        DaemonSnapshot(repository=""): (Action.SET_UP, True),
        snapshot(status="running"): (Action.BACK_UP, False),
        snapshot(last_error="boom"): (Action.BACK_UP, True),
        snapshot(last_backup=0): (Action.BACK_UP, True),
        snapshot(last_backup=EPOCH - 10): (Action.BACK_UP, True),
    }
    for state, (action, enabled) in cases.items():
        view = build_status(state, NOW)
        assert (view.action, view.action_enabled) == (action, enabled), view.health


def test_button_labels_say_what_they_do():
    assert build_status(DaemonSnapshot(repository=""), NOW).action_label == "Set up backups"
    assert build_status(snapshot(last_error="x"), NOW).action_label == "Try again"
    assert build_status(snapshot(last_backup=EPOCH - 10), NOW).action_label == "Back up now"
    assert build_status(DaemonSnapshot(reachable=False), NOW).action_label == ""


def test_a_long_multiline_engine_error_is_shown_as_one_short_paragraph():
    noisy = "line one\n" + "x" * 500 + "\nlast line"
    view = build_status(snapshot(last_error=noisy), NOW)
    assert "\n" not in view.subtitle
    assert len(view.subtitle) <= 241 and view.subtitle.endswith("…")


def test_every_icon_is_a_vector_that_ships_with_adwaita():
    """The names Adwaita 50 really provides; `emblem-ok`/`emblem-synchronizing` are not among them."""
    shipped = {
        "dialog-warning-symbolic", "drive-harddisk-symbolic", "view-refresh-symbolic",
        "dialog-error-symbolic", "appointment-soon-symbolic", "object-select-symbolic",
    }
    states = [
        DaemonSnapshot(reachable=False), DaemonSnapshot(repository=""),
        snapshot(status="running"), snapshot(last_error="x"),
        snapshot(last_backup=0), snapshot(last_backup=EPOCH - 10),
    ]
    assert {build_status(state, NOW).icon_name for state in states} <= shipped


def test_running_takes_precedence_over_an_old_failure():
    view = build_status(snapshot(status="running", last_error="old problem"), NOW)
    assert view.health is Health.RUNNING


def test_no_backup_yet_says_when_the_first_will_run():
    view = build_status(snapshot(last_backup=0, schedule="daily"), NOW)
    assert view.health is Health.PENDING
    assert "every day" in view.subtitle and view.can_back_up_now


def test_a_healthy_state_reports_the_last_backup_and_schedule():
    view = build_status(snapshot(last_backup=EPOCH - 5 * 60, schedule="hourly"), NOW)
    assert view.health is Health.OK
    assert "5 minutes ago" in view.subtitle and "every hour" in view.subtitle
    assert view.can_back_up_now


def test_every_state_has_an_icon_and_a_title():
    states = [
        DaemonSnapshot(reachable=False),
        DaemonSnapshot(repository=""),
        snapshot(status="running"),
        snapshot(last_error="x"),
        snapshot(last_backup=0),
        snapshot(last_backup=EPOCH - 10),
    ]
    for state in states:
        view = build_status(state, NOW)
        assert view.title and view.icon_name.endswith("-symbolic")


from delta.ui.status import until_time


@pytest.mark.parametrize(
    ("seconds_ahead", "expected"),
    [
        (-500, "in a moment"),
        (0, "in a moment"),
        (59, "in a moment"),
        (60, "in 1 minute"),
        (40 * 60, "in 40 minutes"),
        (3600, "in 1 hour"),
        (5 * 3600, "in 5 hours"),
        (24 * 3600, "in 1 day"),
        (3 * 24 * 3600, "in 3 days"),
    ],
)
def test_until_time(seconds_ahead, expected):
    assert until_time(EPOCH + seconds_ahead, NOW) == expected


def test_a_known_next_backup_is_announced_when_protected():
    view = build_status(snapshot(last_backup=EPOCH - 600, next_backup=EPOCH + 2400), NOW)
    assert view.health is Health.OK
    assert view.subtitle == "Last backup: 10 minutes ago. Next backup: in 40 minutes."


def test_without_a_known_next_backup_the_schedule_is_described_instead():
    view = build_status(snapshot(last_backup=EPOCH - 600), NOW)
    assert view.subtitle == "Last backup: 10 minutes ago. Backups run every hour."


def test_the_first_backup_says_when_it_will_run():
    assert build_status(snapshot(next_backup=EPOCH + 1800), NOW).subtitle == (
        "The first backup runs in 30 minutes."
    )
    assert build_status(snapshot(), NOW).subtitle == "The first backup runs every hour."


LOCK = "Failed to create/acquire the lock /backups/repo/lock.exclusive (timeout)."


def test_a_lock_failure_offers_to_unlock_instead_of_retrying():
    view = build_status(snapshot(last_error=LOCK, last_backup=EPOCH - 100), NOW)
    assert view.health is Health.LOCKED
    assert view.action is Action.UNLOCK and view.action_label == "Unlock…"
    assert "locked" in view.title and not view.can_back_up_now


def test_running_still_wins_over_a_lock_failure():
    assert build_status(snapshot(status="running", last_error=LOCK), NOW).health is Health.RUNNING


def test_the_lock_state_uses_a_shipped_icon():
    assert build_status(snapshot(last_error=LOCK), NOW).icon_name == "dialog-warning-symbolic"


# --- the drive with the backups is not connected ---------------------------------------------------


def test_a_drive_that_is_not_connected_says_so_and_where_it_has_to_be():
    view = build_status(snapshot(status="unavailable", repository="/run/media/u/BACKUPS/delta"), NOW)

    assert view.health is Health.UNAVAILABLE
    assert view.title == "The drive with your backups is not connected"
    assert "/run/media/u/BACKUPS/delta" in view.subtitle and "by itself" in view.subtitle
    assert view.icon_name == "drive-removable-media-symbolic"


def test_a_drive_that_is_not_connected_is_not_an_error_and_can_be_checked_again():
    view = build_status(snapshot(status="unavailable"), NOW)

    assert (view.action, view.action_label, view.action_enabled) == (Action.BACK_UP, "Check again", True)
    assert view.can_back_up_now and view.icon_name != "dialog-error-symbolic"


def test_it_is_what_is_said_even_if_an_earlier_backup_failed():
    view = build_status(snapshot(status="unavailable", last_error="Repository /x does not exist."), NOW)

    assert view.health is Health.UNAVAILABLE and "does not exist" not in view.subtitle


def test_a_backup_that_is_running_is_running_whatever_came_before():
    assert build_status(snapshot(status="running", last_error="x"), NOW).health is Health.RUNNING


def test_without_a_repository_it_is_not_a_drive_that_is_missing():
    assert build_status(snapshot(status="unavailable", repository=""), NOW).health is Health.NOT_CONFIGURED


# --- the place cannot be used, and each cause says so -------------------------------------------------


@pytest.mark.parametrize(
    "reason, title, icon",
    [
        ("other-drive", "Your backups are not on this drive", "drive-harddisk-symbolic"),
        ("other-repository", "These are not your backups", "dialog-warning-symbolic"),
        ("full", "The place with your backups is full", "drive-harddisk-symbolic"),
        ("read-only", "The place with your backups is read-only", "changes-prevent-symbolic"),
        ("denied", "You cannot write where your backups are kept", "changes-prevent-symbolic"),
        ("missing", "The drive with your backups is not connected", "drive-removable-media-symbolic"),
        ("empty", "The drive with your backups is not connected", "drive-removable-media-symbolic"),
        ("", "The drive with your backups is not connected", "drive-removable-media-symbolic"),
    ],
)
def test_each_cause_has_its_own_title_and_says_where_the_place_is(reason, title, icon):
    view = build_status(snapshot(status="unavailable", repository="/run/media/u/BACKUPS/delta", reason=reason), NOW)

    assert (view.health, view.title, view.icon_name) == (Health.UNAVAILABLE, title, icon)
    assert "/run/media/u/BACKUPS/delta" in view.subtitle
    assert (view.action, view.action_label, view.action_enabled) == (Action.BACK_UP, "Check again", True)


def test_a_place_that_is_full_points_to_the_preferences_and_not_to_a_cable():
    view = build_status(snapshot(status="unavailable", repository="/x", reason="full"), NOW)

    assert "Free some space" in view.subtitle and "preferences" in view.subtitle and "Connect" not in view.subtitle
