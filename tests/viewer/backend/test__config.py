from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

import pytest

from mne_lsl.viewer.backend import (
    SCHEMA_VERSION,
    STATE_AVAILABLE,
    STATE_CHECKING,
    STATE_INVALID,
    STATE_LOADING,
    STATE_UNAVAILABLE_CHANNELS,
    STATE_UNAVAILABLE_NO_MATCH,
    ViewerConfig,
    _config,
    channel_key,
    config_dir,
    delete_configuration,
    list_configurations,
    save_configuration,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from types import ModuleType

_STATES = (
    STATE_CHECKING,
    STATE_AVAILABLE,
    STATE_UNAVAILABLE_CHANNELS,
    STATE_UNAVAILABLE_NO_MATCH,
    STATE_INVALID,
    STATE_LOADING,
)

# referenced, never re-typed as literals: two independent spellings of one string is the
# exact divergence 'channel_key''s own docstring warns about, and a test spelling the
# reason itself passes just as happily against a module which no longer emits it.
_REASON_UNREADABLE = _config._REASON_UNREADABLE
_REASON_NEWER = _config._REASON_NEWER


def _write(stem: str, content: str) -> Path:
    """Write a raw configuration file and return its path."""
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}.json"
    path.write_text(content, encoding="utf-8")
    return path


def _full() -> ViewerConfig:
    """Return a configuration with every field populated."""
    identity = ("Cognionics", "eeg", "EEG-256")
    return ViewerConfig(
        name="2-stream comparison",
        streams=[identity, ("Markers", "annotations", "marker-001")],
        channels={channel_key(identity): ["Fp1", "Fp2", "F7"]},
        presentation={"layout": "<?xml version='1.0'?><root/>", "rows": 20},
    )


# -- import rules -------------------------------------------------------------------
def test_no_qt_no_lsl_import(
    module_scan: Callable[[ModuleType], tuple[set[str], set[str]]],
) -> None:
    """Test that '_config.py' imports neither Qt nor LSL and never names 'StreamLSL'.

    This is what makes configuration persistence testable with plain pytest, and it is a
    source-level rule: it cannot be asserted through 'sys.modules', since importing this
    module transitively imports both.

    The identifiers are checked as well as the import paths, see the same test in
    'test__discovery.py' for the two forms each set alone misses.
    """
    imports, identifiers = module_scan(_config)
    forbidden = {"qtpy", "PyQt6", "PySide6", "pyqtgraph", "lsl"}
    for name in imports:
        assert not forbidden & set(name.split(".")), name
    assert not (forbidden | {"StreamLSL"}) & identifiers


# -- constants and paths ------------------------------------------------------------
def test_config_dir(config_home: Path) -> None:
    """Test that the directory follows 'Path.home()' and is a dedicated subdirectory."""
    assert config_dir() == config_home / ".mne-lsl" / "viewer" / "configurations"
    # dedicated, so that '~/.mne-lsl/viewer/settings.json' -- the global theme
    # preference -- is never globbed as a corrupt configuration.
    assert config_dir().name == "configurations"


def test_states_are_distinct() -> None:
    """Test that the six card states are distinct lowercase tags."""
    assert len(set(_STATES)) == len(_STATES)
    for state in _STATES:
        assert state
        assert state == state.lower()


def test_schema_version() -> None:
    """Test the current schema version."""
    assert SCHEMA_VERSION == 1


def test_channel_key() -> None:
    """Test that an identity keys the channel mapping unambiguously.

    A tabulation is accepted in an LSL stream name, thus a join on one -- or on any
    other single character -- gives two different identities the same key.
    """
    assert channel_key(("Polar", "eeg", "unit-001")) == '["Polar", "eeg", "unit-001"]'
    assert channel_key(("A\tB", "C", "D")) != channel_key(("A", "B\tC", "D"))


# -- slug ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("2-stream comparison", "2-stream-comparison"),
        ("MyConfig", "myconfig"),
        ("myconfig", "myconfig"),
        # accents are dropped rather than transliterated, which is deliberate: the
        # authoritative name lives inside the file, the stem only has to be unique.
        ("Ünïcödé", "n-c-d"),
        ("日本語", "configuration"),  # nothing survives -> the fallback stem
        ("  --  ", "configuration"),
        ("", "configuration"),
        ("con", "con-cfg"),
        ("COM1", "com1-cfg"),
        ("a/b", "a-b"),
        ("../../etc/passwd", "etc-passwd"),
        ("a" * 100, "a" * 64),
    ],
)
def test_slug(name: str, slug: str) -> None:
    """Test the slug derivation, including the filesystem traps it neutralizes."""
    assert _config._slug(name) == slug


def test_slug_strips_twice() -> None:
    """Test that truncation cannot leave a trailing hyphen behind.

    The strip runs twice in '_slug': capping at 64 characters re-introduces the hyphen
    which the first strip had removed.
    """
    assert _config._slug("a" * 63 + " b") == "a" * 63


# -- round-trip ---------------------------------------------------------------------
def test_save_and_list(config_home: Path) -> None:
    """Test that a fully populated configuration round-trips."""
    cfg = _full()
    path = save_configuration(cfg)
    assert path == config_dir() / "2-stream-comparison.json"
    assert sorted(config_dir().glob("*.json")) == [path]
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert '\n  "name"' in text  # indent=2, for inspectability
    (parsed,) = list_configurations()
    assert parsed == cfg
    assert parsed.invalid_reason is None
    # the identities come back as tuples, which is what the availability check compares.
    assert all(isinstance(identity, tuple) for identity in parsed.streams)


def test_save_overwrites(config_home: Path) -> None:
    """Test that saving the same name twice replaces the file in place."""
    cfg = _full()
    first = save_configuration(cfg)
    cfg.presentation = {"rows": 8}
    second = save_configuration(cfg)
    assert first == second
    assert sorted(config_dir().glob("*.json")) == [first]
    (parsed,) = list_configurations()
    assert parsed.presentation == {"rows": 8}


def test_save_slug_collision(config_home: Path) -> None:
    """Test that names sharing a slug get one file each, each keeping its own name.

    The third name is the *stem* the first two share, which is the interesting one:
    'a/b' and 'a b' both slug to a stem neither of them spells, so a lookup falling back
    to the stem cannot confuse them, while 'a-b' spells it exactly.
    """
    identity = [("a", "b", "c")]
    first = save_configuration(ViewerConfig(name="a/b", streams=identity))
    second = save_configuration(ViewerConfig(name="a b", streams=identity))
    third = save_configuration(ViewerConfig(name="a-b", streams=identity))
    assert [path.name for path in (first, second, third)] == [
        "a-b.json",
        "a-b-2.json",
        "a-b-3.json",
    ]
    assert [cfg.name for cfg in list_configurations()] == ["a b", "a-b", "a/b"]


def test_save_does_not_overwrite_a_configuration_by_its_stem(config_home: Path) -> None:
    """Test that saving a name which spells another file's stem does not overwrite it.

    The authoritative name lives *inside* the file and the stem is only derived from it,
    thus matching a save on the stem silently replaces an unrelated configuration and
    loses it: 'My Config' is written to 'my-config.json', and a later save of the
    configuration named 'my-config' must not land in that same file.
    """
    streams = [("a", "b", "c")]
    first = save_configuration(ViewerConfig(name="My Config", streams=streams))
    assert first.name == "my-config.json"
    second = save_configuration(ViewerConfig(name="my-config", streams=streams))
    assert second.name == "my-config-2.json"
    assert [cfg.name for cfg in list_configurations()] == ["My Config", "my-config"]


def test_save_leaves_no_temporary_file(config_home: Path) -> None:
    """Test that the atomic write leaves nothing behind on success."""
    save_configuration(_full())
    assert list(config_dir().glob("*.tmp")) == []


def test_save_failure_keeps_the_previous_file(
    config_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that a failed replace leaves the previous file byte-identical.

    That is the entire point of writing to a temporary file and replacing it: a reader
    sees either the old or the new file, never a torn one.
    """
    cfg = _full()
    path = save_configuration(cfg)
    before = path.read_bytes()

    def _replace(*args: object, **kwargs: object) -> None:
        raise OSError("no space left on device")

    monkeypatch.setattr(os, "replace", _replace)
    cfg.presentation = {"rows": 1}
    with pytest.raises(OSError, match="no space left"):
        save_configuration(cfg)
    assert path.read_bytes() == before


def test_save_rejects_a_bad_argument(config_home: Path) -> None:
    """Test that the type and the name of a configuration are validated."""
    with pytest.raises(TypeError, match="'cfg' must be an instance of ViewerConfig"):
        save_configuration({"name": "x"})
    with pytest.raises(ValueError, match="cannot be empty"):
        save_configuration(ViewerConfig(name="   "))


def test_save_rejects_a_configuration_without_stream(config_home: Path) -> None:
    """Test that a configuration referencing no stream is refused instead of written.

    '_parse_streams' refuses an empty 'streams' on the way back in, so writing one would
    hand back the path of a file which the very next listing reports as invalid.
    """
    with pytest.raises(ValueError, match="at least one stream"):
        save_configuration(ViewerConfig(name="no stream"))
    assert list_configurations() == []


def test_save_propagates_an_unserializable_payload(config_home: Path) -> None:
    """Test that an unserializable 'presentation' is a caller bug, not a corrupt file.

    The payload is opaque to '_config', thus a value it cannot serialize is a bug in the
    writer and must not be silently dropped.
    """
    cfg = ViewerConfig(name="cfg", streams=[("a", "b", "c")])
    cfg.presentation = {"x": object()}
    with pytest.raises(TypeError):
        save_configuration(cfg)


# -- listing ------------------------------------------------------------------------
def test_list_configurations_empty(config_home: Path) -> None:
    """Test that listing a missing directory is empty and does not create it."""
    assert list_configurations() == []
    # nothing in the package writes to the filesystem at import or on first use.
    assert not config_dir().exists()


def test_list_configurations_order(config_home: Path) -> None:
    """Test that configurations are ordered by casefolded name, invalid ones too."""
    for name in ("beta", "Alpha"):
        save_configuration(ViewerConfig(name=name, streams=[("a", "b", "c")]))
    _write("corrupt", "{")
    assert [cfg.name for cfg in list_configurations()] == ["Alpha", "beta", "corrupt"]


# -- the invalid boundary -----------------------------------------------------------
_VALID = {"schema_version": 1, "name": "cfg", "streams": [["a", "b", "c"]]}


def _raw(**overrides: object) -> str:
    """Return the JSON of a valid envelope with 'overrides' applied, 'None' deleting."""
    data = dict(_VALID)
    for key, value in overrides.items():
        if value is None:
            del data[key]
        else:
            data[key] = value
    return json.dumps(data)


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("{", _REASON_UNREADABLE),
        ("[]", _REASON_UNREADABLE),
        ('"x"', _REASON_UNREADABLE),
        (_raw(schema_version=None), _REASON_UNREADABLE),
        (_raw(schema_version="1"), _REASON_UNREADABLE),
        (_raw(schema_version=1.0), _REASON_UNREADABLE),
        (_raw(schema_version=0), _REASON_UNREADABLE),
        (_raw(schema_version=True), _REASON_UNREADABLE),
        (_raw(schema_version=2), _REASON_NEWER),
        (_raw(name=None), _REASON_UNREADABLE),
        (_raw(name=""), _REASON_UNREADABLE),
        (_raw(name="   "), _REASON_UNREADABLE),
        (_raw(name=123), _REASON_UNREADABLE),
        (_raw(streams=None), _REASON_UNREADABLE),
        (_raw(streams={}), _REASON_UNREADABLE),
        (_raw(streams=[]), _REASON_UNREADABLE),
        (_raw(streams=[["a", "b"]]), _REASON_UNREADABLE),
        (_raw(streams=[["a", "b", ""]]), _REASON_UNREADABLE),
        (_raw(streams=[["a", "b", "c"], "x"]), _REASON_UNREADABLE),
        (_raw(channels=[]), _REASON_UNREADABLE),
    ],
)
def test_invalid_envelope(config_home: Path, content: str, reason: str) -> None:
    """Test that an uninterpretable envelope yields an invalid card with a reason."""
    _write("broken", content)
    (cfg,) = list_configurations()
    assert cfg.invalid_reason == reason
    assert cfg.streams == []
    assert cfg.channels == {}
    assert cfg.presentation == {}


def test_invalid_title_from_the_inner_name(config_home: Path) -> None:
    """Test that an invalid card is titled by the inner name when it is readable."""
    _write("some-stem", _raw(schema_version=99, name="My workspace"))
    (cfg,) = list_configurations()
    assert cfg.name == "My workspace"
    assert cfg.invalid_reason == _REASON_NEWER


def test_invalid_title_falls_back_to_the_stem(config_home: Path) -> None:
    """Test that an invalid card is titled by the file stem when nothing else is."""
    _write("some-stem", "{")
    (cfg,) = list_configurations()
    assert cfg.name == "some-stem"


# -- tolerated leaves ---------------------------------------------------------------
def test_tolerates_a_malformed_channels_entry(
    config_home: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that an unusable 'channels' entry is dropped rather than failing the file.

    The envelope is validated strictly and the leaves are tolerated. That line is what
    lets an additive field arrive without bumping the schema version. A non-string key
    is not covered, as JSON has none.
    """
    caplog.set_level(logging.WARNING, logger="mne_lsl")
    channels = {"good": ["Fp1"], "not-names": ["Fp1", 1], "not-a-list": "Fp1"}
    _write("cfg", _raw(channels=channels))
    (cfg,) = list_configurations()
    assert cfg.invalid_reason is None
    assert cfg.channels == {"good": ["Fp1"]}
    assert "channels" in caplog.text


def test_tolerates_a_missing_channels_mapping(config_home: Path) -> None:
    """Test that an absent 'channels' mapping defaults to empty.

    An identity with no entry there is an event source: identity-matched, never probed.
    """
    _write("cfg", _raw())
    (cfg,) = list_configurations()
    assert cfg.invalid_reason is None
    assert cfg.channels == {}


def test_tolerates_a_malformed_presentation(
    config_home: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that an unusable 'presentation' payload defaults to empty."""
    caplog.set_level(logging.WARNING, logger="mne_lsl")
    _write("cfg", _raw(presentation=5))
    (cfg,) = list_configurations()
    assert cfg.invalid_reason is None
    assert cfg.presentation == {}
    assert "presentation" in caplog.text


def test_ignores_an_unknown_key(config_home: Path) -> None:
    """Test that an unknown top-level key does not invalidate the configuration.

    It is ignored, and therefore dropped by the next save: that is the documented
    consequence of tolerating unknown keys rather than refusing the file.
    """
    _write("cfg", _raw(written_by={"mne_lsl": "1.15.0"}))
    (cfg,) = list_configurations()
    assert cfg.invalid_reason is None
    assert cfg.name == "cfg"
    path = save_configuration(cfg)
    assert "written_by" not in json.loads(path.read_text(encoding="utf-8"))


# -- delete -------------------------------------------------------------------------
def test_delete_configuration(config_home: Path) -> None:
    """Test that a configuration is deleted by its human-readable name."""
    path = save_configuration(_full())
    delete_configuration("2-stream comparison")
    assert not path.exists()
    assert list_configurations() == []


def test_delete_configuration_is_case_insensitive(config_home: Path) -> None:
    """Test that the name lookup ignores case, as the slug does."""
    save_configuration(ViewerConfig(name="MyConfig", streams=[("a", "b", "c")]))
    delete_configuration("myconfig")
    assert list_configurations() == []


def test_delete_configuration_by_stem(config_home: Path) -> None:
    """Test that a corrupt file can be deleted through its card title.

    An invalid card is titled by the file stem when the inner name is unreadable, and
    Delete is the only way to clear such a file from the interface, thus the lookup must
    fall back to the stem or Delete would silently do nothing.
    """
    path = _write("corrupt", "{")
    delete_configuration("corrupt")
    assert not path.exists()


def test_delete_configuration_never_matches_a_valid_stem(config_home: Path) -> None:
    """Test that the stem of a *valid* configuration is not a name Delete answers to.

    The fallback exists for an invalid card, whose title may be its file stem. Applying
    it to a valid configuration would make 'Delete a-b' erase the configuration named
    'a/b', which the interface never showed under that title.
    """
    path = save_configuration(ViewerConfig(name="a/b", streams=[("a", "b", "c")]))
    assert path.name == "a-b.json"
    delete_configuration("a-b")
    assert path.exists()


def test_delete_configuration_unknown(config_home: Path) -> None:
    """Test that deleting an unknown configuration is a silent no-op."""
    path = save_configuration(_full())
    delete_configuration("does not exist")
    assert path.exists()


def test_delete_configuration_missing_directory(config_home: Path) -> None:
    """Test that deleting from a directory which does not exist is a no-op."""
    delete_configuration("anything")
    assert not config_dir().exists()
