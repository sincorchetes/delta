"""Reads the configured repository from GSettings (env override for development)."""

import os

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio

from delta.domain.repository import Repository
from delta.domain.retention import RetentionPolicy

SCHEMA_ID = "io.github.sincorchetes.Delta"


def configured_repository() -> Repository | None:
    """None when nothing is configured, or when the setting is not a valid repository location
    (one left by an older version): the app then asks to set backups up again."""
    location = os.environ.get("DELTA_REPOSITORY") or _gsettings_location()
    if not location:
        return None
    try:
        return Repository(location)
    except ValueError:
        return None


def configured_sources() -> tuple[str, ...]:
    """Folders chosen for backup; empty when unset (the caller decides the default)."""
    settings = open_settings()
    return tuple(settings.get_strv("backup-sources")) if settings is not None else ()


def configured_excludes() -> tuple[str, ...]:
    """Paths the user chose to skip; empty when unset."""
    settings = open_settings()
    return tuple(settings.get_strv("excluded-paths")) if settings is not None else ()


def configured_retention() -> RetentionPolicy:
    """GFS policy from GSettings; defaults when the schema is not installed."""
    if not _schema_installed():
        return RetentionPolicy()
    settings = Gio.Settings.new(SCHEMA_ID)
    return RetentionPolicy(
        keep_hourly=settings.get_int("keep-hourly"),
        keep_daily=settings.get_int("keep-daily"),
        keep_weekly=settings.get_int("keep-weekly"),
        keep_monthly=settings.get_int("keep-monthly"),
    )


def open_settings() -> Gio.Settings | None:
    """The app's GSettings, or None when the schema is not installed."""
    return Gio.Settings.new(SCHEMA_ID) if _schema_installed() else None


def save_repository(repo: Repository) -> None:
    settings = open_settings()
    if settings is not None:
        settings.set_string("repository-location", repo.location)


class SettingsRepositoryIdentity:
    """The identifier of the repository that Delta made or adopted, in GSettings next to where it is."""

    def expected(self) -> str:
        settings = open_settings()
        return settings.get_string("repository-id") if settings is not None else ""

    def remember(self, repo_id: str) -> None:
        settings = open_settings()
        if settings is not None:
            settings.set_string("repository-id", repo_id)


def _schema_installed() -> bool:
    source = Gio.SettingsSchemaSource.get_default()
    return source is not None and source.lookup(SCHEMA_ID, True) is not None


def _gsettings_location() -> str:
    if not _schema_installed():
        return ""
    return Gio.Settings.new(SCHEMA_ID).get_string("repository-location")
