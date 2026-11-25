"""What the tests of test_restore_beside share."""

import os
from datetime import datetime

from delta.application.restore_service import SCRATCH_PREFIX, RestoreService
from delta.domain.repository import Repository
from delta.domain.snapshot import Snapshot


NOW = datetime(2026, 11, 10, 13, 5, 0)


class FakeEngine:
    """Extracts what the 'snapshot' holds, recreating the full original path."""

    def __init__(self, files=None, folders=None):
        self.files = files or {}
        self.folders = folders or {}
        self.calls = []  # the paths of each extract call

    def list_snapshots(self, repo):
        return [Snapshot("id1", "first", NOW)]

    def extract(self, repo, snapshot, paths, destination):
        self.calls.append(paths)
        for path in paths:
            target = os.path.join(destination, path.lstrip("/"))
            if path in self.folders:
                for name, content in self.folders[path].items():
                    os.makedirs(os.path.dirname(os.path.join(target, name)), exist_ok=True)
                    with open(os.path.join(target, name), "w") as handle:
                        handle.write(content)
            elif path in self.files:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "w") as handle:
                    handle.write(self.files[path])


def service(home, engine):
    return RestoreService(engine, Repository("/r"), str(home), clock=lambda: NOW)


def read(path):
    with open(path) as handle:
        return handle.read()


def scratch_left(folder):
    return [name for name in os.listdir(folder) if name.startswith(SCRATCH_PREFIX)]
