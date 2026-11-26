"""Adapters around the platform, with the platform replaced: settings, notifications, launching, systemd."""

from types import SimpleNamespace

from delta.domain.repository import Repository
from delta.domain.retention import RetentionPolicy
from delta.infrastructure import settings


# --- settings ------------------------------------------------------------------------------------


class Stored:
    """What GSettings holds."""

    def __init__(self, **values):
        self.values, self.written = values, {}

    def get_string(self, key):
        return self.values[key]

    def get_strv(self, key):
        return self.values[key]

    def get_int(self, key):
        return self.values[key]

    def set_string(self, key, value):
        self.written[key] = value


def with_schema(monkeypatch, stored):
    """Install a stand-in for Gio where the schema is there (stored given) or is not (None)."""
    source = SimpleNamespace(lookup=lambda schema, recursive: object() if stored is not None else None)
    monkeypatch.setattr(
        settings,
        "Gio",
        SimpleNamespace(
            SettingsSchemaSource=SimpleNamespace(get_default=lambda: source),
            Settings=SimpleNamespace(new=lambda schema: stored),
        ),
    )


def test_the_schema_is_not_installed_when_there_is_no_default_source(monkeypatch):
    monkeypatch.setattr(
        settings, "Gio", SimpleNamespace(SettingsSchemaSource=SimpleNamespace(get_default=lambda: None))
    )

    assert settings._schema_installed() is False


def test_the_repository_comes_from_the_environment_first(monkeypatch):
    monkeypatch.setenv("DELTA_REPOSITORY", "/srv/repo")
    with_schema(monkeypatch, Stored(**{"repository-location": "/media/disk/backups"}))

    assert settings.configured_repository() == Repository("/srv/repo")


def test_a_repository_that_is_not_a_local_path_counts_as_none(monkeypatch):
    monkeypatch.setenv("DELTA_REPOSITORY", "relative/repo")

    assert settings.configured_repository() is None


def test_the_repository_comes_from_gsettings_otherwise(monkeypatch):
    monkeypatch.delenv("DELTA_REPOSITORY", raising=False)
    with_schema(monkeypatch, Stored(**{"repository-location": "/media/disk/backups"}))

    assert settings.configured_repository() == Repository("/media/disk/backups")


def test_without_the_schema_or_an_environment_value_nothing_is_configured(monkeypatch):
    monkeypatch.delenv("DELTA_REPOSITORY", raising=False)
    with_schema(monkeypatch, None)

    assert settings.configured_repository() is None


def test_the_chosen_folders_and_exclusions_are_read(monkeypatch):
    with_schema(monkeypatch, Stored(**{"backup-sources": ["/a", "/b"], "excluded-paths": ["/a/tmp"]}))

    assert settings.configured_sources() == ("/a", "/b")
    assert settings.configured_excludes() == ("/a/tmp",)


def test_without_the_schema_no_folders_or_exclusions_are_chosen(monkeypatch):
    with_schema(monkeypatch, None)

    assert settings.configured_sources() == () and settings.configured_excludes() == ()


def test_the_retention_is_read_from_gsettings_or_defaults(monkeypatch):
    with_schema(
        monkeypatch,
        Stored(**{"keep-hourly": 1, "keep-daily": 2, "keep-weekly": 3, "keep-monthly": 4}),
    )
    assert settings.configured_retention() == RetentionPolicy(1, 2, 3, 4)

    with_schema(monkeypatch, None)
    assert settings.configured_retention() == RetentionPolicy()


def test_the_chosen_repository_is_saved_when_there_is_a_schema(monkeypatch):
    stored = Stored()
    with_schema(monkeypatch, stored)

    settings.save_repository(Repository("/media/disk/backups"))

    assert stored.written == {"repository-location": "/media/disk/backups"}


def test_saving_the_repository_without_a_schema_does_nothing(monkeypatch):
    with_schema(monkeypatch, None)

    settings.save_repository(Repository("/media/disk/backups"))

    assert settings.open_settings() is None
