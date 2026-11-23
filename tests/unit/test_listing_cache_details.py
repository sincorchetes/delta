"""What the cache of listings keeps, drops, derives and from where."""

import json

from delta.infrastructure.listing_cache import ListingCache, _cut


def entry(path):
    return json.dumps({"path": path, "type": "-", "size": 1})


def listing(*paths):
    return "\n".join(entry(path) for path in paths)


def test_a_path_that_starts_with_the_letters_of_a_trim_is_cut_by_what_it_says_and_not_by_its_letters():
    text = listing("XXdocs", "XXdocs/a", "other")

    assert _cut(text, "/XXdocs") == listing("XXdocs", "XXdocs/a")


def test_what_exactly_fills_the_cache_stays():
    cache = ListingCache(max_bytes=10)
    cache.put("r", "s", "/a", "aaaaa")
    cache.put("r", "s", "/b", "bbbbb")

    assert cache.get("r", "s", "/a") == "aaaaa" and cache.get("r", "s", "/b") == "bbbbb"
    assert cache._bytes == 10


def test_what_does_not_fit_is_dropped_oldest_first_and_the_count_follows():
    cache = ListingCache(max_bytes=10)
    cache.put("r", "s", "/a", "a" * 6)
    cache.put("r", "s", "/b", "b" * 20)  # too big with the other: the oldest goes, and the new one stays even if alone

    assert cache.get("r", "s", "/a") is None and cache.get("r", "s", "/b") == "b" * 20
    assert cache._bytes == 20

    cache.put("r", "s", "/c", "c" * 5)

    assert cache.get("r", "s", "/b") is None and cache.get("r", "s", "/c") == "c" * 5
    assert cache._bytes == 5


def test_a_new_cache_holds_nothing():
    assert ListingCache()._bytes == 0


def test_a_listing_derived_from_an_ancestor_is_kept_for_the_next_time():
    cache = ListingCache()
    cache.put("r", "s", "/a", listing("a", "a/b", "a/b/c"))

    derived = cache.get("r", "s", "/a/b")

    assert derived == listing("a/b", "a/b/c")
    assert ("r", "s", "/a/b") in cache._items


def test_an_ancestor_that_was_given_with_a_slash_at_the_end_still_covers_what_is_below_it():
    cache = ListingCache()
    cache.put("r", "s", "/a/", listing("a", "a/b"))

    assert cache.get("r", "s", "/a/b") == listing("a/b")


def test_a_folder_that_only_ends_with_the_letters_of_a_trim_is_not_an_ancestor_of_another():
    cache = ListingCache()
    cache.put("r", "s", "/aX", listing("aX", "aX/b"))

    assert cache.get("r", "s", "/a/b") is None


def test_what_belongs_to_another_repository_or_snapshot_is_not_looked_in_and_does_not_stop_the_search():
    cache = ListingCache()
    cache.put("other", "s", "/", listing("a", "a/b"))
    cache.put("r", "another", "/", listing("a", "a/b"))
    cache.put("r", "s", "/a", listing("a", "a/b"))

    assert cache.get("r", "s", "/a/b") == listing("a/b")


def test_the_closest_ancestor_is_the_one_used():
    cache = ListingCache()
    cache.put("r", "s", "/a", listing("a", "a/b", "a/b/c", "a/z"))
    cache.put("r", "s", "/a/b", listing("a/b", "a/b/c"))

    assert cache.get("r", "s", "/a/b/c") == listing("a/b/c")
    assert ("r", "s", "/a/b/c") in cache._items
