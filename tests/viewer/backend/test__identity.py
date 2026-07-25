from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import pytest

from mne_lsl.viewer.backend import StreamIdentity

if TYPE_CHECKING:
    from collections.abc import Callable

    from mne_lsl.viewer.backend import StreamDescriptor


def test_as_tuple(descriptor: Callable[..., StreamDescriptor]) -> None:
    """Test that the identity round-trips through its tuple form."""
    identity = descriptor(name="Polar", source_id="src-1").identity
    assert identity.as_tuple() == ("Polar", "eeg", "src-1")
    assert StreamIdentity(*identity.as_tuple()) == identity


def test_descriptor_identity(descriptor: Callable[..., StreamDescriptor]) -> None:
    """Test that a descriptor exposes the identity object, not a bare tuple."""
    obj = descriptor(name="Polar", source_id="src-1")
    assert isinstance(obj.identity, StreamIdentity)
    assert obj.identity.as_tuple() == ("Polar", "eeg", "src-1")


def test_frozen(descriptor: Callable[..., StreamDescriptor]) -> None:
    """Test that neither dataclass can be mutated after construction."""
    obj = descriptor()
    for target, attribute in ((obj.identity, "name"), (obj, "n_channels")):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(target, attribute, "other")


def test_slots_and_hashable(descriptor: Callable[..., StreamDescriptor]) -> None:
    """Test that both dataclasses carry no instance dictionary and are hashable.

    Hashability is what the identity de-duplication of 'ViewerWindow.open_streams'
    relies on, and slots are what makes the ownership rule of a descriptor structural.
    """
    obj = descriptor()
    for target in (obj.identity, obj):
        assert not hasattr(target, "__dict__")
        assert len({target, target}) == 1


def test_same_name_different_source_id(
    descriptor: Callable[..., StreamDescriptor],
) -> None:
    """Test that two streams differing only by 'source_id' stay distinct.

    Two same-name streams are an explicitly supported case: the identity is the full
    3-tuple, thus the data layer must keep them apart before any interface does. Only
    inequality is asserted, never a hash inequality: distinct hashes are not a property
    the language promises, and the set below is what the de-duplication actually needs.
    """
    first, second = descriptor(source_id="unit-001"), descriptor(source_id="unit-002")
    assert first.identity != second.identity
    assert len({first, second}) == 2
