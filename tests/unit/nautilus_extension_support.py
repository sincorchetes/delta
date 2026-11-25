"""What the tests of test_nautilus_extension share."""

import importlib.util
import sys
import types
from pathlib import Path
import gi
import pytest
from gi import repository


EXTENSION = Path(__file__).resolve().parents[2] / "src" / "nautilus" / "delta_extension.py"


class FakeMenuItem:
    def __init__(self, name, label):
        self.name, self.label, self.handlers = name, label, []

    def connect(self, signal, callback, *args):
        self.handlers.append((signal, callback, args))


class FakeColumn:
    def __init__(self, name, attribute, label, description):
        self.name, self.attribute, self.label, self.description = name, attribute, label, description


@pytest.fixture
def extension(monkeypatch):
    nautilus = types.ModuleType("Nautilus")
    nautilus.MenuProvider = type("MenuProvider", (), {})
    nautilus.InfoProvider = type("InfoProvider", (), {})
    nautilus.ColumnProvider = type("ColumnProvider", (), {})
    nautilus.MenuItem = FakeMenuItem
    nautilus.Column = FakeColumn
    real = gi.require_version
    monkeypatch.setattr(
        gi, "require_version", lambda name, version: None if name == "Nautilus" else real(name, version)
    )
    monkeypatch.setitem(sys.modules, "gi.repository.Nautilus", nautilus)
    monkeypatch.setattr(repository, "Nautilus", nautilus, raising=False)
    spec = importlib.util.spec_from_file_location("delta_extension_under_test", EXTENSION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Location:
    def __init__(self, path):
        self._path = path

    def get_path(self):
        return self._path


class FileInfo:
    def __init__(self, path, directory=False, scheme="file"):
        self._path, self._directory, self._scheme = path, directory, scheme
        self.attributes, self.emblems = {}, []

    def add_string_attribute(self, name, value):
        self.attributes[name] = value

    def add_emblem(self, name):
        self.emblems.append(name)

    def is_directory(self):
        return self._directory

    def get_uri_scheme(self):
        return self._scheme

    def get_location(self):
        return Location(self._path)


@pytest.fixture
def provider(extension, monkeypatch):
    monkeypatch.setattr(extension.GLib, "get_home_dir", lambda: "/home/ana")
    monkeypatch.setattr(extension, "repository_location", lambda source=None: "/run/media/ana/Disk/delta-backups")
    return extension.DeltaMenuProvider()


class FakeSchemaSource:
    def __init__(self, schema=None):
        self._schema = schema

    def lookup(self, schema_id, recursive):
        return self._schema if schema_id == "io.github.sincorchetes.Delta" else None


def _compile(folder: Path, messages: dict) -> Path:
    """Write a minimal .mo file (no msgfmt needed): that is what gettext reads."""
    import struct

    pairs = sorted({"": "Content-Type: text/plain; charset=UTF-8\n", **messages}.items())
    ids = b"\0".join(key.encode() for key, _ in pairs) + b"\0"
    strings = b"\0".join(value.encode() for _, value in pairs) + b"\0"
    count, table = len(pairs), 7 * 4
    id_offsets, string_offsets, position = [], [], table + count * 16
    for key, _ in pairs:
        id_offsets.append((len(key.encode()), position))
        position += len(key.encode()) + 1
    for _, value in pairs:
        string_offsets.append((len(value.encode()), position))
        position += len(value.encode()) + 1
    data = struct.pack("<7I", 0x950412DE, 0, count, table, table + count * 8, 0, 0)
    data += b"".join(struct.pack("<2I", *item) for item in id_offsets)
    data += b"".join(struct.pack("<2I", *item) for item in string_offsets)
    mo = folder / "delta.mo"
    mo.write_bytes(data + ids + strings)
    return mo


HOME = "/home/ana"


def backup_info(extension, last=1000, sources=(), excludes=()):
    return extension.BackupInfo(last, tuple(sources), tuple(excludes))


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class FakeState:
    def __init__(self, info):
        self._info = info

    def get(self):
        return self._info


@pytest.fixture
def home(tmp_path, extension, monkeypatch):
    monkeypatch.setattr(extension.GLib, "get_home_dir", lambda: str(tmp_path))
    (tmp_path / "Documents").mkdir()
    (tmp_path / "Documents" / "a.txt").write_text("x")
    return tmp_path


def info_for(extension, info):
    return extension.DeltaInfoProvider(state=FakeState(info))
