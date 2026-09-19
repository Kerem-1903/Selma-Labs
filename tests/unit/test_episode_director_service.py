from __future__ import annotations

import json

import pytest

from cli.main import main
from core.application.services.episode_director_service import EpisodeDirectorService
from core.application.services.episode_preparation_service import EpisodePreparationService
from core.domain.exceptions import PreProductionValidationError
from core.application.services.asset_approval_service import AssetApprovalService
from core.domain.value_objects.character_pose_pack import (
    POSE_PACK_POSE_IDS,
    CharacterPoseEvidence,
    CharacterPosePackManifest,
)
from core.domain.value_objects.episode_director_plan import DirectorShot


def _location(location_id: str = "rain-rooftop"):
    from core.application.services.location_bible_factory_service import LocationBibleFactoryService

    return LocationBibleFactoryService().create({
        "location_id": location_id,
        "name": "Rain Rooftop" if location_id == "rain-rooftop" else "Empty Station",
        "description": "A rooftop above a neon city" if location_id == "rain-rooftop" else "An abandoned platform",
        "immutable_geometry": ["water tank"] if location_id == "rain-rooftop" else ["clock tower"],
        "architecture": ["concrete ledge"] if location_id == "rain-rooftop" else ["steel canopy"],
        "palette": ["blue", "amber"] if location_id == "rain-rooftop" else ["blue", "grey"],
        "lighting_sources": ["neon signs"] if location_id == "rain-rooftop" else ["platform lamps"],
        "weather_options": ["rain"] if location_id == "rain-rooftop" else ["clear"],
        "style": "painted anime background",
    })


def _pose_pack() -> CharacterPosePackManifest:
    digest = "a" * 64
    poses = tuple(CharacterPoseEvidence(
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
    ) for index, pose_id in enumerate(POSE_PACK_POSE_IDS))
    manifest = CharacterPosePackManifest(
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
    receipt = AssetApprovalService.receipt(
        asset_id=manifest.character_id,
        asset_hash=AssetApprovalService.asset_set_digest(
            [pose.content_hash for pose in manifest.poses]
        ),
        manifest_payload=manifest.to_dict(),
        approved_by="art-director",
    )
    from dataclasses import replace
    return replace(
        manifest,
        human_approved=True,
        approval_receipt=receipt.to_dict(),
    )


def _background_pack(location_id="rain-rooftop", recipes=("wide-01",)):
    from core.domain.value_objects.background_production import BackgroundCandidate, BackgroundCandidatePack

    pack = BackgroundCandidatePack(
        location_id=location_id,
        candidates=tuple(BackgroundCandidate(
            recipe_id=recipe,
            storage_key=f"backgrounds/{location_id}/source/{recipe}.png",
            width=1344,
            height=768,
            attempt=1,
            content_hash="b" * 64,
        ) for recipe in recipes),
    )
    receipt = AssetApprovalService.receipt(
        asset_id=pack.location_id,
        asset_hash=AssetApprovalService.asset_set_digest(
            [candidate.content_hash for candidate in pack.candidates]
        ),
        manifest_payload=pack.to_dict(),
        approved_by="art-director",
    )
    from dataclasses import replace
    return replace(pack, human_approved=True, approval_receipt=receipt.to_dict())


def test_director_shot_preserves_one_frame_boundary_without_ms_duration_rounding_error():
    shot = DirectorShot(
        shot_id="pilot-shot-001",
        scene_id="pilot-scene-001",
        purpose="hold a precise frame",
        story_beat="setup",
        source_script_lines=("hold",),
        dialogue="",
        duration_seconds=1 / 24,
        character_id="akira",
        character_pose_id="FRONT_NEUTRAL",
        pose_reason="readable silhouette",
        character_action="holds",
        expression="neutral",
        shot_size="wide",
        camera_angle="front",
        camera_movement="locked_hold",
        background_recipe_id="rooftop-wide",
        background_prompt="empty rooftop",
        foreground_effects=(),
        transition_in="cut",
        transition_out="cut",
        start_ms=1 * 1000 // 24,
        end_ms=2 * 1000 // 24,
        reasoning="frame boundary test",
        start_frame=1,
        duration_frames=1,
    )
    assert shot.end_frame == 2


def test_director_builds_contiguous_24fps_plan_with_pose_and_background_decisions():
    plan = EpisodeDirectorService().plan_text(
        "SCENE: Rain Rooftop\nAKIRA: Stay behind me.\nThe signal flickers in the rain.\n\nSCENE: Abandoned Station\nAKIRA: The truth is here.",
        episode_id="pilot", title="The Signal",
    )
    assert plan.fps == 24
    assert [shot.shot_id for scene in plan.scenes for shot in scene.shots] == [
        "pilot-shot-001", "pilot-shot-002", "pilot-shot-003", "pilot-shot-004"
    ]
    character_clips = [clip for clip in plan.timeline if clip.track == "CHARACTER"]
    assert [clip.start_frame for clip in character_clips] == [0, 48, 96, 144]
    assert character_clips[-1].start_frame + character_clips[-1].duration_frames == plan.duration_frames


def test_director_uses_location_recipe_but_keeps_background_provisional_without_asset():
    plan = EpisodeDirectorService().plan_text(
        "SCENE: Rain Rooftop\nAKIRA: watches the signal.", episode_id="location-test", locations=(_location(),)
    )
    requirement = plan.background_requirements[0]
    assert requirement.status == "PLANNED"
    assert requirement.asset_ref == ""
    assert plan.scenes[0].shots[0].background_recipe_id.startswith("rain-rooftop-")
    assert next(item for item in plan.timeline if item.track == "BACKGROUND").asset_type == "background_recipe"
    with pytest.raises(PreProductionValidationError):
        EpisodeDirectorService().plan_text("", episode_id="empty")


def test_location_ids_transliterate_accented_names_instead_of_deleting_them():
    """Non-ASCII letters must be folded, never dropped.

    Deleting them turned "SAINT ORA KLINIGI - NOROLOJI IZOLASYON ODASI" into
    "saint-ora-kl-n-n-roloj-zolasyon-odasi": the location name is lost, and any
    two locations that differ only by their accents collapse onto one storage id.
    """
    safe_id = EpisodeDirectorService._safe_id

    assert safe_id("SAINT ORA KLİNİĞİ - NÖROLOJİ İZOLASYON ODASI", "location") == (
        "saint-ora-klinigi-noroloji-izolasyon-odasi"
    )
    assert safe_id("KIRMIZI HAT - ÇATI SERVİS ROTASI", "location") == (
        "kirmizi-hat-cati-servis-rotasi"
    )
    assert safe_id("MNEMOS KULESİ - SAHA LABORATUVARI", "location") == (
        "mnemos-kulesi-saha-laboratuvari"
    )
    # Accents change the spelling; they must never fold two names onto one id.
    assert safe_id("ESKİ PAZAR GEÇİDİ", "location") == "eski-pazar-gecidi"
    assert safe_id("GÖZ", "location") == "goz"
    assert safe_id("IŞIK", "location") == "isik"
    assert safe_id("IJSSELMEER", "location") == "ijsselmeer"


def test_unapproved_assets_remain_provisional_even_when_complete():
    pose = _pose_pack()
    from dataclasses import replace
    from core.domain.value_objects.background_production import BackgroundCandidatePack

    unapproved_background = replace(
        _background_pack(recipes=("wide-01",)),
        human_approved=False,
        approval_receipt=None,
    )
    plan = EpisodeDirectorService().plan_text(
        "SCENE: Rain Rooftop\nAKIRA: watches the signal.",
        episode_id="approval-gate",
        locations=(_location(),),
        pose_packs={"akira": replace(pose, human_approved=False, approval_receipt=None)},
        background_packs={"rain-rooftop": unapproved_background},
    )
    assert plan.character_requirements[0].status == "PLANNED"
    assert plan.scenes[0].shots[0].character_pose_asset_ref == ""
    assert plan.background_requirements[0].status == "PLANNED"
    assert plan.scenes[0].shots[0].background_asset_ref == ""


def test_director_resolves_five_pose_assets_and_generated_background_asset():
    plan = EpisodeDirectorService().plan_text(
        "SCENE: Rain Rooftop\nAKIRA: watches the signal.", episode_id="asset-test",
        locations=(_location(),), pose_packs={"akira": _pose_pack()},
        background_packs={"rain-rooftop": _background_pack(recipes=("wide-01", "close-09"))},
    )
    character = plan.character_requirements[0]
    shot = plan.scenes[0].shots[0]
    assert character.status == "READY"
    assert set(character.pose_asset_refs) == set(POSE_PACK_POSE_IDS)
    assert shot.character_pose_asset_ref == character.pose_asset_refs[shot.character_pose_id]
    assert plan.background_requirements[0].status == "READY"
    assert next(item for item in plan.timeline if item.track == "BACKGROUND").asset_type == "background_asset"


def test_director_marks_unmatched_background_recipe_as_provisional():
    plan = EpisodeDirectorService().plan_text(
        "SCENE: Empty Station\nAKIRA waits.", episode_id="missing-asset",
        locations=(_location("empty-station"),),
        background_packs={"empty-station": _background_pack("empty-station", ("medium-99",))},
    )
    assert plan.background_requirements[0].status == "PLANNED"
    assert plan.background_requirements[0].asset_ref == ""


def test_preparation_creates_resumable_jobs_for_missing_assets():
    plan = EpisodeDirectorService().plan_text("SCENE: Rain Rooftop\nAKIRA: We move now.", episode_id="prepare-test", locations=(_location(),))
    result = EpisodePreparationService().prepare(plan)
    assert result.status == "PLANNED"
    assert [job.kind for job in result.jobs] == ["POSE_PACK", "BACKGROUND_PACK"]
    assert all(job.status == "PLANNED" for job in result.jobs)
    assert all(job.shot_ids for job in result.jobs)


def test_preparation_marks_resolved_pose_and_background_jobs_ready():
    plan = EpisodeDirectorService().plan_text(
        "SCENE: Rain Rooftop\nAKIRA: watches the signal.", episode_id="ready-test",
        locations=(_location(),), pose_packs={"akira": _pose_pack()},
        background_packs={"rain-rooftop": _background_pack(recipes=("wide-01", "close-09"))},
    )
    result = EpisodePreparationService().prepare(plan)
    assert result.status == "READY"
    assert all(job.status == "READY" for job in result.jobs)


def test_preparation_resume_preserves_failed_job_until_explicit_retry():
    plan = EpisodeDirectorService().plan_text("SCENE: Rooftop\nAKIRA: We wait.", episode_id="resume-test")
    service = EpisodePreparationService()
    failed_payload = service.prepare(plan).to_dict()
    failed_payload["jobs"][0].update(status="FAILED", attempts=1, last_error="provider unavailable")
    previous = type(service.prepare(plan)).from_dict(failed_payload)
    resumed = service.prepare(plan, previous=previous)
    retried = service.prepare(plan, previous=previous, retry_job_ids=("pose-pack-akira",))
    assert resumed.jobs[0].status == "FAILED"
    assert retried.jobs[0].status == "PLANNED"
    assert retried.jobs[0].attempts == 2


def test_episode_cli_without_output_prints_json_and_does_not_construct_container(tmp_path, capsys):
    script = tmp_path / "episode.txt"
    script.write_text("SCENE: Rooftop\nAKIRA: We move now.", encoding="utf-8")
    def forbidden_container():
        raise AssertionError("episode planning must not construct production wiring")
    assert main(["episode", "plan", "--input", str(script)], container_factory=forbidden_container) == 0
    assert json.loads(capsys.readouterr().out)["episode_director_plan"]["fps"] == 24


def test_episode_prepare_cli_writes_plan_and_jobs(tmp_path):
    script = tmp_path / "episode.txt"
    output = tmp_path / "prepare.json"
    script.write_text("SCENE: Rooftop\nAKIRA: We move now.", encoding="utf-8")
    assert main(["episode", "prepare", "--input", str(script), "--output", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["preparation_status"] == "PLANNED"
    assert payload["summary"]["job_count"] == 2


def test_episode_prepare_cli_resume_and_retry_job(tmp_path):
    script = tmp_path / "episode.txt"
    first_output = tmp_path / "first.json"
    retry_output = tmp_path / "retry.json"
    script.write_text("SCENE: Rooftop\nAKIRA: We wait.", encoding="utf-8")
    assert main(["episode", "prepare", "--input", str(script), "--output", str(first_output)]) == 0
    payload = json.loads(first_output.read_text(encoding="utf-8"))
    payload["jobs"][0].update(status="FAILED", attempts=1, last_error="provider unavailable")
    first_output.write_text(json.dumps(payload), encoding="utf-8")
    assert main(["episode", "prepare", "--input", str(script), "--output", str(retry_output), "--resume", str(first_output), "--retry-job", "pose-pack-akira"]) == 0
    retry = json.loads(retry_output.read_text(encoding="utf-8"))
    pose_job = next(job for job in retry["jobs"] if job["job_id"] == "pose-pack-akira")
    assert pose_job["attempts"] == 2
    assert pose_job["status"] == "PLANNED"


def test_episode_cli_writes_plan_and_inspect_summary(tmp_path, capsys):
    script = tmp_path / "episode.txt"
    output = tmp_path / "episode-plan.json"
    script.write_text("SCENE: Rooftop\nAKIRA: We move now.", encoding="utf-8")
    assert main(["episode", "plan", "--input", str(script), "--output", str(output), "--episode-id", "cli-pilot", "--title", "CLI Pilot"]) == 0
    capsys.readouterr()
    assert main(["episode", "inspect", "--input", str(output)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["episode_id"] == "cli-pilot"
    assert summary["shot_count"] == 2
    assert summary["duration_frames"] > 0


def test_episode_prepare_does_not_construct_container(tmp_path):
    script = tmp_path / "episode.txt"
    output = tmp_path / "prepare.json"
    script.write_text("SCENE: Rooftop\nAKIRA: We wait.", encoding="utf-8")
    def forbidden_container():
        raise AssertionError("episode preparation must not construct production wiring")
    assert main(["episode", "prepare", "--input", str(script), "--output", str(output)], container_factory=forbidden_container) == 0
