"""Public facade of the viewer."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..stream import BaseStream
    from ._window import ViewerWindow


class Viewer:
    """Qt 6 viewer to discover, inspect and monitor LSL streams.

    Every launch starts disconnected: no stream is reconnected automatically, and the
    discovery runs in the background while the window is already responsive.

    Parameters
    ----------
    stream : BaseStream | None
        A connected stream to open a document for. It is **borrowed**: the viewer never
        disconnects it and closing its document leaves it connected, which is the
        :meth:`~mne_lsl.stream.BaseStream.plot` path. A stream which the viewer creates
        itself from the landing page is owned and is disconnected when its document
        closes.
    theme : str
        ``'auto'`` follows the OS color scheme, ``'light'`` and ``'dark'`` force it.
    """

    def __init__(
        self, stream: BaseStream | None = None, *, theme: str = "auto"
    ) -> None:
        """Initialize the viewer without creating any Qt object."""

    def show(self) -> ViewerWindow:
        """Create the application and the window, then show it.

        Does not enter the event loop, thus it returns immediately. This is the entry
        point used by the tests and by a caller which already runs an event loop.

        Returns
        -------
        window : ViewerWindow
            The window which was shown.
        """

    def start(self) -> int:
        """Show the window and run the event loop until the window closes.

        The blocking entry point of the ``mne-lsl viewer`` command. A failure during the
        startup tears down whatever was already built, including a borrowed stream's
        document, before propagating.

        Returns
        -------
        code : int
            The exit code of the event loop.
        """

    @property
    def window(self) -> ViewerWindow | None:
        """The window, or ``None`` before :meth:`show` was called."""
