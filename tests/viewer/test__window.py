from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from qtpy.QtWidgets import QMessageBox

from mne_lsl.stream import StreamLSL
from mne_lsl.viewer import _window
from mne_lsl.viewer._bootstrap import import_ads
from mne_lsl.viewer._document import StreamDocument
from mne_lsl.viewer._launcher import PROGRESS_TEXT
from mne_lsl.viewer.backend import (
    Connector,
    Discovery,
    StreamDescriptor,
    StreamIdentity,
)
from mne_lsl.viewer.display import WINDOW_RANGE
from mne_lsl.viewer.theme import _ADS_ICONS, _MODES

ads = import_ads()

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytestqt.qtbot import QtBot
    from qtpy.QtWidgets import QApplication

    from mne_lsl.viewer._window import ViewerWindow
    from mne_lsl.viewer.theme import ThemeController


def _descriptor_for(
    stream: StreamLSL, *, source_id: str | None = None
) -> StreamDescriptor:
    """Return a descriptor for a stream the fixture created.

    Deliberately not built with 'backend.stream_identity': that helper is code of this
    phase and must not be what validates the rest of it.
    """
    return StreamDescriptor(
        identity=StreamIdentity(
            name=stream.name,
            stype=stream.stype,
            source_id=stream.source_id if source_id is None else source_id,
        ),
        n_channels=len(stream.ch_names),
        sfreq=stream.info["sfreq"],
        hostname="localhost",
        dtype="float32",
    )


def _open(
    window: ViewerWindow, stream: StreamLSL, *, source_id: str | None = None
) -> StreamDocument:
    """Open one document for ``stream``, through the connector's own callback.

    Every test but the end-to-end one drives this path rather than the network: the
    connector is what hands a connected stream over, and this is the slot it hands to.
    """
    descriptor = _descriptor_for(stream, source_id=source_id)
    window._on_connected(descriptor, stream)
    return window.documents[-1]


def _spy_open(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[tuple[StreamDescriptor, ...], float]]:
    """Record every 'Connector.open' call instead of connecting anything."""
    calls: list[tuple[tuple[StreamDescriptor, ...], float]] = []
    monkeypatch.setattr(
        Connector,
        "open",
        lambda self, descriptors, bufsize: calls.append((tuple(descriptors), bufsize)),
    )
    return calls


# -- the landing page and the workspace ------------------------------------------------
def test_landing_first(window: ViewerWindow) -> None:
    """Test that a fresh window shows the launcher and not an empty workspace."""
    assert window._stack.currentWidget() is window._landing
    assert window.documents == ()
    assert window.active_document is None
    assert window._sb_state.text() == "Disconnected"
    assert window._sb_identity.text() == ""
    assert window._sb_meta.text() == ""


def test_window_configures_the_docking_flags(
    flush_deletes: Callable[..., None], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that the window sets the docking flags itself, before its dock manager.

    Spied, and not read back off 'CDockManager': the flags are process-global static
    state, thus any earlier test which set them leaves a window which never configures
    them indistinguishable -- and the reading form then passes in every collection order
    but the one where this module runs first.
    """
    calls: list[int] = []
    original = _window.configure_docking

    def _configure() -> None:
        calls.append(1)
        original()

    monkeypatch.setattr(_window, "configure_docking", _configure)
    built = _window.ViewerWindow()
    try:
        assert calls == [1]
    finally:
        built.close()
        flush_deletes(built)


def test_focus_highlighting_is_live(
    app: QApplication,
    window: ViewerWindow,
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
) -> None:
    """Test that the focus signal really fires, i.e. the docking flags were set in time.

    The behavioural proxy for 'the flags were set before the manager was constructed':
    with 'FocusHighlighting' off at construction the signal never fires, and switching
    it on afterwards crashes the process on the next 'addDockWidget'.

    Two documents over **one** stream: what a second document needs here is a second
    identity, not a second connection, and a connection is 1.68 s of liblsl handshake.
    """
    seen: list[object] = []
    window._manager.focusedDockWidgetChanged.connect(lambda _old, now: seen.append(now))
    stream, _ = lsl_stream()
    first = _open(window, stream, source_id="unit-1")
    second = _open(window, stream, source_id="unit-2")
    window.show()
    app.processEvents()
    seen.clear()
    window._raise(first)
    app.processEvents()
    assert seen
    assert window._manager.focusedDockWidget() in (first, second)


def test_open_streams_connects_and_opens(
    window: ViewerWindow,
    qtbot: QtBot,
    outlets: Callable[..., StreamDescriptor],
) -> None:
    """Test the whole connect path, once, against a real outlet on the network.

    The one test which goes through discovery and the connector thread: a mis-called
    buffer derivation, a missing connector connection or a document which is never
    registered all surface here and nowhere else. Kept to exactly one test because the
    liblsl resolution is intermittently flaky under parallel load.

    The 'failed' signal is watched as well, so that a connection which liblsl lost the
    race for reports its own reason instead of an opaque wait timeout:
    'StreamLSL.connect' applies a 2 s timeout to the resolution, which a loaded machine
    can exceed.
    """
    descriptor = outlets(n_channels=3, ch_names=["Fp1", "Fp2", "Cz"])
    failures: list[str] = []
    window._connector.failed.connect(lambda _d, message: failures.append(message))
    window.open_streams([descriptor])
    qtbot.waitUntil(lambda: len(window.documents) == 1 or bool(failures), timeout=20000)
    assert not failures, failures
    doc = window.documents[0]
    assert doc.identity == descriptor.identity
    assert doc.owns_stream
    assert doc.stream.connected
    assert doc.trace.running
    assert window._stack.currentWidget() is window._dock_host
    assert window.active_document is doc


def test_open_streams_derives_bufsize(
    window: ViewerWindow,
    descriptor: Callable[..., StreamDescriptor],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that the batch carries a buffer covering the widest selectable window.

    A hardcoded size, or the *current* window instead of the maximum, leaves the display
    drawing over part of its time axis as soon as the window is widened.

    The derivation is spied rather than recomputed: 'derive_bufsize(WINDOW_RANGE[1])' is
    30.0 today, thus asserting the value alone passes with the literal '30.0' written at
    the call site -- the second-literal failure the shared bound exists to prevent.
    """
    calls = _spy_open(monkeypatch)
    derived: list[float] = []
    original = _window.derive_bufsize

    def _derive(seconds: float) -> float:
        derived.append(seconds)
        return original(seconds)

    monkeypatch.setattr(_window, "derive_bufsize", _derive)
    entry = descriptor()
    window.open_streams([entry])
    assert len(calls) == 1
    wanted, bufsize = calls[0]
    assert wanted == (entry,)
    assert derived == [WINDOW_RANGE[1]]
    assert bufsize == original(WINDOW_RANGE[1])
    assert bufsize >= WINDOW_RANGE[1]
    assert bufsize == int(bufsize)


def test_open_streams_skips_event_sources(
    window: ViewerWindow,
    descriptor: Callable[..., StreamDescriptor],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that an event source is never connected as a document.

    'StreamLSL' refuses a buffer in seconds for an irregularly sampled stream, thus the
    user would see an unexplained connection error for a stream the launcher lists.
    """
    calls = _spy_open(monkeypatch)
    window.open_streams([descriptor(sfreq=0.0)])
    assert calls == []
    assert window.documents == ()
    # a regular descriptor in the same batch is still opened.
    regular = descriptor()
    window.open_streams([descriptor(sfreq=0.0), regular])
    assert len(calls) == 1
    assert calls[0][0] == (regular,)


def test_open_streams_raises_an_open_identity(
    window: ViewerWindow,
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that opening an identity which is already open raises its document.

    Without the de-duplication the same stream gets two documents, two channel models
    and two render clocks.

    Two documents over one stream: distinct identities are what this needs, and each
    connection is 1.68 s of liblsl handshake.
    """
    stream, _ = lsl_stream()
    first = _open(window, stream, source_id="unit-1")
    second = _open(window, stream, source_id="unit-2")
    assert window.active_document is second
    calls = _spy_open(monkeypatch)
    window.open_streams(
        [_descriptor_for(first.stream, source_id=first.identity.source_id)]
    )
    assert calls == []
    assert len(window.documents) == 2
    assert window.active_document is first


def test_open_streams_dedups_in_flight(
    window: ViewerWindow,
    descriptor: Callable[..., StreamDescriptor],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that two opens of one identity back to back connect it once.

    A double click on 'Open selected' would otherwise connect the same stream twice, and
    the second stream is then released -- an inlet and its acquisition thread built for
    nothing.
    """
    calls = _spy_open(monkeypatch)
    entry = descriptor()
    window.open_streams([entry])
    window.open_streams([entry])
    assert len(calls) == 1


def test_open_streams_merges_the_batch_in_flight(
    window: ViewerWindow,
    descriptor: Callable[..., StreamDescriptor],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that a second Open carries the still-connecting streams with it.

    'Connector.open' bumps its generation counter, i.e. it supersedes the batch in
    flight instead of queueing behind it. Submitting only the new selection therefore
    drops the stream the user asked for first -- and its identity is then in flight
    forever, so it can never be opened again for the life of the process.
    """
    calls = _spy_open(monkeypatch)
    first, second = descriptor(name="first"), descriptor(name="second")
    window.open_streams([first])
    window.open_streams([second])
    assert len(calls) == 2
    assert calls[0][0] == (first,)
    assert calls[1][0] == (first, second)
    assert set(window._connecting) == {first.identity, second.identity}


def test_a_failure_survives_a_sibling_success(
    window: ViewerWindow,
    descriptor: Callable[..., StreamDescriptor],
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that the success of one stream does not wipe the failure of its sibling.

    The status bar is the only error surface of a failed connection, thus a batch which
    clears it unconditionally when the last outcome comes back tells the user nothing at
    all about the stream which failed.
    """
    _spy_open(monkeypatch)
    stream, _ = lsl_stream()
    good = _descriptor_for(stream)
    bad = descriptor(name="unreachable")
    window.open_streams([bad, good])
    assert window.statusBar().currentMessage() == "Connecting to 2 stream(s)…"
    window._on_failed(bad, "boom")
    window._on_connected(good, stream)
    message = window.statusBar().currentMessage()
    assert "unreachable" in message
    assert "boom" in message
    assert window._connecting == {}
    assert len(window.documents) == 1


def test_a_completed_batch_clears_its_own_message(
    window: ViewerWindow,
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that a clean batch empties the in-flight map and takes its message away."""
    _spy_open(monkeypatch)
    stream, _ = lsl_stream()
    entry = _descriptor_for(stream)
    window.open_streams([entry])
    assert window.statusBar().currentMessage()
    window._on_connected(entry, stream)
    assert window._connecting == {}
    assert window.statusBar().currentMessage() == ""


def test_on_connected_releases_a_duplicate(
    window: ViewerWindow,
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
) -> None:
    """Test that a stream arriving for an identity already open is disconnected.

    The connector transfers ownership with its signal, thus returning without
    disconnecting leaks a live inlet plus its acquisition thread for the whole process,
    invisibly.
    """
    first, _ = lsl_stream()
    late, _ = lsl_stream()
    descriptor = _descriptor_for(first)
    window._on_connected(descriptor, first)
    assert len(window.documents) == 1
    window._on_connected(descriptor, late)
    assert len(window.documents) == 1
    assert not late.connected
    assert first.connected


def test_documents_tab_together(
    window: ViewerWindow,
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
) -> None:
    """Test that every document lands in one dock area: tabs, not stacked panes.

    Three documents over one stream: three identities are what this needs, and each
    connection is 1.68 s of liblsl handshake.
    """
    stream, _ = lsl_stream()
    docs = [_open(window, stream, source_id=f"unit-{index}") for index in range(3)]
    areas = {doc.dockAreaWidget() for doc in docs}
    assert len(areas) == 1
    assert window._manager.dockAreaCount() == 1


def test_object_names_unique_over_the_process(
    window: ViewerWindow,
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
) -> None:
    """Test that a closed document never frees its name for a later one.

    Qt-ADS keeps a closed dock widget in its map forever, thus a counter derived from
    the number of *open* documents reuses a name which is still taken -- measured to
    lose a map entry and to write an ambiguous saved layout.

    Two streams and three documents, and not one stream for all three: closing 'first'
    disconnects the stream it owns, thus the last document would then build a channel
    model over a dead stream.
    """
    first = _open(window, lsl_stream()[0])
    survivor, _ = lsl_stream()
    second = _open(window, survivor, source_id="unit-2")
    first.closeDockWidget()
    third = _open(window, survivor, source_id="unit-3")
    names = {doc.objectName() for doc in (first, second, third)}
    assert len(names) == 3
    assert len(window._manager.dockWidgetsMap()) == 3


# -- the status bar --------------------------------------------------------------------
def test_status_bar_follows_focus(
    window: ViewerWindow,
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
) -> None:
    """Test that the status bar retargets to whichever document became active."""
    first = _open(window, lsl_stream(n_channels=8, sfreq=100.0)[0])
    second = _open(window, lsl_stream(n_channels=5, sfreq=250.0)[0])
    window._set_active(first)
    assert "8/8 ch" in window._sb_meta.text()
    assert "100 Hz" in window._sb_meta.text()
    assert first.identity.name in window._sb_identity.text()
    window._set_active(second)
    assert "5/5 ch" in window._sb_meta.text()
    assert "250 Hz" in window._sb_meta.text()
    assert "100 Hz" not in window._sb_meta.text()
    assert second.identity.name in window._sb_identity.text()


def test_status_bar_follows_document_changed(
    window: ViewerWindow,
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
) -> None:
    """Test that the shared status bar follows the active document's own changes.

    What it pins is the outcome, not the guard in the handler: the bar is always drawn
    from the active document, thus a background document freezing cannot change it
    either way. Dropping the 'changed' connection altogether is what this catches.

    Two documents over one stream: distinct identities are what this needs, and each
    connection is 1.68 s of liblsl handshake.
    """
    stream, _ = lsl_stream()
    first = _open(window, stream, source_id="unit-1")
    second = _open(window, stream, source_id="unit-2")
    assert window.active_document is second
    second.set_frozen(True)
    assert "Frozen" in window._sb_state.text()
    second.set_frozen(False)
    assert "Live" in window._sb_state.text()
    before = window._sb_state.text()
    first.set_frozen(True)
    assert window._sb_state.text() == before


def test_status_bar_identity_elided_with_tooltip(
    window: ViewerWindow,
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
) -> None:
    """Test that a long source ID is shortened in the label and kept in the tooltip.

    The full value has to stay recoverable from the interface: it is half of what makes
    an identity exact.
    """
    source_id = "source-" + "x" * 40
    doc = _open(window, lsl_stream()[0], source_id=source_id)
    assert doc.identity.source_id == source_id
    assert source_id not in window._sb_identity.text()
    assert "…" in window._sb_identity.text()
    assert source_id in window._sb_identity.toolTip()
    assert doc.identity.name in window._sb_identity.toolTip()


def test_progress_reaches_both_surfaces(window: ViewerWindow) -> None:
    """Test that a discovery tag reaches the launcher label and the status bar alike."""
    window._on_progress("checking")
    assert window._landing._progress.text() == PROGRESS_TEXT["checking"]
    assert window.statusBar().currentMessage() == PROGRESS_TEXT["checking"]
    # an unknown tag must not raise from inside a Qt slot.
    window._on_progress("some-new-tag")
    assert window._landing._progress.text() == "some-new-tag"
    assert window.statusBar().currentMessage() == "some-new-tag"


def test_open_action_tracks_selection(
    window: ViewerWindow, descriptor: Callable[..., StreamDescriptor]
) -> None:
    """Test that the Open action follows the selection, and a pass which replaced it.

    A discovery pass rebuilds the table under the selection, thus the action has to be
    re-evaluated with no user interaction at all.
    """
    assert not window._act_open.isEnabled()
    window._on_streams_found([descriptor(name="a"), descriptor(name="b")])
    assert not window._act_open.isEnabled()
    window._landing._table.selectRow(0)
    assert window._act_open.isEnabled()
    window._on_streams_found([])
    assert not window._act_open.isEnabled()


def test_failed_connection_keeps_documents(
    window: ViewerWindow,
    descriptor: Callable[..., StreamDescriptor],
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
) -> None:
    """Test that a failed connection is reported without touching what is open.

    One stable error surface: a status message naming the stream, and no dialog to
    dismiss per failed stream of a batch.
    """
    doc = _open(window, lsl_stream()[0])
    failing = descriptor(name="unreachable")
    window._on_failed(failing, "boom")
    assert window.documents == (doc,)
    assert doc.stream.connected
    message = window.statusBar().currentMessage()
    assert "unreachable" in message
    assert "boom" in message
    assert window.findChildren(QMessageBox) == []


def test_refresh_clears_the_error_surface(
    window: ViewerWindow,
    descriptor: Callable[..., StreamDescriptor],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that a refresh takes the previous failure off the status bar.

    A failed connection is shown with no timeout and no dialog, thus the next refresh or
    open is the only thing which ends it: without this the bar goes on naming a stream
    the user has since asked the network for again. The discovery pass itself is stubbed
    out, as a real one costs a second and the close waits for it.
    """
    monkeypatch.setattr(Discovery, "refresh", lambda self: None)
    window._on_failed(descriptor(name="unreachable"), "boom")
    assert "unreachable" in window.statusBar().currentMessage()
    window.refresh()
    assert window.statusBar().currentMessage() == ""


# -- the borrowed-stream path ---------------------------------------------------------
def test_adopt_stream_borrows(
    window: ViewerWindow,
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
) -> None:
    """Test that an adopted stream is borrowed and survives its document.

    This is the 'BaseStream.plot()' contract seen from the window: defaulting the
    ownership to 'True' here would disconnect a stream the caller still owns.
    """
    stream, _ = lsl_stream()
    doc = window.adopt_stream(stream)
    assert not doc.owns_stream
    assert doc.identity == StreamIdentity(stream.name, stream.stype, stream.source_id)
    assert doc.trace.running
    doc.closeDockWidget()
    assert stream.connected
    assert window.documents == ()


def test_adopt_stream_rejects(
    window: ViewerWindow,
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
) -> None:
    """Test that only a connected, regularly sampled LSL stream can be adopted, once.

    The sampling-rate refusal is the 'BaseStream.plot()' path: 'open_streams' skips an
    event source before it can reach a document, thus without the check at the document
    itself the public path opens a viewer which cannot draw the stream it was handed.
    """
    with pytest.raises(TypeError, match="only open a document for an LSL stream"):
        window.adopt_stream(object())
    with pytest.raises(RuntimeError, match="only known once it is connected"):
        window.adopt_stream(StreamLSL(2.0, name="mne-lsl-viewer-absent"))
    assert window.documents == ()
    event_source, _ = lsl_stream(n_channels=2, sfreq=0.0, bufsize=50)
    with pytest.raises(ValueError, match="irregularly sampled"):
        window.adopt_stream(event_source)
    assert window.documents == ()
    stream, _ = lsl_stream()
    doc = window.adopt_stream(stream)
    assert window.adopt_stream(stream) is doc
    assert len(window.documents) == 1


# -- theming --------------------------------------------------------------------------
def test_theme_flip_reskins_and_retints(
    app: QApplication,
    controller: ThemeController,
    window: ViewerWindow,
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that a theme flip reaches the toolbar, the dock chrome and every document.

    A 'QIcon' bakes its color at creation, thus the rendered pixmaps are what has to
    change -- for the toolbar actions and for the docking title-bar glyphs alike.

    The docking *glyphs* are what pins the dock re-skin: the style sheet is a static
    string installed by the constructor and never cleared, so asserting on it passes
    with the whole re-skin deleted from the flip handler.
    """
    doc = _open(window, lsl_stream()[0])
    controller.install(app, "light")
    light = [
        action.icon().pixmap(16, 16).toImage() for action, _ in window._toolbar_icons
    ]
    assert len(light) == len(window._toolbar_icons)
    assert all(not image.isNull() for image in light)
    provider = window._manager.iconProvider()
    light_ads = {
        slot: provider.customIcon(getattr(ads.eIcon, slot)).pixmap(16, 16).toImage()
        for slot in _ADS_ICONS
    }
    assert all(not image.isNull() for image in light_ads.values())
    retinted: list[object] = []
    monkeypatch.setattr(
        StreamDocument, "retint_icons", lambda self: retinted.append(self)
    )
    controller.set_mode("dark")
    dark = [
        action.icon().pixmap(16, 16).toImage() for action, _ in window._toolbar_icons
    ]
    assert "ads--CDockWidgetTab" in window._manager.styleSheet()
    for index, (before, after) in enumerate(zip(light, dark, strict=True)):
        assert before != after, index
    for slot, before in light_ads.items():
        after = provider.customIcon(getattr(ads.eIcon, slot)).pixmap(16, 16).toImage()
        assert before != after, slot
    assert retinted == [doc]


def test_theme_toggle_offers_every_mode() -> None:
    """Test that the toggle segments are the theme vocabulary itself, in its order.

    The index of the current setting is looked up in the shared tuple, thus a segment
    list which disagreed with it would raise from the constructor, or leave the
    highlight on a mode which is not the one in effect.
    """
    assert tuple(setting for _, _, setting in _window._THEME_SEGMENTS) == _MODES


def test_closed_window_stops_following_the_theme(
    app: QApplication, controller: ThemeController, window: ViewerWindow
) -> None:
    """Test that a closed window no longer re-themes itself on an OS theme flip.

    The theme controller is a process singleton and 'Viewer' holds its window forever,
    thus a closed one which stayed connected keeps rebuilding the icons of a dead
    toolbar -- and its documents are torn down by then, so nobody can see any of it.
    """
    controller.install(app, "light")
    window.close()
    assert not window._following_theme
    before = [
        action.icon().pixmap(16, 16).toImage() for action, _ in window._toolbar_icons
    ]
    controller.set_mode("dark")
    after = [
        action.icon().pixmap(16, 16).toImage() for action, _ in window._toolbar_icons
    ]
    for index, (closed, flipped) in enumerate(zip(before, after, strict=True)):
        assert closed == flipped, index


def test_reshown_window_follows_the_theme_again(
    app: QApplication, controller: ThemeController, window: ViewerWindow
) -> None:
    """Test that a window shown after a close reconnects and catches the flip it missed.

    The required counterpart of dropping the connection on close: a window put back on
    screen without it would keep the icons of whichever mode was current when it closed,
    for the rest of the process.
    """
    controller.install(app, "light")
    light = window._toolbar_icons[0][0].icon().pixmap(16, 16).toImage()
    window.close()
    controller.set_mode("dark")  # flipped while the window was not listening
    window.show()
    assert window._following_theme
    assert window._toolbar_icons[0][0].icon().pixmap(16, 16).toImage() != light


# -- teardown -------------------------------------------------------------------------
def test_last_document_returns_to_landing(
    window: ViewerWindow,
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
) -> None:
    """Test that closing the last document brings the launcher back."""
    doc = _open(window, lsl_stream()[0])
    assert window._stack.currentWidget() is window._dock_host
    doc.closeDockWidget()
    assert window.documents == ()
    assert window.active_document is None
    assert window._stack.currentWidget() is window._landing
    assert window._sb_state.text() == "Disconnected"
    assert window._sb_meta.text() == ""


def test_closing_the_active_document_follows_the_tab(
    window: ViewerWindow,
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
) -> None:
    """Test that the status bar retargets to the tab Qt-ADS promoted, not to a guess.

    Closing the current tab makes the docking system promote another one, and it is not
    the last document opened: with three open it promotes the *first*. A guess therefore
    leaves the shared bar describing a document which is not the one on screen.
    """
    stream, _ = lsl_stream()
    docs = [_open(window, stream, source_id=f"unit-{index}") for index in range(3)]
    assert window.active_document is docs[2]
    docs[2].closeDockWidget()
    promoted = docs[0].dockAreaWidget().currentDockWidget()
    assert promoted in docs[:2]
    assert window.active_document is promoted


def test_close_all_documents(
    window: ViewerWindow,
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
) -> None:
    """Test that every document is closed, and not every other one.

    Iterating the live list while the close handler removes from it skips half of them.

    Three documents over one stream: the per-document assertion is on the render clock,
    which is one object per document, and it is what a list-mutation bug shows up in --
    the connection is shared, thus asserting it thrice would assert one object thrice.
    """
    stream, _ = lsl_stream()
    docs = [_open(window, stream, source_id=f"unit-{index}") for index in range(3)]
    window.close_all_documents()
    assert window.documents == ()
    for doc in docs:
        assert not doc.trace.running
    assert not stream.connected


def test_close_event_closes_documents(
    window: ViewerWindow,
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
) -> None:
    """Test that closing the window tears its documents down.

    Measured: neither the window nor the dock host closes the dock widgets by itself,
    thus without this loop every clock keeps ticking and every stream stays connected.
    """
    doc = _open(window, lsl_stream()[0])
    window.close()
    assert window.documents == ()
    assert not doc.trace.running
    assert not doc.stream.connected


def test_close_event_stops_the_workers(
    window: ViewerWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that both workers are stopped by the window closing.

    The 'aboutToQuit' fallback each worker owner installs needs a running event loop,
    i.e. it never fires on the path which merely shows the window, thus this is the only
    teardown there.
    """
    stopped: list[str] = []
    for cls in (Discovery, Connector):
        original = cls.stop

        def _stop(self, _original=original, _name=cls.__name__) -> None:
            stopped.append(_name)
            _original(self)

        monkeypatch.setattr(cls, "stop", _stop)
    window.refresh()
    assert window._discovery._thread.isRunning()
    window.close()
    assert stopped == ["Discovery", "Connector"]
    assert not window._discovery._thread.isRunning()
    assert not window._connector._thread.isRunning()


def test_refresh_after_a_close_starts_no_worker(window: ViewerWindow) -> None:
    """Test that a closed window starts no discovery pass, and reports itself as closed.

    'Discovery.refresh' starts its worker thread on demand and 'closeEvent' is the whole
    teardown, thus a pass asked for afterwards leaves a running thread which nothing
    will ever stop.
    """
    assert not window.closed
    window.close()
    assert window.closed
    window.refresh()
    assert not window._discovery._thread.isRunning()
