from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

    from mne_lsl.stream import BaseStream


@pytest.fixture
def streams() -> Generator[list[BaseStream], None, None]:
    """Yield a list of streams to disconnect at teardown.

    Every test which obtains a connected stream appends it here instead of disconnecting
    it itself: a failing assertion would otherwise leave a live inlet and its
    acquisition thread behind.
    """
    connected: list[BaseStream] = []
    yield connected
    for stream in reversed(connected):
        # Neither 'connected' nor 'disconnect' can be trusted on a stream whose
        # connection raised halfway through -- 'connected' asserts that its attributes
        # are either all set or all unset -- thus the teardown cannot gate on the first
        # and has to tolerate the second raising.
        with contextlib.suppress(AssertionError):
            stream.disconnect()
    connected.clear()
