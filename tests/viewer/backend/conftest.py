from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

    from mne_lsl.stream import BaseStream


@pytest.fixture
def config_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point 'Path.home()' at a temporary directory and return it.

    The configuration directory is computed from 'Path.home()' on every call precisely
    so that it can be redirected here, instead of being frozen into a module constant at
    import time.
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


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
