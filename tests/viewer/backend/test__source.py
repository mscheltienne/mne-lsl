from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy as np
import pytest

from mne_lsl.lsl import StreamInlet
from mne_lsl.stream import BaseStream, StreamLSL
from mne_lsl.viewer.backend import (
    _source,
    connect_stream,
    create_stream,
    probe_channels,
    resolve_descriptors,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from mne_lsl.viewer.backend import StreamDescriptor


# -- construction, no network -------------------------------------------------------
def test_create_stream(descriptor: Callable[..., StreamDescriptor]) -> None:
    """Test that the full identity and the buffer size are threaded through."""
    absent = descriptor()
    stream = create_stream(absent, 4.0)
    assert isinstance(stream, BaseStream)
    assert not stream.connected
    assert (stream.name, stream.stype, stream.source_id) == absent.identity.as_tuple()
    assert stream._bufsize == 4.0


@pytest.mark.parametrize("bufsize", [2.5, 0.5])
def test_create_stream_rejects_a_fractional_buffer_of_an_event_stream(
    descriptor: Callable[..., StreamDescriptor], bufsize: float
) -> None:
    """Test that a non-integral buffer size is refused before anything is opened.

    'StreamLSL.connect' checks this only after it has created and opened the inlet, and
    does not reset the stream on the way out, leaving an object whose 'connected'
    property and 'disconnect' method both raise -- not even '__del__' can close that
    inlet. The descriptor carries 'sfreq', thus the value is refused here, at
    construction, which also matters because 'Connector.open' passes a single buffer
    size to a batch holding regular and event streams alike.
    """
    with pytest.raises(ValueError, match="must be a whole number of samples"):
        create_stream(descriptor(sfreq=0.0), bufsize)
    # a regularly sampled stream takes any buffer size, fractional or not.
    assert create_stream(descriptor(), bufsize)._bufsize == bufsize


def test_connect_stream_passes_recover_explicitly(
    monkeypatch: pytest.MonkeyPatch, descriptor: Callable[..., StreamDescriptor]
) -> None:
    """Test that 'recover=False' is passed explicitly, not inherited from a default.

    'tests/conftest.py::_no_recover' patches the *default* to 'False' for every test, so
    asserting the effective value would pass even if the viewer passed nothing at all --
    and would then behave differently in production, where the library default is
    'True'. The keyword itself is what must be asserted.
    """
    assert StreamLSL.connect.__kwdefaults__["recover"] is False  # the fixture is active
    captured: dict[str, object] = {}

    def _connect(self: StreamLSL, *args: object, **kwargs: object) -> StreamLSL:
        captured.update(kwargs)
        return self

    monkeypatch.setattr(StreamLSL, "connect", _connect)
    connect_stream(descriptor(), 4.0)
    assert captured["recover"] is False


def test_probe_channels_inlet_arguments(
    monkeypatch: pytest.MonkeyPatch, outlets: Callable[..., StreamDescriptor]
) -> None:
    """Test that the probe inlet is throwaway, destroyed, and never closed first.

    'close_stream' is broken in liblsl and closing before destruction can abort the
    process, thus 'never called' is the load-bearing assertion here. '_del' is asserted
    as 'called', not 'called once': the inlet drops out of scope when the probe returns
    and '__del__' calls it again, where it is a no-op.
    """
    captured: dict[str, object] = {}
    calls: list[str] = []

    class _RecordingInlet(StreamInlet):
        def __init__(self, sinfo: object, **kwargs: object) -> None:
            captured.update(kwargs)
            super().__init__(sinfo, **kwargs)

        def close_stream(self) -> None:
            calls.append("close_stream")
            super().close_stream()

        def _del(self) -> None:
            calls.append("_del")
            super()._del()

    monkeypatch.setattr(_source, "StreamInlet", _RecordingInlet)
    descriptor = outlets(n_channels=3, ch_names=["Fp1", "Fp2", "Cz"])
    assert probe_channels(descriptor) == ["Fp1", "Fp2", "Cz"]
    assert captured == {"max_buffered": 1, "recover": False}
    assert "close_stream" not in calls
    assert "_del" in calls


def test_probe_channels_absent_identity(
    descriptor: Callable[..., StreamDescriptor],
) -> None:
    """Test that an identity which is not on the network raises with its reason."""
    with pytest.raises(RuntimeError, match="does not uniquely identify an LSL stream"):
        probe_channels(descriptor())


# -- discovery ----------------------------------------------------------------------
def test_resolve_descriptors(outlets: Callable[..., StreamDescriptor]) -> None:
    """Test that an outlet is described by identity and headline metadata."""
    descriptor = outlets(n_channels=5, sfreq=128.0, stype="eeg")
    assert descriptor.n_channels == 5
    assert descriptor.sfreq == 128.0
    assert descriptor.identity.stype == "eeg"
    assert descriptor.hostname
    assert descriptor.dtype == np.float32
    # No stream info escaped the resolution: a descriptor is frozen and made of plain
    # values only, which is what lets it cross a thread boundary.
    assert not hasattr(descriptor, "__dict__")
    for value in (descriptor.n_channels, descriptor.sfreq, descriptor.hostname):
        assert isinstance(value, (str, int, float, np.generic))


def test_resolve_descriptors_is_sorted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that the descriptors come out sorted by identity, whatever came in.

    'resolve_streams' de-duplicates through a set and therefore returns an unordered
    list, which would reshuffle the launcher table between two passes of an unchanged
    network. Fed a deliberately reversed list rather than real outlets: the order a set
    happens to yield for two or three streams is already the sorted one often enough
    that a live resolution cannot tell a sorted implementation from an unsorted one. The
    stand-ins are read exactly like a stream info -- five properties, then dropped --
    which is all '_descriptor' ever does with one.
    """
    identities = [("zzz", "unit-2"), ("zzz", "unit-1"), ("aaa", "unit-3")]
    monkeypatch.setattr(
        _source,
        "resolve_streams",
        lambda *args: [
            SimpleNamespace(
                name=name,
                stype="eeg",
                source_id=source_id,
                n_channels=4,
                sfreq=100.0,
                hostname="host-1",
                dtype="float32",
            )
            for name, source_id in identities
        ],
    )
    keys = [descriptor.identity.as_tuple() for descriptor in resolve_descriptors(1.0)]
    assert keys == [
        ("aaa", "eeg", "unit-3"),
        ("zzz", "eeg", "unit-1"),
        ("zzz", "eeg", "unit-2"),
    ]


def test_resolve_descriptors_same_name(
    outlets: Callable[..., StreamDescriptor],
) -> None:
    """Test that two streams sharing a name are kept apart by their source ID.

    Never asserts the total number of streams found: the link is shared with whatever
    else runs on the machine, so only the presence of the created identities is checked.
    """
    name = f"mne-lsl-viewer-{uuid.uuid4()}"
    first = outlets(name=name, n_channels=4)
    second = outlets(name=name, n_channels=6)
    assert first.identity != second.identity
    found = {
        descriptor.identity: descriptor
        for descriptor in resolve_descriptors(2.0)
        if descriptor.identity.name == name
    }
    assert set(found) == {first.identity, second.identity}
    # the channel counts differ, thus a mix-up between the two cannot pass unnoticed.
    assert found[first.identity].n_channels == 4
    assert found[second.identity].n_channels == 6


def test_probe_channels_same_name(outlets: Callable[..., StreamDescriptor]) -> None:
    """Test that the probe of a same-name pair returns the right unit's channels."""
    name = f"mne-lsl-viewer-{uuid.uuid4()}"
    first = outlets(name=name, n_channels=2, ch_names=["L", "R"])
    second = outlets(name=name, n_channels=3, ch_names=["X", "Y", "Z"])
    assert probe_channels(first) == ["L", "R"]
    assert probe_channels(second) == ["X", "Y", "Z"]


@pytest.mark.parametrize(
    ("ch_names", "expected", "match"),
    [
        (["Cz", "Cz", "Fp1"], ["Cz-0", "Cz-1", "Fp1"], "not unique"),
        ([], ["0", "1", "2"], "channel description"),
    ],
)
def test_probe_channels_degenerate_names(
    outlets: Callable[..., StreamDescriptor],
    ch_names: list[str],
    expected: list[str],
    match: str,
) -> None:
    """Test that duplicate and absent channel names still resolve deterministically.

    The names come from 'get_channel_info()', never 'get_channel_names()': comparing
    the raw wire names would make both kinds of stream permanently unavailable. Both
    cases make MNE emit a 'RuntimeWarning', which is an error under this test suite's
    configuration, thus the warning is asserted rather than silenced.
    """
    descriptor = outlets(n_channels=3, ch_names=ch_names)
    with pytest.warns(RuntimeWarning, match=match):
        assert probe_channels(descriptor) == expected


# -- connection ---------------------------------------------------------------------
def test_connect_stream(
    outlets: Callable[..., StreamDescriptor], streams: list[BaseStream]
) -> None:
    """Test that a descriptor connects end-to-end against a silent outlet."""
    descriptor = outlets(n_channels=3, sfreq=64.0, ch_names=["Fp1", "Fp2", "Cz"])
    stream = connect_stream(descriptor, 2.0)
    streams.append(stream)  # disconnected by the fixture, whatever the assertions do
    assert isinstance(stream, BaseStream)
    assert stream.connected
    assert stream.info["sfreq"] == 64.0
    assert stream.ch_names == ["Fp1", "Fp2", "Cz"]


def test_connect_stream_absent_identity(
    descriptor: Callable[..., StreamDescriptor],
) -> None:
    """Test that connecting to an absent identity raises rather than hanging."""
    with pytest.raises(RuntimeError, match="do not uniquely identify an LSL stream"):
        connect_stream(descriptor(), 2.0)
