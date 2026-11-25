"""The preferences, as real widgets."""

from gtk_helpers import of_type
from gi.repository import Adw
from delta.i18n import _
from panes_and_dialogs_support import checks, preferences


def test_the_destination_is_shown():
    dialog, _settings, _toasts = preferences()

    assert any(
        "/media/disk/delta-backups" in (row.get_subtitle() or "")
        for row in of_type(dialog.get_visible_page(), Adw.ActionRow)
    )


def test_without_a_destination_it_says_so():
    dialog, _settings, _toasts = preferences(**{"repository-location": ""})

    assert any(row.get_subtitle() == _("Not set up yet") for row in of_type(dialog.get_visible_page(), Adw.ActionRow))


def test_choosing_another_schedule_is_saved():
    dialog, settings, _toasts = preferences()

    dialog._schedule.set_selected(1)

    assert settings.written == [("schedule", "daily")]


def test_the_schedule_already_in_force_is_not_written_again():
    dialog, settings, _toasts = preferences()

    dialog._on_schedule(dialog._schedule, None)

    assert settings.written == []


def test_a_schedule_set_by_hand_is_not_overwritten_by_looking_at_it():
    dialog, settings, _toasts = preferences(schedule="*-*-* 03:00:00")

    dialog._schedule.set_selected(3)  # the "Custom" entry stands for what is already set

    assert settings.written == []


def test_choosing_a_retention_option_saves_its_four_values():
    dialog, settings, _toasts = preferences()

    checks(dialog)[2].set_active(True)  # "Long": 24, 14, 12, 36

    assert dict(settings.written) == {"keep-daily": 14, "keep-weekly": 12, "keep-monthly": 36}
    assert [key for key, _value in settings.written if key == "keep-hourly"] == []


def test_the_option_in_force_is_ticked_and_a_hand_set_value_gets_its_own_row():
    dialog, _settings, _toasts = preferences(**{"keep-daily": 9})

    boxes = checks(dialog)

    assert len(boxes) == 4 and boxes[3].get_active() and not boxes[3].get_sensitive()
    assert not any(box.get_active() for box in boxes[:3])


def test_unticking_an_option_changes_nothing():
    dialog, settings, _toasts = preferences()

    dialog._on_preset(checks(dialog)[0], 0)
    dialog._on_preset(checks(dialog)[1], 99)

    assert settings.written == []


def test_chosen_folders_and_exclusions_are_saved_as_lists():
    dialog, settings, _toasts = preferences()

    dialog._sources._add("/home/u/docs")
    dialog._exclusions._add("/home/u/docs/tmp")

    assert ("backup-sources", ["/home/u/docs"]) in settings.written
    assert ("excluded-paths", ["/home/u/docs/tmp"]) in settings.written


def test_an_exclusion_that_would_skip_everything_is_refused_with_a_toast():
    dialog, settings, toasts = preferences()

    dialog._exclusions._add("/home/u")

    assert len(toasts) == 1 and settings.written == []
