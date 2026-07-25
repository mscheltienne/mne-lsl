"""Construction of a stream object from a descriptor.

Together with :mod:`~mne_lsl.viewer.backend._discovery`, this module is the only place
in the viewer which names an LSL-specific object: everything downstream is typed to
:class:`~mne_lsl.stream.BaseStream`, so that a future protocol gains a source module
here and nothing else.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...stream import BaseStream
    from ._identity import StreamDescriptor


def create_stream(descriptor: StreamDescriptor, bufsize: float) -> BaseStream:
    """Create a disconnected stream for ``descriptor``.

    Parameters
    ----------
    descriptor : StreamDescriptor
        Descriptor of the stream to create, providing the exact identity tuple.
    bufsize : float
        Size of the stream buffer, in seconds.

    Returns
    -------
    stream : BaseStream
        The stream object, not connected yet.
    """


def probe_channels(descriptor: StreamDescriptor) -> list[str]:
    """Return the channel names of a stream, by briefly connecting to it.

    Discovery reports the channel count but not the channel names, which are only
    available once an inlet is opened. This is used to evaluate the availability of a
    saved configuration against the channels it expects.

    Parameters
    ----------
    descriptor : StreamDescriptor
        Descriptor of the stream to probe.

    Returns
    -------
    ch_names : list of str
        The channel names, in acquisition order.
    """
