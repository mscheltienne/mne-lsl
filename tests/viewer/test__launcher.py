from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from qtpy.QtCore import QItemSelectionModel, Qt
from qtpy.QtWidgets import QAbstractItemView

import mne_lsl.viewer._launcher
from mne_lsl.viewer._launcher import PROGRESS_TEXT, EmptyStatePage

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from types import ModuleType

    from mne_lsl.viewer.backend import StreamDescriptor

# Nothing the page may name: it lists what it is given, reports what it is told and
# resolves nothing itself. This is the property the whole design rests on -- the window
# owns discovery, the connections and the configurations.
_FORBIDDEN = frozenset(
    {
        "Connector",
        "Discovery",
        "connect_stream",
        "create_stream",
        "list_configurations",
        "probe_channels",
        "resolve_descriptors",
        "save_configuration",
    }
)


@pytest.fixture
def page(flush_deletes: Callable[..., None]) -> Generator[EmptyStatePage]:
    """Yield a landing page, closed and deleted afterwards."""
    built = EmptyStatePage()
    built.resize(900, 700)
    yield built
    built.close()
    flush_deletes(built)


def _select(page: EmptyStatePage, *rows: int) -> None:
    """Select ``rows`` of the stream table, in the order given.

    Through the selection model rather than 'selectRow', which clears the selection
    first and so can never build the multi-selection the page exists to serve.
    """
    table = page._table
    table.clearSelection()
    flags = (
        QItemSelectionModel.SelectionFlag.Select
        | QItemSelectionModel.SelectionFlag.Rows
    )
    for row in rows:
        table.selectionModel().select(table.model().index(row, 0), flags)


def test_empty_page(page: EmptyStatePage) -> None:
    """Test that a fresh page shows no stream and is never blank while it waits."""
    assert page._table.rowCount() == 0
    assert page.selected_descriptors() == []
    assert page._progress.text() == PROGRESS_TEXT["checking"]
    assert page._events_label.text() == "No event sources discovered."


def test_set_streams_lists_regular_only(
    page: EmptyStatePage, descriptor: Callable[..., StreamDescriptor]
) -> None:
    """Test that only the regularly sampled streams are openable rows.

    An event source cannot own a document -- 'StreamLSL' refuses to connect to one with
    a buffer in seconds -- thus listing it as a row would offer an action which always
    fails.
    """
    regular = [descriptor(name=f"regular-{index}") for index in range(3)]
    events = [descriptor(name=f"marker-{index}", sfreq=0.0) for index in range(2)]
    page.set_streams([*events, *regular])
    assert page._table.rowCount() == 3
    assert [page._table.item(row, 0).text() for row in range(3)] == [
        "regular-0",
        "regular-1",
        "regular-2",
    ]
    for name in ("marker-0", "marker-1"):
        assert name in page._events_label.text()
    assert page._events_label.toolTip() == page._events_label.text()
    page.set_streams(regular)
    assert page._events_label.text() == "No event sources discovered."


def test_set_streams_columns(
    page: EmptyStatePage, descriptor: Callable[..., StreamDescriptor]
) -> None:
    """Test that each cell holds its own field, so a column swap cannot pass.

    Nothing else in the suite would catch the type and the source ID trading places.
    """
    entry = descriptor(
        name="Polar",
        stype="ecg",
        source_id="unit-7",
        n_channels=3,
        sfreq=130.5,
        hostname="host-9",
    )
    page.set_streams([entry])
    assert [page._table.item(0, column).text() for column in range(6)] == [
        "Polar",
        "ecg",
        "unit-7",
        "3",
        "130.5",
        "host-9",
    ]
    assert page._table.item(0, 0).font().bold()


def test_set_streams_rebuild(
    page: EmptyStatePage, descriptor: Callable[..., StreamDescriptor]
) -> None:
    """Test that a shorter pass leaves no stale row and no stale descriptor.

    A descriptor kept past the pass which removed it is a stream the window would try to
    open although discovery no longer sees it.
    """
    first = [descriptor(name=f"stream-{index}") for index in range(3)]
    page.set_streams(first)
    _select(page, 2)
    assert page.selected_descriptors() == [first[2]]
    page.set_streams(first[:1])
    assert page._table.rowCount() == 1
    assert page.selected_descriptors() == []


def test_set_streams_keeps_the_selected_identity(
    page: EmptyStatePage, descriptor: Callable[..., StreamDescriptor]
) -> None:
    """Test that a discovery pass re-anchors the selection on the identity it held.

    The selection lives in table *row* indices, thus a pass which merely inserted one
    stream shifts every later row under it: the user picks C, a colleague's B appears,
    and the window connects B with the highlight never moving. Asserted for an insertion
    and for a same-length rebuild, as the row count alone cannot detect either.
    """
    a, b, c = (descriptor(name=name) for name in ("A", "B", "C"))
    page.set_streams([a, c])
    _select(page, 1)
    assert page.selected_descriptors() == [c]
    page.set_streams([a, b, c])  # a colleague's stream appeared meanwhile
    assert page.selected_descriptors() == [c]
    assert sorted({index.row() for index in page._table.selectedIndexes()}) == [2]
    page.set_streams([c, a, b])  # same length, every row holds another stream
    assert page.selected_descriptors() == [c]


def test_event_source_names_are_never_markup(
    page: EmptyStatePage, descriptor: Callable[..., StreamDescriptor]
) -> None:
    """Test that a stream name reaches the event line as text and never as markup.

    A name is remote input and the line is a 'QLabel', i.e. 'AutoText' by default: a
    source named '<!--' erases every name after it from what is rendered, and '<b>x</b>'
    shows as 'x', so the name on screen is not the one published. A tooltip has no
    format of its own and always auto-detects rich text, hence the escaping.
    """
    page.set_streams(
        [descriptor(name="<!--", sfreq=0.0), descriptor(name="<b>x</b>", sfreq=0.0)]
    )
    assert page._events_label.textFormat() == Qt.TextFormat.PlainText
    assert "<!--" in page._events_label.text()
    assert "<b>x</b>" in page._events_label.text()
    assert "&lt;!--" in page._events_label.toolTip()
    assert "&lt;b&gt;x&lt;/b&gt;" in page._events_label.toolTip()
    assert "<b>" not in page._events_label.toolTip()


def test_selected_descriptors_row_order(
    page: EmptyStatePage, descriptor: Callable[..., StreamDescriptor]
) -> None:
    """Test that the selection comes back in row order, once per row, as passed in.

    'selectedIndexes()' reports one index per cell, thus six entries per selected row
    and in click order; and indexing the unsplit list would return an event source.

    The selection *mode* is asserted here because the helper below drives the selection
    model, which ignores it: a table left on 'SingleSelection' still reports two rows
    selected to every test of this module while a user could only ever pick one.
    """
    events = [descriptor(name="marker", sfreq=0.0)]
    regular = [descriptor(name=f"stream-{index}") for index in range(3)]
    page.set_streams([*events, *regular])
    assert (
        page._table.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection
    )
    _select(page, 2, 0)
    selected = page.selected_descriptors()
    assert selected == [regular[0], regular[2]]
    assert selected[0] is regular[0]
    assert selected[1] is regular[2]


def test_selection_changed_emitted(
    page: EmptyStatePage, descriptor: Callable[..., StreamDescriptor]
) -> None:
    """Test that a selection, and a rebuilt table, both report themselves.

    Without the first the 'Open selected' action stays disabled forever; without the
    second the window never re-evaluates it over the table a discovery pass replaced.

    The rebuild is asserted with **nothing selected**, and at an unchanged row count: Qt
    emits 'itemSelectionChanged' by itself whenever it drops rows out of a selection --
    measured twice for a rebuild under a live selection, never for one under an empty
    selection -- so any other shape passes with the page's own emission deleted.
    """
    page.set_streams([descriptor(name="stream-0"), descriptor(name="stream-1")])
    seen: list[int] = []
    page.selection_changed.connect(lambda: seen.append(1))
    _select(page, 1)
    assert len(seen) == 1
    page._table.clearSelection()
    seen.clear()
    page.set_streams([descriptor(name="other-0"), descriptor(name="other-1")])
    assert len(seen) == 1


def test_open_requested_on_double_click(
    page: EmptyStatePage, descriptor: Callable[..., StreamDescriptor]
) -> None:
    """Test that a double click opens the selection, and nothing when there is none.

    An empty emission would make the window start a batch of zero connections and show a
    'Connecting to 0 stream(s)' message.
    """
    regular = [descriptor(name=f"stream-{index}") for index in range(2)]
    page.set_streams(regular)
    seen: list[object] = []
    page.open_requested.connect(seen.append)
    page._table.clearSelection()
    page._table.itemDoubleClicked.emit(page._table.item(0, 0))
    assert seen == []
    _select(page, 1)
    page._table.itemDoubleClicked.emit(page._table.item(1, 0))
    assert seen == [[regular[1]]]


def test_set_progress_tags(page: EmptyStatePage) -> None:
    """Test that every discovery tag maps to its own text, and an unknown one to itself.

    A 'KeyError' here would surface from inside a Qt slot, and two tags collapsing to
    one string would make a failed pass indistinguishable from a finished one.
    """
    texts = set()
    for tag in ("checking", "updated", "failed", "empty"):
        page.set_progress(tag)
        assert page._progress.text() == PROGRESS_TEXT[tag]
        assert page._progress.text()
        texts.add(page._progress.text())
    assert len(texts) == 4
    page.set_progress("some-new-tag")
    assert page._progress.text() == "some-new-tag"


def test_launcher_is_passive(
    module_scan: Callable[[ModuleType], tuple[set[str], set[str]]],
) -> None:
    """Test that the landing page resolves, connects and reads nothing itself.

    A source-level check, as importing any viewer module necessarily imports the LSL
    layer. The identifiers come from the syntax tree, thus a docstring naming the
    window's responsibilities is documentation and not a dependency.
    """
    imports, identifiers = module_scan(mne_lsl.viewer._launcher)
    segments = {segment for path in imports for segment in path.split(".")}
    assert (segments | identifiers).isdisjoint(_FORBIDDEN)
