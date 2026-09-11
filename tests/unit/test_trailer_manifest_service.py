from __future__ import annotations

import asyncio
import wave

from core.application.services.trailer_animatic_service import TrailerAnimaticService
from core.application.services.trailer_director_service import TrailerDirectorService
from core.application.services.trailer_gate_service import TrailerGateService
from core.application.services.trailer_manifest_service import TrailerManifestService
from core.domain.value_objects.trailer_brief import TrailerBrief
from core.domain.value_objects.trailer_plan import TrailerPlan
from infrastructure.storage.local_fs_storage import LocalFsStorage
from core.application.services.episode_director_service import EpisodeDirectorService


def _plan() -> TrailerPlan:
    episode = EpisodeDirectorService().plan_text(
        "SCENE: Rooftop\nAKIRA: We move now.\n\nSCENE: Station\nMNEMOS: The signal is close."
    )
    return TrailerDirectorService().plan(episode, TrailerBrief(trailer_id="manifest-test"))


def _wav_bytes(samples: int = 2400, sample_rate: int = 48000) -> bytes:
    import io

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\0\0" * samples)
    return buffer.getvalue()


def test_frozen_manifest_rejects_nested_asset_mutation():
    plan = _plan()
    base = TrailerManifestService().build(plan)
    evidence = {
        asset["shot_id"]: {
            "start_keyframe": "start.png",
            "background_clean": "background.png",
            "character_reference": "character.png",
            "approval_receipts": ["receipt.json"],
            "prompt_hash": "p" * 64,
            "workflow_hash": "w" * 64,
            "audio_hash": "a" * 64,
        }
        for asset in base.assets
    }
    manifest = TrailerManifestService.resolve(base, evidence, strict=True, freeze=True)
    manifest.assets[0]["prompt_hash"] = "x" * 64

    assert not manifest.has_integrity()
    assert TrailerGateService.wan_test_status(
        plan, animatic_mode="STRICT", manifest=manifest
    ) == "BLOCKED_MANIFEST_HASHES"


def test_trailer_audio_hash_is_calculated_from_storage_bytes_and_overflow_blocks(tmp_path):
    storage = LocalFsStorage(str(tmp_path))
    plan = _plan()
    mnemos = next(shot for shot in plan.shots if shot.system_voice)
    audio_key = "audio/mnemos.wav"
    audio_bytes = _wav_bytes(samples=mnemos.duration_frames * 3000)
    asyncio.run(storage.save(audio_key, audio_bytes, "audio/wav"))
    assets = {
        mnemos.shot_id: {
            "audio_storage_key": audio_key,
            "audio_hash": "",
        }
    }

    normalized, diagnostics = asyncio.run(
        TrailerAnimaticService(storage).prepare_audio_assets(
            plan, assets, shot_ids=[mnemos.shot_id]
        )
    )

    assert normalized[mnemos.shot_id]["audio_hash"]
    assert normalized[mnemos.shot_id]["audio_hash"] != "0" * 64
    assert diagnostics[0]["status"] == "BLOCKED"
    assert diagnostics[0]["timing"]["overflow_frames"] > 0
