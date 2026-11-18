import json
import threading

from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner
from delta.infrastructure.listing_cache import ListingCache


def listing(*paths):
    return "\n".join(json.dumps({"path": p, "type": "-", "size": 1, "mtime": "2026-01-01T00:00:00.000000"}) for p in paths)


def paths_of(text):
    return [json.loads(line)["path"] for line in text.splitlines()]


TREE = listing(
    "home/u/Pictures",
    "home/u/Pictures/a.png",
    "home/u/Pictures/trip",
    "home/u/Pictures/trip/1.jpg",
    "home/u/Pictures/trip/raw/2.nef",
    "home/u/Pictures2/b.png",  # a sibling that only shares the start of the name
)


def test_what_was_put_comes_back_exactly():
    cache = ListingCache()
    cache.put("/r", "s1", "home/u/Pictures", TREE)
    assert cache.get("/r", "s1", "home/u/Pictures") == TREE


def test_a_path_never_seen_and_not_inside_anything_seen_is_a_miss():
    cache = ListingCache()
    cache.put("/r", "s1", "home/u/Pictures", TREE)
    assert cache.get("/r", "s1", "home/u/Documents") is None


def test_a_folder_inside_a_listed_one_is_cut_out_of_it():
    cache = ListingCache()
    cache.put("/r", "s1", "home/u/Pictures", TREE)

    assert paths_of(cache.get("/r", "s1", "home/u/Pictures/trip")) == [
        "home/u/Pictures/trip",
        "home/u/Pictures/trip/1.jpg",
        "home/u/Pictures/trip/raw/2.nef",
    ]


def test_a_sibling_with_a_longer_name_is_never_mistaken_for_being_inside():
    cache = ListingCache()
    cache.put("/r", "s1", "home/u/Pictures", TREE)

    assert cache.get("/r", "s1", "home/u/Pictures2") is None  # not below Pictures: borg must say


def test_cutting_a_folder_out_of_a_wider_listing_leaves_its_siblings_behind():
    cache = ListingCache()
    cache.put("/r", "s1", "home/u", TREE)  # TREE also holds Pictures2, a sibling of Pictures

    cut = paths_of(cache.get("/r", "s1", "home/u/Pictures"))

    assert "home/u/Pictures2/b.png" not in cut and "home/u/Pictures/a.png" in cut


def test_a_path_whose_name_starts_the_same_is_not_cut_in():
    cache = ListingCache()
    cache.put("/r", "s1", "home/u", listing("home/u", "home/u/ab/x", "home/u/a/y"))
    assert paths_of(cache.get("/r", "s1", "home/u/a")) == ["home/u/a/y"]


def test_the_closest_listed_ancestor_is_the_one_used():
    cache = ListingCache()
    cache.put("/r", "s1", "home/u", listing("home/u/Pictures/x", "home/u/OLD"))
    cache.put("/r", "s1", "home/u/Pictures", listing("home/u/Pictures", "home/u/Pictures/x", "home/u/Pictures/y/z"))

    assert paths_of(cache.get("/r", "s1", "home/u/Pictures/y")) == ["home/u/Pictures/y/z"]


def test_a_derived_answer_is_remembered_and_can_be_cut_again():
    cache = ListingCache()
    cache.put("/r", "s1", "home/u/Pictures", TREE)
    cache.get("/r", "s1", "home/u/Pictures/trip")

    assert paths_of(cache.get("/r", "s1", "home/u/Pictures/trip/raw")) == ["home/u/Pictures/trip/raw/2.nef"]


def test_nothing_is_shared_between_snapshots_or_repositories():
    cache = ListingCache()
    cache.put("/r", "s1", "home/u/Pictures", TREE)

    assert cache.get("/r", "s2", "home/u/Pictures") is None
    assert cache.get("/other", "s1", "home/u/Pictures") is None
    assert cache.get("/r", "s2", "home/u/Pictures/trip") is None


def test_a_path_that_is_not_in_the_listing_is_remembered_as_empty_not_as_unknown():
    cache = ListingCache()
    cache.put("/r", "s1", "home/u/Pictures", TREE)

    assert cache.get("/r", "s1", "home/u/Pictures/never") == ""  # known: not there, so no borg call


def test_the_least_recently_used_answers_go_first_when_the_memory_is_full():
    cache = ListingCache(max_bytes=250)
    cache.put("/r", "s1", "a", "x" * 100)
    cache.put("/r", "s1", "b", "y" * 100)
    cache.get("/r", "s1", "a")  # a is now the freshest
    cache.put("/r", "s1", "c", "z" * 100)

    assert cache.get("/r", "s1", "a") is not None
    assert cache.get("/r", "s1", "c") is not None
    assert cache.get("/r", "s1", "b") is None


def test_one_answer_bigger_than_the_whole_memory_is_still_kept_until_the_next():
    cache = ListingCache(max_bytes=10)
    cache.put("/r", "s1", "big", "x" * 100)
    assert cache.get("/r", "s1", "big") == "x" * 100


def test_replacing_an_answer_does_not_leak_its_size():
    cache = ListingCache(max_bytes=250)
    for _ in range(50):
        cache.put("/r", "s1", "a", "x" * 100)
    cache.put("/r", "s1", "b", "y" * 100)
    assert cache.get("/r", "s1", "a") is not None and cache.get("/r", "s1", "b") is not None


def test_many_threads_can_use_it_at_once():
    cache = ListingCache()
    cache.put("/r", "s1", "home/u/Pictures", TREE)
    failures = []

    def work(n):
        try:
            for _ in range(200):
                if cache.get("/r", "s1", "home/u/Pictures/trip") is None:
                    failures.append("an entry that was put in was not found")  # not an assert: the except below would swallow it
                cache.put("/r", f"s{n}", "p", "x")
        except Exception as err:  # noqa: BLE001 - the test reports any failure of any thread
            failures.append(err)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []


# --- the engine asks borg once -----------------------------------------------------------------


class CountingRunner(BorgRunner):
    """A BorgRunner whose borg is a counter that answers with a fixed listing."""

    def __init__(self, answer):
        super().__init__()
        self.answer, self.calls = answer, []

    def _run(self, argv, repo, cwd=None, on_progress=None):
        self.calls.append(argv)
        return self.answer


REPO = Repository("/r")
FULL = listing(
    "home/u/Pictures",
    "home/u/Pictures/a.png",
    "home/u/Pictures/trip",
    "home/u/Pictures/trip/1.jpg",
)


def test_the_same_question_twice_asks_borg_once():
    runner = CountingRunner(FULL)
    runner.list_folder(REPO, "s1", "/home/u/Pictures")
    runner.list_folder(REPO, "s1", "/home/u/Pictures")
    assert len(runner.calls) == 1


def test_the_listing_the_folder_view_asked_for_also_serves_the_comparison_and_the_search():
    runner = CountingRunner(FULL)
    runner.list_folder(REPO, "s1", "/home/u/Pictures")
    runner.list_tree(REPO, "s1", "/home/u/Pictures")
    runner.search_folder(REPO, "s1", "/home/u/Pictures", "png", 10)
    assert len(runner.calls) == 1


def test_going_into_a_subfolder_asks_borg_nothing_more():
    runner = CountingRunner(FULL)
    runner.list_folder(REPO, "s1", "/home/u/Pictures")

    inside = runner.list_folder(REPO, "s1", "/home/u/Pictures/trip")

    assert [e.name for e in inside] == ["1.jpg"]
    assert len(runner.calls) == 1


def test_another_snapshot_does_ask_borg_again():
    runner = CountingRunner(FULL)
    runner.list_folder(REPO, "s1", "/home/u/Pictures")
    runner.list_folder(REPO, "s2", "/home/u/Pictures")
    assert len(runner.calls) == 2
