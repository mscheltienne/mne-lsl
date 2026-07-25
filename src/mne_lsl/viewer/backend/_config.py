"""Named configurations: the envelope and its JSON persistence.

Configurations are application-managed: the storage location and the file format are
deliberately hidden from the interface, which only ever asks for a human-readable name.
This module is deliberately free of Qt and of LSL imports.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...utils._checks import check_type
from ...utils.logs import logger

# Bumped whenever the serialized layout changes; a configuration carrying an unknown
# version is reported as 'invalid' rather than migrated silently.
SCHEMA_VERSION = 1

# Availability states of a configuration card. The 4 settled states are distinct on
# purpose: the reason shown to the user differs.
STATE_CHECKING = "checking"  # the channel probe of an identity match is in flight
STATE_AVAILABLE = "available"  # every identity is present and the channels match
STATE_UNAVAILABLE_NO_MATCH = "unavailable-no-match"  # an identity tuple is missing
STATE_UNAVAILABLE_CHANNELS = "unavailable-channels"  # identities match, channels do not
STATE_INVALID = "invalid"  # schema/version mismatch or corrupt JSON
STATE_LOADING = "loading"  # the configuration is being opened

# Reasons carried by an invalid configuration, i.e. by one whose envelope could not be
# interpreted. Two distinct strings, because the two situations call for different user
# actions: delete the file, or upgrade MNE-LSL.
_REASON_UNREADABLE = "unreadable configuration file"
_REASON_NEWER = "written by a newer version of MNE-LSL"

# Case-insensitive on every Windows filesystem, and unusable as a file name whatever the
# extension. mne-lsl ships Windows wheels, thus the check is not academic.
_WINDOWS_RESERVED = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{k}" for k in range(1, 10)),
        *(f"lpt{k}" for k in range(1, 10)),
    }
)

# Bound on the slug collision walk. A user with 999 configurations sharing a slug has a
# different problem; the bound exists so a bug cannot spin forever.
_MAX_COLLISIONS = 1000


def config_dir() -> Path:
    """Return the directory holding the saved configurations.

    Returns
    -------
    directory : Path
        ``~/.mne-lsl/viewer/configurations``, which may not exist yet.

    Notes
    -----
    Computed on every call rather than resolved once into a module constant, for two
    reasons. The home directory is read at call time instead of at import time, which is
    what lets the tests point it elsewhere with
    ``monkeypatch.setattr(Path, "home", ...)``, and it keeps the import of this module
    free of filesystem access. The ``configurations`` subdirectory matters as well: the
    global theme preference lives in ``~/.mne-lsl/viewer/settings.json``, and a
    ``*.json`` glob over the parent would list it as a corrupt configuration.

    A persistent home dot-directory, not a cache which the OS may purge, and not a
    :mod:`platformdirs` location: a single visible path, identical on every platform, is
    the deliberate choice. There is no environment override.
    """
    return Path.home() / ".mne-lsl" / "viewer" / "configurations"


def channel_key(identity: tuple[str, str, str]) -> str:
    r"""Return the key of ``identity`` in the ``channels`` mapping of a configuration.

    Parameters
    ----------
    identity : tuple of str
        Exact identity tuple ``(name, stype, source_id)``.

    Returns
    -------
    key : str
        The 3 elements as a JSON array, e.g. ``'["Polar", "eeg", "unit-001"]'``.

    Notes
    -----
    Spelled once here because it is the contract between the writer of a configuration
    and the availability check which reads it back: two independent spellings of the
    same encoding is how the two silently diverge.

    A JSON array rather than a join on a separator character. An LSL stream name is free
    text and a tabulation *is* accepted in one, so joining on a tabulation would give
    ``('A\tB', 'C', 'D')`` and ``('A', 'B\tC', 'D')`` the same key -- contrived, but an
    ambiguous key is not a property worth relying on. :mod:`json` escapes its own
    separators, thus the encoding is unambiguous whatever the identifiers hold.
    """
    return json.dumps(identity)


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
        Channel names expected per stream, keyed by :func:`channel_key`. Compared
        against the probed channel set to distinguish
        :data:`STATE_UNAVAILABLE_CHANNELS` from :data:`STATE_UNAVAILABLE_NO_MATCH`. An
        identity of :attr:`streams` with no entry here is an event source: it takes part
        in the identity match and is never probed.
    presentation : dict
        Opaque payload: per-document presentation state (channel edits, visibility and
        order, display and processing settings, event mappings), the Qt-ADS layout
        returned by ``CDockManager.saveState()`` and the main-window geometry.
    invalid_reason : str | None
        ``None`` for a configuration whose envelope was interpreted. Otherwise the
        reason the interface shows on the invalid card, every other field being empty.
    """

    name: str
    schema_version: int = SCHEMA_VERSION
    streams: list[tuple[str, str, str]] = field(default_factory=list)
    channels: dict[str, list[str]] = field(default_factory=dict)
    presentation: dict[str, Any] = field(default_factory=dict)
    invalid_reason: str | None = None


def _slug(name: str) -> str:
    """Return the file stem of a configuration named ``name``.

    Parameters
    ----------
    name : str
        Human-readable configuration name.

    Returns
    -------
    slug : str
        A stem which is safe on every supported filesystem.

    Notes
    -----
    ``casefold()`` runs *before* the substitution, which is what makes APFS, HFS+, ext4
    and NTFS behave identically: the stem can then never differ from another one by case
    alone. The character class strips path separators, ``..``, spaces and every
    non-ASCII character, so the human name stays free-form -- a purely non-Latin name
    slugs to ``'configuration'`` and collides its way to ``configuration-2``.

    The trailing hyphen is stripped **twice** on purpose: truncating to 64 characters
    can re-introduce one which the first strip had removed.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:64].strip("-")
    slug = slug or "configuration"
    if slug in _WINDOWS_RESERVED:
        slug += "-cfg"
    return slug


def _unreadable(title: str) -> ViewerConfig:
    """Return the invalid card of a configuration whose envelope did not interpret.

    Parameters
    ----------
    title : str
        Title the interface shows on the card, see :func:`_parse`.

    Returns
    -------
    cfg : ViewerConfig
        An empty configuration carrying :data:`_REASON_UNREADABLE`.
    """
    return ViewerConfig(name=title, invalid_reason=_REASON_UNREADABLE)


def _read(path: Path) -> dict[str, Any] | None:
    """Return the JSON object stored in ``path``, or ``None`` if unreadable.

    Parameters
    ----------
    path : Path
        Path of the file to read.

    Returns
    -------
    data : dict | None
        The decoded mapping, or ``None`` if the file could not be read, does not hold
        valid JSON, or does not hold a JSON object.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _parse_streams(data: dict[str, Any]) -> list[tuple[str, str, str]] | None:
    """Return the identity tuples of ``data``, or ``None`` if the list is malformed.

    Parameters
    ----------
    data : dict
        The decoded configuration mapping.

    Returns
    -------
    streams : list of tuple of str | None
        The identity tuples, or ``None`` if the field is absent, is not a non-empty
        list, or holds an entry which is not 3 non-empty strings.
    """
    streams = data.get("streams")
    if not isinstance(streams, list) or len(streams) == 0:
        return None
    identities = []
    for entry in streams:
        if not isinstance(entry, (list, tuple)) or len(entry) != 3:
            return None
        if not all(isinstance(item, str) and item for item in entry):
            return None
        identities.append(tuple(entry))
    return identities


def _parse_channels(data: dict[str, Any], path: Path) -> dict[str, list[str]] | None:
    """Return the channel mapping of ``data``, or ``None`` if it is not a mapping.

    Parameters
    ----------
    data : dict
        The decoded configuration mapping.
    path : Path
        Path of the file, for the log messages.

    Returns
    -------
    channels : dict | None
        The channel names per identity key. ``None`` only if the field is present and is
        not a mapping, which is an envelope failure; an unusable *entry* is dropped with
        a log line instead, as leaf tolerance is what lets an additive schema change
        stay version-compatible.
    """
    channels = data.get("channels", {})
    if not isinstance(channels, dict):
        return None
    parsed: dict[str, list[str]] = {}
    for key, value in channels.items():
        if not isinstance(key, str) or not isinstance(value, list):
            logger.warning("Dropping a malformed 'channels' entry of %s.", path)
            continue
        if not all(isinstance(item, str) for item in value):
            logger.warning(
                "Dropping the 'channels' entry of %s which does not hold channel "
                "names.",
                path,
            )
            continue
        parsed[key] = list(value)
    return parsed


def _parse(path: Path) -> ViewerConfig:
    """Return the configuration stored in ``path``, invalid if the envelope is not.

    Parameters
    ----------
    path : Path
        Path of the file to parse.

    Returns
    -------
    cfg : ViewerConfig
        The parsed configuration, or one carrying an :attr:`ViewerConfig.invalid_reason`
        and an empty payload.

    Notes
    -----
    The envelope is validated strictly and everything beyond it is tolerated, which is
    the line that lets an additive field arrive without bumping
    :data:`SCHEMA_VERSION`: a strict leaf check would make every future viewer change a
    breaking change, while a strict envelope check is what actually protects the load
    path. An invalid card is titled by the file's ``name`` when that much is readable,
    else by the file stem, so that it can be identified and deleted.
    """
    data = _read(path)
    if data is None:
        return _unreadable(path.stem)
    # the title of an invalid card, once the file itself was decoded.
    name = data.get("name")
    title = name.strip() if isinstance(name, str) and name.strip() else path.stem
    version = data.get("schema_version")
    # a bool passes 'isinstance(True, int)', and a JSON float is not an int: both are
    # rejected, as neither can be a version this reader knows.
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        return _unreadable(title)
    if version > SCHEMA_VERSION:
        return ViewerConfig(name=title, invalid_reason=_REASON_NEWER)
    # 'version < SCHEMA_VERSION' is unreachable while SCHEMA_VERSION == 1. A version 2
    # gains one '_upgrade_v1_to_v2(data)' call here, not a migration framework.
    if not isinstance(name, str) or not name.strip():
        return _unreadable(title)
    streams = _parse_streams(data)
    if streams is None:
        return _unreadable(title)
    channels = _parse_channels(data, path)
    if channels is None:
        return _unreadable(title)
    presentation = data.get("presentation", {})
    if not isinstance(presentation, dict):
        logger.warning("Ignoring the malformed 'presentation' payload of %s.", path)
        presentation = {}
    # unknown top-level keys are ignored, thus dropped by the next save. That is the
    # documented consequence of tolerating them rather than refusing the file.
    return ViewerConfig(
        name=name,
        schema_version=version,
        streams=streams,
        channels=channels,
        presentation=presentation,
    )


def _find(name: str) -> Path | None:
    """Return the file holding the configuration named ``name``, if any.

    Parameters
    ----------
    name : str
        Name of the configuration to look up, matched case-insensitively.

    Returns
    -------
    path : Path | None
        Path of the file, or ``None`` if no file matches.

    Notes
    -----
    The authoritative name lives *inside* the file, thus every configuration is parsed
    and it is that name which is compared. An invalid configuration matches too, on the
    title its card carries -- the inner name when that much was readable, the file stem
    otherwise -- because :func:`delete_configuration` is the only way to clear a corrupt
    file from the interface and can only be asked for what the card shows. A valid match
    wins over an invalid one.

    The file stem of a *valid* configuration is deliberately never compared: it is
    derived from the name, it is not the name. Comparing it would let
    ``save_configuration(ViewerConfig(name='my-config'))`` silently overwrite the
    unrelated configuration named ``'My Config'``, which :func:`_slug` had already
    put in ``my-config.json``.
    """
    target = name.casefold()
    invalid: Path | None = None
    for path in sorted(config_dir().glob("*.json")):
        cfg = _parse(path)
        if cfg.name.casefold() != target:
            continue
        if cfg.invalid_reason is None:
            return path
        if invalid is None:
            invalid = path
    return invalid


def _new_path(name: str) -> Path:
    """Return a free path for a configuration named ``name``.

    Parameters
    ----------
    name : str
        Name of the configuration to write.

    Returns
    -------
    path : Path
        ``<slug>.json``, or ``<slug>-2.json``, ``<slug>-3.json``, ... if taken.

    Raises
    ------
    RuntimeError
        If no free path was found.
    """
    directory = config_dir()
    slug = _slug(name)
    for k in range(1, _MAX_COLLISIONS):
        path = directory / (f"{slug}.json" if k == 1 else f"{slug}-{k}.json")
        if not path.exists():
            return path
    raise RuntimeError(
        f"Could not find a free file name for the configuration '{name}': "
        f"'{slug}.json' and its {_MAX_COLLISIONS - 2} numbered variants are all taken."
    )


def _to_dict(cfg: ViewerConfig) -> dict[str, Any]:
    """Return the JSON-serializable mapping of ``cfg``.

    Parameters
    ----------
    cfg : ViewerConfig
        The configuration to serialize.

    Returns
    -------
    data : dict
        The mapping written to disk. :attr:`ViewerConfig.invalid_reason` is not part of
        it: it describes a file which could not be read, never one being written.

    Notes
    -----
    The payload is referenced, not copied: :func:`json.dumps` serializes a tuple as a
    JSON array just as it does a list, and :func:`_atomic_write` consumes the mapping
    synchronously, so there is no window in which a caller could mutate it.
    """
    return {
        "schema_version": cfg.schema_version,
        "name": cfg.name,
        "streams": cfg.streams,
        "channels": cfg.channels,
        "presentation": cfg.presentation,
    }


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Write ``data`` to ``path`` as JSON, atomically.

    Parameters
    ----------
    path : Path
        Path of the file to write.
    data : dict
        The mapping to serialize.

    Notes
    -----
    :func:`os.replace` on a closed handle guarantees that a reader sees either the old
    or the new file, never a torn one, which is the only property that matters here. No
    :func:`os.fsync`: this is a preferences store, trivially recreatable, not a
    durability-critical one. ``indent=2`` because inspectability is the reason JSON was
    chosen in the first place.

    A failure between the write and the replace leaves a ``.json.tmp`` file behind. It
    is deliberately never cleaned up: ``glob('*.json')`` does not match it, so it is
    invisible to the interface and harmless, and the next save of the same
    configuration overwrites it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def list_configurations() -> list[ViewerConfig]:
    """Return the saved configurations, ordered by name.

    A file which does not parse or which carries an unknown schema version is returned
    with an empty payload so that the interface can show it as invalid instead of
    hiding it.

    Returns
    -------
    configurations : list of ViewerConfig
        The saved configurations found in :func:`config_dir`.

    Notes
    -----
    Never creates the directory: nothing in the package writes to the filesystem at
    import or on first use. A missing directory simply yields an empty list, as
    :meth:`~pathlib.Path.glob` on a missing directory is empty rather than an error.

    There is no index file. Listing is one glob plus a parse over a handful of files,
    whereas an index would add a second write target and a consistency problem to
    repair whenever a file appears or disappears out of band.
    """
    configs = [_parse(path) for path in sorted(config_dir().glob("*.json"))]
    return sorted(configs, key=lambda cfg: cfg.name.casefold())


def save_configuration(cfg: ViewerConfig) -> Path:
    """Write ``cfg`` to :func:`config_dir`, replacing an existing file of that name.

    Parameters
    ----------
    cfg : ViewerConfig
        The configuration to save.

    Returns
    -------
    fname : Path
        Path of the written file.

    Raises
    ------
    TypeError
        If ``cfg`` is not a :class:`ViewerConfig`.
    ValueError
        If :attr:`ViewerConfig.name` is empty or blank, or if
        :attr:`ViewerConfig.streams` is empty.

    Notes
    -----
    The name is only checked for being non-blank. The 120-character cap is interface
    policy, applied by the Save-as prompt, and no character is rejected because
    :func:`_slug` neutralizes them all.

    An empty :attr:`ViewerConfig.streams` is refused because :func:`_parse_streams`
    refuses it on the way back in: writing one would return a path to a file the next
    :func:`list_configurations` reports as invalid. The writer and the reader have to
    agree on that, and a configuration referencing no stream has nothing to show anyway.

    A :class:`TypeError` raised by :func:`json.dumps` on a non-serializable
    :attr:`ViewerConfig.presentation` propagates: that payload is opaque to this module
    and a value it cannot serialize is a caller bug, not a corrupt file.
    """
    check_type(cfg, (ViewerConfig,), "cfg")
    if not cfg.name.strip():
        raise ValueError("The name of a configuration cannot be empty.")
    if len(cfg.streams) == 0:
        raise ValueError("A configuration must reference at least one stream.")
    path = _find(cfg.name) or _new_path(cfg.name)
    _atomic_write(path, _to_dict(cfg))
    logger.debug("Saved the configuration '%s' to %s.", cfg.name, path)
    return path


def delete_configuration(name: str) -> None:
    """Delete the configuration named ``name``; missing files are ignored.

    Parameters
    ----------
    name : str
        Name of the configuration to delete.
    """
    check_type(name, (str,), "name")
    path = _find(name)
    if path is None:
        return
    path.unlink(missing_ok=True)
    logger.debug("Deleted the configuration '%s' at %s.", name, path)
