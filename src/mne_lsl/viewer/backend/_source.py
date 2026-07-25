"""Discovery of the streams on the network and construction of a stream object.

This module is the only place in the viewer which names an LSL-specific object:
everything downstream is typed to :class:`~mne_lsl.stream.BaseStream`, so that a future
protocol gains a source module here and nothing else.

Notes
-----
Every :class:`~mne_lsl.lsl.StreamInfo` this module creates is created, read and
destroyed inside a single function body. One is never stored on an attribute, never
placed in a container which outlives the call, never returned, and never named outside
this module: its ``__del__`` destroys the native stream info, so handing one to another
thread or caching it invites a hard crash. What crosses out is
:class:`~mne_lsl.viewer.backend.StreamDescriptor`, a frozen dataclass of plain values,
and :class:`~mne_lsl.stream.BaseStream`, which has no Qt thread affinity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...lsl import StreamInlet, resolve_streams
from ...stream import StreamLSL
from ._identity import StreamDescriptor, StreamIdentity

if TYPE_CHECKING:
    from ...lsl.stream_info import _BaseStreamInfo
    from ...stream import BaseStream

# Discovery pass: long enough for the outlets of a local subnet to answer, short enough
# to be re-run on demand. 'resolve_streams' blocks the full timeout when unrestricted,
# thus this is also the cost of one pass.
_RESOLVE_TIMEOUT = 1.0

# Channel probe: liblsl's own timeouts, applied once per operation. No watchdog, as a
# blocking liblsl call cannot be interrupted and a watchdog would be theatre.
_PROBE_TIMEOUT = 2.0


def _descriptor(sinfo: _BaseStreamInfo) -> StreamDescriptor:
    """Return the descriptor of ``sinfo``, reading every property once.

    Parameters
    ----------
    sinfo : StreamInfo
        Stream info to read, owned by the caller and destroyed by it.

    Returns
    -------
    descriptor : StreamDescriptor
        A frozen descriptor holding no reference to ``sinfo``.
    """
    return StreamDescriptor(
        identity=StreamIdentity(
            name=sinfo.name, stype=sinfo.stype, source_id=sinfo.source_id
        ),
        n_channels=sinfo.n_channels,
        sfreq=sinfo.sfreq,
        hostname=sinfo.hostname,
        dtype=sinfo.dtype,
    )


def resolve_descriptors(timeout: float = _RESOLVE_TIMEOUT) -> list[StreamDescriptor]:
    """Return a descriptor for every stream currently present on the network.

    Parameters
    ----------
    timeout : float
        Timeout of the resolution, in seconds. An unrestricted resolution blocks for the
        full duration, thus this must never be called on the GUI thread.

    Returns
    -------
    descriptors : list of StreamDescriptor
        Descriptors of the streams found, regular and irregular alike, sorted by
        identity.

    Notes
    -----
    The sort is not cosmetic: :func:`~mne_lsl.lsl.resolve_streams` de-duplicates through
    a :class:`set` and therefore returns an unordered list, which would reshuffle the
    launcher table between two passes of an unchanged network.

    The resolved stream infos are local to this call and die when it returns, on the
    thread which called it. That is the ownership rule of this module.
    """
    sinfos = resolve_streams(timeout)
    descriptors = [_descriptor(sinfo) for sinfo in sinfos]
    return sorted(descriptors, key=lambda descriptor: descriptor.identity.as_tuple())


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

    Raises
    ------
    ValueError
        If ``bufsize`` is not integral while the stream is irregularly sampled.

    Notes
    -----
    The ``bufsize`` check is this module's, not the library's.
    :meth:`~mne_lsl.stream.StreamLSL.connect` validates ``bufsize`` against
    ``sfreq == 0`` only *after* it has created and opened the inlet, and it does not
    reset the stream on the way out: the :class:`ValueError` leaves an object whose
    :attr:`~mne_lsl.stream.BaseStream.connected` property and
    :meth:`~mne_lsl.stream.BaseStream.disconnect` method both raise, so not even
    ``__del__`` can close the inlet it just opened. A descriptor already carries
    :attr:`~mne_lsl.viewer.backend.StreamDescriptor.sfreq`, thus the viewer refuses the
    value up front. That matters because
    :meth:`~mne_lsl.viewer.backend.Connector.open` passes one ``bufsize`` to a batch
    holding regular and event streams alike, where a single non-integral value would
    otherwise half-connect every event stream of the configuration.
    """
    identity = descriptor.identity
    if descriptor.sfreq == 0 and bufsize != int(bufsize):
        raise ValueError(
            f"The buffer size of the irregularly sampled stream {identity.as_tuple()} "
            f"must be a whole number of samples, got {bufsize}."
        )
    return StreamLSL(
        bufsize,
        name=identity.name,
        stype=identity.stype,
        source_id=identity.source_id,
    )


def connect_stream(descriptor: StreamDescriptor, bufsize: float) -> BaseStream:
    """Create and connect a stream for ``descriptor``, blocking until it is ready.

    Parameters
    ----------
    descriptor : StreamDescriptor
        Descriptor of the stream to connect to, providing the exact identity tuple.
    bufsize : float
        Size of the stream buffer, in seconds.

    Returns
    -------
    stream : BaseStream
        The connected stream.

    Raises
    ------
    RuntimeError
        If the identity no longer matches exactly one stream, or if the stream is a
        string stream, which :class:`~mne_lsl.stream.StreamLSL` refuses.
    ValueError
        If ``bufsize`` is not integral while the stream is irregularly sampled, raised
        by :func:`create_stream` before anything is opened.

    Notes
    -----
    This is the single place in the viewer where ``recover`` is written, and it is
    written as ``False``. With ``recover=True`` liblsl re-resolves a lost stream forever
    at 500 ms intervals, matching on the identity, the channel count and the format but
    not on the sampling rate, and Python observes nothing at all -- no error, no state
    change, just an indefinitely empty pull. The per-document disconnection notice the
    viewer must show cannot exist on top of that, and neither can the check that the
    stream which came back is the stream which left. The library default stays ``True``,
    as flipping it would change the behaviour of every existing consumer, so the viewer
    passes ``False`` explicitly.

    It also exists so that the discovery transport needs no LSL knowledge: ``recover``
    is a :class:`~mne_lsl.stream.StreamLSL` keyword absent from
    :meth:`~mne_lsl.stream.BaseStream.connect`, thus passing it from a
    ``BaseStream``-typed call site would break on the first non-LSL protocol.

    ``acquisition_delay`` and ``timeout`` keep the library defaults. A generous timeout
    would directly lengthen the failure path, as a missing identity burns most of it
    before raising.
    """
    return create_stream(descriptor, bufsize).connect(recover=False)


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

    Raises
    ------
    RuntimeError
        If the identity does not match exactly one stream on the network, or if the
        inlet could not be opened or read within the probe timeout. The message is the
        reason the interface shows, thus this raises rather than returning an empty
        list, which would be indistinguishable from a stream publishing no channels.

    Notes
    -----
    The identity is re-resolved here, because a descriptor deliberately carries no
    stream info of its own -- see this module's ownership rule. A fully specified
    identity resolves instantly on a local network, and the repeated probe cost is meant
    to be avoided one level up, by caching the *names* against ``(identity, uid)``: a
    changed ``uid`` proves the channel set may have changed, and an unchanged one proves
    it cannot have.

    The names come from :meth:`~mne_lsl.lsl.StreamInfo.get_channel_info`, never from
    :meth:`~mne_lsl.lsl.StreamInfo.get_channel_names`: a stream publishing duplicates
    advertises ``['Cz', 'Cz', 'Fp1']`` on the wire while the viewer sees MNE's
    deterministic ``['Cz-0', 'Cz-1', 'Fp1']``, and a stream publishing no names at all
    advertises ``None`` while the viewer sees ``['0', '1', ...]``. Comparing the raw
    names would make both kinds of stream permanently unavailable.

    Event and marker streams are matched on their identity only and are never probed: a
    string marker stream has no meaningful channel set. That is the caller's rule, not a
    guard here.

    The probe inlet is destroyed with :meth:`~mne_lsl.lsl.StreamInlet._del` and never
    closed first: ``close_stream`` is broken in liblsl (sccn/liblsl#180) and closing
    before destruction engages the recovery machinery, whose cancellation races with the
    destruction and can abort the process (sccn/liblsl#220). ``recover=False`` keeps
    that machinery out of a throwaway inlet altogether.
    """
    sinfos = resolve_streams(_PROBE_TIMEOUT, *descriptor.identity.as_tuple())
    if len(sinfos) != 1:
        # mirrors 'StreamLSL.connect''s own message, as both are shown to the user.
        raise RuntimeError(
            "The identity 'name', 'stype' and 'source_id' does not uniquely identify "
            f"an LSL stream. {len(sinfos)} were found: "
            f"{[(sinfo.name, sinfo.stype, sinfo.source_id) for sinfo in sinfos]}."
        )
    inlet = StreamInlet(sinfos[0], max_buffered=1, recover=False)
    try:
        inlet.open_stream(timeout=_PROBE_TIMEOUT)
        sinfo = inlet.get_sinfo(timeout=_PROBE_TIMEOUT)
        # copied out of an 'Info' which is about to be destroyed with its stream info.
        return list(sinfo.get_channel_info()["ch_names"])
    finally:
        inlet._del()
