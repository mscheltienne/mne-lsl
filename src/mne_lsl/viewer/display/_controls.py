"""Control bar of the trace display, the single source of truth for display state.

The controller has no Display page: this bar owns the display state, i.e. the visible
row count, the time window, the amplitude scale, the trace color mode and the channel /
event label toggles. Rows, window and scale are ``− VALUE +`` steppers whose read-out is
click-to-edit; there is no permanent spin box.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qtpy.QtCore import Signal
from qtpy.QtWidgets import QWidget

if TYPE_CHECKING:
    from collections.abc import Mapping


class DisplayControls(QWidget):
    """Button bar owning the display state of one trace display.

    Attributes
    ----------
    rows_changed : Signal
        Emitted with the new visible row count.
    window_changed : Signal
        Emitted with the new time window, in seconds.
    scale_changed : Signal
        Emitted with the new amplitude multiplier.
    color_mode_changed : Signal
        Emitted with the new trace color mode, ``'channel'`` or ``'type'``.
    labels_toggled : Signal
        Emitted when the channel labels are shown or hidden.
    events_toggled : Signal
        Emitted when the event overlays are shown or hidden.

    Parameters
    ----------
    parent : QWidget | None
        Parent widget.
    """

    rows_changed = Signal(int)
    window_changed = Signal(float)
    scale_changed = Signal(float)
    color_mode_changed = Signal(str)
    labels_toggled = Signal(bool)
    events_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the control bar."""

    @property
    def state(self) -> dict[str, Any]:
        """Current display state, one entry per control."""

    def set_state(self, state: Mapping[str, Any]) -> None:
        """Restore the display state, e.g. from a configuration.

        Parameters
        ----------
        state : dict
            A mapping shaped like :attr:`state`. Unknown keys are ignored.
        """

    def set_rows(self, value: int) -> None:
        """Set the visible row count and emit :attr:`rows_changed`."""

    def set_window(self, value: float) -> None:
        """Set the time window in seconds and emit :attr:`window_changed`."""

    def set_scale(self, value: float) -> None:
        """Set the amplitude multiplier and emit :attr:`scale_changed`."""

    def retint_icons(self) -> None:
        """Rebuild the bar icons after a theme flip, as a ``QIcon`` bakes its color."""
