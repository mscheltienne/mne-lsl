"""Landing page: discovery progress, saved configurations and available streams."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import Signal
from qtpy.QtWidgets import QWidget

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .backend import StreamDescriptor, ViewerConfig


class EmptyStatePage(QWidget):
    """Compact launcher shown while no stream document is open.

    Three regions in a centred, max-width column: a title, the saved configurations,
    shown first when any exist, and the available regular streams with a multi-selection
    and an open action. The page is passive: the window resolves the identities and
    performs the connections.

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
    open_configuration : Signal
        Emitted with the :class:`~mne_lsl.viewer.backend.ViewerConfig` of a card which
        is ready and was activated.
    """

    selection_changed = Signal()
    open_requested = Signal(object)
    open_configuration = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the page."""

    def set_streams(self, descriptors: Sequence[StreamDescriptor]) -> None:
        """Populate the table with the regular streams and note the event sources.

        Parameters
        ----------
        descriptors : sequence of StreamDescriptor
            Every descriptor found by the last discovery pass. Descriptors with a null
            sampling rate are listed as event sources rather than as openable streams.
        """

    def set_progress(self, tag: str) -> None:
        """Reflect a discovery state tag, e.g. ``'checking'``, in the progress label."""

    def set_configurations(self, configs: Sequence[ViewerConfig]) -> None:
        """Rebuild the saved-configuration cards.

        An identity-matching configuration moves to the top and shows its availability
        state; a configuration which is unavailable or invalid stays visible, disabled,
        and spells out the precise reason.

        Parameters
        ----------
        configs : sequence of ViewerConfig
            The saved configurations to show.
        """

    def selected_descriptors(self) -> list[StreamDescriptor]:
        """Return the descriptors of the currently selected regular streams."""
