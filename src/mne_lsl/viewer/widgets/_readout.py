"""Compact read-out label which becomes an inline editor on click."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtWidgets import QWidget

if TYPE_CHECKING:
    from collections.abc import Callable


class EditableReadout(QWidget):
    """Read-out label which becomes an inline editor on click.

    Clicking the label swaps it in place for a line edit seeded with the current value;
    committing with Enter or on focus-out parses the text, calls ``commit`` with the
    parsed number and reverts to the label. There is no permanent edit or spin box: the
    label is the field only while editing, keeping the control strip compact.

    Parameters
    ----------
    commit : callable
        Called with the parsed value when an edit is committed.
    tip : str
        Tooltip of the read-out, suffixed with a hint that it is editable.
    parent : QWidget | None
        Parent widget.
    """

    def __init__(
        self, commit: Callable[[float], None], tip: str, parent: QWidget | None = None
    ) -> None:
        """Initialize the read-out."""

    def set_text(self, text: str) -> None:
        """Set the displayed read-out text.

        Parameters
        ----------
        text : str
            Formatted value, e.g. ``'12.5s'``.
        """

    def begin_edit(self) -> None:
        """Swap the label for the editor, seeded with the current read-out text."""
