from __future__ import annotations

import pytest

from core.domain.value_objects.portable_storage_key import PortableStorageKey


def test_portable_storage_key_preserves_one_canonical_posix_representation():
    key = PortableStorageKey("characters/akira/references/front/0001.png")

    assert str(key) == "characters/akira/references/front/0001.png"
    assert key.name == "0001.png"
    assert key.suffix == ".png"
    assert key.require_suffix(".png") is key


@pytest.mark.parametrize(
    "value",
    (
        "",
        " storyboards/shot.png",
        "storyboards/shot.png ",
        "/storyboards/shot.png",
        "../storyboards/shot.png",
        "storyboards/../shot.png",
        ".",
        "storyboards\\shot.png",
        "C:/storyboards/shot.png",
        "storyboards//shot.png",
        "storyboards/./shot.png",
        "storyboards/shot.png/",
    ),
)
def test_portable_storage_key_rejects_noncanonical_or_unsafe_values(value):
    with pytest.raises(ValueError):
        PortableStorageKey(value)


def test_portable_storage_key_rejects_unapproved_suffix():
    with pytest.raises(ValueError, match="must use one of"):
        PortableStorageKey("motion/shot.gif").require_suffix(".mp4", ".webm")
