"""Deterministic plot colors, channel-type colors and icons.

pyqtgraph items and ``QIcon`` objects do not read the ``QPalette``: they bake their
colors, thus they must be rebuilt from these helpers on every theme change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qtpy.QtGui import QColor, QIcon

# Golden-ratio conjugate: successive multiples spread the hues maximally.
_GOLDEN_RATIO = 0.618033988749895

# Fixed per-type colors: categorical hues muted to S=0.50, V=0.75 so a wall of traces
# reads calmly; misc stays neutral gray. Accepted in 'brief/design/01_trace_display_-
# feedback.md'.
_TYPE_COLORS: dict[str, str] = {
    "eeg": "#6098bf",
    "eog": "#bf8c60",
    "ecg": "#bf6060",
    "emg": "#60bf60",
    "stim": "#9260bf",
    "misc": "#999999",
}


def plot_colors(mode: str = "auto") -> dict[str, str]:
    """Return the pyqtgraph canvas colors for ``mode``.

    Parameters
    ----------
    mode : str
        ``'auto'``, ``'light'`` or ``'dark'``.

    Returns
    -------
    colors : dict
        ``'background'``, ``'foreground'`` and ``'grid'`` as ``#rrggbb`` strings.
    """


def trace_color(index: int, mode: str = "auto") -> QColor:
    """Return the deterministic trace color of a channel, tuned for ``mode``.

    Parameters
    ----------
    index : int
        Channel index in presentation order.
    mode : str
        ``'auto'``, ``'light'`` or ``'dark'``.

    Returns
    -------
    color : QColor
        A muted, distinct color legible on the mode's plot background.
    """


def channel_color(index: int) -> QColor:
    """Return the deterministic color of a channel index, golden-ratio spaced.

    Parameters
    ----------
    index : int
        Channel index in presentation order.

    Returns
    -------
    color : QColor
        A muted color tuned for a dark plot background.
    """


def type_color(ch_type: str) -> QColor:
    """Return the fixed color of a channel type.

    Parameters
    ----------
    ch_type : str
        Channel type, e.g. ``'eeg'``. Unknown types fall back to the misc color.

    Returns
    -------
    color : QColor
        The channel-type color.
    """


def contrast_ratio(fg: QColor, bg: QColor) -> float:
    """Return the WCAG contrast ratio between two opaque colors.

    Parameters
    ----------
    fg : QColor
        Foreground color.
    bg : QColor
        Background color.

    Returns
    -------
    ratio : float
        The contrast ratio, between 1 and 21.
    """


def icon(name: str, **kwargs) -> QIcon:
    """Return a QtAwesome icon, so every component draws icons the same way.

    Parameters
    ----------
    name : str
        QtAwesome icon name, e.g. ``'mdi6.refresh'``.
    **kwargs
        Additional keyword arguments are provided to :func:`qtawesome.icon`, e.g.
        ``color`` or ``scale_factor``.

    Returns
    -------
    icon : QIcon
        The rendered icon, colored with the active theme's icon token by default.
    """
