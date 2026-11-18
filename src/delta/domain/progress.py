"""Progress reported by a running backup."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProgressEvent:
    files: int
    original_size: int
    path: str
