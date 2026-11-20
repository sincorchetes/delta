"""Properties that must hold for any input, not for the handful an example thought of."""

import json
import posixpath
from datetime import datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from delta.domain.errors import EngineError, InvalidPath
from delta.domain.paths import validate_in_home, validate_restore
from delta.domain.recurrence import WEEKDAYS, Recurrence, parse
from delta.infrastructure.borg_parsing import (
    log_messages,
    parse_folder_listing,
    parse_folder_search,
    parse_folder_tree,
    parse_progress,
    parse_snapshots,
)

CHECKED = settings(max_examples=150, deadline=None)
HOME = "/home/u"

# --- paths: nothing that escapes the home folder gets through ----------------------------------------

segments = st.one_of(st.text(alphabet="ab._ -ñ", min_size=1, max_size=4), st.sampled_from(["", ".", ".."]))
any_path = st.builds(lambda parts, absolute: ("/" if absolute else "") + "/".join(parts), st.lists(segments, max_size=7), st.booleans())
inside = st.lists(st.text(alphabet="ab._ -ñ", min_size=1, max_size=4).filter(lambda s: s != ".."), max_size=5)


@CHECKED
@given(any_path)
def test_a_path_that_is_accepted_is_absolute_normal_and_inside_the_home_folder(path):
    try:
        result = validate_in_home(path, HOME)
    except InvalidPath:
        return

    assert posixpath.isabs(result) and ".." not in result.split("/")
    assert result == HOME or result.startswith(HOME + "/")
    assert posixpath.normpath(result) == result
    assert validate_in_home(result, HOME) == result


@CHECKED
@given(any_path)
def test_a_path_with_a_parent_reference_is_never_accepted(path):
    if ".." in path.split("/"):
        with pytest.raises(InvalidPath):
            validate_in_home(path, HOME)


@CHECKED
@given(inside)
def test_what_is_written_inside_the_home_folder_is_accepted(parts):
    path = "/".join([HOME, *parts])

    assert validate_in_home(path, HOME) == posixpath.normpath(path)


@CHECKED
@given(any_path, any_path)
def test_a_restore_is_accepted_only_when_both_ends_are(source, target):
    try:
        validate_restore(source, target, HOME)
    except InvalidPath:
        return

    assert validate_in_home(source, HOME) and validate_in_home(target, HOME)


# --- what Borg says: whatever it is, it is read or refused with the error that has a name ------------

names = st.text(alphabet="abAB c[*.-ñ", min_size=1, max_size=3)
moments = st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1))
BASE = "home/u/docs"


def listing(files):
    """`borg list --json-lines` of these files and the folders above them."""
    lines, folders = [], set()
    for parts, size, mtime in files:
        for depth in range(1, len(parts)):
            folders.add("/".join(parts[:depth]))
        lines.append({"path": "/".join([BASE, *parts]), "type": "-", "size": size, "mtime": mtime.isoformat()})
    lines += [{"path": f"{BASE}/{folder}", "type": "d", "size": 0, "mtime": "2026-01-01T00:00:00"} for folder in sorted(folders)]
    return "\n".join(json.dumps(line) for line in lines)


unique_files = st.dictionaries(
    st.lists(names, min_size=1, max_size=3).map(tuple), st.tuples(st.integers(0, 10**6), moments), max_size=8
).filter(lambda files: not any(a != b and b[: len(a)] == a for a in files for b in files))  # a file is not also a folder


def as_files(files):
    return [(parts, size, mtime) for parts, (size, mtime) in files.items()]


@CHECKED
@given(unique_files)
def test_the_listing_of_a_folder_names_each_child_once_and_adds_up_what_is_below(files):
    entries = parse_folder_listing(listing(as_files(files)), f"/{BASE}")

    assert sorted(entry.name for entry in entries) == sorted({parts[0] for parts in files})
    assert all("/" not in entry.name for entry in entries)
    assert sum(entry.size for entry in entries) == sum(size for size, _mtime in files.values())
    for entry in entries:
        assert entry.is_dir == any(len(parts) > 1 and parts[0] == entry.name for parts in files)


@CHECKED
@given(unique_files)
def test_the_tree_of_a_folder_has_every_file_with_its_size(files):
    tree = {entry.name: entry for entry in parse_folder_tree(listing(as_files(files)), f"/{BASE}")}

    for parts, (size, _mtime) in files.items():
        assert tree["/".join(parts)].size == size and not tree["/".join(parts)].is_dir


@CHECKED
@given(unique_files, st.text(alphabet="abAB c[*", max_size=3), st.integers(1, 5))
def test_a_search_returns_only_what_matches_and_never_more_than_the_limit(files, query, limit):
    hits = parse_folder_search(listing(as_files(files)), f"/{BASE}", query, limit)

    needle = query.strip().casefold()
    assert len(hits) <= limit
    assert all(needle in hit.name.rpartition("/")[2].casefold() for hit in hits)
    everything = parse_folder_search(listing(as_files(files)), f"/{BASE}", query, 10**6)
    assert hits == everything[:limit]


@CHECKED
@given(st.text())
def test_any_text_is_read_as_snapshots_or_refused_with_the_error_of_the_engine(text):
    try:
        parse_snapshots(text)
    except EngineError:
        pass


@CHECKED
@given(st.text())
def test_any_line_of_progress_is_an_event_or_nothing(line):
    parse_progress(line)


@CHECKED
@given(st.text())
def test_any_text_of_errors_is_flattened_to_text(text):
    assert isinstance(log_messages(text), str)


# --- the schedule: when it says it fires is when it fires -------------------------------------------

weekday_sets = st.none() | st.sets(st.integers(0, 6), min_size=1).map(frozenset)
month_sets = st.none() | st.sets(st.integers(1, 12), min_size=1).map(frozenset)
recurrences = st.one_of(
    st.builds(Recurrence, minute=st.integers(0, 59), second=st.integers(0, 59), hour=st.none() | st.integers(0, 23), weekdays=weekday_sets),
    st.builds(
        Recurrence, minute=st.integers(0, 59), second=st.integers(0, 59), hour=st.none() | st.integers(0, 23),
        months=month_sets, day=st.none() | st.integers(1, 28),
    ),
)


@CHECKED
@given(recurrences, moments)
def test_the_next_moment_is_after_and_is_one_the_schedule_fires_at(recurrence, moment):
    following = recurrence.next_after(moment)

    assert following > moment
    assert recurrence._matches_day(following)
    assert (following.minute, following.second) == (recurrence.minute, recurrence.second)
    assert recurrence.hour is None or following.hour == recurrence.hour


@CHECKED
@given(recurrences, moments)
def test_nothing_that_fires_is_skipped_between_a_moment_and_the_next(recurrence, moment):
    following = recurrence.next_after(moment)

    assert recurrence.latest_up_to(following) == following
    assert recurrence.latest_up_to(following - timedelta(seconds=1)) <= moment


@CHECKED
@given(recurrences, moments)
def test_the_latest_moment_is_not_after_and_the_one_that_follows_it_is_after(recurrence, moment):
    latest = recurrence.latest_up_to(moment)

    assert latest <= moment < recurrence.next_after(latest) or recurrence.next_after(latest) > moment
    assert recurrence.next_after(latest) > latest


@CHECKED
@given(st.text())
def test_any_expression_is_a_schedule_or_a_value_error(expression):
    try:
        assert isinstance(parse(expression), Recurrence)
    except ValueError:
        pass


@CHECKED
@given(st.lists(st.sampled_from(sorted(WEEKDAYS)), min_size=1, max_size=4, unique=True), st.integers(0, 23), st.integers(0, 59), st.integers(0, 59))
def test_a_schedule_written_the_way_delta_offers_it_is_read_back(days, hour, minute, second):
    expression = f"{','.join(day.capitalize() for day in days)} *-*-* {hour:02}:{minute:02}:{second:02}"

    assert parse(expression) == Recurrence(minute, second, hour, frozenset(WEEKDAYS[day] for day in days))
