import logging
import os

from delta.daemon.composition import resolve_sources

HOME = "/home/user"


def test_unset_means_the_whole_home_folder():
    assert resolve_sources((), HOME) == (HOME,)


def test_configured_folders_are_used_instead_of_home():
    assert resolve_sources(("/home/user/Pictures", "/srv/data"), HOME) == (
        "/home/user/Pictures",
        "/srv/data",
    )


def test_tilde_is_expanded_and_paths_normalised():
    expanded = os.path.expanduser("~/Documents")
    assert resolve_sources(("~/Documents", "/srv//data/"), HOME) == (expanded, "/srv/data")


def test_duplicates_are_removed_keeping_order():
    assert resolve_sources(("/a", "/b", "/a"), HOME) == ("/a", "/b")


def test_relative_paths_are_dropped_not_widened_to_home(caplog):
    with caplog.at_level(logging.WARNING):
        result = resolve_sources(("Pictures", "/srv/data"), HOME)
    assert result == ("/srv/data",)
    assert "not an absolute path" in caplog.text


def test_only_invalid_entries_yield_no_sources_instead_of_all_of_home():
    assert resolve_sources(("Pictures", "../etc"), HOME) == ()
