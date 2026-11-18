import pytest

pytest.importorskip("gi")

from delta.ui.folder_data import FolderData


class FakeClient:
    """Records each question and lets the test answer it whenever it likes, in any order."""

    def __init__(self):
        self.asked = []  # (kind, snapshot, folder, extra)
        self.replies = {}  # kind -> [reply, ...] oldest first

    def _record(self, kind, snapshot, folder, extra, reply):
        self.asked.append((kind, snapshot, folder, extra))
        self.replies.setdefault(kind, []).append(reply)

    def list_folder(self, snapshot, folder, reply):
        self._record("listing", snapshot, folder, None, reply)

    def search_folder(self, snapshot, folder, query, reply):
        self._record("search", snapshot, folder, query, reply)

    def list_changed(self, snapshot, folder, reply):
        self._record("changes", snapshot, folder, None, reply)

    def answer(self, kind, rows=None, error=None, which=-1):
        self.replies[kind][which](rows, error)

    def count(self, kind):
        return sum(1 for item in self.asked if item[0] == kind)


class Run:
    def __init__(self):
        self.client, self.ready, self.errors = FakeClient(), [], []
        self.data = FolderData(self.client, lambda: self.ready.append(1), lambda *e: self.errors.append(e))


ROW = {"name": "a.txt", "is_dir": False, "size": 1, "mtime": 0}


def test_opening_asks_for_the_folder_and_nothing_is_ready_until_it_arrives():
    run = Run()
    run.data.open("snap", "/home/u/Pictures")

    assert run.client.asked == [("listing", "snap", "/home/u/Pictures", None)]
    assert run.data.loading is True and run.data.listing == [] and run.ready == []


def test_when_the_folder_arrives_it_is_kept_and_announced():
    run = Run()
    run.data.open("snap", "/home/u/Pictures")

    run.client.answer("listing", [ROW])

    assert run.data.listing == [ROW] and run.data.loading is False and run.ready == [1]


def test_the_comparison_with_the_disk_is_asked_in_the_background_once_the_folder_is_there():
    run = Run()
    run.data.open("snap", "/home/u/Pictures")
    assert run.client.count("changes") == 0  # not before: the list comes first

    run.client.answer("listing", [ROW])

    assert run.client.asked[-1] == ("changes", "snap", "/home/u/Pictures", None)
    assert run.data.asking_changes is True


def test_the_changes_are_kept_when_they_arrive():
    run = Run()
    run.data.open("snap", "/f")
    run.client.answer("listing", [ROW])

    run.client.answer("changes", [{"name": "x/y.txt"}])

    assert run.data.changes == [{"name": "x/y.txt"}] and run.data.asking_changes is False
    assert run.ready == [1, 1]  # the folder, then the marks


def test_asking_for_changes_twice_while_one_is_on_its_way_asks_once():
    run = Run()
    run.data.open("snap", "/f")
    run.client.answer("listing", [ROW])

    run.data.ensure_changes()
    run.data.ensure_changes()

    assert run.client.count("changes") == 1


def test_ensuring_changes_that_are_known_asks_nothing():
    run = Run()
    run.data.open("snap", "/f")
    run.client.answer("listing", [ROW])
    run.client.answer("changes", [])

    run.data.ensure_changes()

    assert run.client.count("changes") == 1


def test_refreshing_keeps_the_old_changes_until_the_new_ones_arrive():
    run = Run()
    run.data.open("snap", "/f")
    run.client.answer("listing", [ROW])
    run.client.answer("changes", [{"name": "old"}])

    run.data.refresh_changes()

    assert run.data.changes == [{"name": "old"}]  # no blink: the marks stay meanwhile
    run.client.answer("changes", [{"name": "new"}])
    assert run.data.changes == [{"name": "new"}]


def test_an_answer_for_a_folder_we_already_left_is_dropped():
    run = Run()
    run.data.open("snap", "/home/u/A")
    first = run.client.replies["listing"][0]

    run.data.enter("/home/u/B")
    first([{"name": "from-A"}], None)  # A answers late

    assert run.data.listing == [] and run.data.loading is True and run.ready == []


def test_leaving_a_folder_drops_its_changes_and_search_too():
    run = Run()
    run.data.open("snap", "/home/u/A")
    run.client.answer("listing", [ROW])
    run.data.search("png")
    late_changes, late_search = run.client.replies["changes"][0], run.client.replies["search"][0]

    run.data.enter("/home/u/B")
    late_changes([{"name": "A-change"}], None)
    late_search([{"name": "A-hit"}], None)

    assert run.data.changes is None and run.data.hits is None
    assert run.data.asking_changes is False


def test_entering_a_folder_forgets_what_was_known_about_the_last():
    run = Run()
    run.data.open("snap", "/home/u/A")
    run.client.answer("listing", [ROW])
    run.client.answer("changes", [{"name": "x/y"}])

    run.data.enter("/home/u/B")

    assert run.data.changes is None and run.data.hits is None


def test_a_search_is_for_the_folder_being_looked_at_and_its_answer_is_kept():
    run = Run()
    run.data.open("snap", "/home/u/A")
    run.client.answer("listing", [ROW])

    run.data.search("png")
    run.client.answer("search", [{"name": "p.png"}])

    assert run.client.asked[-1] == ("search", "snap", "/home/u/A", "png")
    assert run.data.hits == [{"name": "p.png"}]


def test_a_newer_search_replaces_an_older_one_that_arrives_late():
    run = Run()
    run.data.open("snap", "/f")
    run.data.search("p")
    run.data.search("pn")

    run.client.answer("search", [{"name": "slow-answer-to-p"}], which=0)
    assert run.data.hits is None  # the first question is no longer the one being asked
    run.client.answer("search", [{"name": "answer-to-pn"}], which=1)

    assert run.data.hits == [{"name": "answer-to-pn"}]


def test_clearing_the_search_drops_one_still_on_its_way():
    run = Run()
    run.data.open("snap", "/f")
    run.data.search("png")

    run.data.clear_search()
    run.client.answer("search", [{"name": "late"}])

    assert run.data.hits is None


def test_a_failure_is_reported_with_what_was_being_asked():
    run = Run()
    run.data.open("snap", "/f")

    run.client.answer("listing", error="boom")

    assert run.errors == [("listing", "Could not read this folder", "boom")]
    assert run.data.loading is False and run.ready == []


def test_a_failed_comparison_is_reported_as_such_and_can_be_asked_again():
    run = Run()
    run.data.open("snap", "/f")
    run.client.answer("listing", [ROW])

    run.client.answer("changes", error="no disk")
    run.data.ensure_changes()

    assert run.errors[0][0] == "changes" and run.data.changes is None
    assert run.client.count("changes") == 2


def test_a_failed_search_is_reported_as_a_search():
    run = Run()
    run.data.open("snap", "/f")
    run.data.search("x")
    run.client.answer("search", error="boom")
    assert run.errors == [("search", "The search failed", "boom")]


def test_the_root_stays_where_it_was_opened_while_the_folder_moves():
    run = Run()
    run.data.open("snap", "/home/u/Pictures")
    run.data.enter("/home/u/Pictures/trip")

    assert run.data.root == "/home/u/Pictures" and run.data.folder == "/home/u/Pictures/trip"
