"""The history window, the restore-deleted flow and changing the destination, as real widgets."""

from types import SimpleNamespace
import pytest
from gtk_helpers import of_type
from gi.repository import GObject, Gtk
from delta.i18n import _
from delta.ui import history_window
from delta.ui.history_window import HistoryWindow, Row, _column
from delta.ui import preferences_dialog
from delta.ui.restore_deleted import confirm_replace
from panes_and_dialogs_support import preferences, rows
from panes_and_dialogs_support import restoring  # noqa: F401  (fixtures)


def test_the_history_waits_for_the_daemon_then_lists_the_backups(client):
    window = HistoryWindow(None, client)
    assert window._stack.get_visible_child_name() == "loading"

    client.answer(
        "list_snapshots",
        [{"id": "1", "name": "first", "time": 1_700_000_000}, {"id": "2", "name": "second", "time": 1_700_100_000}],
        None,
    )

    assert window._stack.get_visible_child_name() == "list"
    assert window._store.get_n_items() == 2 and window._count.get_text() == "2 backups"
    assert window._store.get_item(0).name == "second"  # newest first


def test_the_history_says_why_old_backups_are_not_in_it(client):
    window = HistoryWindow(None, client)
    listing = window._stack.get_child_by_name("list")
    notes = []
    child = listing.get_first_child()
    while child is not None:
        notes.append(child)
        child = child.get_next_sibling()

    assert [w.get_label() for w in notes if isinstance(w, Gtk.Label) and "removed" in w.get_label()] == [
        "Older backups are removed to save space. Change how many are kept in the preferences."
    ]


def test_an_empty_repository_says_there_are_no_backups_yet(client):
    window = HistoryWindow(None, client)

    client.answer("list_snapshots", [], None)

    assert window._stack.get_visible_child_name() == "empty" and window._empty.get_title() == "No backups yet"


def test_a_daemon_error_is_explained(client):
    window = HistoryWindow(None, client)

    client.answer("list_snapshots", None, "the repository is locked")

    assert window._empty.get_title() == "Could not read the backups"
    assert "locked" in window._empty.get_description()


def test_the_table_cells_show_the_chosen_attribute(monkeypatch):
    handlers = {}

    def recording_connect(self, name, handler):
        handlers[name] = handler
        return GObject.Object.connect(self, name, handler)

    monkeypatch.setattr(Gtk.SignalListItemFactory, "connect", recording_connect)
    column = _column("Date", "when")
    cell = {}
    item = SimpleNamespace(
        set_child=lambda child: cell.update(child=child),
        get_child=lambda: cell["child"],
        get_item=lambda: Row(name="n", when="2026-01-01  10:00", ago="2 days ago"),
    )

    handlers["setup"](column.get_factory(), item)
    handlers["bind"](column.get_factory(), item)

    assert cell["child"].get_text() == "2026-01-01  10:00" and column.get_title() == "Date"


def test_the_history_module_builds_rows_from_history_rows():
    row = Row.of(SimpleNamespace(name="a", when="b", ago="c"))

    assert (row.name, row.when, row.ago) == ("a", "b", "c") and history_window.Row is Row


def test_nothing_deleted_is_said_and_nothing_is_asked(restoring, client, dialogs):
    restoring.flow.start("s", "/home/u/docs")
    client.answer("list_deleted", [], None)

    assert len(restoring.toasts) == 1 and dialogs.items == []


def test_a_daemon_error_while_looking_is_reported(restoring, client, dialogs):
    restoring.flow.start("s", "/home/u/docs")
    client.answer("list_deleted", None, "locked")

    assert len(restoring.toasts) == 1 and dialogs.items == []


def test_the_user_confirms_and_the_whole_folder_comes_back_in_one_job(restoring, client, dialogs):
    restoring.flow.start("s", "/home/u/docs")
    client.answer("list_deleted", rows(3), None)
    assert "3" in dialogs.items[-1][0].get_body()

    dialogs.respond("restore")
    assert client.asked("restore_deleted") == [("s", "/home/u/docs")] and restoring.tracker.busy

    restoring.tracker.on_started("job", None)
    restoring.tracker.on_finished("job", True, "3")

    assert restoring.done == 1 and len(restoring.toasts) == 1 and not restoring.tracker.busy


def test_cancelling_restores_nothing(restoring, client, dialogs):
    restoring.flow.start("s", "/home/u/docs")
    client.answer("list_deleted", rows(2), None)

    dialogs.respond("cancel")

    assert client.asked("restore_deleted") == [] and not restoring.tracker.busy


def test_while_a_job_runs_nothing_new_is_started(restoring, client, dialogs):
    restoring.tracker.begin(lambda ok, message: None)

    restoring.flow.start("s", "/home/u/docs")

    assert client.asked("list_deleted") == []


def test_answering_yes_after_another_job_began_does_nothing(restoring, client, dialogs):
    restoring.flow.start("s", "/home/u/docs")
    client.answer("list_deleted", rows(1), None)
    restoring.tracker.begin(lambda ok, message: None)

    dialogs.respond("restore")

    assert client.asked("restore_deleted") == []


@pytest.mark.parametrize(
    ("count", "heading"), [(1, "Replace the current version?"), (3, "Replace 3 current versions?")]
)
def test_replacing_asks_first_and_only_a_yes_goes_ahead(dialogs, count, heading):
    yes = []

    confirm_replace(None, count, lambda: yes.append(True))
    assert dialogs.items[-1][0].get_heading() == heading
    dialogs.respond("cancel")
    dialogs.respond("replace")

    assert yes == [True]


def test_the_destination_can_be_changed_when_there_is_a_daemon_to_ask(monkeypatch):
    opened = []

    class Wizard:
        def __init__(self, parent, client, settings, on_done, change=False):
            opened.append((client, settings, change, on_done))

        def present(self):
            opened.append("shown")

    monkeypatch.setattr(preferences_dialog, "SetupWizard", Wizard)
    dialog, settings, _toasts = preferences(client="client")
    (button,) = [b for b in of_type(dialog.get_visible_page(), Gtk.Button) if b.get_label() == _("Change…")]

    button.emit("clicked")

    assert opened[0][:3] == ("client", settings, True) and opened[1] == "shown"
    settings.values["repository-location"] = "/media/other/delta"
    opened[0][3]()
    assert dialog._location_row.get_subtitle() == "/media/other/delta"


def test_without_a_daemon_or_a_destination_there_is_nothing_to_change():
    for dialog in (preferences()[0], preferences(client="client", **{"repository-location": ""})[0]):
        assert not [b for b in of_type(dialog.get_visible_page(), Gtk.Button) if b.get_label() == _("Change…")]
