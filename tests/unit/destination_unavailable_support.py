"""What the tests of test_destination_unavailable share."""

from delta.domain.destination import DestinationState


MISSING, EMPTY, AVAILABLE = DestinationState.MISSING, DestinationState.EMPTY, DestinationState.AVAILABLE
