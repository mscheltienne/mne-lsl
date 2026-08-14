"""Landing page: discovery progress and the available streams."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

from qtpy.QtCore import QItemSelectionModel, Qt, Signal
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from superqt import QElidingLabel

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .backend import StreamDescriptor, StreamIdentity

# Human-readable discovery states, keyed by the tag 'Discovery.progress' emits. Declared
# here because the launcher label and the window's transient status message must read
# the same, and a second table is how the two silently diverge. Read through
# 'progress_text' below, never with '.get(tag, tag)' at the call site: that is the same
# divergence one level down.
PROGRESS_TEXT = {
    "checking": "Checking for streams…",
    "updated": "Updated just now",
    "failed": "Discovery failed — press Refresh to retry",
    "empty": "No streams found",
}
# Column headers of the available-stream table, in order.
_COLUMNS = ("Name", "Type", "Source ID", "Channels", "Rate (Hz)", "Host")
# The table is height-capped and scrolls, so the region stays compact instead of a
# large, mostly empty table stretching to fill the page.
_TABLE_MAX_H = 210
# Maximum width of the centred content column.
_COLUMN_MAX_W = 820


def progress_text(tag: str) -> str:
    """Return the human-readable text of a discovery state ``tag``.

    Parameters
    ----------
    tag : str
        State tag, as ``Discovery.progress`` emits it.

    Returns
    -------
    text : str
        The text of the tag, or the tag itself when it is unknown: both consumers are Qt
        slots, where a :class:`KeyError` becomes an unhandled exception, and a tag with
        no text of its own is still more informative than nothing.
    """
    return PROGRESS_TEXT.get(tag, tag)


class EmptyStatePage(QWidget):
    """Compact launcher shown while no stream document is open.

    A centred, max-width column: a title and the available regular streams, with a
    multi-selection. The page owns no button: it reports its selection and a double
    click on it, and the window owns the Open action. The page is passive throughout --
    the window resolves the identities and performs the connections.

    Parameters
    ----------
    parent : QWidget | None
        Parent widget.

    Attributes
    ----------
    selection_changed : Signal
        Emitted when the stream multi-selection changes, so the window can enable or
        disable its 'Open selected' action.
    open_requested : Signal
        Emitted with the ``list`` of selected
        :class:`~mne_lsl.viewer.backend.StreamDescriptor` to open.
    """

    selection_changed = Signal()
    open_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the page."""
        super().__init__(parent)
        # The regular descriptors, in table-row order: this list *is* the row to
        # descriptor map. Nothing is stashed in an item data role, as what a 'QVariant'
        # round trip does to a frozen dataclass differs between the two Qt bindings.
        self._descriptors: list[StreamDescriptor] = []

        title = QLabel("Open live streams")
        font = QFont(title.font())
        # font-relative rather than a pixel size, so the title follows the system font.
        font.setPointSizeF(font.pointSizeF() * 1.6)
        font.setBold(True)
        title.setFont(font)
        subtitle = QLabel(
            "Select one or more streams and open them; each opens its own document."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: palette(mid);")

        self._progress = QLabel()
        self._progress.setStyleSheet("color: palette(mid); font-style: italic;")

        self._table = self._build_table()
        self._events_label = QElidingLabel()
        # A stream name is remote input and this is a 'QLabel', i.e. 'AutoText': one
        # named '<!--' erases every name after it from the line, '<b>x</b>' shows as 'x'
        # and an '<img>' embeds a local file. The table is immune, as an item renders
        # its text verbatim, and the tooltip is escaped below -- a tooltip always
        # auto-detects rich text and has no format of its own.
        self._events_label.setTextFormat(Qt.TextFormat.PlainText)
        self._events_label.setStyleSheet("color: palette(mid);")
        streams_group = QGroupBox("Available streams")
        streams_box = QVBoxLayout(streams_group)
        streams_box.setSpacing(6)
        streams_box.addWidget(self._table)
        streams_box.addWidget(self._events_label)

        content = QWidget()
        content.setMaximumWidth(_COLUMN_MAX_W)
        column = QVBoxLayout(content)
        column.setSpacing(8)
        column.addWidget(title)
        column.addWidget(subtitle)
        column.addWidget(self._progress)
        column.addWidget(streams_group)
        column.addStretch(1)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.addStretch(1)
        outer.addWidget(content)
        outer.addStretch(1)

        self.set_progress("checking")  # never an empty label before the first pass
        self.set_streams([])  # the fallback text of the event line, from the same path

    def _build_table(self) -> QTableWidget:
        """Build the available-stream table."""
        table = QTableWidget(0, len(_COLUMNS))
        table.setHorizontalHeaderLabels(_COLUMNS)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        table.setColumnWidth(0, 160)
        table.setMaximumHeight(_TABLE_MAX_H)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        table.itemSelectionChanged.connect(self.selection_changed)
        table.itemDoubleClicked.connect(self._on_double_click)
        return table

    def set_streams(self, descriptors: Sequence[StreamDescriptor]) -> None:
        """Populate the table with the regular streams and note the event sources.

        Parameters
        ----------
        descriptors : sequence of StreamDescriptor
            Every descriptor found by the last discovery pass. Descriptors with a null
            sampling rate are listed as event sources rather than as openable streams.

        Notes
        -----
        The selection is re-anchored on the identities it held. It lives in table *row*
        indices, thus a pass which merely inserted or removed one stream would leave the
        highlight on a different stream than the user picked -- and the window would
        then connect that one, with nothing on screen signalling the switch. An identity
        which the pass no longer reports simply loses its selection.
        """
        regular = [descriptor for descriptor in descriptors if descriptor.sfreq != 0]
        events = [descriptor for descriptor in descriptors if descriptor.sfreq == 0]
        selected = {descriptor.identity for descriptor in self.selected_descriptors()}
        self._descriptors = regular
        self._table.setRowCount(len(regular))
        for row, descriptor in enumerate(regular):
            identity = descriptor.identity
            values = (
                identity.name,
                identity.stype,
                identity.source_id,
                str(descriptor.n_channels),
                f"{descriptor.sfreq:g}",
                descriptor.hostname,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    font = QFont(item.font())
                    font.setBold(True)
                    item.setFont(font)
                self._table.setItem(row, column, item)
        self._select_identities(selected)
        if events:
            names = ", ".join(descriptor.identity.name for descriptor in events)
            text = f"Event sources (not openable as a document): {names}"
        else:
            text = "No event sources discovered."
        self._events_label.setText(text)
        # Elided in place, thus the tooltip is the only way back to the full text -- and
        # escaped, as a tooltip renders markup whatever the label was told.
        self._events_label.setToolTip(escape(text))
        # The table was rebuilt under the selection, thus the window has to re-evaluate
        # its Open action even though no user interaction took place.
        self.selection_changed.emit()

    def _select_identities(self, identities: set[StreamIdentity]) -> None:
        """Select the rows whose descriptor carries one of ``identities``.

        Parameters
        ----------
        identities : set of StreamIdentity
            Identities to select; one absent from the table selects nothing.
        """
        model = self._table.selectionModel()
        flags = (
            QItemSelectionModel.SelectionFlag.Select
            | QItemSelectionModel.SelectionFlag.Rows
        )
        self._table.clearSelection()
        for row, descriptor in enumerate(self._descriptors):
            if descriptor.identity in identities:
                model.select(self._table.model().index(row, 0), flags)

    def set_progress(self, tag: str) -> None:
        """Reflect a discovery state tag, e.g. ``'checking'``, in the progress label.

        Parameters
        ----------
        tag : str
            The state tag, resolved by :func:`progress_text`.
        """
        self._progress.setText(progress_text(tag))

    def selected_descriptors(self) -> list[StreamDescriptor]:
        """Return the descriptors of the currently selected regular streams.

        Returns
        -------
        descriptors : list of StreamDescriptor
            The selected descriptors, in table-row order and without duplicates -- a
            selected row reports one index per column.
        """
        rows = sorted({index.row() for index in self._table.selectedIndexes()})
        # Cross-binding insurance, and not a reachable path under PyQt6: measured, Qt
        # clears the selection of the rows it removes *before* delivering
        # 'itemSelectionChanged', so no index past the descriptors can arrive here. Kept
        # because PySide6 is not exercised locally and the failure there would be an
        # 'IndexError' raised inside a Qt slot rather than a missing selection.
        return [self._descriptors[row] for row in rows if row < len(self._descriptors)]

    def _on_double_click(self, *_args) -> None:
        """Request the selected streams to be opened, if any."""
        descriptors = self.selected_descriptors()
        if descriptors:
            self.open_requested.emit(descriptors)
