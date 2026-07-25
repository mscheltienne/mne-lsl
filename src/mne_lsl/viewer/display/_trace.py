"""Multichannel trace display.

Accepted rendering design: a fixed pool of persistent :class:`pyqtgraph.PlotDataItem`
curves stacked with ``setPos`` and amplitude-scaled with a ``QTransform``, so changing
the scale never rewrites the sample arrays. A curve is only ever reassigned to a channel
while it sits in the off-screen overscan band, which gives smooth fractional row
scrolling without pop-in. The window is drawn against relative time on a fixed ``0 → W``
axis, and the acquisition and render cadences stay independent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtWidgets import QWidget

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from ...stream import BaseStream
    from ..controller import ChannelModel

# Rows kept off-screen above and below the visible band, where a curve may be
# (re)assigned to another channel.
_OVERSCAN = 4
# Render clock period, in milliseconds; independent of the acquisition cadence.
_RENDER_MS = 33


class TraceDisplay(QWidget):
    """Trace display of one stream document: a control bar over a scrolling plot.

    Parameters
    ----------
    stream : BaseStream
        The connected stream which is polled by the render clock.
    model : ChannelModel
        The channel model shared with the controller, providing the presentation order,
        the visibility and the channel metadata.
    parent : QWidget | None
        Parent widget.
    """

    def __init__(
        self, stream: BaseStream, model: ChannelModel, parent: QWidget | None = None
    ) -> None:
        """Initialize the display."""

    # -- lifecycle ------------------------------------------------------------------
    def start(self) -> None:
        """Start the render clock."""

    def stop(self) -> None:
        """Stop the render clock; idempotent."""

    @property
    def running(self) -> bool:
        """Whether the render clock is running."""

    # -- vertical navigation --------------------------------------------------------
    def scroll_to(self, row: float) -> None:
        """Move the top of the viewport to the fractional row ``row``.

        Parameters
        ----------
        row : float
            Target offset, in channel rows. Fractional values are allowed and clamped to
            the last page.
        """

    def scroll_by(self, rows: float) -> None:
        """Scroll the viewport by ``rows`` channel rows, fractional allowed."""

    # -- channel layout -------------------------------------------------------------
    def set_channel_layout(
        self, order: Sequence[int], hidden: Iterable[int] = ()
    ) -> None:
        """Set the presentation order and the hidden channels of the display.

        Parameters
        ----------
        order : sequence of int
            Acquisition indices of the channels, in display order.
        hidden : iterable of int
            Acquisition indices of the channels which are not drawn.
        """
        # The mechanism connecting the channel model to the traces, i.e. how an order or
        # visibility change reaches the curve pool without disturbing the scroll
        # position, is pending a separate design decision. This is the seam it will
        # land on; nothing here presumes the mechanism.
