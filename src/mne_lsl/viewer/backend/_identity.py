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
        return (self.name, self.stype, self.source_id)


@dataclass(frozen=True, slots=True)
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
    uid : str
        Identifier of the *outlet instance*, not of the stream: re-instantiating an
        outlet under the same identity yields a different ``uid``. A channel set cached
        against ``(identity, uid)`` is therefore still valid, while a changed ``uid``
        proves nothing about the channels and forces a fresh probe.

    Notes
    -----
    ``uid`` is deliberately not part of :class:`StreamIdentity`: an identity is the
    ``(name, stype, source_id)`` triple, and folding the instance identifier into it
    would make every reconnection of the same stream a different stream.

    Frozen, and built exclusively of plain Python and numpy scalar types, because a
    descriptor is what crosses the worker/GUI thread boundary in place of the
    :class:`~mne_lsl.lsl.StreamInfo` it was read from: that object's ``__del__``
    destroys the native stream info, so it must never be stored nor handed to another
    thread. Freezing makes that ownership rule structural instead of conventional, and
    makes a descriptor hashable, which is what the identity de-duplication of
    :meth:`~mne_lsl.viewer._window.ViewerWindow.open_streams` relies on.
    """

    identity: StreamIdentity
    n_channels: int
    sfreq: float
    hostname: str
    dtype: str | DTypeLike
    uid: str
