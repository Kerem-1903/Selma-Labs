"""CLI handlers for the narrow anime pilot golden path."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.application.services.episode_animatic_service import EpisodeAnimaticService
from core.application.services.episode_director_service import EpisodeDirectorService
from core.application.services.pilot_golden_path_service import PilotGoldenPathService
from core.application.services.screenplay_normalization_service import (
    ScreenplayNormalizationService,
)
from core.domain.value_objects.episode_director_plan import (
    DirectorCharacterRequirement,
    DirectorScene,
    DirectorShot,
    EpisodeDirectorPlan,
    EpisodeTimelineClip,
    frame_to_ms,
)
from infrastructure.providers.render.remotion_animatic_exporter import (
    RemotionAnimaticExporter,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage

JsonWriter = Callable[[str | Path, dict[str, Any]], Path]
JsonLoader = Callable[[str | Path], dict[str, Any]]
AwaitableRunner = Callable[[Any], Any]


def run_pilot_command(
    arguments: argparse.Namespace,
    *,
    write_json: JsonWriter,
    awaitable_run: AwaitableRunner | None = None,
) -> int:
    """Run pilot init/check/plan/smoke without coupling to the CLI monolith."""
    service = PilotGoldenPathService()
    if arguments.pilot_command == "init":
        target = service.initialize(
            arguments.output,
            pilot_id=arguments.pilot_id,
            title=arguments.title,
        )
        print(str(target.resolve()))
        return 0

    if arguments.pilot_command == "check":
        report = service.check_file(arguments.input)
        payload = report.to_dict()
        if arguments.output:
            print(write_json(arguments.output, payload))
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if report.status == "READY" else 2

    if arguments.pilot_command == "plan":
        report = service.check_file(arguments.input)
        if report.status != "READY":
            raise ValueError(
                "Pilot screenplay is not ready: " + ", ".join(report.failures)
            )

        script = ScreenplayNormalizationService().from_fountain(
            Path(arguments.input).read_text(encoding="utf-8"),
            script_id=report.pilot_id,
            title=report.title,
        )
        plan = EpisodeDirectorService().plan_episode(script)
        payload = {
            "schema_version": 1,
            "episode_director_plan": plan.to_dict(),
        }
        print(write_json(arguments.output, payload))
        return 0

    if arguments.pilot_command == "smoke":
        return _run_pilot_smoke(
            arguments,
            write_json=write_json,
            awaitable_run=awaitable_run or asyncio.run,
        )

    raise ValueError(f"Unsupported pilot command: {arguments.pilot_command}")


def _run_pilot_smoke(
    arguments: argparse.Namespace,
    *,
    write_json: JsonWriter,
    awaitable_run: AwaitableRunner,
) -> int:
    """Render a five-second anchor smoke without claiming character approval."""
    plan = _five_second_anchor_smoke_plan(
        akira_image=arguments.akira_image,
        kaito_image=arguments.kaito_image,
    )
    storage = LocalFsStorage(arguments.storage_root)
    result = awaitable_run(
        EpisodeAnimaticService(storage).build(plan, mode="STRICT")
    )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": result.status,
        "smoke_kind": "ANCHOR_SMOKE_NOT_VIEW_PACK_APPROVED",
        "plan": plan.to_dict(),
        "animatic": result.to_dict(),
    }
    if result.status == "BLOCKED" or result.project is None:
        print(write_json(arguments.output, payload))
        return 2

    props_path = awaitable_run(
        RemotionAnimaticExporter(storage, arguments.motion_public_dir).export(
            result.project
        )
    )
    payload["remotion_props_path"] = str(props_path)
    if arguments.render:
        from core.application.services.animatic_render_service import (
            AnimaticRenderService,
        )
        from infrastructure.providers.render.ffprobe_media_inspection_provider import (
            FfprobeMediaInspectionProvider,
        )

        render_result = awaitable_run(
            AnimaticRenderService(
                motion_directory="motion",
                inspector=FfprobeMediaInspectionProvider(),
                browser_executable=arguments.browser_executable,
            ).render(
                result.project,
                props_path=props_path,
                output_path=arguments.render_output,
            )
        )
        payload["render"] = render_result.to_dict()
        if render_result.status != "READY_FOR_REVIEW":
            print(write_json(arguments.output, payload))
            return 3

    print(write_json(arguments.output, payload))
    return 0


def _five_second_anchor_smoke_plan(
    *,
    akira_image: str,
    kaito_image: str,
) -> EpisodeDirectorPlan:
    """Create two contiguous 60-frame shots from explicit canonical anchors."""
    episode_id = "kirik-kayit-anchor-smoke-5s"
    scene_id = f"{episode_id}-scene-001"
    shots = (
        _smoke_shot(
            shot_id=f"{episode_id}-shot-001",
            scene_id=scene_id,
            character_id="akira",
            image_key=akira_image,
            start_frame=0,
            purpose="Establish Akira in the approved canonical anchor.",
            story_beat="setup",
            shot_size="wide",
        ),
        _smoke_shot(
            shot_id=f"{episode_id}-shot-002",
            scene_id=scene_id,
            character_id="kaito",
            image_key=kaito_image,
            start_frame=60,
            purpose="Cut to Kaito for a direct reaction beat.",
            story_beat="reaction",
            shot_size="close_up",
        ),
    )
    scene = DirectorScene(
        scene_id=scene_id,
        title="Anchor smoke",
        location_id="smoke-studio",
        scene_purpose="Verify the five-second editorial and media path.",
        story_beat="setup",
        emotional_intent="neutral",
        time_of_day="studio",
        weather="clear",
        continuity_notes=("Anchor smoke only; not a character turnaround approval.",),
        shots=shots,
    )
    return EpisodeDirectorPlan(
        schema_version=1,
        episode_id=episode_id,
        title="Kırık Kayıt — 5s Anchor Smoke",
        decision_mode="RULE_FALLBACK",
        provider="pilot-anchor-smoke-v1",
        fps=24,
        total_duration_seconds=5.0,
        scenes=(scene,),
        character_requirements=(
            DirectorCharacterRequirement(
                character_id="akira",
                pose_ids=("FRONT_NEUTRAL",),
                status="PLANNED",
                pose_asset_refs={},
            ),
            DirectorCharacterRequirement(
                character_id="kaito",
                pose_ids=("FRONT_NEUTRAL",),
                status="PLANNED",
                pose_asset_refs={},
            ),
        ),
        background_requirements=(),
        timeline=tuple(
            EpisodeTimelineClip(
                track="CHARACTER",
                clip_id=f"{shot.shot_id}-character",
                shot_id=shot.shot_id,
                start_frame=shot.start_frame or 0,
                duration_frames=shot.duration_frames or 60,
                label=shot.character_id,
                asset_type="canonical_anchor_smoke",
                asset_ref=shot.character_pose_asset_ref,
            )
            for shot in shots
        ),
        warnings=(
            "This is an anchor smoke only; the Akira/Kaito view packs remain unapproved.",
        ),
        metadata={
            "smoke_kind": "ANCHOR_SMOKE_NOT_VIEW_PACK_APPROVED",
            "target_duration_seconds": 5.0,
            "target_fps": 24,
        },
    )


def _smoke_shot(
    *,
    shot_id: str,
    scene_id: str,
    character_id: str,
    image_key: str,
    start_frame: int,
    purpose: str,
    story_beat: str,
    shot_size: str,
) -> DirectorShot:
    duration_frames = 60
    end_frame = start_frame + duration_frames
    return DirectorShot(
        shot_id=shot_id,
        scene_id=scene_id,
        purpose=purpose,
        story_beat=story_beat,
        source_script_lines=(purpose,),
        dialogue="",
        duration_seconds=duration_frames / 24,
        character_id=character_id,
        character_pose_id="FRONT_NEUTRAL",
        pose_reason="Canonical anchor smoke frame; no pose-pack approval implied.",
        character_action="holds neutral anchor",
        expression="neutral",
        shot_size=shot_size,
        camera_angle="front",
        camera_movement="locked_hold",
        background_recipe_id="smoke-studio",
        background_prompt="neutral studio background",
        foreground_effects=(),
        transition_in="cut",
        transition_out="cut",
        start_ms=frame_to_ms(start_frame),
        end_ms=frame_to_ms(end_frame),
        reasoning=purpose,
        character_pose_asset_ref=image_key,
        start_frame=start_frame,
        duration_frames=duration_frames,
    )


__all__ = ["run_pilot_command"]
