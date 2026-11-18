"""What the preferences offer and how each choice maps to GSettings. No GTK, no D-Bus."""

import os
from dataclasses import dataclass

from delta.i18n import _

Retention = tuple[int, int, int, int]  # hourly, daily, weekly, monthly


@dataclass(frozen=True)
class ComboModel:
    """Labels of a drop-down and which one is selected.

    When the stored value is none of the presets (set by hand, or by an older version) a last
    "Custom" entry stands for it, so the drop-down never claims a choice that is not in force.
    """

    labels: tuple[str, ...]
    selected: int
    has_custom: bool = False


@dataclass(frozen=True)
class RetentionPreset:
    label: str
    description: str
    values: Retention


SCHEDULES = ("hourly", "daily", "weekly")


def schedule_labels() -> tuple[str, ...]:
    return (_("Every hour"), _("Every day"), _("Every week"))


def schedule_model(expression: str) -> ComboModel:
    labels = schedule_labels()
    if expression in SCHEDULES:
        return ComboModel(labels, SCHEDULES.index(expression))
    return ComboModel((*labels, _("Custom")), len(labels), has_custom=True)


def schedule_value(index: int) -> str | None:
    """The expression for a chosen entry; None for the "Custom" entry (nothing to change)."""
    return SCHEDULES[index] if 0 <= index < len(SCHEDULES) else None


def retention_presets() -> tuple[RetentionPreset, ...]:
    return (
        RetentionPreset(
            _("Short"),
            _("Every hour for half a day and every day for a week."),
            (12, 7, 0, 0),
        ),
        RetentionPreset(
            _("Standard"),
            _("Every hour for a day, every day for a week, every week for a month and every month for a year."),
            (24, 7, 4, 12),
        ),
        RetentionPreset(
            _("Long"),
            _("Every hour for a day, every day for two weeks, every week for three months and every month for three years."),
            (24, 14, 12, 36),
        ),
    )


def retention_model(values: Retention) -> ComboModel:
    presets = retention_presets()
    labels = tuple(preset.label for preset in presets)
    for index, preset in enumerate(presets):
        if preset.values == values:
            return ComboModel(labels, index)
    return ComboModel((*labels, _("Custom")), len(labels), has_custom=True)


def retention_values(index: int) -> Retention | None:
    presets = retention_presets()
    return presets[index].values if 0 <= index < len(presets) else None


def retention_description(index: int) -> str:
    presets = retention_presets()
    if 0 <= index < len(presets):
        return presets[index].description
    return _("Set outside Delta; choose one of the options to replace it.")


def add_path(paths: tuple[str, ...], path: str) -> tuple[str, ...]:
    """Append a chosen path (normalised, no duplicates, order kept). Relative paths are refused."""
    if not os.path.isabs(path):
        return paths
    normal = os.path.normpath(path)
    return paths if normal in paths else (*paths, normal)


def remove_path(paths: tuple[str, ...], path: str) -> tuple[str, ...]:
    return tuple(item for item in paths if item != path)


def exclusion_problem(path: str, sources: tuple[str, ...], home: str) -> str | None:
    """Why skipping `path` would leave nothing to back up (or hide everything), else None."""
    normal = os.path.normpath(path)
    roots = [os.path.normpath(source) for source in sources] or [os.path.normpath(home)]
    for root in roots:
        if root == normal or root.startswith(normal.rstrip("/") + "/"):
            return _("That would skip everything you back up.")
    return None
