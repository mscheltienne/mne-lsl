"""One dockable stream document: a controller and a trace display."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import Signal

from ._bootstrap import import_ads

ads = import_ads()

if TYPE_CHECKING:
    from qtpy.QtWidgets import QWidget

    from ..stream import BaseStream
    from .backend import StreamIdentity


class StreamDocument(ads.CDockWidget):
    """One stream document, i.e. the dockable unit of one regularly sampled stream.

    The content is a toolbar over a horizontal splitter holding the controller and the
    trace display. Documents tab together and split cleanly when dragged to a side; the
    controller can be hidden per document.

    Parameters
    ----------
    manager : ads.CDockManager
        The dock manager owning the document area. Required: the two-argument
        ``CDockWidget(title, parent)`` form is deprecated in PySide6-QtAds 5.0.0 and its
        ``DeprecationWarning`` is an error under the pytest configuration of this
        repository.
    stream : BaseStream
        The connected stream rendered by this document.
    identity : StreamIdentity
        Exact identity of the stream, reported by the status bar and saved in a
        configuration.
    owns_stream : bool
        If ``True``, :meth:`teardown` disconnects the stream. A borrowed stream, i.e.
        one provided to :class:`~mne_lsl.viewer.Viewer` by
        :meth:`~mne_lsl.stream.BaseStream.plot`, is never disconnected by the viewer.
    parent : QWidget | None
        Parent widget.

    Attributes
    ----------
    changed : Signal
        Emitted with the document itself when its state moves, e.g. on a freeze or a
        change of the displayed channel count, so the shared status bar refreshes.
    """

    changed = Signal(object)

    def __init__(
        self,
        manager: ads.CDockManager,
        stream: BaseStream,
        identity: StreamIdentity,
        *,
        owns_stream: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the document."""
        # 'CDockWidget''s C++ constructor calls 'setObjectName(title)', and Qt-ADS keys
        # its dock-widget map, thus its layout save/restore, by 'objectName()'. Naming a
        # document after the stream name would therefore make two same-name streams
        # collide, which is an explicitly supported case since an identity is the
        # '(name, stype, source_id)' triple. Set a unique 'setObjectName(f"stream-{i}")'
        # *before* 'addDockWidget', which is where the map is populated, and let the tab
        # title carry the human stream name.

    # -- state ----------------------------------------------------------------------
    @property
    def frozen(self) -> bool:
        """Whether the viewport is frozen while the acquisition keeps rolling."""

    def set_frozen(self, frozen: bool) -> None:
        """Freeze or resume the viewport, i.e. stop or start the render clock."""

    @property
    def controller_visible(self) -> bool:
        """Whether the controller panel is shown."""

    def set_controller_visible(self, visible: bool) -> None:
        """Show or hide the controller panel, restoring its previous width."""

    def status_fields(self) -> dict[str, str]:
        """Return the status-bar fields describing the current state of the document.

        Returns
        -------
        fields : dict
            The connection and live/frozen state, the identity, the displayed and total
            channel counts, the sampling rate, the retained history and the processing
            latency.
        """

    def retint_icons(self) -> None:
        """Rebuild the toolbar icons and the indicator for the active theme."""

    # -- teardown and recovery ------------------------------------------------------
    def teardown(self) -> None:
        """Stop the render clock and release the stream, if owned.

        Idempotent: it runs from the Qt-ADS ``closed`` signal, thus for a close from the
        document toolbar, from the dock-area close button and from the window closing,
        and may be called again on a stream which is already disconnected.
        """

    def on_stream_lost(self) -> None:
        """Interrupt the render and show the per-document disconnection notice.

        The notice is non-modal and offers to acknowledge and close the document; if it
        is left open and the stream returns with the same channels and settings, the
        display resumes and the notice closes itself. How the loss is detected, which
        must come from the liblsl inlet status rather than from a 'no new samples'
        heuristic, is a separate open investigation.
        """
