"""Render and score a local, licensed visual-edit studio reference."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.application.services.visual_edit_planning_service import (  # noqa: E402
    VisualEditPlanningService,
)
from core.application.services.visual_quality_gate_service import (  # noqa: E402
    VisualQualityGateService,
)
from core.domain.entities.media_asset import MediaAsset  # noqa: E402
from core.domain.value_objects.asset_diversity import AssetUsage  # noqa: E402
from core.domain.value_objects.visual_intent import VisualIntent  # noqa: E402
from infrastructure.providers.render.ffmpeg_media_quality_analysis_provider import (  # noqa: E402
    FfmpegMediaQualityAnalysisProvider,
)
from infrastructure.providers.render.ffmpeg_render_provider import (  # noqa: E402
    FfmpegRenderProvider,
)

RUN_ID = "552fecff-e2e1-40f9-9781-8790fa996f47"


async def main() -> None:
    output_dir = PROJECT_ROOT / "output"
    run_path = PROJECT_ROOT / ".selma_runs" / f"{RUN_ID}.json"
    source_master = output_dir / f"{RUN_ID}.mp4"
    subtitle_path = output_dir / f"{RUN_ID}.ass"
    reference_path = output_dir / "visual_edit_reference.mp4"
    report_path = output_dir / "visual_edit_reference_report.json"

    run = json.loads(run_path.read_text(encoding="utf-8"))
    artifacts = run["artifact_manifest"]
    intent_data = artifacts.get("VISUAL_LOCALIZATION_V2", {}).get(
        "visual_intents"
    ) or artifacts["SCENE_PLANNING"]["visual_intents"]
    intents = [VisualIntent(**item) for item in intent_data]
    adjusted, plan = VisualEditPlanningService().plan(intents)

    video_artifact = artifacts["VISION_SEARCH"]
    clips = [str(path) for path in video_artifact["video_clips"]]
    assets = [MediaAsset(**item) for item in video_artifact["selected_assets"]]
    usages = [
        AssetUsage.from_dict(item) for item in video_artifact["asset_usages"]
    ]

    renderer = FfmpegRenderProvider()
    await renderer.render_shorts(
        str(source_master),
        str(subtitle_path),
        clips,
        str(reference_path),
        audio_start_ms=0,
        audio_end_ms=plan.duration_ms,
        clip_durations_seconds=[beat.duration_ms / 1_000 for beat in plan.beats],
        motion_types=[beat.motion_type for beat in plan.beats],
        shot_types=[beat.shot_type for beat in plan.beats],
        visual_jobs=[intent.visual_job for intent in adjusted],
        procedural_audio_accents=False,
    )

    signals = await FfmpegMediaQualityAnalysisProvider().analyze(
        str(reference_path)
    )
    quality = VisualQualityGateService().evaluate(
        plan=plan,
        visual_intents=adjusted,
        source_assets=assets,
        asset_usages=usages,
        quality_signals=signals,
    )
    report = {
        "reference_video": str(reference_path),
        "source_run_id": RUN_ID,
        "free_stack": ["FFmpeg", "Remotion", "Pexels License"],
        "visual_edit_plan": plan.to_dict(),
        "rendered_signals": signals.to_dict(),
        "visual_quality": quality.to_dict(),
    }
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({
        "reference_video": str(reference_path),
        "report": str(report_path),
        "automatic_score": quality.automatic_score,
        "passed": quality.passed,
        "detected_scene_changes": len(signals.scene_change_timestamps_seconds),
        "maximum_visual_stasis_seconds": signals.maximum_visual_stasis_seconds,
    }, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
