from __future__ import annotations

import json

import pytest

from cli.main import main
from core.application.services.episode_director_service import EpisodeDirectorService
from core.domain.exceptions import PreProductionValidationError
from core.domain.value_objects.character_pose_pack import (
    POSE_PACK_POSE_IDS,
    CharacterPoseEvidence,
    CharacterPosePackManifest,
)


def _location(location_id: str = "rain-rooftop"):
    from core.application.services.location_bible_factory_service import LocationBibleFactoryService

    return LocationBibleFactoryService().create(
        {
            "location_id": location_id,
            "name": "Rain Rooftop" if location_id == "rain-rooftop" else "Empty Station",
            "description": "A rooftop above a neon city" if location_id == "rain-rooftop" else "An abandoned platform",
            "immutable_geometry": ["water tank"] if location_id == "rain-rooftop" else ["clock tower"],
            "architecture": ["concrete ledge"] if location_id == "rain-rooftop" else ["steel canopy"],
            "palette": ["blue", "amber"] if location_id == "rain-rooftop" else ["blue", "grey"],
            "lighting_sources": ["neon signs"] if location_id == "rain-rooftop" else ["platform lamps"],
            "weather_options": ["rain"] if location_id == "rain-rooftop" else ["clear"],
            "style": "painted anime background",
        }
    )


def _pose_pack() -> CharacterPosePackManifest:
    digest = "a" * 64
    poses = tuple(
        CharacterPoseEvidence(
            pose_id=pose_id,
            storage_key=f"characters/akira/v1/pose-pack/poses/{pose_id.casefold()}.png",
            content_hash=digest,
            pose_template_storage_key=f"characters/_pose_templates/{pose_id.casefold()}.png",
            pose_template_hash=digest,
            seed=index,
            width=768,
            height=1152,
            reference_storage_keys=("references/akira.png",),
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
        character_id="akira",
        character_version=1,
        brief_hash=digest,
        style_id="selma-style",
        style_reference_storage_key="series-style/selma-style/reference.png",
        style_reference_hash=digest,
        poses=poses,
        status="PENDING_HUMAN_REVIEW",
        contact_sheet_storage_key="characters/akira/v1/pose-pack/contact-sheet.png",
        contact_sheet_content_hash=digest,
        manifest_storage_key="characters/akira/v1/pose-pack/manifest.json",
    )


def test_director_builds_contiguous_24fps_plan_with_pose_and_background_decisions():
    plan = EpisodeDirectorService().plan_text(
        """
        SCENE: Rain Rooftop
        AKIRA: Stay behind me.
        The signal flickers in the rain.

        SCENE: Abandoned Station
        AKIRA: The truth is here.
        """,
        episode_id="pilot",
        title="The Signal",
    )

    assert plan.fps == 24
    assert plan.duration_frames == round(plan.total_duration_seconds * 24)
    assert plan.decision_mode == "RULE_FALLBACK"
    assert len(plan.scenes) == 2
    assert all(scene.shots for scene in plan.scenes)
    assert [shot.shot_id for scene in plan.scenes for shot in scene.shots] == [
        "pilot-shot-001",
        "pilot-shot-002",
        "pilot-shot-003",
        "pilot-shot-004",
    ]
    assert all(
        shot.character_pose_id
        in {
            "FRONT_NEUTRAL",
            "THREE_QUARTER_LEFT",
            "PROFILE_LEFT",
            "THREE_QUARTER_RIGHT",
            "BACK_FULL_BODY",
        }
        for scene in plan.scenes
        for shot in scene.shots
    )
    character_clips = [clip for clip in plan.timeline if clip.track == "CHARACTER"]
    assert [clip.start_frame for clip in character_clips] == [0, 48, 96, 144]
    assert character_clips[-1].start_frame + character_clips[-1].duration_frames == plan.duration_frames
    assert all(clip.track in plan.tracks() for clip in plan.timeline)


def test_director_uses_location_recipe_but_keeps_background_provisional_without_asset():
    plan = EpisodeDirectorService().plan_text(
        "SCENE: Rain Rooftop\nAKIRA: watches the signal.",
        episode_id="location-test",
        locations=(_location(),),
    )

    requirement = plan.background_requirements[0]
    assert requirement.status == "PLANNED"
    assert requirement.asset_ref == ""
    assert requirement.location_id == "rain-rooftop"
    assert plan.scenes[0].shots[0].background_recipe_id.startswith("rain-rooftop-")
    assert next(item for item in plan.timeline if item.track == "BACKGROUND").asset_type == "background_recipe"

    with pytest.raises(PreProductionValidationError):
        EpisodeDirectorService().plan_text("", episode_id="empty")


def test_director_resolves_five_pose_assets_and_generated_background_asset():
    from core.domain.value_objects.background_production import (
        BackgroundCandidate,
        BackgroundCandidatePack,
    )

    background_pack = BackgroundCandidatePack(
        location_id="rain-rooftop",
        candidates=(
            BackgroundCandidate(
                recipe_id="wide-01",
                storage_key="backgrounds/rain-rooftop/source/wide-01.png",
                width=1344,
                height=768,
                attempt=1,
            ),
        ),
    )
    plan = EpisodeDirectorService().plan_text(
        "SCENE: Rain Rooftop\nAKIRA: watches the signal.",
        episode_id="asset-test",
        locations=(_location(),),
        pose_packs={"akira": _pose_pack()},
        background_packs={"rain-rooftop": background_pack},
    )

    character = plan.character_requirements[0]
    shot = plan.scenes[0].shots[0]
    assert character.status == "READY"
    assert set(character.pose_asset_refs) == set(POSE_PACK_POSE_IDS)
    assert character.pose_pack_manifest_ref.endswith("manifest.json")
    assert shot.character_pose_asset_ref == character.pose_asset_refs[shot.character_pose_id]
    assert plan.background_requirements[0].status == "READY"
    assert shot.background_asset_ref == plan.background_requirements[0].asset_ref
    assert next(item for item in plan.timeline if item.track == "CHARACTER").asset_type == "pose"
    assert next(item for item in plan.timeline if item.track == "CHARACTER").asset_ref == shot.character_pose_asset_ref
    assert next(item for item in plan.timeline if item.track == "BACKGROUND").asset_type == "background_asset"


def test_director_marks_unmatched_background_recipe_as_provisional():
    from core.domain.value_objects.background_production import (
        BackgroundCandidate,
        BackgroundCandidatePack,
    )

    plan = EpisodeDirectorService().plan_text(
        "SCENE: Empty Station\nAKIRA waits.",
        episode_id="missing-asset",
        locations=(_location("empty-station"),),
        background_packs={
            "empty-station": BackgroundCandidatePack(
                location_id="empty-station",
                candidates=(
                    BackgroundCandidate(
                        recipe_id="medium-99",
                        storage_key="backgrounds/empty-station/source/medium-99.png",
                        width=1344,
                        height=768,
                        attempt=1,
                    ),
                ),
            )
        },
    )

    assert plan.background_requirements[0].status == "PLANNED"
    assert plan.background_requirements[0].asset_ref == ""
    assert next(item for item in plan.timeline if item.track == "BACKGROUND").asset_type == "background_recipe"


def test_episode_cli_without_output_prints_json_and_does_not_construct_container(tmp_path, capsys):
    script = tmp_path / "episode.txt"
    script.write_text("SCENE: Rooftop\nAKIRA: We move now.", encoding="utf-8")

    def forbidden_container():
        raise AssertionError("episode planning must not construct production wiring")

    assert main(
        ["episode", "plan", "--input", str(script)],
        container_factory=forbidden_container,
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["episode_director_plan"]["fps"] == 24


def test_episode_cli_writes_plan_and_inspect_summary(tmp_path, capsys):
    script = tmp_path / "episode.txt"
    output = tmp_path / "episode-plan.json"
    script.write_text("SCENE: Rooftop\nAKIRA: We move now.", encoding="utf-8")

    assert main(
        [
            "episode",
            "plan",
            "--input",
            str(script),
            "--output",
            str(output),
            "--episode-id",
            "cli-pilot",
            "--title",
            "CLI Pilot",
        ]
    ) == 0
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["episode_director_plan"]["fps"] == 24
    capsys.readouterr()

    assert main(["episode", "inspect", "--input", str(output)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["episode_id"] == "cli-pilot"
    assert summary["scene_count"] == 1
    assert summary["shot_count"] == 2
    assert summary["duration_frames"] > 0
