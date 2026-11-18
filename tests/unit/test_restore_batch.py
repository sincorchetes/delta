from delta.ui.job_tracker import JobTracker
from delta.ui.restore_batch import RestoreBatch, deleted_confirm_text, deleted_result_text, summary


class FakeClient:
    def __init__(self):
        self.requests = []

    def restore_as_copy(self, snapshot, path, reply):
        self.requests.append(("copy", snapshot, path))

    def restore_replace(self, snapshot, path, reply):
        self.requests.append(("replace", snapshot, path))


class Run:
    """A batch wired to a real tracker, with the daemon's answers played by hand."""

    def __init__(self, items):
        self.client, self.tracker, self.done = FakeClient(), JobTracker(), []
        self.batch = RestoreBatch(self.client, self.tracker, "snap", items, lambda *r: self.done.append(r))
        self.jobs = 0

    def answer(self, ok=True, message="/home/u/out"):
        self.jobs += 1
        job = f"j{self.jobs}"
        self.tracker.on_started(job, None)
        self.tracker.on_finished(job, ok, message)


def test_items_are_restored_one_after_another_never_together():
    run = Run([("/home/u/a", False), ("/home/u/b", False), ("/home/u/c", False)])
    run.batch.start()

    assert run.client.requests == [("copy", "snap", "/home/u/a")]
    run.answer(message="/home/u/a (restored)")
    assert run.client.requests[-1] == ("copy", "snap", "/home/u/b")
    run.answer(message="/home/u/b (restored)")
    run.answer(message="/home/u/c (restored)")

    assert [r[2] for r in run.client.requests] == ["/home/u/a", "/home/u/b", "/home/u/c"]
    restored, failures, done = run.done[0]
    assert restored == ["/home/u/a (restored)", "/home/u/b (restored)", "/home/u/c (restored)"]
    assert failures == [] and done == ["/home/u/a", "/home/u/b", "/home/u/c"]


def test_each_item_chooses_how_it_comes_back():
    """A deleted item goes back under its own name; one that still exists is restored beside it."""
    run = Run([("/home/u/deleted.txt", True), ("/home/u/there.txt", False)])
    run.batch.start()
    run.answer()
    run.answer()
    assert run.client.requests == [
        ("replace", "snap", "/home/u/deleted.txt"),
        ("copy", "snap", "/home/u/there.txt"),
    ]


def test_the_tracker_stays_busy_until_the_last_one_ends():
    run = Run([("/home/u/a", False), ("/home/u/b", False)])
    run.batch.start()
    run.answer()
    assert run.tracker.busy  # b is next: the window must not let anything else start
    run.answer()
    assert not run.tracker.busy


def test_a_failure_does_not_stop_the_rest_and_is_not_counted_as_done():
    run = Run([("/home/u/a", False), ("/home/u/b", False)])
    run.batch.start()

    run.answer(ok=False, message="boom")
    run.answer(message="/home/u/b (restored)")

    assert run.done == [(["/home/u/b (restored)"], ["boom"], ["/home/u/b"])]


def test_an_empty_batch_finishes_at_once():
    run = Run([])
    run.batch.start()
    assert run.client.requests == [] and run.done == [([], [], [])]


def test_a_start_error_counts_as_a_failure_too():
    run = Run([("/home/u/a", False)])
    run.batch.start()
    run.tracker.on_started(None, "another job is already running")
    assert run.done == [([], ["another job is already running"], [])]


def test_one_item_restored_as_a_copy_is_named():
    assert summary(["/home/u/docs/a (restored 2026-11-12).txt"], [], in_place=False) == "Restored as a (restored 2026-11-12).txt"


def test_one_item_put_back_is_named_without_saying_copy():
    assert summary(["/home/u/docs/a.txt"], [], in_place=True) == "Restored a.txt"


def test_several_items_are_counted():
    assert summary(["/a", "/b", "/c"], [], in_place=False) == "Restored 3 items"


def test_a_single_failure_says_why():
    assert summary([], ["the folder is read-only"], in_place=False) == "the folder is read-only"


def test_a_failure_without_a_reason_still_says_something():
    assert summary([], [""], in_place=False) == "It could not be restored."


def test_everything_failing_says_so():
    assert summary([], ["boom", "boom"], in_place=False) == "None could be restored: boom"


def test_a_mix_says_how_many_of_each():
    assert summary(["/a", "/b"], ["boom"], in_place=False) == "2 restored, 1 not: boom"


def test_the_confirmation_says_how_many_and_how_big_and_that_nothing_existing_is_touched():
    one = deleted_confirm_text(1, "2.4 MB")
    many = deleted_confirm_text(12, "88.0 MB")

    assert one.startswith("1 item (2.4 MB) that was in this folder")
    assert many.startswith("12 items (88.0 MB) that were in this folder")
    assert "Nothing that exists now is touched." in one and "Nothing that exists now is touched." in many


def test_the_result_counts_the_items_that_came_back():
    assert deleted_result_text(True, "1") == "Restored 1 item"
    assert deleted_result_text(True, "7") == "Restored 7 items"


def test_when_nothing_was_missing_any_more_it_says_so_instead_of_claiming_success():
    assert deleted_result_text(True, "0") == "Nothing needed restoring."
    assert deleted_result_text(True, "") == "Nothing needed restoring."


def test_a_failure_gives_its_reason_or_a_fallback():
    assert deleted_result_text(False, "the folder is read-only") == "the folder is read-only"
    assert deleted_result_text(False, "") == "It could not be restored."
