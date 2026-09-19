from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cli.main import main
from core.application.services.episode_asset_generation_service import (
    EpisodeAssetGenerationService,
)
from core.application.services.episode_director_service import EpisodeDirectorService
from core.application.services.location_bible_factory_service import LocationBibleFactoryService
from core.domain.value_objects.background_production import (
    BackgroundCandidatePack,
)
from core.domain.value_objects.character_pose_pack import (
    CharacterPosePackManifest,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage


class _PoseFactory:
    async def generate_pack(self, *args, **kwargs):
        del args, kwargs
        raise RuntimeError("ComfyUI unavailable")


class _BackgroundFactory:
    async def generate(self, location):
        del location
        raise RuntimeError("background provider unavailable")


def _location():
    return LocationBibleFactoryService().create(
        {
            "location_id": "rooftop",
            "name": "Rooftop",
            "description": "A rooftop above the city",
            "immutable_geometry": ["water tank"],
            "architecture": ["concrete ledge"],
            "palette": ["blue"],
            "lighting_sources": ["neon"],
            "weather_options": ["rain"],
            "style": "anime background",
        }
    )


def _plan():
    return EpisodeDirectorService().plan_text(
        "SCENE: Rooftop\nAKIRA: We move now.",
        episode_id="asset-bridge",
        locations=(_location(),),
    )


def test_generation_bridge_reports_failed_pose_and_background_jobs(tmp_path):
    service = EpisodeAssetGenerationService(
        _PoseFactory(),
        _BackgroundFactory(),
        LocalFsStorage(str(tmp_path / "storage")),
    )
    result = asyncio.run(
        service.generate(
            _plan(),
            output_root=tmp_path / "episode-assets",
            locations=(_location(),),
            pose_jobs=[{"character_id": "akira"}],
        )
    )

    assert result.to_dict()["status"] == "FAILED"
    assert "pose-pack-akira" in result.failures
    assert "background-pack-rooftop" in result.failures
    assert not result.pose_packs
    assert not result.background_packs


def test_generation_bridge_persists_factory_manifests_and_is_explicitly_provisional(tmp_path):
    storage = LocalFsStorage(str(tmp_path / "storage"))
    manifest = _manifest("akira")
    await_batch = AsyncMock(
        return_value={
            "characters": [
                {
                    "character_id": "akira",
                    "status": manifest.status,
                    "manifest_storage_key": manifest.manifest_storage_key,
                }
            ]
        }
    )
    class BackgroundFactory:
        async def generate(self, location, *, evaluate=True):
            assert location.location_id == "rooftop"
            assert evaluate is False
            return _background_pack(location.location_id)

    asyncio.run(storage.save(
        manifest.manifest_storage_key,
        (json.dumps(manifest.to_dict()) + "\n").encode("utf-8"),
        "application/json",
    ))
    service = EpisodeAssetGenerationService(
        object(),
        BackgroundFactory(),
        storage,
    )
    with patch(
        "core.application.services.episode_asset_generation_service.CharacterPosePackBatchService"
    ) as batch_cls:
        batch_cls.return_value.run = await_batch
        result = asyncio.run(
            service.generate(
                _plan(),
                output_root=tmp_path / "episode-assets",
                locations=(_location(),),
                pose_jobs=[{"character_id": "akira"}],
            )
        )

    assert result.to_dict()["status"] == "COMPLETED"
    assert (tmp_path / "episode-assets/pose-packs/akira.json").is_file()
    assert result.pose_packs["akira"].status == "PENDING_HUMAN_REVIEW"


def _manifest(character_id: str) -> CharacterPosePackManifest:
    digest = "a" * 64
    from core.domain.value_objects.character_pose_pack import (
        POSE_PACK_POSE_IDS,
        CharacterPoseEvidence,
    )

    poses = tuple(
        CharacterPoseEvidence(
            pose_id=pose_id,
            storage_key=f"characters/{character_id}/{pose_id}.png",
            content_hash=digest,
            pose_template_storage_key=f"templates/{pose_id}.png",
            pose_template_hash=digest,
            seed=index,
            width=768,
            height=1152,
            reference_storage_keys=("refs/anchor.png",),
            reference_hashes=(digest,),
            style_reference_hash=digest,
            prompt_hash=digest,
            workflow_hash=digest,
            model_hashes={"checkpoint": digest},
            qc_report={"passed": True},
        )
        for index, pose_id in enumerate(POSE_PACK_POSE_IDS)
    )
    return CharacterPosePackManifest(
        schema_version=1,
        character_id=character_id,
        character_version=1,
        brief_hash=digest,
        style_id="style",
        style_reference_storage_key="styles/style.png",
        style_reference_hash=digest,
        poses=poses,
        status="PENDING_HUMAN_REVIEW",
        contact_sheet_storage_key="characters/contact.png",
        contact_sheet_content_hash=digest,
        manifest_storage_key=f"characters/{character_id}/manifest.json",
        human_approved=True,
    )


def test_episode_prepare_dispatches_assets_only_when_requested(tmp_path, capsys):
    script = tmp_path / "episode.txt"
    output = tmp_path / "prepare.json"
    script.write_text("SCENE: Rooftop\nAKIRA: We move now.", encoding="utf-8")
    generation = SimpleNamespace(
        pose_packs={},
        background_packs={},
        failures={"background-pack-rooftop": "provider unavailable"},
        to_dict=lambda: {
            "status": "FAILED",
            "failures": {"background-pack-rooftop": "provider unavailable"},
            "artifacts": [],
        },
    )
    service = SimpleNamespace(
        generate=AsyncMock(return_value=generation),
    )
    container = SimpleNamespace(episode_asset_generation_service=service)
    assert main(
        [
            "episode", "prepare", "--input", str(script), "--output", str(output),
            "--generate-assets", "--asset-mode", "PRODUCTION",
        ],
        container_factory=lambda: container,
    ) == 0
    capsys.readouterr()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["asset_generation"]["status"] == "FAILED"
    assert payload["preparation_status"] == "BLOCKED"
    service.generate.assert_awaited_once()


def _background_pack(location_id: str) -> BackgroundCandidatePack:
    from core.domain.value_objects.background_production import BackgroundCandidate

    return BackgroundCandidatePack(
        location_id=location_id,
        candidates=(
            BackgroundCandidate(
                recipe_id="wide-01",
                storage_key=f"backgrounds/{location_id}/wide.png",
                width=1344,
                height=768,
                attempt=1,
            ),
        ),
    )
