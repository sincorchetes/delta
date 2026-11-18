from delta.ui.job_tracker import JobTracker


def tracker_with_results():
    results, tracker = [], JobTracker()
    tracker.begin(lambda ok, message: results.append((ok, message)))
    return tracker, results


def test_the_result_is_reported_when_the_signal_follows_the_reply():
    tracker, results = tracker_with_results()
    tracker.on_started("job1", None)
    tracker.on_finished("job1", True, "/home/u/a (restored)")
    assert results == [(True, "/home/u/a (restored)")] and not tracker.busy


def test_a_signal_that_beats_the_reply_is_not_lost():
    tracker, results = tracker_with_results()
    tracker.on_finished("job1", True, "done")
    assert results == []
    tracker.on_started("job1", None)
    assert results == [(True, "done")]


def test_a_failed_start_is_reported_once_and_ends_the_wait():
    tracker, results = tracker_with_results()
    tracker.on_started(None, "another job is already running")
    tracker.on_finished("x", True, "late")
    assert results == [(False, "another job is already running")] and not tracker.busy


def test_other_jobs_finishing_are_ignored():
    tracker, results = tracker_with_results()
    tracker.on_started("mine", None)
    tracker.on_finished("someone-elses", False, "boom")
    assert results == [] and tracker.busy
    tracker.on_finished("mine", True, "ok")
    assert results == [(True, "ok")]


def test_nothing_happens_when_no_job_is_awaited():
    tracker = JobTracker()
    tracker.on_started("job", None)
    tracker.on_finished("job", True, "x")
    assert not tracker.busy


def test_an_early_result_of_a_previous_wait_does_not_leak_into_the_next():
    tracker, results = tracker_with_results()
    tracker.on_finished("old", False, "stale")
    tracker.on_started("old", None)
    tracker.begin(lambda ok, message: results.append((ok, message)))
    tracker.on_started("new", None)
    tracker.on_finished("new", True, "fresh")
    assert results[-1] == (True, "fresh")
