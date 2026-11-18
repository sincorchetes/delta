import pytest

from delta.ui.preferences import (
    SCHEDULES,
    add_path,
    exclusion_problem,
    remove_path,
    retention_description,
    retention_model,
    retention_presets,
    retention_values,
    schedule_model,
    schedule_value,
)

HOME = "/home/user"


@pytest.mark.parametrize("expression", SCHEDULES)
def test_every_known_schedule_selects_its_entry_without_a_custom_one(expression):
    model = schedule_model(expression)
    assert model.selected == SCHEDULES.index(expression) and not model.has_custom
    assert len(model.labels) == len(SCHEDULES)


def test_a_schedule_set_by_hand_shows_as_custom_and_changes_nothing_until_replaced():
    model = schedule_model("*-*-* 03:00:00")
    assert model.has_custom and model.labels[model.selected] == "Custom"
    assert schedule_value(model.selected) is None


def test_each_schedule_entry_writes_its_expression():
    assert [schedule_value(i) for i in range(3)] == ["hourly", "daily", "weekly"]


def test_the_default_retention_is_the_standard_preset():
    model = retention_model((24, 7, 4, 12))
    assert model.labels[model.selected] == "Standard" and not model.has_custom


def test_every_preset_round_trips():
    for index, preset in enumerate(retention_presets()):
        assert retention_model(preset.values).selected == index
        assert retention_values(index) == preset.values


def test_values_set_by_hand_show_as_custom_and_are_not_overwritten_by_it():
    model = retention_model((5, 5, 5, 5))
    assert model.has_custom and model.labels[model.selected] == "Custom"
    assert retention_values(model.selected) is None
    assert "outside Delta" in retention_description(model.selected)


def test_no_preset_throws_away_all_history():
    assert all(any(preset.values) for preset in retention_presets())


def test_presets_are_ordered_from_less_to_more_history():
    totals = [sum(preset.values) for preset in retention_presets()]
    assert totals == sorted(totals) and len(set(totals)) == len(totals)


def test_adding_a_path_normalises_and_ignores_duplicates_and_relative_paths():
    paths = add_path((), "/srv//data/")
    assert paths == ("/srv/data",)
    assert add_path(paths, "/srv/data") == paths
    assert add_path(paths, "relative/dir") == paths
    assert add_path(paths, "/srv/other") == ("/srv/data", "/srv/other")


def test_removing_a_path_keeps_the_rest_in_order():
    assert remove_path(("/a", "/b", "/c"), "/b") == ("/a", "/c")
    assert remove_path(("/a",), "/zzz") == ("/a",)


@pytest.mark.parametrize("path", ["/", "/home", HOME, "/home/user/"])
def test_skipping_the_whole_home_or_above_is_refused_when_backing_up_home(path):
    assert exclusion_problem(path, (), HOME) is not None


def test_skipping_a_chosen_source_or_a_parent_of_it_is_refused():
    sources = ("/home/user/Pictures", "/srv/data")
    assert exclusion_problem("/home/user/Pictures", sources, HOME) is not None
    assert exclusion_problem("/srv", sources, HOME) is not None


def test_skipping_something_inside_a_source_is_fine():
    assert exclusion_problem("/home/user/Downloads", (), HOME) is None
    assert exclusion_problem("/home/user/Pictures/raw", ("/home/user/Pictures",), HOME) is None


def test_a_sibling_with_the_same_prefix_is_not_confused_with_a_parent():
    assert exclusion_problem("/home/us", (), HOME) is None


def test_a_known_retention_option_is_described():
    from delta.ui.preferences import retention_presets

    assert retention_description(0) == retention_presets()[0].description
