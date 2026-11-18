"""Read-only D-Bus questions: slow ones run off the main loop and answer with `aa{sv}`."""

import threading

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib

from delta.application.deleted_service import DeletedService
from delta.application.version_service import VersionService
from delta.daemon.job_calls import ERROR_FAILED, ERROR_INVALID_PATH, ERROR_UNAVAILABLE
from delta.daemon.variants import folder_entry_to_variant, version_to_variant
from delta.domain.errors import DeltaError, InvalidPath
from delta.i18n import _


def run_query(invocation, produce) -> None:
    """Run a slow read-only query off the main loop and reply with `aa{sv}`."""

    def work() -> None:
        try:
            rows = produce()
            GLib.idle_add(invocation.return_value, GLib.Variant("(aa{sv})", (rows,)))
        except InvalidPath as err:
            GLib.idle_add(invocation.return_dbus_error, ERROR_INVALID_PATH, str(err))
        except DeltaError as err:
            GLib.idle_add(invocation.return_dbus_error, ERROR_FAILED, str(err))

    threading.Thread(target=work, daemon=True).start()


def _unavailable(invocation) -> None:
    invocation.return_dbus_error(ERROR_UNAVAILABLE, _("versions are not available"))


def list_versions(versions: VersionService | None, parameters, invocation) -> None:
    if versions is None:
        _unavailable(invocation)
        return
    (path,) = parameters.unpack()
    run_query(invocation, lambda: [version_to_variant(v) for v in versions.list_versions(path)])


def list_folder(versions: VersionService | None, parameters, invocation) -> None:
    if versions is None:
        _unavailable(invocation)
        return
    snapshot, path = parameters.unpack()
    run_query(invocation, lambda: [folder_entry_to_variant(e) for e in versions.list_folder(snapshot, path)])


def list_deleted(deleted: DeletedService | None, parameters, invocation) -> None:
    """What a folder held in a snapshot that is gone now, for the window to show before restoring."""
    if deleted is None:
        _unavailable(invocation)
        return
    snapshot, folder = parameters.unpack()
    run_query(invocation, lambda: [folder_entry_to_variant(e) for e in deleted.find(snapshot, folder)])


def list_changed(deleted: DeletedService | None, parameters, invocation) -> None:
    """Everything below a folder that is not as the snapshot had it: gone, or different today."""
    if deleted is None:
        _unavailable(invocation)
        return
    snapshot, folder = parameters.unpack()
    run_query(invocation, lambda: [folder_entry_to_variant(e) for e in deleted.find_changed(snapshot, folder)])


def search_folder(versions: VersionService | None, parameters, invocation) -> None:
    if versions is None:
        _unavailable(invocation)
        return
    snapshot, path, query = parameters.unpack()
    run_query(
        invocation, lambda: [folder_entry_to_variant(e) for e in versions.search_folder(snapshot, path, query)]
    )
