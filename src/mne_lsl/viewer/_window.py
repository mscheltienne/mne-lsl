"""Main window: the application toolbar, the document area and the status bar."""

from __future__ import annotations

from typing import TYPE_CHECKING

import qtpy
from qtpy.QtCore import QSize, Qt, qVersion
from qtpy.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QStackedWidget,
    QWidget,
)

from .._version import __version__
from ..utils.logs import logger
from ._bootstrap import configure_docking, import_ads
from ._document import StreamDocument
from ._launcher import EmptyStatePage, progress_text
from .backend import Connector, Discovery, derive_bufsize, stream_identity
from .display import WINDOW_RANGE
from .theme import (
    _ADS_ICONS,
    _ADS_QSS,
    _ICON_PX,
    _MODES,
    follow_theme,
    icon,
    theme_controller,
)
from .widgets import AnimatedSegmentedControl

if TYPE_CHECKING:
    from collections.abc import Sequence

    from qtpy.QtGui import QAction, QCloseEvent, QShowEvent
    from qtpy.QtWidgets import QToolBar

    from ..stream import BaseStream
    from .backend import StreamDescriptor, StreamIdentity

ads = import_ads()

# Characters kept of the source ID in the status bar before eliding; the full value
# stays in the tooltip. Character-based on purpose: a status-bar segment has no measured
# rectangle to elide against, and a character count is what a test can assert.
_SOURCE_ID_CHARS = 14
# Theme toggle segments, as (label, tooltip, user setting). The settings are the shared
# 'theme._MODES', in its order: the index lookup below relies on it, and a test pins it.
_THEME_SEGMENTS = (
    ("Auto", "Follow the operating system theme", "auto"),
    ("Light", "Force the light theme", "light"),
    ("Dark", "Force the dark theme", "dark"),
)


def _elide(text: str) -> str:
    """Return ``text`` cut to ``_SOURCE_ID_CHARS`` characters, with an ellipsis."""
    if len(text) <= _SOURCE_ID_CHARS:
        return text
    return f"{text[:_SOURCE_ID_CHARS]}…"


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
        super().__init__(parent)
        self.setWindowTitle("MNE-LSL viewer")
        self._documents: list[StreamDocument] = []
        self._active: StreamDocument | None = None
        self._closed = False
        self._dock_area = None
        # Monotonic, and never 'len(self._documents)': a closed document keeps its entry
        # in the manager's dock-widget map for the life of the process, thus a reused
        # name loses a map entry and writes an ambiguous saved layout.
        self._next_index = 0
        # The batch in flight, and the message it wrote. Descriptors and not identities:
        # the connector supersedes a batch rather than queueing behind it, so a new one
        # has to carry the still-connecting descriptors with it.
        self._connecting: dict[StreamIdentity, StreamDescriptor] = {}
        self._batch_message = ""
        self._toolbar_icons: list[tuple[QAction, str]] = []

        # Connected before anything can call 'open()': a 'Connector' hands stream
        # ownership over with its signal, thus a batch started before the receiver
        # exists would drop a live stream and leak its inlet.
        self._discovery = Discovery(parent=self)
        self._connector = Connector(parent=self)
        self._discovery.progress.connect(self._on_progress)
        self._discovery.streams_found.connect(self._on_streams_found)
        self._connector.connected.connect(self._on_connected)
        self._connector.failed.connect(self._on_failed)

        self._landing = EmptyStatePage(self)
        self._landing.selection_changed.connect(self._update_open_action)
        self._landing.open_requested.connect(self.open_streams)

        # The docking flags are static and consumed by the 'CDockManager' constructor:
        # setting one afterwards crashes the process on the next 'addDockWidget'.
        configure_docking()
        self._dock_host = QMainWindow()
        self._manager = ads.CDockManager(self._dock_host)
        self._manager.focusedDockWidgetChanged.connect(self._on_focus_changed)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._landing)
        self._stack.addWidget(self._dock_host)
        self.setCentralWidget(self._stack)

        self._build_toolbar()
        self._build_status_bar()
        self._apply_ads_theme()
        self._following_theme = False
        follow_theme(self, self._on_theme_changed, True)
        self._update_open_action()
        self._update_status_bar()
        # No discovery pass here: 'Viewer.show()' starts the first one. A pass costs
        # about a second and the 'stop()' of a close waits for the one in flight, which
        # every test of this window would otherwise pay.

    # -- construction ------------------------------------------------------------------
    def _build_toolbar(self) -> None:
        """Build the application toolbar."""
        bar = self.addToolBar("Main")
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        bar.setIconSize(QSize(_ICON_PX, _ICON_PX))
        self._add_action(
            bar, "mdi6.refresh", "Refresh", "Look for the streams on the network again"
        ).triggered.connect(self.refresh)
        self._act_open = self._add_action(
            bar,
            "mdi6.play-box-outline",
            "Open selected",
            "Open one document per selected stream",
        )
        self._act_open.triggered.connect(self._open_selected)
        bar.addSeparator()
        self._add_action(
            bar, "mdi6.help-circle-outline", "About", "Versions and Qt binding in use"
        ).triggered.connect(self._about)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        bar.addWidget(self._build_theme_toggle())

    def _add_action(self, bar: QToolBar, name: str, text: str, tooltip: str) -> QAction:
        """Add one toolbar action and register its icon for the theme flip.

        Parameters
        ----------
        bar : QToolBar
            The toolbar the action is added to.
        name : str
            QtAwesome icon name.
        text : str
            Action text.
        tooltip : str
            Action tooltip.

        Returns
        -------
        action : QAction
            The action which was added.
        """
        action = bar.addAction(icon(name), text)
        action.setToolTip(tooltip)
        # a 'QIcon' bakes its color at creation, thus a flip replays this table.
        self._toolbar_icons.append((action, name))
        return action

    def _build_theme_toggle(self) -> QWidget:
        """Build the Auto/Light/Dark control, synced to the current user setting.

        Notes
        -----
        The lookup needs no guard: the segments carry the theme vocabulary itself, thus
        the current setting is one of them by construction -- there is no fourth setting
        the resolver would accept and the toggle could not show.
        """
        toggle = AnimatedSegmentedControl(_THEME_SEGMENTS)
        toggle.set_index(_MODES.index(theme_controller.setting), emit=False)
        toggle.changed.connect(theme_controller.set_mode)
        # Every color of that widget is a palette role, thus it needs no retinting.
        return toggle

    def _build_status_bar(self) -> None:
        """Build the three permanent status-bar segments, left to right."""
        self._sb_state = QLabel()
        self._sb_identity = QLabel()
        self._sb_meta = QLabel()
        for label in (self._sb_state, self._sb_identity, self._sb_meta):
            label.setContentsMargins(6, 0, 6, 0)
            self.statusBar().addPermanentWidget(label)
        # 'showMessage' stays free for the transients: progress and the errors.

    # -- state -------------------------------------------------------------------------
    @property
    def documents(self) -> tuple[StreamDocument, ...]:
        """The open documents, in the order they were opened."""
        return tuple(self._documents)

    @property
    def active_document(self) -> StreamDocument | None:
        """The document the status bar describes, or ``None`` while none is open."""
        return self._active

    @property
    def closed(self) -> bool:
        """Whether the window has been closed, and is therefore spent.

        Notes
        -----
        A closed window is not reusable: :meth:`closeEvent` is the whole teardown, so it
        has stopped both workers and torn every document down. It is exposed because
        nothing else can tell -- ``QWidget`` emits ``destroyed`` on the C++ deletion
        only, and :class:`~mne_lsl.viewer.Viewer` keeps a reference to its window
        forever, so a closed one stays alive and answers every call.
        """
        return self._closed

    # -- discovery ---------------------------------------------------------------------
    def refresh(self) -> None:
        """Start one discovery pass; a no-op once the window is closed.

        Notes
        -----
        The guard is not decoration: ``Discovery.refresh`` starts its worker thread on
        demand, and after :meth:`closeEvent` nothing is left to stop it again.
        """
        if self._closed:
            return
        self.statusBar().clearMessage()
        self._discovery.refresh()

    def _on_progress(self, tag: str) -> None:
        """Reflect a discovery state tag on the landing page and in the status bar."""
        self._landing.set_progress(tag)
        self.statusBar().showMessage(progress_text(tag), 4000)

    def _on_streams_found(self, descriptors: object) -> None:
        """Publish the descriptors of a finished pass on the landing page.

        Notes
        -----
        The Open action is *not* re-evaluated here: publishing the descriptors rebuilds
        the table, which the page reports through ``selection_changed`` -- the one path,
        connected in the constructor. A second call from here would run the same
        evaluation twice per discovery pass and, worse, keep passing if the page ever
        stopped reporting a rebuild at all.
        """
        self._landing.set_streams(descriptors)

    # -- opening documents -------------------------------------------------------------
    def open_streams(self, descriptors: Sequence[StreamDescriptor]) -> None:
        """Connect to ``descriptors`` in the background and open one document each.

        A descriptor whose identity is already open raises the existing document instead
        of connecting twice; a failed connection is reported without closing the
        documents which are already open. A connection which is still in flight is
        carried into the new batch rather than being dropped.

        Parameters
        ----------
        descriptors : sequence of StreamDescriptor
            Descriptors of the regular streams to open.
        """
        wanted: dict[StreamIdentity, StreamDescriptor] = {}
        for descriptor in descriptors:
            identity = descriptor.identity
            existing = self._document_for(identity)
            if existing is not None:
                self._raise(existing)
                continue
            if descriptor.sfreq == 0:
                # an event source owns no document: it has no continuous signal to draw,
                # and 'StreamLSL' refuses a buffer in seconds for one.
                logger.warning(
                    "The stream %s is an event source and cannot be opened as a "
                    "document.",
                    identity.as_tuple(),
                )
                continue
            wanted[identity] = descriptor
        if not wanted:
            return
        # 'Connector.open' bumps its generation counter, thus it *supersedes* the batch
        # in flight instead of queueing behind it: the descriptors which have not come
        # back yet are merged into the new batch, or the streams the user asked for
        # first are dropped silently and their identities stay in flight for the life of
        # the process. Assigned, never accumulated, for the same reason.
        merged = self._connecting | wanted
        if merged == self._connecting:
            return  # a double click: the batch in flight already covers every identity
        self._connecting = merged
        self._batch_message = f"Connecting to {len(merged)} stream(s)…"
        self.statusBar().showMessage(self._batch_message)
        # Derived from the widest window the display can select, never from the current
        # one: a window wider than the buffer draws over part of the time axis for the
        # rest of the session, silently.
        self._connector.open(list(merged.values()), derive_bufsize(WINDOW_RANGE[1]))

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

        Raises
        ------
        RuntimeError
            If the stream is not connected.
        TypeError
            If the stream is not an LSL stream, i.e. if it carries no identity.
        ValueError
            If the stream is irregularly sampled, i.e. if it declares ``sfreq == 0``.
        """
        identity = stream_identity(stream)
        existing = self._document_for(identity)
        if existing is not None:
            self._raise(existing)
            return existing
        doc = StreamDocument(self._manager, stream, identity, owns_stream=False)
        self._register(doc)
        return doc

    def _on_connected(self, descriptor: object, stream: object) -> None:
        """Open a document for a stream which just connected."""
        identity = descriptor.identity
        self._connecting.pop(identity, None)
        self._batch_step()
        if self._document_for(identity) is not None:
            # The connector transferred the ownership of the stream with its signal,
            # thus returning without disconnecting leaks a live inlet and its
            # acquisition thread for the life of the process.
            logger.warning(
                "A document is already open for the stream %s; releasing the stream "
                "which just connected.",
                identity.as_tuple(),
            )
            try:
                stream.disconnect()
            except Exception as error:  # deliberately broad, as in the teardown path
                logger.warning("Could not release a duplicate stream: %s", error)
            return
        self._register(StreamDocument(self._manager, stream, identity))

    def _on_failed(self, descriptor: object, message: str) -> None:
        """Report a connection which failed, leaving the open documents untouched."""
        self._connecting.pop(descriptor.identity, None)
        self._batch_step()
        # No timeout and no dialog: one stable error surface, cleared by the next
        # refresh or open. The connector has already logged the exception.
        self.statusBar().showMessage(
            f"Could not open {descriptor.identity.name}: {message}"
        )

    def _batch_step(self) -> None:
        """Clear the batch's own message once every connection has come back.

        Notes
        -----
        The substitute for the ``finished`` signal the connector does not have: a batch
        is complete once nothing is left in flight.

        Only a message this batch itself wrote is cleared. Clearing unconditionally
        wipes the failure of one stream as soon as a sibling of the same batch succeeds,
        and the status bar is the only error surface there is.
        """
        if self._connecting:
            return
        if self.statusBar().currentMessage() == self._batch_message:
            self.statusBar().clearMessage()

    def _register(self, doc: StreamDocument) -> None:
        """Register a document in the dock manager and make it the active one.

        Parameters
        ----------
        doc : StreamDocument
            The document to register.

        Notes
        -----
        The single ``addDockWidget`` call site, so that the object-name rule cannot come
        apart from it. Qt-ADS keys its dock-widget map, and thus its saved layout, on
        ``objectName()``, which the ``CDockWidget`` constructor sets to the tab title --
        and two streams may legitimately share a name. The counter is monotonic because
        a closed document keeps its map entry for the life of the process.

        The window owns the docking here and nothing else: the render clock is started
        by the document's own constructor, which is what owns the live/frozen state.
        """
        doc.setObjectName(f"stream-{self._next_index}")
        self._next_index += 1
        # 'None' *is* the two-argument form: the signature is 'addDockWidget(area,
        # dockwidget, DockAreaWidget=nullptr, Index=-1)', thus the first document needs
        # no branch of its own.
        self._manager.addDockWidget(
            ads.DockWidgetArea.CenterDockWidgetArea, doc, self._dock_area
        )
        self._dock_area = doc.dockAreaWidget()
        self._documents.append(doc)
        doc.closed.connect(lambda document=doc: self._on_document_closed(document))
        doc.changed.connect(self._on_document_changed)
        self._stack.setCurrentWidget(self._dock_host)
        self._raise(doc)

    def _raise(self, doc: StreamDocument) -> None:
        """Bring ``doc`` to the front and make it the status bar's subject.

        Notes
        -----
        Explicit, because ``focusedDockWidgetChanged`` does not fire for the first
        document added to a window: the signal follows a user tab switch, it is not the
        source of truth.
        """
        doc.setAsCurrentTab()
        self._set_active(doc)

    def _document_for(self, identity: StreamIdentity) -> StreamDocument | None:
        """Return the open document of ``identity``, or ``None``."""
        return next(
            (doc for doc in self._documents if doc.identity == identity),
            None,
        )

    def _open_selected(self) -> None:
        """Open the streams selected on the landing page."""
        self.open_streams(self._landing.selected_descriptors())

    def _update_open_action(self) -> None:
        """Enable the Open action only while a stream is selected."""
        self._act_open.setEnabled(bool(self._landing.selected_descriptors()))

    # -- the active document and the status bar ----------------------------------------
    def _on_focus_changed(self, _old: object, now: object) -> None:
        """Follow a user-driven focus change to another document."""
        if isinstance(now, StreamDocument):
            self._set_active(now)

    def _set_active(self, doc: StreamDocument | None) -> None:
        """Make ``doc`` the document the status bar describes."""
        self._active = doc
        self._update_status_bar()

    def _on_document_changed(self, _doc: StreamDocument) -> None:
        """Refresh the status bar for a change of any document.

        Notes
        -----
        The emitter is ignored: :meth:`_update_status_bar` renders
        :attr:`active_document` whoever emitted, thus a guard on the emitter would be an
        invariant no behaviour distinguishes -- measured at 4 µs for a full redraw, on a
        signal which fires once per user action and never per tick or per row.
        """
        self._update_status_bar()

    def _update_status_bar(self) -> None:
        """Render the active document's fields into the three permanent segments."""
        if self._active is None:
            self._sb_state.setText("Disconnected")
            self._sb_identity.clear()
            self._sb_identity.setToolTip("")
            self._sb_meta.clear()
            return
        fields = self._active.status_fields()
        # read off the document itself: an identity is immutable, thus copying it into
        # the fields of every refresh would be one more place for it to disagree with.
        identity = self._active.identity
        self._sb_state.setText(fields["state"])
        self._sb_identity.setText(
            f"{identity.name} • {identity.stype} • {_elide(identity.source_id)}"
        )
        # the elided source ID stays recoverable, as half of an exact identity.
        self._sb_identity.setToolTip(
            f"{identity.name} • {identity.stype} • {identity.source_id}"
        )
        self._sb_meta.setText(
            " • ".join(
                (
                    fields["channels"],
                    fields["sfreq"],
                    fields["history"],
                    fields["latency"],
                )
            )
        )

    # -- theming -----------------------------------------------------------------------
    def _apply_ads_theme(self) -> None:
        """Push the docking style sheet and the docking title-bar glyphs.

        Notes
        -----
        ponytail: re-registering the glyphs colors the tabs and areas created *after* a
        theme flip, while an already-built title-bar button keeps its baked icon until
        it is rebuilt. The upgrade is to walk the live title bars and re-set the icons.
        """
        self._manager.setStyleSheet(_ADS_QSS)
        provider = self._manager.iconProvider()
        for slot, glyph in _ADS_ICONS.items():
            provider.registerCustomIcon(getattr(ads.eIcon, slot), icon(glyph))

    def _on_theme_changed(self, _mode: str) -> None:
        """Rebuild every baked icon of the window and of its documents."""
        for action, name in self._toolbar_icons:
            action.setIcon(icon(name))
        self._apply_ads_theme()
        for doc in self._documents:
            doc.retint_icons()

    def showEvent(self, event: QShowEvent) -> None:
        """Follow the theme again, and catch up whatever a flip changed while hidden.

        Notes
        -----
        The counterpart of the unfollow in :meth:`closeEvent`, and the same pair the
        trace display and the Channels page carry: a window hidden across a theme flip
        would otherwise keep the previous mode's baked toolbar icons and dock chrome.
        """
        super().showEvent(event)
        if not self._following_theme:
            follow_theme(self, self._on_theme_changed, True)
            self._on_theme_changed(theme_controller.mode)  # catch up a missed flip

    def _about(self) -> None:
        """Show the three versions a bug report needs."""
        QMessageBox.about(
            self,
            "About the MNE-LSL viewer",
            f"MNE-LSL {__version__}\nQt binding: {qtpy.API_NAME}\nQt {qVersion()}",
        )

    # -- teardown ----------------------------------------------------------------------
    def _on_document_closed(self, doc: StreamDocument) -> None:
        """Drop a closed document and retarget the status bar.

        Notes
        -----
        The document's own ``teardown`` is connected to ``closed`` by its constructor,
        thus it has already run by the time this does.

        ponytail: the closed dock widget stays in the manager's map, so one document's
        widget tree -- its curve pool, its model and its page -- lives on for the
        process, per closed document. The upgrade is ``removeDockWidget`` plus
        ``deleteLater`` from here, which leaves an invalid Python wrapper behind and is
        therefore conditioned on the PySide6 job being green first. Note
        ``deleteDockWidget`` does not exist in the PyQt6 distribution.
        """
        if doc in self._documents:
            self._documents.remove(doc)
        if self._active is doc:
            # Asked of the dock area rather than guessed as the last document opened:
            # Qt-ADS has already promoted another tab by the time this runs -- measured,
            # shown and unshown -- and its choice is not the last one as soon as three
            # are open, so the bar would describe a document which is not the visible
            # tab. The membership check covers an area emptied by a split.
            area = doc.dockAreaWidget()
            current = None if area is None else area.currentDockWidget()
            if current not in self._documents:
                current = self._documents[-1] if self._documents else None
            self._active = current
        if not self._documents:
            self._stack.setCurrentWidget(self._landing)
        self._update_status_bar()

    def close_all_documents(self) -> None:
        """Close every open document, tearing down its render clock and stream."""
        # a copy: the close handler mutates the list this iterates.
        for doc in tuple(self._documents):
            doc.closeDockWidget()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Close every document cleanly before the window closes.

        Notes
        -----
        Both stops are mandatory. Closing the window does not close the dock widgets by
        itself -- measured: no ``closed`` is emitted and every render clock keeps
        ticking -- and the ``aboutToQuit`` fallback each worker owner installs is only
        emitted when a real event loop exits, i.e. never on the path which merely shows
        the window. This is the only teardown there.
        """
        self._closed = True
        self.close_all_documents()
        self._discovery.stop()
        self._connector.stop()
        follow_theme(self, self._on_theme_changed, False)
        super().closeEvent(event)
