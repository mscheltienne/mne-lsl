"""Segmented control with a highlight which slides on selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import Signal
from qtpy.QtWidgets import QWidget

if TYPE_CHECKING:
    from collections.abc import Sequence


class AnimatedSegmentedControl(QWidget):
    """Compact segmented control with a highlight which slides on selection.

    Exactly one segment is active at a time. Flat transparent equal-flex buttons sit
    over a single backing highlight widget, animated on its ``geometry``; exclusivity is
    the current index, not a ``QButtonGroup``.

    Parameters
    ----------
    items : sequence of tuple of str
        ``(label, tooltip, value)`` triples, left to right. The first is active.
    parent : QWidget | None
        Parent widget.

    Attributes
    ----------
    changed : Signal
        Emitted with the ``value`` of the newly selected segment.
    """

    changed = Signal(str)

    def __init__(
        self, items: Sequence[tuple[str, str, str]], parent: QWidget | None = None
    ) -> None:
        """Initialize the segmented control."""

    @property
    def current_index(self) -> int:
        """Index of the active segment."""

    @property
    def current_value(self) -> str:
        """Value of the active segment."""

    def set_index(
        self, index: int, *, animate: bool = False, emit: bool = True
    ) -> None:
        """Activate the segment at ``index``.

        Parameters
        ----------
        index : int
            Segment to activate.
        animate : bool
            If ``True``, slide the highlight; else snap it, e.g. on resize or restore.
        emit : bool
            If ``True``, emit :attr:`changed`. Set to ``False`` to sync silently.
        """
