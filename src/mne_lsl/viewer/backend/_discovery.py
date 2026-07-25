"""Background stream discovery and connection.

Both objects run their blocking work off the GUI thread and report through Qt signals,
which is the transport boundary: nothing outside this module touches a worker thread.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import QObject, Signal

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ._identity import StreamDescriptor


class Discovery(QObject):
    """Resolve the streams present on the network, without blocking the GUI.

    Attributes
    ----------
    progress : Signal
        Emitted with a state tag, one of ``'checking'``, ``'updated'``, ``'failed'`` or
        ``'empty'``.
    streams_found : Signal
        Emitted with the ``list`` of :class:`~mne_lsl.viewer.backend.StreamDescriptor`
        found by the last pass, regular and irregular streams alike.
    """

    progress = Signal(str)
    streams_found = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the discovery object."""

    def refresh(self) -> None:
        """Start one discovery pass, replacing a pass which is still running."""

    def stop(self) -> None:
        """Stop the running pass and wait for its worker; idempotent."""


class Connector(QObject):
    """Connect to streams in the background, one document at a time.

    A failed connection is reported and leaves the already connected streams untouched;
    the all-or-nothing rollback of a configuration load is the caller's decision.

    Attributes
    ----------
    connected : Signal
        Emitted with ``(descriptor, stream)`` for every stream which connected, the
        stream being a :class:`~mne_lsl.stream.BaseStream`.
    failed : Signal
        Emitted with ``(descriptor, message)`` when a connection failed.
    """

    connected = Signal(object, object)
    failed = Signal(object, str)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the connector object."""

    def open(self, descriptors: Sequence[StreamDescriptor], bufsize: float) -> None:
        """Connect to every stream of ``descriptors`` in the background.

        Parameters
        ----------
        descriptors : sequence of StreamDescriptor
            Descriptors of the streams to connect to.
        bufsize : float
            Size of the stream buffers, in seconds.
        """

    def stop(self) -> None:
        """Cancel the pending connections and wait for the worker; idempotent."""
