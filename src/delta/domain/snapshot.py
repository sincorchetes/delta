"""A point-in-time backup archive."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Snapshot:
    id: str
    name: str
    created: datetime
