"""One dockable stream document: a controller and a trace display."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import QSize, Qt, Signal
from qtpy.QtWidgets import (
    QLabel,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..utils.logs import logger
from ._bootstrap import import_ads
from .controller import ChannelModel, ChannelsPage
from .display import TraceDisplay
from .theme import _ICON_PX, icon, theme_controller, tokens

if TYPE_CHECKING:
    from ..stream import BaseStream
    from .backend import StreamIdentity

ads = import_ads()

# Initial widths of the controller panel and of the trace display, in pixels: the panel
# opens a little wider than its own minimum and the display takes the rest.
_PANEL_SIZES = (300, 900)


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

    Raises
    ------
    ValueError
        If the stream is irregularly sampled, i.e. if it declares ``sfreq == 0``.

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
        # Refused here, the choke point both entry points meet at: 'open_streams' skips
        # an event source already, while 'adopt_stream' -- the 'BaseStream.plot()' path
        # -- would otherwise open a document over a stream with no continuous signal,
        # whose time axis means nothing and whose window 'get_data' reads as a count.
        if float(stream.info["sfreq"]) == 0:
            raise ValueError(
                f"The stream {identity.as_tuple()} is irregularly sampled and cannot "
                "be opened as a document: it carries no continuous signal to draw."
            )
        # 'CDockWidget''s C++ constructor calls 'setObjectName(title)', and Qt-ADS keys
        # its dock-widget map, thus its layout save/restore, by 'objectName()'. Naming a
        # document after the stream name would therefore make two same-name streams
        # collide, which is an explicitly supported case since an identity is the
        # '(name, stype, source_id)' triple. The unique object name is assigned by the
        # window, in the one method which also calls 'addDockWidget' -- where the map is
        # populated -- and the tab title carries the human stream name.
        super().__init__(manager, identity.name, parent)
        self._stream = stream
        self._identity = identity
        self._owns_stream = bool(owns_stream)
        self._frozen = False
        self._torn = False

        # a document docks and tabs inside the main window for this milestone; it does
        # not become a separate top-level window. The only call there is: closable,
        # movable and focusable are in 'DefaultDockWidgetFeatures' already, and setting
        # them explicitly yields a bit-identical mask -- measured 547 either way, from a
        # 551 default. 'test_focus_highlighting_is_live' and
        # 'test_teardown_via_closed_signal' are the net if a binding ever drops one.
        self.setFeature(ads.CDockWidget.DockWidgetFeature.DockWidgetFloatable, False)
        # The one teardown hook. Qt-ADS routes the document toolbar's close button, the
        # dock-area close button and the window's own close loop through
        # 'closeDockWidget()', which emits this exactly once, and it delivers no close
        # event to the content widget -- so without this nothing stops the render clock.
        self.closed.connect(self.teardown)

        self.model = ChannelModel(stream, parent=self)
        self.channels = ChannelsPage(self.model, parent=self)
        self.trace = TraceDisplay(stream, parent=self)
        # The initial push. It keeps the display's own default -- acquisition order,
        # every channel visible -- from being what is drawn: the model is the only owner
        # of the order and the visibility, so it states them once here and on every
        # change below.
        self.trace.set_channel_layout(self.model.visible_acq_indices())
        self.model.layout_changed.connect(self._push_layout)
        self.model.metadata_changed.connect(self.trace.refresh_metadata)

        self._panel = self._build_panel()
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._panel)
        self._splitter.addWidget(self.trace)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes(list(_PANEL_SIZES))

        content = QWidget()
        box = QVBoxLayout(content)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        box.addWidget(self._build_toolbar())
        box.addWidget(self._splitter, 1)
        self.setWidget(content)
        self.retint_icons()
        # Last, and here rather than in the window's registration: this object owns the
        # live/frozen state, so a document whose clock the caller has not started yet
        # reports 'Live' over a viewport which never advances.
        self.trace.start()

    # -- construction ------------------------------------------------------------------
    def _build_panel(self) -> QTabWidget:
        """Build the controller panel, i.e. the tab widget holding the Channels page."""
        panel = QTabWidget()
        panel.setTabPosition(QTabWidget.TabPosition.West)
        panel.setDocumentMode(True)
        # One tab: the Processing and Events pages are added by the phases which
        # implement them, and instantiating either stub today yields a widget which
        # raises.
        panel.addTab(self.channels, "Channels")
        return panel

    def _build_toolbar(self) -> QToolBar:
        """Build the document toolbar: the indicator, the toggles and the close."""
        bar = QToolBar()
        bar.setMovable(False)
        bar.setIconSize(QSize(_ICON_PX, _ICON_PX))

        self._indicator = QLabel()
        self._indicator.setContentsMargins(6, 0, 6, 0)
        self._indicator.setToolTip(
            "Whether the viewport advances. The acquisition keeps running while the "
            "viewport is frozen."
        )
        bar.addWidget(self._indicator)

        self._freeze_button = QToolButton()
        self._freeze_button.setCheckable(True)
        self._freeze_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._freeze_button.setToolTip(
            "Freeze the viewport on the current window, or resume it"
        )
        self._freeze_button.toggled.connect(self.set_frozen)
        bar.addWidget(self._freeze_button)

        self._controller_button = QToolButton()
        self._controller_button.setCheckable(True)
        self._controller_button.setChecked(True)
        self._controller_button.setToolTip("Show or hide the controller panel")
        self._controller_button.toggled.connect(self.set_controller_visible)
        bar.addWidget(self._controller_button)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)

        self._close_button = QToolButton()
        # A button added with 'addWidget' ignores the bar's own icon size and renders
        # oversized, thus the size is set on the button as well.
        self._close_button.setIconSize(QSize(_ICON_PX, _ICON_PX))
        self._close_button.setToolTip("Close this stream document")
        self._close_button.clicked.connect(self.closeDockWidget)
        bar.addWidget(self._close_button)
        return bar

    # -- state -------------------------------------------------------------------------
    @property
    def identity(self) -> StreamIdentity:
        """Exact identity of the stream this document renders."""
        return self._identity

    @property
    def stream(self) -> BaseStream:
        """The stream this document renders, owned or borrowed."""
        return self._stream

    @property
    def owns_stream(self) -> bool:
        """Whether closing this document disconnects the stream."""
        return self._owns_stream

    @property
    def frozen(self) -> bool:
        """Whether the viewport is frozen while the acquisition keeps rolling."""
        return self._frozen

    def set_frozen(self, frozen: bool) -> None:
        """Freeze or resume the viewport, i.e. stop or start the render clock.

        Parameters
        ----------
        frozen : bool
            Whether to freeze the viewport.

        Notes
        -----
        A no-op once the document was torn down. Reachable programmatically only, as the
        freeze button went with its toolbar, but resuming there restarts the 33 ms clock
        with nothing left to stop it -- and over a *borrowed* stream, which the teardown
        leaves connected, that clock draws into a closed widget.
        """
        if self._torn:
            return
        self._frozen = bool(frozen)
        if self._frozen:
            self.trace.stop()
        else:
            self.trace.start()
        # mirrored under 'blockSignals', so that a programmatic call does not come back
        # through 'toggled' and emit 'changed' a second time.
        blocked = self._freeze_button.blockSignals(True)
        self._freeze_button.setChecked(self._frozen)
        self._freeze_button.blockSignals(blocked)
        self._refresh_freeze_ui()
        self.changed.emit(self)

    def _refresh_freeze_ui(self) -> None:
        """Label the freeze button with the action it performs and paint the indicator.

        Notes
        -----
        One method and one branch on :attr:`StreamDocument.frozen` for both, as the two
        are never refreshed apart: a freeze and a theme flip each need the pair, and two
        copies of the condition are how a state ends up labelled 'Live' next to a frozen
        indicator.
        """
        palette = tokens(theme_controller.mode)
        if self._frozen:
            glyph, label = "mdi6.play", "Live"
            text, color = "■ Frozen", palette.warning
        else:
            glyph, label = "mdi6.pause", "Freeze"
            text, color = "● Live", palette.success
        self._freeze_button.setIcon(icon(glyph))
        self._freeze_button.setText(label)
        # the glyph and the word are the cues which are not the color.
        self._indicator.setText(text)
        self._indicator.setStyleSheet(f"color: {color}; font-weight: 600;")

    @property
    def controller_visible(self) -> bool:
        """Whether the controller panel is shown."""
        # 'isHidden', not 'isVisible': a document which was never added to a shown
        # window has no visible child at all, while the toggle state is a property of
        # the panel alone.
        return not self._panel.isHidden()

    def set_controller_visible(self, visible: bool) -> None:
        """Show or hide the controller panel; it comes back at its previous width.

        Parameters
        ----------
        visible : bool
            Whether to show the controller panel.

        Notes
        -----
        No width is remembered here, on purpose. Measured: a
        :class:`~qtpy.QtWidgets.QSplitter` restores a hidden child to the width it had,
        whatever the user dragged it to and even across a resize of the window while it
        was hidden. Saving and re-applying the sizes around this toggle is therefore
        code no behaviour can distinguish. What *would* lose the width is an explicit
        ``setSizes`` while the panel is hidden.
        """
        visible = bool(visible)
        self._panel.setVisible(visible)
        blocked = self._controller_button.blockSignals(True)
        self._controller_button.setChecked(visible)
        self._controller_button.blockSignals(blocked)

    def status_fields(self) -> dict[str, str]:
        """Return the status-bar fields describing the current state of the document.

        Returns
        -------
        fields : dict
            The connection and live/frozen state, the displayed and total channel
            counts, the sampling rate, the retained history and the processing latency.
            The identity is deliberately absent: it is immutable and the caller already
            holds it, in :attr:`StreamDocument.identity`.

        Notes
        -----
        Nothing is read off the stream while it is disconnected: both
        :attr:`~mne_lsl.stream.BaseStream.info` and
        :attr:`~mne_lsl.stream.BaseStream.n_buffer` raise there.

        The gate covers a stream which is *already* disconnected, and not one going away
        under it: :attr:`~mne_lsl.stream.BaseStream.connected` asserts that four
        attributes are either all set or all unset, while the acquisition thread clears
        them one at a time, so the gate itself raises ``AssertionError`` mid-disconnect.
        That is an upstream defect and it is not guarded here, as the fix belongs to
        :attr:`~mne_lsl.stream.BaseStream.connected`.
        """
        fields = {
            "state": "Disconnected",
            "channels": "—",
            "sfreq": "—",
            "history": "—",
            "latency": "—",
        }
        if not self._stream.connected:
            return fields
        sfreq = float(self._stream.info["sfreq"])
        fields["state"] = "Connected • " + ("Frozen" if self._frozen else "Live")
        # The displayed count is what the viewport shows, not what the layout holds: a
        # stream with fewer channels than the row count shows all of them.
        fields["channels"] = (
            f"{min(self.trace.n_visible, self.trace.n_rows)}/{self.trace.n_channels} ch"
        )
        fields["sfreq"] = f"{sfreq:g} Hz"
        # no zero guard: the constructor refuses a stream declaring 'sfreq == 0'.
        fields["history"] = f"{self._stream.n_buffer / sfreq:g} s history"
        fields["latency"] = "No processing • 0 ms"
        return fields

    def retint_icons(self) -> None:
        """Rebuild the toolbar icons and the indicator for the active theme."""
        # a 'QIcon' bakes its color at creation, thus a theme flip needs every icon of
        # the bar rebuilt rather than merely repainted.
        self._refresh_freeze_ui()  # the freeze glyph and the indicator color
        self._controller_button.setIcon(icon("mdi6.tune-variant"))
        self._close_button.setIcon(icon("mdi6.close"))

    # -- the model -> display edge -----------------------------------------------------
    def _push_layout(self) -> None:
        """Push the model's visible channels onto the display, then report it."""
        # read fresh on every emission and never cached: the model is the owner of both
        # the order and the visibility.
        self.trace.set_channel_layout(self.model.visible_acq_indices())
        self.changed.emit(self)  # the status bar's displayed/total count moved

    # -- teardown and recovery ---------------------------------------------------------
    def teardown(self) -> None:
        """Stop the render clock and release the stream, if owned.

        Idempotent: it runs from the Qt-ADS ``closed`` signal, thus for a close from the
        document toolbar, from the dock-area close button and from the window closing,
        and may be called again on a stream which is already disconnected.

        Notes
        -----
        The children go first, so that no render tick can read a stream which is going
        away. A failing ``disconnect()`` is logged and swallowed: a window close tears
        down every document in a loop, and one half-connected stream which raises there
        would otherwise abandon the teardown of all the others.

        The model to display edge is dropped as well, and before the display is closed:
        the model outlives the document's widgets, and a layout push arriving afterwards
        reaches a closed display -- which for a *borrowed* stream, still connected, is a
        freshly fetched window drawn into a widget nobody can see.
        """
        if self._torn:
            return
        self._torn = True
        self.model.layout_changed.disconnect(self._push_layout)
        self.model.metadata_changed.disconnect(self.trace.refresh_metadata)
        self.trace.close()
        self.channels.close()
        if self._owns_stream and self._stream.connected:
            try:
                self._stream.disconnect()
            except Exception as error:  # deliberately broad, see the note above
                logger.warning(
                    "Could not disconnect the stream %s: %s",
                    self._identity.as_tuple(),
                    error,
                )
