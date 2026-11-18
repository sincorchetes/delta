"""When a schedule fires, in the cases that tell one reading of a calendar expression from another."""

from datetime import datetime

import pytest

from delta.domain.recurrence import SEARCH_DAYS, Recurrence, parse

WEDNESDAY = datetime(2026, 11, 18, 10, 30, 15)  # 2026-11-18 is a Wednesday


@pytest.mark.parametrize(
    ("expression", "after", "expected"),
    [
        ("hourly", WEDNESDAY, datetime(2026, 11, 18, 11, 0)),
        ("hourly", datetime(2026, 11, 18, 10, 0, 0), datetime(2026, 11, 18, 11, 0)),  # strictly after
        ("hourly", datetime(2026, 11, 18, 23, 30), datetime(2026, 11, 19, 0, 0)),
        ("daily", WEDNESDAY, datetime(2026, 11, 19, 0, 0)),
        ("daily", datetime(2026, 11, 18, 0, 0, 0), datetime(2026, 11, 19, 0, 0)),
        ("weekly", WEDNESDAY, datetime(2026, 11, 23, 0, 0)),  # the next Monday
        ("weekly", datetime(2026, 11, 23, 0, 0, 0), datetime(2026, 11, 30, 0, 0)),
        ("monthly", WEDNESDAY, datetime(2026, 12, 1, 0, 0)),
        ("monthly", datetime(2026, 12, 15), datetime(2027, 1, 1, 0, 0)),
        ("quarterly", WEDNESDAY, datetime(2027, 1, 1, 0, 0)),
        ("quarterly", datetime(2026, 2, 1), datetime(2026, 4, 1, 0, 0)),
        ("semiannually", datetime(2026, 2, 1), datetime(2026, 7, 1, 0, 0)),
        ("yearly", WEDNESDAY, datetime(2027, 1, 1, 0, 0)),
        ("annually", WEDNESDAY, datetime(2027, 1, 1, 0, 0)),
        ("*-*-* 03:30", WEDNESDAY, datetime(2026, 11, 19, 3, 30)),
        ("*-*-* 18:00:30", WEDNESDAY, datetime(2026, 11, 18, 18, 0, 30)),
        ("*-*-* 10:30:15", WEDNESDAY, datetime(2026, 11, 19, 10, 30, 15)),
        ("Mon,Fri *-*-* 18:00", WEDNESDAY, datetime(2026, 11, 20, 18, 0)),  # Friday
        ("Mon..Fri *-*-* 08:00", datetime(2026, 11, 20, 9, 0), datetime(2026, 11, 23, 8, 0)),  # over the weekend
        ("Fri..Mon *-*-* 08:00", WEDNESDAY, datetime(2026, 11, 20, 8, 0)),  # a range that wraps
        ("  HOURLY  ", WEDNESDAY, datetime(2026, 11, 18, 11, 0)),
    ],
)
def test_the_next_time_it_fires(expression, after, expected):
    assert parse(expression).next_after(after) == expected


@pytest.mark.parametrize(
    ("expression", "at", "expected"),
    [
        ("hourly", WEDNESDAY, datetime(2026, 11, 18, 10, 0)),
        ("hourly", datetime(2026, 11, 18, 10, 0, 0), datetime(2026, 11, 18, 10, 0)),  # at, not only before
        ("hourly", datetime(2026, 11, 18, 0, 0, 1), datetime(2026, 11, 18, 0, 0)),
        ("daily", WEDNESDAY, datetime(2026, 11, 18, 0, 0)),
        ("weekly", WEDNESDAY, datetime(2026, 11, 16, 0, 0)),  # the Monday before
        ("monthly", WEDNESDAY, datetime(2026, 11, 1, 0, 0)),
        ("yearly", WEDNESDAY, datetime(2026, 1, 1, 0, 0)),
        ("*-*-* 18:00", WEDNESDAY, datetime(2026, 11, 17, 18, 0)),  # today's is still to come: yesterday's
        ("*-*-* 10:00", WEDNESDAY, datetime(2026, 11, 18, 10, 0)),
        ("Mon..Fri *-*-* 08:00", datetime(2026, 11, 22, 12, 0), datetime(2026, 11, 20, 8, 0)),
    ],
)
def test_the_last_time_it_should_have_fired(expression, at, expected):
    assert parse(expression).latest_up_to(at) == expected


def test_fractions_of_a_second_do_not_make_a_moment_count_twice():
    moment = datetime(2026, 11, 18, 11, 0, 0, 500)

    assert parse("hourly").next_after(moment) == datetime(2026, 11, 18, 12, 0)
    assert parse("hourly").latest_up_to(moment) == datetime(2026, 11, 18, 11, 0)


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "minutely",
        "*-*-01 02:00",  # a day of the month: only systemd
        "Mon *-*-*",  # no time
        "03:30",  # no date
        "*-*-* 25:00",
        "*-*-* 10:60",
        "*-*-* 10:00:60",
        "*-*-* 1:00",  # systemd allows it; here two digits are asked for, to be sure of the reading
        "*-*-* 10",
        "*-*-* 10:00:00:00",
        "Foo *-*-* 10:00",
        "Mon..Foo *-*-* 10:00",
        "Mon *-*-* 10:00 extra",
    ],
)
def test_only_what_delta_offers_can_be_followed(expression):
    with pytest.raises(ValueError):
        parse(expression)


def test_a_schedule_with_no_day_in_its_search_never_fires():
    never = Recurrence(day=31, months=frozenset({2}), hour=0)  # there is no 31st of February

    with pytest.raises(ValueError, match=r"^this schedule never fires$"):
        never.next_after(WEDNESDAY)
    with pytest.raises(ValueError, match=r"^this schedule never fires$"):
        never.latest_up_to(WEDNESDAY)


@pytest.mark.parametrize(
    ("expression", "reason"),
    [
        ("Foo *-*-* 10:00", "unknown weekday in 'Foo'"),
        ("Mon..Foo *-*-* 10:00", "unknown weekday in 'Mon..Foo'"),
        ("Mon,Foo *-*-* 10:00", "unknown weekday in 'Mon,Foo'"),
        ("*-*-* 25:00", "not a time of day: '25:00'"),
        ("*-*-* 24:00", "not a time of day: '24:00'"),
        ("*-*-* 10:60", "not a time of day: '10:60'"),
        ("*-*-* 10:00:60", "not a time of day: '10:00:60'"),
        ("*-*-* 1:00", "not a time of day: '1:00'"),
        ("*-*-* 10", "not a time of day: '10'"),
        ("minutely", "only the schedules Delta offers can be followed here: 'minutely'"),
    ],
)
def test_a_refusal_says_what_was_wrong(expression, reason):
    with pytest.raises(ValueError) as caught:
        parse(expression)

    assert str(caught.value) == reason


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("Mon..Wed *-*-* 08:00", {0, 1, 2}),
        ("Fri..Mon *-*-* 08:00", {4, 5, 6, 0}),  # a range that wraps past Sunday
        ("Sat..Tue *-*-* 08:00", {5, 6, 0, 1}),
        ("Sun..Sun *-*-* 08:00", {6}),
        ("Tue,Thu,Sat..Sun *-*-* 08:00", {1, 3, 5, 6}),
        ("mon *-*-* 08:00", {0}),  # not case-sensitive
    ],
)
def test_which_weekdays_a_list_or_a_range_names(expression, expected):
    assert parse(expression).weekdays == frozenset(expected)


@pytest.mark.parametrize("last_moment", ["*-*-* 00:00:00", "*-*-* 23:59:59", "*-*-* 23:00", "*-*-* 00:59"])
def test_the_first_and_last_values_of_a_time_of_day_are_valid(last_moment):
    assert parse(last_moment).next_after(WEDNESDAY) > WEDNESDAY


def test_the_search_reaches_a_whole_year_ahead_and_behind():
    yearly = parse("yearly")

    assert SEARCH_DAYS > 366
    assert yearly.next_after(datetime(2026, 1, 1, 0, 0, 0)) == datetime(2027, 1, 1, 0, 0)
    assert yearly.latest_up_to(datetime(2026, 12, 31, 23, 59, 59)) == datetime(2026, 1, 1, 0, 0)
