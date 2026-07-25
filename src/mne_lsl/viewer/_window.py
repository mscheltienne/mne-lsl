"""Main window: the application toolbar, the document area and the status bar."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtWidgets import QMainWindow

from ._bootstrap import import_ads

ads = import_ads()

if TYPE_CHECKING:
    from collections.abc import Sequence

    from qtpy.QtGui import QCloseEvent
    from qtpy.QtWidgets import QWidget

    from ..stream import BaseStream
    from ._document import StreamDocument
    from .backend import StreamDescriptor, ViewerConfig


class ViewerWindow(QMainWindow):
    """The one window owning the complete experience.

    The central widget stacks the landing page and the document host, whose central
    widget is a Qt-ADS ``CDockManager``. Documents are ``CDockWidget`` instances: they
    tab together with IDE-style top tabs and split the space in two when dragged to a
    side.
    The shared status bar follows the focused document through
    ``focusedDockWidgetChanged``.

    Parameters
    ----------
    parent : QWidget | None
        Parent widget.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the window, its dock manager, toolbar and status bar."""
        # The Qt-ADS configuration flags are static and read by the 'CDockManager'
        # constructor, thus they must be set *before* creating it:
        # - 'FocusHighlighting' drives the status-bar-follows-focus wiring;
        # - 'EqualSplitOnInsertion' keeps a programmatic split balanced;
        # - 'XmlCompressionEnabled=False' and 'XmlAutoFormattingEnabled=True' keep
        #   'saveState()' inspectable, as it returns a zlib-compressed 'QByteArray' by
        #   default while the configuration format wants readable XML.
        # 'DockWidgetFloatable' stays off for the first milestone: a document docks and
        # tabs inside the main window, it does not become a separate top-level window.

    def refresh(self) -> None:
        """Start one discovery pass and re-evaluate the saved configurations."""

    def open_streams(self, descriptors: Sequence[StreamDescriptor]) -> None:
        """Connect to ``descriptors`` in the background and open one document each.

        A descriptor whose identity is already open raises the existing document instead
        of connecting twice; a failed connection is reported without closing the
        documents which are already open.

        Parameters
        ----------
        descriptors : sequence of StreamDescriptor
            Descriptors of the regular streams to open.
        """

    def adopt_stream(self, stream: BaseStream) -> StreamDocument:
        """Open a document for an already connected stream, without owning it.

        This is the :meth:`~mne_lsl.stream.BaseStream.plot` path: the stream is
        borrowed, thus closing the document never disconnects it. The window provides
        its dock manager to the document it builds.

        Parameters
        ----------
        stream : BaseStream
            A connected stream owned by the caller.

        Returns
        -------
        document : StreamDocument
            The document which was opened.
        """

    def open_configuration(self, cfg: ViewerConfig) -> None:
        """Restore a saved configuration, all-or-nothing.

        Revalidates the availability, connects every required stream in the background,
        validates the channel-dependent settings, builds the documents off the saved
        Qt-ADS layout and reveals the workspace only once every document is ready. If
        any required connection fails, every stream opened by that attempt is closed,
        the window returns to the landing page with a refreshed discovery and an
        actionable error dialog is shown.

        Parameters
        ----------
        cfg : ViewerConfig
            The configuration to restore.
        """

    def close_all_documents(self) -> None:
        """Close every open document, tearing down its render clock and stream."""

    def closeEvent(self, event: QCloseEvent) -> None:
        """Close every document cleanly before the window closes."""
