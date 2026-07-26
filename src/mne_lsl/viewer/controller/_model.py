"""Channel model backing the Channels page and the trace display.

Single source of truth for the channel presentation: name, type, unit, bad state,
visibility and display order live here and nowhere else. Metadata edits route to the
stream operations (:meth:`~mne_lsl.stream.BaseStream.rename_channels`,
:meth:`~mne_lsl.stream.BaseStream.set_channel_types`,
:meth:`~mne_lsl.stream.BaseStream.set_channel_units` and ``stream.info['bads']``), while
visibility and display order are viewer presentation state which the trace display
mirrors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mne._fiff.constants import FIFF
from qtpy.QtCore import QAbstractListModel, QModelIndex, Qt

if TYPE_CHECKING:
    from collections.abc import Iterable

    from qtpy.QtCore import QObject

    from ...stream import BaseStream

# Choices offered by the inspector combo boxes and the context-menu submenus.
CH_TYPES = ["eeg", "eog", "ecg", "emg", "stim", "misc"]

# Combined unit control: one human label per '(unit kind, unit multiplier)' pair, i.e.
# per '(FIFF_UNIT_*, FIFF_UNITM_*)'. The label is 'SI_prefix(unit_mul) + symbol(unit)',
# e.g. V with -6 -> uV. 'BaseStream.get_channel_units()' returns exactly this pair per
# channel.
#
# Open question: 'BaseStream.set_channel_units()' writes the multiplier only, and raises
# for a channel whose kind is FIFF_UNIT_NONE, since MNE derives the kind from the
# channel type. Assigning a unit *kind* therefore requires either a channel-type change
# or an mne-lsl API extension. To resolve during the implementation phase.
_UNITS: list[tuple[str, int, int]] = [
    ("µV", FIFF.FIFF_UNIT_V, FIFF.FIFF_UNITM_MU),
    ("mV", FIFF.FIFF_UNIT_V, FIFF.FIFF_UNITM_M),
    ("V", FIFF.FIFF_UNIT_V, FIFF.FIFF_UNITM_NONE),
    ("fT", FIFF.FIFF_UNIT_T, FIFF.FIFF_UNITM_F),
    ("T", FIFF.FIFF_UNIT_T, FIFF.FIFF_UNITM_NONE),
    ("T/m", FIFF.FIFF_UNIT_T_M, FIFF.FIFF_UNITM_NONE),
    ("µM", FIFF.FIFF_UNIT_MOL, FIFF.FIFF_UNITM_MU),
    ("mV/m²", FIFF.FIFF_UNIT_V_M2, FIFF.FIFF_UNITM_M),
    ("°C", FIFF.FIFF_UNIT_CEL, FIFF.FIFF_UNITM_NONE),
    ("S", FIFF.FIFF_UNIT_S, FIFF.FIFF_UNITM_NONE),
    ("(none)", FIFF.FIFF_UNIT_NONE, FIFF.FIFF_UNITM_NONE),
]
UNIT_LABELS = [label for label, _, _ in _UNITS]

# Curated shortlist per channel type; a type carrying FIFF_UNIT_NONE, e.g. misc, and an
# unknown type offer the full list.
_UNIT_CHOICES: dict[str, list[str]] = {
    "eeg": ["µV", "mV", "V"],
    "eog": ["µV", "mV", "V"],
    "ecg": ["µV", "mV", "V"],
    "emg": ["µV", "mV", "V"],
    "stim": ["V", "(none)"],
    "misc": UNIT_LABELS,
}

# Custom roles read by the row delegate and by the inspector. The list has a single
# column, thus the index of a row carries the entire channel.
_UR = int(Qt.ItemDataRole.UserRole)
NameRole = _UR + 1
TypeRole = _UR + 2
UnitRole = _UR + 3
VisibleRole = _UR + 4
BadRole = _UR + 5


def unit_label(kind: int, mul: int) -> str:
    """Return the human label of a ``(kind, multiplier)`` unit pair.

    Parameters
    ----------
    kind : int
        FIFF unit kind, ``FIFF_UNIT_*``.
    mul : int
        FIFF unit multiplier, ``FIFF_UNITM_*``, i.e. the power of ten.

    Returns
    -------
    label : str
        The human label, e.g. ``'µV'``.
    """


def unit_pair(label: str) -> tuple[int, int]:
    """Return the ``(kind, multiplier)`` pair of a unit ``label``.

    Parameters
    ----------
    label : str
        Human unit label, e.g. ``'µV'``.

    Returns
    -------
    kind : int
        FIFF unit kind, ``FIFF_UNIT_*``.
    mul : int
        FIFF unit multiplier, ``FIFF_UNITM_*``.
    """


def unit_choices(ch_type: str | None) -> list[str]:
    """Return the unit labels offered for ``ch_type``.

    Parameters
    ----------
    ch_type : str | None
        Channel type, or ``None`` for a selection spanning several types.

    Returns
    -------
    labels : list of str
        The curated shortlist, or every label for an unknown or mixed type.
    """


@dataclass
class Channel:
    """Editable state of one channel and its original stream values.

    Parameters
    ----------
    name : str
        Current channel name.
    ch_type : str
        Current channel type.
    unit_kind : int
        Physical unit kind, ``FIFF_UNIT_*``.
    unit_mul : int
        Decimal power-of-ten multiplier, ``FIFF_UNITM_*``.
    visible : bool
        Whether the channel is drawn by the trace display, i.e. presentation state.
    bad : bool
        Whether the channel is marked bad, mirroring ``stream.info['bads']``.
        Independent of the visibility: a bad channel stays visible, dimmed and struck
        through, unless it is also hidden.
    acq_index : int
        Index of the channel in acquisition order.
    orig : tuple
        Original ``(name, ch_type, unit_kind, unit_mul, bad)``, restored by a reset.
    """

    name: str
    ch_type: str
    unit_kind: int
    unit_mul: int
    visible: bool
    bad: bool
    acq_index: int
    orig: tuple[str, str, int, int, bool]

    @property
    def unit(self) -> str:
        """Human unit label of the ``(kind, multiplier)`` pair."""


class ChannelModel(QAbstractListModel):
    """List model holding the channel metadata, visibility and display order.

    Parameters
    ----------
    stream : BaseStream
        The connected stream the metadata is read from and written back to.
    parent : QObject | None
        Parent object.
    """

    def __init__(self, stream: BaseStream, parent: QObject | None = None) -> None:
        """Initialize the model from the metadata of a connected stream."""

    def channel(self, row: int) -> Channel:
        """Return the channel at display ``row``.

        Parameters
        ----------
        row : int
            Display row index.

        Returns
        -------
        channel : Channel
            The channel record.
        """

    # -- Qt model interface ---------------------------------------------------------
    def rowCount(self, parent: QModelIndex | None = None) -> int:
        """Return the number of channels, ``0`` for a valid parent."""

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        """Return the item flags of ``index``; editing goes through the inspector."""

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        """Return the channel data of ``index`` under ``role``."""

    def setData(
        self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        """Apply a per-row visibility or bad edit, e.g. from the eye toggle."""

    # -- bulk edits, applied to an entire selection ---------------------------------
    def set_visible(self, rows: Iterable[int], value: bool) -> None:
        """Set the visibility of ``rows`` to ``value``."""

    def set_bad(self, rows: Iterable[int], value: bool) -> None:
        """Mark ``rows`` bad or good, writing to ``stream.info['bads']``."""

    def set_type(self, rows: Iterable[int], value: str) -> None:
        """Set the channel type of ``rows`` to ``value``."""

    def set_unit(self, rows: Iterable[int], label: str) -> None:
        """Set the unit of ``rows`` from a human ``label``, i.e. kind and multiplier."""

    def rename(self, row: int, name: str) -> None:
        """Rename the single channel at ``row``."""

    def reset_metadata(self, rows: Iterable[int]) -> None:
        """Restore the name, type, unit and bad state of ``rows`` to stream values."""

    # -- presentation order, mirrored by the trace display --------------------------
    def order_by(self, kind: str) -> None:
        """Reorder every channel with a deterministic command.

        Parameters
        ----------
        kind : str
            One of ``'acquisition'``, ``'type'`` or ``'alphabetical'``.
        """

    def presentation_order(self) -> list[int]:
        """Return the acquisition indices of the channels, in display order."""

    def hidden_channels(self) -> list[int]:
        """Return the acquisition indices of the channels which are hidden."""
