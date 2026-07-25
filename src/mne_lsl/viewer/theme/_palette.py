"""``QPalette`` construction, theme application and the OS-following controller."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import QObject, Signal

if TYPE_CHECKING:
    from qtpy.QtGui import QPalette
    from qtpy.QtWidgets import QApplication


def build_qpalette(mode: str = "auto") -> QPalette:
    """Build a complete Fusion ``QPalette`` for ``mode``.

    Maps the tokens onto every relevant role for the Active/Inactive groups and a
    dedicated Disabled group so disabled text stays legible. The bevel ramp
    (``Light``/``Midlight``/``Dark``/``Shadow``) is derived from ``window`` so the token
    table stays purely semantic; ``Mid`` is the secondary-text color.

    Parameters
    ----------
    mode : str
        ``'auto'``, ``'light'`` or ``'dark'``.

    Returns
    -------
    palette : QPalette
        The palette to hand to :meth:`QApplication.setPalette`.
    """


def apply_theme(app: QApplication, mode: str = "auto") -> str:
    """Apply the full theme to ``app`` and return the resolved mode.

    Sets the Fusion style, installs the mode's palette and the thin QSS, pushes the
    pyqtgraph background/foreground config, restyles the existing plots and refreshes
    the QtAwesome default icon color. Does not emit ``theme_changed``, which is
    :class:`ThemeController`'s job.

    Parameters
    ----------
    app : QApplication
        The running application.
    mode : str
        ``'auto'`` follows the OS scheme; ``'light'`` / ``'dark'`` force it.

    Returns
    -------
    mode : str
        The concrete mode which was applied, ``'light'`` or ``'dark'``.
    """


class ThemeController(QObject):
    """Re-apply the theme on OS/user changes and notify the consumers.

    Wraps :func:`apply_theme` with the runtime plumbing: it follows
    ``styleHints().colorSchemeChanged`` while the user setting is ``'auto'``, exposes
    the user setting and the resolved mode, and emits :attr:`theme_changed` after every
    (re)theme so consumers can recompute pyqtgraph colors, rebuild cached icons and
    refresh trace pens.

    Attributes
    ----------
    theme_changed : Signal
        Emitted with the resolved mode (``'light'`` / ``'dark'``) after every apply.
    """

    theme_changed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

    @property
    def mode(self) -> str:
        """Resolved concrete mode, ``'light'`` or ``'dark'``."""

    @property
    def setting(self) -> str:
        """User setting, ``'auto'``, ``'light'`` or ``'dark'``."""

    def install(self, app: QApplication, setting: str = "auto") -> str:
        """Bind to ``app``, connect the OS follower and apply ``setting`` once.

        Parameters
        ----------
        app : QApplication
            The running application.
        setting : str
            Initial user setting, ``'auto'``, ``'light'`` or ``'dark'``.

        Returns
        -------
        mode : str
            The concrete mode which was applied.
        """
        # Connect a *bound method* of this instance to
        # 'app.styleHints().colorSchemeChanged', and do not pass
        # 'Qt.ConnectionType.UniqueConnection': connecting a free function with
        # 'UniqueConnection' silently fails to register on PySide6 6.11.1, which would
        # leave the OS theme-following dead under PySide6 while working under PyQt6.

    def set_mode(self, setting: str) -> str:
        """Set the user ``setting``, re-apply the theme and emit the change.

        Parameters
        ----------
        setting : str
            ``'auto'`` follows the OS; ``'light'`` / ``'dark'`` force the mode.

        Returns
        -------
        mode : str
            The concrete mode which was applied.
        """


# Module singleton shared by every consumer, e.g. to connect 'theme_changed'. A QObject
# is safe to build before the QApplication exists, unlike a QWidget.
theme_controller = ThemeController()
