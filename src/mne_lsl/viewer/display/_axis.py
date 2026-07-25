"""Custom pyqtgraph axis and view box of the trace display."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyqtgraph as pg

if TYPE_CHECKING:
    from qtpy.QtGui import QPainter

    from ._trace import TraceDisplay


class ChannelAxis(pg.AxisItem):
    """Left axis labelling the visible rows with their channel name.

    One integer tick per visible channel row, each label painted in the color of its
    trace. A bad channel is prefixed with ``'X '``, a non-color cue on top of the
    distinct label color, so the bad state never depends on color alone.

    Parameters
    ----------
    display : TraceDisplay
        The trace display the axis reads its channel names, colors and row offset from.
    **kwargs
        Additional keyword arguments are provided to :class:`pyqtgraph.AxisItem`.
    """

    def __init__(self, display: TraceDisplay, **kwargs) -> None:
        """Initialize the axis."""

    def tickValues(self, minVal: float, maxVal: float, size: float):
        """Return one integer tick per visible channel row."""

    def tickStrings(self, values, scale: float, spacing: float) -> list[str]:
        """Return the channel names of ``values`` and cache their label colors."""

    def drawPicture(self, p: QPainter, axisSpec, tickSpecs, textSpecs) -> None:
        """Paint the axis, coloring every channel label individually."""

    def wheelEvent(self, ev) -> None:
        """Scroll the channels; the axis never zooms."""


class TraceViewBox(pg.ViewBox):
    """View box with the default pan, zoom and menu disabled.

    The display drives the range explicitly: a wheel event scrolls the channels, or
    scales the amplitude with the control modifier, and a drag is swallowed. This is
    deliberate, the legacy viewer silently changed the amplitude on a wheel event.

    Parameters
    ----------
    display : TraceDisplay
        The trace display the view box routes its input events to.
    **kwargs
        Additional keyword arguments are provided to :class:`pyqtgraph.ViewBox`.
    """

    def __init__(self, display: TraceDisplay, **kwargs) -> None:
        """Initialize the view box."""

    def wheelEvent(self, ev, axis=None) -> None:
        """Scroll the channels, or scale the amplitude with the control modifier."""

    def mouseDragEvent(self, ev, axis=None) -> None:
        """Swallow the drag, so the plot never pans nor rubber-band zooms."""
