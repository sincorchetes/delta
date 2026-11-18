from delta.daemon.config_reloader import SCHEDULE_KEYS, SERVICE_KEYS


def test_changing_the_skipped_paths_rebuilds_the_services_between_jobs():
    assert "excluded-paths" in SERVICE_KEYS


def test_the_schedule_is_applied_at_once_not_between_jobs():
    assert "schedule" in SCHEDULE_KEYS and "schedule" not in SERVICE_KEYS
