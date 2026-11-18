import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio

from delta.daemon.introspection import INTERFACE_NAME, INTERFACE_XML, OBJECT_PATH


def _interface():
    return Gio.DBusNodeInfo.new_for_xml(INTERFACE_XML).interfaces[0]


def test_interface_xml_is_valid():
    assert _interface() is not None


def test_well_known_name_and_object_path():
    assert INTERFACE_NAME == "io.github.sincorchetes.Delta.Service1"
    assert OBJECT_PATH == "/io/github/sincorchetes/Delta/Service1"


def test_declared_methods_match_draft_api():
    names = {method.name for method in _interface().methods}
    assert names == {
        "CreateBackup",
        "CreateRepository",
        "UnlockRepository",
        "UseRepository",
        "ListSnapshots",
        "ListVersions",
        "ListFolder",
        "SearchFolder",
        "ListDeleted",
        "ListChanged",
        "RestoreDeleted",
        "Restore",
        "RestoreAsCopy",
        "RestoreReplace",
        "PreviewVersion",
        "ClearPreviews",
        "MountSnapshot",
        "UnmountSnapshot",
    }


def test_declared_signals_match_draft_api():
    names = {signal.name for signal in _interface().signals}
    assert names == {"Progress", "BackupFinished", "SnapshotClosed"}


def test_declared_properties_match_draft_api():
    props = {prop.name: prop.signature for prop in _interface().properties}
    assert props == {
        "Status": "s",
        "LastBackup": "t",
        "LastError": "s",
        "NextBackup": "t",
        "CanMount": "b",
    }
