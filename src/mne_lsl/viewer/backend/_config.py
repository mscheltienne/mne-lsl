"""Named configurations: the envelope and its JSON persistence.

Configurations are application-managed: the storage location and the file format are
deliberately hidden from the interface, which only ever asks for a human-readable name.
This module is deliberately free of Qt and of LSL imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Persistent home dot-directory, not a cache which the OS may purge.
CONFIG_DIR = Path.home() / ".mne-lsl" / "viewer"

# Bumped whenever the serialized layout changes; a configuration carrying an unknown
# version is reported as 'invalid' rather than migrated silently.
SCHEMA_VERSION = 1

# Availability states of a configuration card. The two 'unavailable' states are distinct
# on purpose: the reason shown to the user differs.
STATE_CHECKING = "checking"  # discovery/probe has not completed yet
STATE_READY = "ready"  # every identity is present and the channels match
STATE_UNAVAILABLE_STREAM = "unavailable-stream"  # an identity tuple is missing
STATE_UNAVAILABLE_CHANNELS = "unavailable-channels"  # identities match, channels do not
STATE_INVALID = "invalid"  # schema/version mismatch or corrupt JSON


@dataclass
class ViewerConfig:
    r"""One named configuration.

    Only the envelope is defined: the exact content of :attr:`presentation` is an open
    design question (see ``brief/design/09_functionality_and_failure_modes.md`` §6),
    thus it is carried as an opaque mapping which the viewer writes and reads back as a
    whole and which nothing else interprets.

    Parameters
    ----------
    name : str
        Human-readable configuration name, also its file name.
    schema_version : int
        Version of the serialized layout, see :data:`SCHEMA_VERSION`.
    streams : list of tuple of str
        Exact identity tuples ``(name, stype, source_id)`` required by the
        configuration, regular and event streams alike. An identity which is missing
        from the network makes the configuration unavailable.
    channels : dict
        Channel names expected per stream, keyed by the identity tuple joined by
        ``'\\t'``. Compared against the probed channel set to distinguish
        :data:`STATE_UNAVAILABLE_CHANNELS` from :data:`STATE_UNAVAILABLE_STREAM`.
    presentation : dict
        Opaque payload: per-document presentation state (channel edits, visibility and
        order, display and processing settings, event mappings), the Qt-ADS layout
        returned by ``CDockManager.saveState()`` and the main-window geometry.
    """

    name: str
    schema_version: int = SCHEMA_VERSION
    streams: list[tuple[str, str, str]] = field(default_factory=list)
    channels: dict[str, list[str]] = field(default_factory=dict)
    presentation: dict[str, Any] = field(default_factory=dict)


def list_configurations() -> list[ViewerConfig]:
    """Return the saved configurations, ordered by name.

    A file which does not parse or which carries an unknown schema version is returned
    with an empty payload so that the interface can show it as invalid instead of
    hiding it.

    Returns
    -------
    configurations : list of ViewerConfig
        The saved configurations found in :data:`CONFIG_DIR`.
    """


def save_configuration(cfg: ViewerConfig) -> Path:
    """Write ``cfg`` to :data:`CONFIG_DIR`, replacing an existing file of that name.

    Parameters
    ----------
    cfg : ViewerConfig
        The configuration to save.

    Returns
    -------
    fname : Path
        Path of the written file.
    """


def delete_configuration(name: str) -> None:
    """Delete the configuration named ``name``; missing files are ignored.

    Parameters
    ----------
    name : str
        Name of the configuration to delete.
    """
