"""Grandfather-father-son retention policy."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RetentionPolicy:
    keep_hourly: int = 24
    keep_daily: int = 7
    keep_weekly: int = 4
    keep_monthly: int = 12

    def __post_init__(self) -> None:
        for name, value in self.as_dict().items():
            if value < 0:
                raise ValueError(f"{name} must not be negative")

    def as_dict(self) -> dict[str, int]:
        return {
            "keep_hourly": self.keep_hourly,
            "keep_daily": self.keep_daily,
            "keep_weekly": self.keep_weekly,
            "keep_monthly": self.keep_monthly,
        }

    @property
    def keeps_anything(self) -> bool:
        return any(self.as_dict().values())
