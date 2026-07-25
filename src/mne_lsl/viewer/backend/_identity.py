"""Stream identity and the descriptor returned by discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from numpy.typing import DTypeLike


@dataclass(frozen=True, slots=True)
class StreamIdentity:
    """Exact identity of a stream, ``(name, stype, source_id)``.

    A stream is identified by the full tuple and never by its name alone: two streams
    may share a name and differ by type or source ID.

    Parameters
    ----------
    name : str
        Stream name.
    stype : str
        Stream type, e.g. ``'eeg'``.
    source_id : str
        Source ID of the stream.
    """

    name: str
    stype: str
    source_id: str

    def as_tuple(self) -> tuple[str, str, str]:
        """Return the identity as a plain ``(name, stype, source_id)`` tuple."""


@dataclass
class StreamDescriptor:
    """Description of a stream present on the network, as returned by discovery.

    Built from a :class:`~mne_lsl.lsl.StreamInfo` without opening an inlet, thus the
    channel names are not part of it: they require a connection, see
    :func:`~mne_lsl.viewer.backend.probe_channels`.

    Parameters
    ----------
    identity : StreamIdentity
        Exact identity of the stream.
    n_channels : int
        Number of channels.
    sfreq : float
        Nominal sampling rate, ``0`` for an irregularly sampled (event) stream.
    hostname : str
        Host on which the outlet runs.
    dtype : str | DTypeLike
        Channel format of the stream.
    """

    identity: StreamIdentity
    n_channels: int
    sfreq: float
    hostname: str
    dtype: str | DTypeLike
