"""Channels page: a single-column list, a compact toolbar and a contextual inspector.

Accepted design: Proposal A's lean single-column list plus a contextual inspector which
appears only when at least one channel is selected. A plain click selects, while the
leading eye glyph is the dedicated visibility toggle; ordering is command-driven through
the animated segmented control and writes the shared model order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtWidgets import QStyledItemDelegate, QWidget

if TYPE_CHECKING:
    from qtpy.QtCore import QAbstractItemModel, QModelIndex, QObject
    from qtpy.QtGui import QPainter
    from qtpy.QtWidgets import QStyleOptionViewItem

    from ._model import ChannelModel


class ChannelDelegate(QStyledItemDelegate):
    """Paint one compact channel row and route the eye-glyph clicks.

    The row renders as aligned columns ``name │ ● type │ unit``: the metadata cluster,
    i.e. the bad marker, the type-color dot, the type text and the unit, is packed
    right-to-left with measured font metrics and pinned to the right edge, while the
    name fills the left span and elides. A click inside the leading eye rectangle
    toggles the visibility; a click anywhere else is left to the view, which performs
    its normal multi-selection.

    Parameters
    ----------
    parent : QObject | None
        Parent object.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the delegate and build its palette-derived icons."""

    def refresh_palette(self) -> None:
        """Rebuild the palette-derived eye and bad icons after a theme change."""

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        """Paint the row of ``index``."""

    def editorEvent(
        self,
        event,
        model: QAbstractItemModel,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> bool:
        """Toggle the visibility on a click inside the eye rectangle."""


class ChannelsPage(QWidget):
    """Channels page of the controller.

    The page does not own its model: the stream document builds one
    :class:`~mne_lsl.viewer.controller.ChannelModel` and shares it with the trace
    display, so the two presentations never hold duplicate channel state.

    Parameters
    ----------
    model : ChannelModel
        The channel model of the stream document.
    parent : QWidget | None
        Parent widget.
    """

    def __init__(self, model: ChannelModel, parent: QWidget | None = None) -> None:
        """Initialize the page over an existing channel model."""

    def retheme(self) -> None:
        """Rebuild the palette-derived delegate icons after a theme flip and repaint."""
