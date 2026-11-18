from delta.daemon.main import APPLICATION_ID, DeltaDaemon


def test_daemon_can_be_constructed():
    """Regression: entry-point wiring must at least build (it once used a missing enum)."""
    daemon = DeltaDaemon()
    assert daemon._app.get_application_id() == APPLICATION_ID


def test_application_id_is_a_valid_gio_id():
    from gi.repository import Gio

    assert Gio.Application.id_is_valid(APPLICATION_ID)
