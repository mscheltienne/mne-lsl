from __future__ import annotations

import contextlib
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mne_lsl.lsl import StreamInfo, StreamOutlet
from mne_lsl.viewer.backend import StreamDescriptor, StreamIdentity, resolve_descriptors

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from mne_lsl.stream import BaseStream

# Bound on the wait for a freshly created outlet to become resolvable. Generous, as it
# is only ever reached when discovery is broken; a local outlet answers instantly.
_RESOLVE_DEADLINE = 10.0


@pytest.fixture
def descriptor() -> Callable[..., StreamDescriptor]:
    """Return a factory building a descriptor out of plain values.

    No outlet is created, and the default 'source_id' is a uuid4, thus the identity is
    never on the network: this is the fixture for the logic which only moves descriptors
    around -- the identity dataclasses, the generation checks of the workers, the
    failure path of a connection -- while 'outlets' is the one to use when the stream
    has to actually answer.
    """

    def _make(
        name: str = "mne-lsl-viewer-absent",
        stype: str = "eeg",
        source_id: str | None = None,
        n_channels: int = 4,
        sfreq: float = 100.0,
        hostname: str = "host-1",
        dtype: str = "float32",
    ) -> StreamDescriptor:
        """Return one descriptor; every field has a default a test can override."""
        return StreamDescriptor(
            identity=StreamIdentity(
                name=name,
                stype=stype,
                source_id=str(uuid.uuid4()) if source_id is None else source_id,
            ),
            n_channels=n_channels,
            sfreq=sfreq,
            hostname=hostname,
            dtype=dtype,
        )

    return _make


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
def outlets(
    request: pytest.FixtureRequest,
) -> Generator[Callable[..., StreamDescriptor], None, None]:
    """Yield a factory creating resolvable LSL outlets, destroyed at teardown.

    The outlets never push a sample: discovery, the channel probe and
    'StreamLSL.connect()' all need an outlet to exist and to answer, not to produce
    data, so a silent outlet covers every assertion of this subpackage without a player
    subprocess or a testing dataset.

    Each outlet is named after the requesting test and gets a uuid4 'source_id', so
    concurrent jobs sharing the link can never collide, and the factory returns only
    once 'resolve_descriptors' actually sees the identity -- the discovery equivalent of
    the player fixture's status handshake.
    """
    created: list[tuple[StreamOutlet, StreamInfo]] = []

    def _start(
        n_channels: int = 4,
        sfreq: float = 100.0,
        stype: str = "eeg",
        ch_names: list[str] | None = None,
        name: str | None = None,
        source_id: str | None = None,
    ) -> StreamDescriptor:
        """Create one outlet and return its descriptor, once it is resolvable.

        'ch_names' defaults to generated names; an **empty** list publishes no channel
        description at all, which is the degenerate case a probe must still handle.
        """
        name = name if name is not None else f"mne-lsl-viewer-{request.node.name}"
        source_id = source_id if source_id is not None else str(uuid.uuid4())
        sinfo = StreamInfo(name, stype, n_channels, sfreq, "float32", source_id)
        if ch_names is None:
            ch_names = [f"ch{k}" for k in range(n_channels)]
        if len(ch_names) != 0:
            sinfo.set_channel_names(ch_names)
        outlet = StreamOutlet(sinfo)
        created.append((outlet, sinfo))
        identity = (name, stype, source_id)
        deadline = time.monotonic() + _RESOLVE_DEADLINE
        while time.monotonic() < deadline:
            for descriptor in resolve_descriptors(1.0):
                if descriptor.identity.as_tuple() == identity:
                    return descriptor
        pytest.fail(f"The outlet {identity} never became resolvable.")

    yield _start
    # teardown in the fixture rather than in the test bodies, so a failing assertion
    # still destroys the outlets instead of leaving them on the network.
    for outlet, _ in reversed(created):
        outlet._del()
    created.clear()


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
