"""The place of the repository, looked at in the file system."""

import os

from delta.domain.destination import DestinationState
from delta.domain.repository import Repository


class LocalDestination:
    def state(self, repo: Repository) -> DestinationState:
        """MISSING when the folder is not there, EMPTY when it holds nothing (a repository never is), else AVAILABLE.

        A folder that cannot be read counts as available: it is there, and the engine will say what it makes of it.
        """
        if not os.path.isdir(repo.location):
            return DestinationState.MISSING
        try:
            with os.scandir(repo.location) as entries:
                if next(entries, None) is None:
                    return DestinationState.EMPTY
        except OSError:
            pass
        return DestinationState.AVAILABLE
