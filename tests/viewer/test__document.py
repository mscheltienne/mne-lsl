from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import pytest
from qtpy.QtWidgets import QMainWindow

from mne_lsl.viewer._bootstrap import configure_docking, import_ads
from mne_lsl.viewer._document import StreamDocument
from mne_lsl.viewer.backend import StreamIdentity
from mne_lsl.viewer.controller import ChannelsPage
from mne_lsl.viewer.display import TraceDisplay
from mne_lsl.viewer.theme import tokens

ads = import_ads()

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from qtpy.QtWidgets import QApplication

    from mne_lsl.stream import StreamLSL
    from mne_lsl.viewer.theme import ThemeController

# Channel names whose alphabetical order differs from the acquisition order.
# Load-bearing: on the default 'ch0...ch6 + STI0' names, an alphabetical reorder returns
# the acquisition order and a reorder test then asserts nothing at all.
_SCRAMBLED = ["zeta", "alpha", "mike", "bravo", "yankee", "charlie", "delta", "STI0"]

_FIELDS = frozenset({"state", "channels", "sfreq", "history", "latency"})


@pytest.fixture
def manager(flush_deletes: Callable[..., None]) -> Generator[ads.CDockManager]:
    """Yield a dock manager on its own host window; a document requires one.

    The flags are set before the manager is constructed because the constructor consumes
    them, and they are process-global: this is never written as a flip-and-restore.
    """
    configure_docking()
    host = QMainWindow()
    host.resize(1200, 700)
    built = ads.CDockManager(host)
    yield built
    host.close()
    flush_deletes(host)


@pytest.fixture
def document(
    manager: ads.CDockManager,
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
    flush_deletes: Callable[..., None],
) -> Generator[Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]]]:
    """Yield a factory building documents over a real stream, torn down afterwards.

    The factory takes the ``lsl_stream`` overrides plus ``owns_stream`` and returns
    ``(document, stream, push)``. The identity is built here from the stream's own
    attributes rather than with 'backend.stream_identity': that helper is code of this
    phase and must not be what validates the rest of it.
    """
    created: list[StreamDocument] = []

    def _make(
        *, owns_stream: bool = True, **kwargs: object
    ) -> tuple[StreamDocument, StreamLSL, Callable[..., None]]:
        """Build one document over a fresh stream and register it for teardown."""
        stream, push = lsl_stream(**kwargs)
        identity = StreamIdentity(stream.name, stream.stype, stream.source_id)
        doc = StreamDocument(manager, stream, identity, owns_stream=owns_stream)
        created.append(doc)
        return doc, stream, push

    yield _make
    for doc in reversed(created):
        doc.teardown()  # idempotent, and a no-op for a document already closed
    flush_deletes(*reversed(created))
    created.clear()


def _dock(manager: ads.CDockManager, doc: StreamDocument, index: int = 0) -> None:
    """Register ``doc`` in ``manager``, as the window's own registration does."""
    doc.setObjectName(f"stream-{index}")
    manager.addDockWidget(ads.DockWidgetArea.CenterDockWidgetArea, doc)


def _stim_row(doc: StreamDocument) -> int:
    """Return the model row of the stim channel of ``doc``."""
    model = doc.model
    return next(
        row for row in range(model.rowCount()) if model.channel(row).ch_type == "stim"
    )


# -- the composition: the model -> display edges --------------------------------------
def test_initial_layout_push(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that the document states the layout once, on construction.

    Pinned with a call spy and never with a row count: a fresh model produces every
    channel visible in acquisition order and the display already starts there, thus the
    two initial states are identical and an 'n_rows' assertion passes with the push
    deleted. The push is what keeps the model the single owner of the order and the
    visibility if either default ever moves.
    """
    calls: list[list[int]] = []
    monkeypatch.setattr(
        TraceDisplay,
        "set_channel_layout",
        lambda self, rows: calls.append(list(rows)),
    )
    doc, stream, _ = document()
    assert calls == [list(range(len(stream.ch_names)))]
    assert doc.trace.n_channels == len(stream.ch_names)


def test_layout_edge(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that every visibility change reaches the display, freshly read each time.

    The second mutation is what kills a '_push_layout' which cached the first list: the
    display would then keep the layout of the first change forever.
    """
    doc, _, _ = document()
    total = doc.trace.n_channels
    doc.model.set_visible([0], False)
    assert doc.trace.n_rows == total - 1
    assert doc.trace._rows == doc.model.visible_acq_indices()
    doc.model.set_visible([3], False)
    assert doc.trace.n_rows == total - 2
    assert doc.trace._rows == doc.model.visible_acq_indices()


def test_layout_edge_emits_changed(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that a layout change reports itself, so the status bar can follow.

    Without the emission the status bar keeps the channel count it had when the document
    opened -- a plausible-looking number, which is how it survives a look at the screen.
    """
    doc, _, _ = document()
    seen: list[object] = []
    doc.changed.connect(seen.append)
    doc.model.set_visible([0], False)
    assert seen == [doc]
    doc.model.set_visible([1], False)
    assert seen == [doc, doc]


def test_reorder_reorders_without_recolouring(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that a reorder moves the rows and recolors nothing.

    The color is seeded by the acquisition index, never by the row, thus the mapping
    from acquisition index to color survives the reorder while the color *of a row*
    changes, because the channel under it changed. A row-seeded color inverts both.
    """
    doc, _, _ = document(ch_names=_SCRAMBLED)
    trace = doc.trace
    rows = range(trace.n_rows)
    before = {trace._rows[row]: trace.color_for(row).name() for row in rows}
    first_row = trace.color_for(0).name()
    doc.model.order_by("alphabetical")
    assert trace._rows != list(range(trace.n_channels))
    assert [trace.channel_name(row) for row in rows] == sorted(
        _SCRAMBLED, key=str.casefold
    )
    after = {trace._rows[row]: trace.color_for(row).name() for row in rows}
    assert after == before
    assert trace.color_for(0).name() != first_row


def test_metadata_edge(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that a metadata change reaches the display without touching the layout.

    'is_bad' is asserted rather than the axis label: the ``'X '`` prefix of a bad
    channel is the axis's, not this accessor's.
    """
    doc, _, _ = document()
    trace = doc.trace
    rows, gain = list(trace._rows), list(trace._gain)
    doc.model.set_bad([0], True)
    assert trace.is_bad(0)
    doc.model.rename(0, "RENAMED")
    assert trace.channel_name(0) == "RENAMED"
    doc.model.set_type([0], "ecg")
    assert trace._gain[0] != gain[0]
    assert trace._rows == rows  # a metadata change is not a layout change


def test_hidden_stim_keeps_events(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that hiding the stim channel drops its trace and keeps its event lines.

    The overlays belong to the Events page, not to channel visibility, thus the picks
    may never simply equal the layout.
    """
    doc, _, push = document()
    trace = doc.trace
    row = _stim_row(doc)
    acq = doc.model.channel(row).acq_index
    doc.model.set_visible([row], False)
    assert acq not in trace._rows
    assert acq in trace._picks
    assert trace._event_pos
    push(stim_at=10)
    trace._render()
    assert any(line.isVisible() for line in trace._event_lines)


def test_all_hidden_placeholder(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that hiding every channel shows the placeholder and renders quietly.

    'get_data(picks=[])' raises *and* logs a bug-report line, which at 30 Hz fills the
    terminal, thus the render must return before it.
    """
    doc, _, _ = document()
    rows = range(doc.model.rowCount())
    doc.model.set_visible(rows, False)
    assert doc.trace.n_rows == 0
    assert doc.trace._empty_label.isVisible()
    assert doc.trace._assigned == {}
    doc.trace._render()  # must not raise
    doc.model.set_visible(rows, True)
    assert doc.trace.n_rows == doc.trace.n_channels
    assert not doc.trace._empty_label.isVisible()


def test_model_ownership(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that the document owns the model and the page merely borrows it.

    A model parented to the page would be destroyed with it, i.e. whenever the
    controller panel is closed, while the document keeps pushing layouts read from it.
    """
    doc, _, _ = document()
    assert doc.channels.model is doc.model
    assert doc.model.parent() is doc
    assert doc.isAncestorOf(doc.channels)
    assert doc.isAncestorOf(doc.trace)
    assert doc.channels.parent() is not doc.model


def test_single_controller_tab(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that the controller panel holds the Channels page and nothing else.

    The Processing and Events pages never call their own 'super().__init__()', thus a
    tab added for either today holds a widget which raises on its first method call.
    """
    doc, _, _ = document()
    assert doc._panel.count() == 1
    assert doc._panel.tabText(0) == "Channels"
    assert doc._panel.widget(0) is doc.channels


def test_construction_starts_the_clock(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that a constructed document is live, clock included.

    This object owns the live/frozen state while the clock lives in the display, thus a
    document whose caller has not started the clock yet reports 'Live' over a viewport
    which never advances.
    """
    doc, _, _ = document()
    assert doc.trace.running
    assert not doc.frozen
    assert doc.status_fields()["state"] == "Connected • Live"


def test_document_refuses_an_event_source(
    manager: ads.CDockManager,
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
) -> None:
    """Test that an irregularly sampled stream cannot own a document.

    Refused at the choke point both entry points meet at: the window's own connect path
    skips an event source already, while the 'BaseStream.plot()' path would otherwise
    open a document whose time axis means nothing.
    """
    stream, _ = lsl_stream(n_channels=2, sfreq=0.0, bufsize=50)
    identity = StreamIdentity(stream.name, stream.stype, stream.source_id)
    with pytest.raises(ValueError, match="irregularly sampled"):
        StreamDocument(manager, stream, identity)


def test_status_fields_documents_the_gate() -> None:
    """Test that the docstring no longer claims the gate covers a mid-disconnect read.

    'BaseStream.connected' asserts that four attributes are all set or all unset, while
    the acquisition thread clears them one at a time, so the gate itself raises
    'AssertionError' in exactly the case it was documented to handle. The root cause is
    upstream and deliberately not guarded here, thus what this phase owns is the claim.
    """
    notes = StreamDocument.status_fields.__doc__.split("Notes")[1]
    assert "may have just gone away" not in notes
    assert "AssertionError" in notes


# -- freeze and the controller toggle -------------------------------------------------
def test_freeze(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that freezing stops the clock, relabels the button and reports once.

    The button is a pause button: it reads 'Freeze' while live and 'Live' while frozen.
    'changed' emitted twice here is the missing 'blockSignals' guard around the mirror,
    which bounces the programmatic call back through 'toggled'.
    """
    doc, _, _ = document()
    seen: list[object] = []
    doc.changed.connect(seen.append)

    doc.set_frozen(True)
    assert doc.frozen
    assert not doc.trace.running
    assert "Frozen" in doc._indicator.text()
    assert doc._freeze_button.text() == "Live"
    assert doc._freeze_button.isChecked()
    assert seen == [doc]

    doc.set_frozen(False)
    assert not doc.frozen
    assert doc.trace.running
    assert "Live" in doc._indicator.text()
    assert doc._freeze_button.text() == "Freeze"
    assert not doc._freeze_button.isChecked()
    assert seen == [doc, doc]


def test_freeze_button_round_trip(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that the toolbar button drives the freeze, once per click."""
    doc, _, _ = document()
    seen: list[object] = []
    doc.changed.connect(seen.append)
    doc._freeze_button.click()
    assert doc.frozen
    assert not doc.trace.running
    assert len(seen) == 1
    doc._freeze_button.click()
    assert not doc.frozen
    assert doc.trace.running
    assert len(seen) == 2


def test_frozen_viewport_does_not_advance(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that hiding a channel while frozen leaves the frozen window on screen.

    Freeze stops the render clock and nothing else, thus a layout push used to run a
    fetch of its own and jump the viewport to the newest samples: the frozen document
    silently showed twice the samples it had been frozen on, still labelled 'Frozen'.
    """
    doc, _, push = document()
    trace = doc.trace
    push(50)
    trace._render()
    row = trace._rows.index(5)
    before = trace._assigned[row].getData()[1].copy()

    doc.set_frozen(True)
    push(50)  # the acquisition keeps running while the viewport is frozen
    doc.model.set_visible([0], False)
    assert doc.frozen
    assert not trace.running
    row = trace._rows.index(5)
    assert np.array_equal(trace._assigned[row].getData()[1], before)

    doc.set_frozen(False)
    trace._render()
    row = trace._rows.index(5)
    assert not np.array_equal(trace._assigned[row].getData()[1], before)


def test_frozen_rows_change_keeps_the_traces(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that the row stepper repaints a frozen document instead of emptying it.

    The row count rebuilds the curve pool, thus a frozen document left the plot with no
    curves and no placeholder while the status bar went on reporting '4/16 ch'.
    """
    doc, _, push = document(n_channels=16)
    trace = doc.trace
    push(50)
    trace._render()
    doc.set_frozen(True)
    trace.controls.set_rows(4)
    assert doc.status_fields()["channels"] == "4/16 ch"
    assert not trace._empty_label.isVisible()
    assert trace._assigned
    for drawn, curve in trace._assigned.items():
        assert curve.getData()[1].size, drawn


def test_controller_visible(
    app: QApplication,
    manager: ads.CDockManager,
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that hiding the controller collapses it and showing it restores its width.

    The document is docked and the host shown on purpose: a splitter holds no real size
    until it has been laid out.

    The width coming back is the splitter's own memory of a hidden child, measured and
    not assumed -- the document deliberately saves nothing. What this pins is therefore
    the user-visible contract, and an explicit 'setSizes' added to the toggle is what
    would break it.
    """
    doc, _, _ = document()
    assert doc.controller_visible
    _dock(manager, doc)
    manager.window().show()
    app.processEvents()
    before = doc._splitter.sizes()
    assert before[0] > 0

    doc.set_controller_visible(False)
    app.processEvents()
    assert not doc.controller_visible
    assert doc._panel.isHidden()
    assert not doc._controller_button.isChecked()
    assert doc._splitter.sizes()[0] == 0

    doc.set_controller_visible(True)
    app.processEvents()
    assert doc.controller_visible
    assert doc._controller_button.isChecked()
    assert doc._splitter.sizes() == before


def test_controller_button_round_trip(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that the toolbar button drives the controller visibility both ways."""
    doc, _, _ = document()
    assert doc._controller_button.isChecked()
    doc._controller_button.click()
    assert not doc.controller_visible
    doc._controller_button.click()
    assert doc.controller_visible


# -- the status-bar fields ------------------------------------------------------------
def test_status_fields_live(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test the fields of a live document, counts and formatting included.

    The channel counts are asserted with the displayed count differing from the total
    and then with the viewport smaller than the layout, which is what a swap of the two,
    or a read of either alone, cannot survive.
    """
    doc, _, _ = document(bufsize=6.0)
    fields = doc.status_fields()
    assert set(fields) == _FIELDS
    assert fields["state"] == "Connected • Live"
    assert fields["channels"] == "8/8 ch"
    assert fields["sfreq"] == "100 Hz"
    assert fields["history"] == "6 s history"
    assert fields["latency"] == "No processing • 0 ms"

    doc.model.set_visible([0, 1, 2], False)
    assert doc.status_fields()["channels"] == "5/8 ch"
    doc.trace.controls.set_rows(3)
    assert doc.status_fields()["channels"] == "3/8 ch"

    doc.set_frozen(True)
    assert doc.status_fields()["state"] == "Connected • Frozen"


def test_status_fields_disconnected(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that a disconnected stream reports its state without being read.

    Both 'info' and 'n_buffer' raise on a disconnected stream, and this is the path the
    connection-loss handling walks into.
    """
    doc, stream, _ = document()
    stream.disconnect()
    fields = doc.status_fields()
    assert set(fields) == _FIELDS
    assert fields["state"] == "Disconnected"
    for key in ("channels", "sfreq", "history", "latency"):
        assert fields[key] == "—", key


# -- teardown -------------------------------------------------------------------------
def test_teardown_owned(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that tearing an owned document down stops the clock and the stream.

    The second call is not decoration: a second 'disconnect()' raises 'RuntimeError',
    and the window's close loop reaches every document after its own 'closed' handler
    already did. Both children are asserted closed through their theme connection, which
    is what their own 'closeEvent' drops.
    """
    doc, stream, _ = document()
    doc.teardown()
    assert not doc.trace.running
    assert not doc.trace._following_theme
    assert not doc.channels._following_theme
    assert not stream.connected
    doc.teardown()
    assert not stream.connected


def test_teardown_closes_each_child_once(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that a second teardown closes neither child again.

    The idempotence guard is load-bearing and no state the other teardown tests read can
    tell: 'TraceDisplay.closeEvent' latches whether it stopped a *running* clock, which
    is what a later 'showEvent' restarts it from, so a second close latches 'False' over
    it and the display comes back frozen on its last frame forever.
    """
    closed: list[str] = []
    for cls, name in ((TraceDisplay, "trace"), (ChannelsPage, "channels")):
        original = cls.close

        def _close(self, _original=original, _name=name) -> bool:
            closed.append(_name)
            return _original(self)

        monkeypatch.setattr(cls, "close", _close)
    doc, _, _ = document()
    doc.teardown()
    assert closed == ["trace", "channels"]
    assert doc.trace._was_running
    doc.teardown()
    assert closed == ["trace", "channels"]
    assert doc.trace._was_running


def test_teardown_closes_the_children_before_the_stream(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that the stream is released only once both children are closed.

    The order is the whole point of the sequence: a render tick or a metadata read
    arriving between the disconnect and the display's close would reach a stream going
    away, and 'BaseStream' raises on nearly every attribute there.
    """
    doc, stream, _ = document()
    order: list[str] = []
    for cls, name in ((TraceDisplay, "trace"), (ChannelsPage, "channels")):
        original = cls.close

        def _close(self, _original=original, _name=name) -> bool:
            order.append(_name)
            return _original(self)

        monkeypatch.setattr(cls, "close", _close)
    disconnect = stream.disconnect

    def _disconnect() -> None:
        order.append("disconnect")
        disconnect()

    monkeypatch.setattr(stream, "disconnect", _disconnect)
    doc.teardown()
    assert order == ["trace", "channels", "disconnect"]
    assert not stream.connected


def test_teardown_borrowed(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that a borrowed stream survives the document it was shown in.

    This is the 'BaseStream.plot()' contract: the caller owns the stream and closing the
    viewer must leave it connected.
    """
    doc, stream, _ = document(owns_stream=False)
    assert not doc.owns_stream
    doc.teardown()
    assert not doc.trace.running
    assert stream.connected


def test_teardown_breaks_the_model_edge(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that a layout change after the teardown reaches the closed display no more.

    The model outlives the document's widgets, so a push arriving afterwards draws into
    a display nobody can see. Asserted over a *borrowed* stream, the case which is not
    benign: an owned one is disconnected by the teardown and the render returns on that,
    while a borrowed one is still connected and the fetch goes through.
    """
    doc, stream, _ = document(owns_stream=False)
    doc.teardown()
    assert stream.connected
    rows, gain = list(doc.trace._rows), list(doc.trace._gain)
    seen: list[object] = []
    doc.changed.connect(seen.append)
    doc.model.set_visible([0], False)
    doc.model.set_type([1], "ecg")
    assert doc.trace._rows == rows
    assert doc.trace._gain == gain
    assert seen == []


def test_set_frozen_is_inert_after_the_teardown(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that resuming a torn-down document does not restart its render clock.

    Asserted over a *borrowed* stream, the case which is not benign: the teardown leaves
    it connected, so a restarted clock fetches real windows and draws them into a closed
    display -- and nothing is left to stop that clock again.
    """
    doc, stream, _ = document(owns_stream=False)
    doc.teardown()
    assert not doc.trace.running
    seen: list[object] = []
    doc.changed.connect(seen.append)
    doc.set_frozen(False)
    assert not doc.trace.running
    doc.set_frozen(True)
    assert not doc.trace.running
    assert seen == []
    assert stream.connected


def test_teardown_via_closed_signal(
    manager: ads.CDockManager,
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that closing the dock widget tears the document down exactly once.

    Qt-ADS delivers no close event to the content widget, thus nothing but this signal
    stops the render clock; and it emits 'closed' once even for two close calls, so the
    count also pins the guard.
    """
    calls: list[object] = []
    original = StreamDocument.teardown

    def _counting(self: StreamDocument) -> None:
        calls.append(self)
        original(self)

    monkeypatch.setattr(StreamDocument, "teardown", _counting)
    doc, stream, _ = document()
    _dock(manager, doc)
    doc.closeDockWidget()
    doc.closeDockWidget()
    assert len(calls) == 1
    assert doc.isClosed()
    assert not doc.trace.running
    assert not stream.connected


def test_teardown_survives_a_failing_disconnect(
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that a stream whose 'disconnect()' raises does not abort the teardown.

    A window close tears every document down in one loop, thus an escaping exception
    here would abandon every document after this one -- with its clock still ticking and
    its stream still connected.
    """
    doc, stream, _ = document()

    def _raise() -> None:
        raise RuntimeError("boom on disconnect")

    monkeypatch.setattr(stream, "disconnect", _raise)
    caplog.set_level(logging.WARNING, logger="mne_lsl")
    doc.teardown()
    assert not doc.trace.running
    assert "boom on disconnect" in caplog.text
    # undone here, and not left to the fixture ordering: the stream fixture disconnects
    # what is still connected at teardown, and it must not meet the raising stand-in.
    monkeypatch.undo()
    assert stream.connected


# -- theming --------------------------------------------------------------------------
def test_retint_icons(
    app: QApplication,
    controller: ThemeController,
    document: Callable[..., tuple[StreamDocument, StreamLSL, Callable[..., None]]],
) -> None:
    """Test that a theme flip repaints the indicator and rebuilds the toolbar icons.

    A 'QIcon' bakes its color at creation and 'qtawesome' memoizes on the icon name
    alone, thus the rendered pixmap is what has to change; and the indicator carries the
    mode's own status color rather than the one the other mode left behind.
    """
    doc, _, _ = document()
    controller.install(app, "light")
    doc.retint_icons()
    light_style = doc._indicator.styleSheet()
    light_icons = [
        button.icon().pixmap(16, 16).toImage()
        for button in (doc._freeze_button, doc._controller_button, doc._close_button)
    ]
    controller.set_mode("dark")
    doc.retint_icons()
    dark_style = doc._indicator.styleSheet()
    dark_icons = [
        button.icon().pixmap(16, 16).toImage()
        for button in (doc._freeze_button, doc._controller_button, doc._close_button)
    ]
    assert tokens("light").success in light_style
    assert tokens("dark").success in dark_style
    for index, (before, after) in enumerate(zip(light_icons, dark_icons, strict=True)):
        assert not before.isNull()
        assert before != after, index
