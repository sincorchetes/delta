"""Which schema the settings look for and open, and what is returned when it is not installed."""

from types import SimpleNamespace

from delta.infrastructure import settings

SCHEMA = "io.github.sincorchetes.Delta"


class Source:
    def __init__(self, installed):
        self.installed, self.asked = installed, []

    def lookup(self, schema_id, recursive):
        self.asked.append((schema_id, recursive))
        return object() if self.installed else None


class Stored:
    def get_string(self, key):
        return "/media/disk/delta"

    def get_int(self, key):
        return 3


def gio(monkeypatch, source):
    created = []

    def new(schema):
        created.append(schema)
        return Stored()

    monkeypatch.setattr(
        settings,
        "Gio",
        SimpleNamespace(SettingsSchemaSource=SimpleNamespace(get_default=lambda: source), Settings=SimpleNamespace(new=new)),
    )
    return created


def test_the_schema_is_looked_up_by_its_id_among_the_ones_installed_and_their_children(monkeypatch):
    source = Source(installed=True)
    gio(monkeypatch, source)

    assert settings._schema_installed() is True
    assert source.asked == [(SCHEMA, True)]


def test_the_settings_are_opened_for_that_schema_when_it_is_installed(monkeypatch):
    created = gio(monkeypatch, Source(installed=True))

    assert isinstance(settings.open_settings(), Stored)
    assert created == [SCHEMA]


def test_the_settings_are_not_opened_when_the_schema_is_not_installed(monkeypatch):
    created = gio(monkeypatch, Source(installed=False))

    assert settings.open_settings() is None
    assert created == []


def test_the_retention_is_read_from_the_settings_of_that_schema(monkeypatch):
    created = gio(monkeypatch, Source(installed=True))

    policy = settings.configured_retention()

    assert created == [SCHEMA] and policy.keep_hourly == 3


def test_the_location_is_read_from_that_schema_and_is_empty_when_there_is_none(monkeypatch):
    created = gio(monkeypatch, Source(installed=True))
    assert settings._gsettings_location() == "/media/disk/delta" and created == [SCHEMA]

    created = gio(monkeypatch, Source(installed=False))
    assert settings._gsettings_location() == "" and created == []
