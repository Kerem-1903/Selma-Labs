from __future__ import annotations

import pytest

from infrastructure.providers.render.remotion_media_inventory import (
    RemotionMediaInventory,
)


def test_inventory_resolves_dynamic_clip_and_audio_cue_media(tmp_path):
    public = tmp_path / "public"
    project = public / "anime-animatic" / "pilot"
    project.mkdir(parents=True)
    (project / "shot.png").write_bytes(b"png")
    (project / "dialogue.wav").write_bytes(b"wav")

    missing = RemotionMediaInventory.validate(
        {
            "clips": [{
                "imageSrc": "anime-animatic/pilot/shot.png",
                "audioSrc": "anime-animatic/pilot/dialogue.wav",
            }],
            "audioCues": [{"storage_key": "anime-animatic/pilot/music.wav"}],
        },
        public,
    )

    assert missing == ("anime-animatic/pilot/music.wav",)


def test_inventory_ignores_placeholders_and_rejects_public_escape(tmp_path):
    public = tmp_path / "public"
    public.mkdir()
    assert RemotionMediaInventory.validate(
        {"clips": [{"imageSrc": "placeholder://shot/visual", "audioSrc": ""}]},
        public,
    ) == ()

    with pytest.raises(ValueError, match="escapes public directory"):
        RemotionMediaInventory.validate(
            {"clips": [{"imageSrc": "../secret.png", "audioSrc": ""}]},
            public,
        )
