from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.application.services.candidate.candidate_evaluation_service import (
    CandidateEvaluationService,
)
from core.domain.entities.character_state import CharacterState
from core.domain.entities.shot_animation import ShotPlan
from core.domain.value_objects.render_config import RenderConfig
from infrastructure.providers.motion.comfyui_motion_adapter import (
    ComfyUIMotionAdapter,
)
from infrastructure.repositories.candidate.sqlite_keyframe_candidate_repository import (
    SqliteKeyframeCandidateRepository,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render one explicitly approved Akira keyframe through two ComfyUI passes."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(
            "assets/characters/akira/references/front/"
            "0001-720eaab8-d8ee-4ef5-bd5e-a0e9a6e3a563.png"
        ),
    )
    parser.add_argument("--output-root", type=Path, default=Path("output/two_pass_smoke"))
    parser.add_argument("--workflow", type=Path, default=Path("assets/comfyui_i2v_workflow.json"))
    parser.add_argument("--server", default="http://127.0.0.1:8188")
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--fps", type=int, default=6)
    parser.add_argument("--seed", type=int, default=1903)
    parser.add_argument("--width", type=int, default=384)
    parser.add_argument("--height", type=int, default=896)
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument(
        "--confirm-human-approved",
        action="store_true",
        help="Required acknowledgement that the supplied source was human-approved.",
    )
    return parser.parse_args()


def _probe_video(path: Path, ffprobe: str) -> dict[str, object]:
    executable = shutil.which(ffprobe) or (ffprobe if Path(ffprobe).is_file() else None)
    if executable is None:
        raise FileNotFoundError(f"FFprobe executable was not found: {ffprobe}")
    completed = subprocess.run(
        (
            executable,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_name,width,height,avg_frame_rate",
            "-of",
            "json",
            str(path),
        ),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    payload = json.loads(completed.stdout)
    duration = float(payload.get("format", {}).get("duration", 0.0))
    streams = payload.get("streams", [])
    video = next(
        (item for item in streams if item.get("width") and item.get("height")),
        None,
    )
    if video is None or duration <= 0:
        raise RuntimeError("FFprobe did not find a valid video stream and duration.")
    return {
        "duration_seconds": duration,
        "codec": str(video.get("codec_name", "")),
        "width": int(video["width"]),
        "height": int(video["height"]),
        "average_frame_rate": str(video.get("avg_frame_rate", "")),
    }


async def run(args: argparse.Namespace) -> Path:
    if not args.confirm_human_approved:
        raise PermissionError(
            "Refusing to create a committed candidate without --confirm-human-approved."
        )
    if not args.source.is_file():
        raise FileNotFoundError(f"Approved source image was not found: {args.source}")
    if not args.workflow.is_file():
        raise FileNotFoundError(f"Two-pass workflow was not found: {args.workflow}")
    if not 0.25 <= args.duration <= 30.0:
        raise ValueError("Duration must be between 0.25 and 30 seconds.")
    frame_count = round(args.duration * args.fps)
    if not 1 <= frame_count <= 64:
        raise ValueError(
            "The bundled ComfyUI workflow supports between 1 and 64 frames; "
            f"received {frame_count}. Lower duration or FPS."
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shot_id = f"akira-smoke-{timestamp}"
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    storage = LocalFsStorage(str(output_root))
    source_key = f"approved/{shot_id}{args.source.suffix.casefold()}"
    source_bytes = args.source.read_bytes()
    await storage.save(source_key, source_bytes, "image/png")

    candidates = CandidateEvaluationService(
        SqliteKeyframeCandidateRepository(str(output_root / "candidates.sqlite"))
    )
    candidate = await candidates.register_candidate(
        shot_contract_id=shot_id,
        storage_key=source_key,
        generation_metadata={
            "source": args.source.as_posix(),
            "content_hash": hashlib.sha256(source_bytes).hexdigest(),
            "human_approval_acknowledged": True,
        },
    )
    await candidates.approve_candidate(candidate.id)
    await candidates.mark_candidate_committed(candidate.id)

    plan = ShotPlan(
        id=shot_id,
        script_id="akira-real-smoke",
        scene_plan_id="akira-real-smoke-scene-001",
        prompt=(
            "akira_girl, cinematic cyberpunk anime, amber eyes, black hair with one "
            "deep-red front streak, subtle breathing, natural blinking, restrained "
            "hair and jacket movement, stable face, one katana only"
        ),
        negative_prompt=(
            "identity drift, different face, extra person, extra limbs, extra sword, "
            "flicker, jitter, text, watermark"
        ),
        duration_seconds=args.duration,
        character_state=CharacterState("akira", "akira-default", [], []),
        requires_lipsync=False,
    ).approve_keyframe(source_key)
    render_config = RenderConfig(
        width=args.width,
        height=args.height,
        fps=args.fps,
        seed=args.seed,
        sampler_name="euler",
        pass1_denoise=0.12,
        pass2_denoise=0.06,
        sampling_steps=16,
        guidance_scale=4.5,
    )
    adapter = ComfyUIMotionAdapter(
        args.server,
        workflow_path=args.workflow,
        storage=storage,
        render_config=render_config,
        candidate_evaluation_service=candidates,
        cache_prefix="motion/two-pass-smoke",
        timeout_seconds=1800,
    )

    progress = 0.0

    def report_progress(value: float) -> None:
        nonlocal progress
        bounded = max(progress, min(1.0, value))
        if bounded - progress >= 0.05 or (bounded == 1.0 and progress < 1.0):
            print(f"ComfyUI progress: {bounded:.0%}", flush=True)
        progress = bounded

    started = time.monotonic()
    clip = await adapter.generate_motion_clip(plan, report_progress)
    elapsed = time.monotonic() - started
    video_bytes = await storage.load(clip.video_path)
    physical_path = output_root / Path(clip.video_path)
    probe = _probe_video(physical_path, args.ffprobe)
    if abs(float(probe["duration_seconds"]) - args.duration) > max(
        0.5, 1.0 / args.fps
    ):
        raise RuntimeError(
            "Rendered duration differs from the requested duration: "
            f"{probe['duration_seconds']} vs {args.duration}."
        )

    report = {
        "shot_id": shot_id,
        "candidate_id": candidate.id,
        "candidate_status": "COMMITTED",
        "source_key": source_key,
        "output_key": clip.video_path,
        "output_path": str(physical_path),
        "content_hash": hashlib.sha256(video_bytes).hexdigest(),
        "bytes": len(video_bytes),
        "seed": clip.seed,
        "cached": clip.cached,
        "elapsed_seconds": round(elapsed, 3),
        "requested_duration_seconds": args.duration,
        "requested_fps": args.fps,
        "two_pass_denoise": [0.12, 0.06],
        "provider_prompt_ids": list(clip.pass_prompt_ids),
        "probe": probe,
    }
    report_path = output_root / f"{shot_id}-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report_path


if __name__ == "__main__":
    try:
        asyncio.run(run(_arguments()))
    except Exception as error:
        print(f"Two-pass motion smoke test failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
