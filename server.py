import asyncio
import os
import re
import time
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.requests import Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config.container import create_container
from config.settings import get_settings
from core.domain.entities.character_state import CharacterState
from core.domain.entities.pipeline_run import PipelineRun
from core.domain.entities.shot_contract import ShotContract
from core.domain.value_objects.shot_constraints import (
    ActionConstraints,
    CameraConstraints,
    VisualConstraints,
)
from infrastructure.repositories.local_json_character_bible_repository import (
    LocalJsonCharacterBibleRepository,
)
from infrastructure.repositories.local_json_run_repository import LocalJsonRunRepository
from infrastructure.storage.local_fs_storage import LocalFsStorage
from scripts.run_factory import build_orchestrator

PROJECT_ROOT = Path(__file__).resolve().parent
app = FastAPI(title="SELMA Labs - Luma Edition")

# Serve only application-owned static assets. Generated output is deliberately
# not mounted as a directory because it can also contain manifests and uploads.
os.makedirs(PROJECT_ROOT / "output", exist_ok=True)
os.makedirs(PROJECT_ROOT / "web" / "static", exist_ok=True)
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "web" / "static"), name="static")

templates = Jinja2Templates(directory=PROJECT_ROOT / "web" / "templates")
# In-memory status tracker for the UI to poll
JOB_STATUS = {}
VIDEO_ARTIFACTS: dict[str, Path] = {}


def resolve_server_host() -> str:
    """Use loopback unless network exposure was explicitly acknowledged."""
    host = os.getenv("SELMA_SERVER_HOST", "127.0.0.1").strip() or "127.0.0.1"
    network_allowed = os.getenv("SELMA_ALLOW_NETWORK", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if host not in {"127.0.0.1", "localhost", "::1"} and not network_allowed:
        raise RuntimeError(
            "Network binding requires SELMA_ALLOW_NETWORK=true. "
            "SELMA Labs has no built-in authentication boundary."
        )
    return host


def parse_user_prompt(prompt: str) -> tuple[str, int, str]:
    """Extracts topic, duration (in ms), and language from a free-text prompt."""
    cleaned = " ".join((prompt or "").split()).strip()

    # 1. Extract Duration (Defaults to 20 seconds / 20000 ms)
    duration_s = 20
    duration_match = re.search(r'(\d+)\s*(saniye|sn|second|sec)', cleaned, re.IGNORECASE)
    if duration_match:
        duration_s = int(duration_match.group(1))

    # 2. Extract Language (Defaults to tr)
    language = "tr"
    if re.search(r'\b(english|ingilizce)\b', cleaned, re.IGNORECASE):
        language = "en"
    elif re.search(r'\b(german|almanca)\b', cleaned, re.IGNORECASE):
        language = "de"
    elif re.search(r'\b(spanish|ispanyolca)\b', cleaned, re.IGNORECASE):
        language = "es"

    # 3. Clean up the topic (if they used 'hakkında', extract that, otherwise pass the whole instruction)
    topic = cleaned
    match = re.search(r"(?:bana\s+)?(.+?)\s+hakkında\b", cleaned, re.IGNORECASE)
    if match:
        topic = match.group(1).strip(" .,:;!?\"")

    return topic, duration_s * 1000, language


@app.get("/api/characters")
async def list_characters():
    """List Character Bibles available to the web generator."""
    settings = get_settings()
    root = Path(settings.character_bible_repository_dir)
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    repository = LocalJsonCharacterBibleRepository(root)
    characters = []
    for path in sorted(root.glob("*.json")):
        try:
            bible = await repository.load(path.stem)
        except Exception:
            continue
        characters.append(
            {
                "id": bible.character_id,
                "reference_count": len(bible.reference_pack),
                "views": sorted(view.value for view in bible.reference_pack),
                "lora_enabled": bool(settings.comfyui_character_lora_name),
            }
        )
    return JSONResponse({"characters": characters})


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )

async def _generate_character_keyframe(
    *,
    job_id: str,
    character_id: str,
    prompt: str,
    style: str,
    seed: int | None = None,
) -> str:
    """Create a new image from the selected Character Bible references."""
    settings = get_settings().model_copy(
        update={"keyframe_generation_provider": "comfyui"}
    )
    bible_repository = LocalJsonCharacterBibleRepository(
        settings.character_bible_repository_dir
    )
    bible = await bible_repository.load(character_id)
    outfit_id = bible.outfit_catalog[0].id if bible.outfit_catalog else "default"
    shot = ShotContract(
        id=f"web-{job_id}",
        camera_constraints=CameraConstraints(
            angle="three-quarter view", lens="50mm portrait lens", movement="static"
        ),
        action_constraints=ActionConstraints(
            primary_action=prompt.strip() or "standing naturally"
        ),
        visual_constraints=VisualConstraints(
            lighting="cinematic soft lighting",
            environment_style=style,
            weather="clear",
        ),
        required_character_states=[
            CharacterState(
                character_id=character_id,
                active_outfit_id=outfit_id,
                injuries=[],
                held_objects=[],
            )
        ],
    )
    container = create_container(settings=settings)
    storyboard = await container.keyframe_generation_service.generate(
        shot_contract=shot, width=1024, height=1024, seed=seed
    )
    frame = storyboard.frames[-1]
    keyframe_storage = LocalFsStorage(settings.keyframe_storage_root_dir)
    image_bytes = await keyframe_storage.load(frame.storage_key)
    output_path = PROJECT_ROOT / "output" / "user_uploads" / "generated_keyframes" / f"{job_id}.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(output_path.write_bytes, image_bytes)
    return str(output_path)


async def run_pipeline(
    job_id: str,
    prompt: str,
    duration: int,
    image_path: str | None = None,
    script_provider: str | None = None,
    voice_provider: str | None = None,
    voice_file_path: str | None = None,
    style: str = "cinematic",
    subtitle_style: str = "hormozi",
    storyboard: bool = False,
    character_id: str | None = None,
    character_seed: int | None = None,
):
    try:
        JOB_STATUS[job_id] = {"status": "generating", "message": "Senaryo ve görsel planlama başlatılıyor...", "video_url": None, "timestamp": time.time()}
        request_settings = get_settings().model_copy()

        topic, duration_ms, lang = parse_user_prompt(prompt)
        duration_ms = duration * 1000 # Override with explicit UI duration if available

        if character_id and not image_path:
            JOB_STATUS[job_id]["message"] = (
                "Karakter referanslarından yeni başlangıç karesi üretiliyor..."
            )
            image_path = await _generate_character_keyframe(
                job_id=job_id,
                character_id=character_id,
                prompt=prompt,
                style=style,
                seed=character_seed,
            )

        if script_provider:
            request_settings.script_provider = script_provider
            # If swarm is chosen, it's only a script provider. Default others to ollama
            fallback_provider = "ollama" if script_provider == "swarm" else script_provider
            request_settings.scene_planning_provider = fallback_provider
            request_settings.fact_check_provider = fallback_provider
            request_settings.translation_provider = fallback_provider

        if voice_provider:
            request_settings.voice_provider = voice_provider
            if voice_file_path and voice_provider == "local_xtts":
                # Assuming setting property or handle logic here
                pass

        style_map = {
            "cinematic": "assets/comfyui_workflow.json",
            "anime": "assets/comfyui_anime_workflow.json",
            "3d": "assets/comfyui_3d_workflow.json",
            "cyberpunk": "assets/comfyui_cyberpunk_workflow.json"
        }
        if style in style_map:
            request_settings.comfyui_workflow_path = style_map[style]

        request_settings.subtitle_style = subtitle_style
        if storyboard:
            # Bypass slow components for fast drafting
            request_settings.video_generation_provider = "none" # or set to a placeholder static image provider
            request_settings.mastering_enabled = False # skip re-encoding / heavy color grading
            JOB_STATUS[job_id]["message"] = "Storyboard mod aktif: Hızlı taslak oluşturuluyor (Video motoru atlanıyor)..."




        # Luma tarzı I2V/T2V konfigürasyonu
        if not storyboard:
            request_settings.video_generation_provider = "comfyui"
        request_settings.video_provider = "hybrid"

        if image_path:
            request_settings.comfyui_mode = "i2v"
            request_settings.i2v_image_path = image_path
        else:
            request_settings.comfyui_mode = "t2v"

        request_settings.youtube_upload_enabled = False # Demo UI'da hızlı test için kapalı tutuyoruz, istenirse açılabilir
        request_settings.apply_cinematic_mastering = True

        run_id = job_id
        os.makedirs(PROJECT_ROOT / ".selma_runs", exist_ok=True)
        repo = LocalJsonRunRepository(PROJECT_ROOT / ".selma_runs")
        pipeline_run = PipelineRun(run_id=run_id)
        await repo.save(pipeline_run)

        output_dir = PROJECT_ROOT / request_settings.storage_root_dir / run_id

        orchestrator = build_orchestrator(
            repo,
            output_dir,
            target_duration_ms=duration_ms,
            enable_topic_pipeline=True,
            content_language=lang,
            settings=request_settings,
        )

        JOB_STATUS[job_id]["message"] = "Yapay Zeka filmi renderlıyor... Lütfen bekleyin."
        await orchestrator.run_topic_factory(
            run_id=run_id,
            topic=topic,
            language=lang,
        )

        # Pipeline is done. Let's find the generated MP4
        # Orchestrator saves to output_dir
        expected_mp4 = None
        if output_dir.exists():
            for artifact in output_dir.iterdir():
                if artifact.is_file() and artifact.suffix.lower() == ".mp4":
                    VIDEO_ARTIFACTS[job_id] = artifact.resolve()
                    expected_mp4 = f"/api/artifacts/{job_id}/video"
                    break

        JOB_STATUS[job_id] = {
            "status": "completed",
            "message": "Film hazır!",
            "video_url": expected_mp4 or "/static/dummy.mp4",
            "timestamp": time.time(),
            "target_duration_ms": duration_ms
        }

    except Exception as e:
        JOB_STATUS[job_id] = {"status": "error", "message": str(e), "video_url": None, "timestamp": time.time()}

@app.post("/api/vision/analyze")
async def analyze_vision(
    image: UploadFile = File(...),
    context: str = Form("")
):
    """
    Endpoint for the UI to request a quick Vision AI analysis of an uploaded image.
    Used to pre-analyze context before full video generation.
    """
    if not image.filename:
        return JSONResponse(status_code=400, content={"error": "No image provided."})

    try:
        from config.provider_registry import get_vision_asset_scoring_service
        settings = get_settings().model_copy()

        # Ensure vision is enabled for this endpoint
        settings.vision_enabled = True

        scoring_service = get_vision_asset_scoring_service(settings)
        vision_provider = scoring_service._vision_provider

        image_bytes = await image.read()

        result = await vision_provider.analyze(
            frame_bytes=[image_bytes],
            scene_context=context or "General analysis"
        )

        return JSONResponse(content={
            "status": "success",
            "provider": vision_provider.provider_identity,
            "analysis": result.to_dict()
        })

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})



@app.get("/api/autopilot/status")
async def autopilot_status():
    return JSONResponse({"status": "inactive"})

@app.post("/api/autopilot/toggle")
async def autopilot_toggle():
    return JSONResponse({"status": "inactive"})


@app.get("/gallery", response_class=HTMLResponse)
async def gallery(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="gallery.html",
    )

@app.get("/api/gallery")
async def api_gallery():
    try:
        repo = LocalJsonRunRepository(PROJECT_ROOT / ".selma_runs")
        runs = await repo.get_all()
        return JSONResponse({
            "runs": [run.to_dict() for run in runs]
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/workspace/{job_id}", response_class=HTMLResponse)
async def workspace(request: Request, job_id: str):
    return templates.TemplateResponse(
        request=request,
        name="workspace.html",
        context={"job_id": job_id},
    )


@app.post("/api/publish/{job_id}")
async def api_publish(job_id: str, platform: str = Form(...)):
    try:
        from infrastructure.repositories.local_json_run_repository import LocalJsonRunRepository
        repo = LocalJsonRunRepository(PROJECT_ROOT / ".selma_runs")
        run = await repo.get_by_id(job_id)

        if not run.has_completed_stage("mastering") and not run.has_completed_stage("render"):
            raise ValueError("Run has not completed render or mastering.")

        # Determine actual video path from artifacts
        video_path_str = None
        if run.has_completed_stage("mastering"):
            video_path_str = run.get_stage_artifact("mastering").get("file_path")
        elif run.has_completed_stage("render"):
            video_path_str = run.get_stage_artifact("render").get("file_path")

        if not video_path_str:
             raise ValueError("Could not find video file path in artifacts.")

        video_path = PROJECT_ROOT / video_path_str
        if not video_path.exists():
             raise FileNotFoundError(f"Video missing at {video_path}")

        from infrastructure.providers.publish.omnichannel_upload_provider import OmnichannelUploadProvider
        uploader = OmnichannelUploadProvider()

        result_id = await uploader.upload_video(
            platform=platform,
            video_path=str(video_path),
            title=f"Selma AI Gen Video - {job_id[:8]}",
            description="Auto-generated by SELMA Dream Machine",
            tags=["AI", "Shorts", "Generated"]
        )

        return JSONResponse({"status": "success", "platform": platform, "platform_id": result_id})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/generate")
async def generate(
    background_tasks: BackgroundTasks,
    prompt: str = Form(...),
    duration: int = Form(20),
    style: str = Form("cinematic"),
    subtitle_style: str = Form("hormozi"),
    storyboard: bool = Form(False),
    character_id: str | None = Form(None),
    character_seed: int | None = Form(None),
    image: UploadFile | None = File(None),
    script_provider: str | None = Form(None),
    voice_provider: str | None = Form(None),
    voice_file: UploadFile | None = File(None),
):
    job_id = str(uuid.uuid4())
    image_path = None
    voice_file_path = None

    upload_dir_base = PROJECT_ROOT / "output" / "user_uploads"

    if image and image.filename:
        upload_dir_img = upload_dir_base / "images"
        os.makedirs(upload_dir_img, exist_ok=True)
        safe_filename = "".join(c for c in image.filename if c.isalnum() or c in "._-")
        if not safe_filename:
            safe_filename = "upload.jpg"
        image_path = str(upload_dir_img / f"{job_id}_{safe_filename}")
        with open(image_path, "wb") as buffer:
            import shutil
            shutil.copyfileobj(image.file, buffer)

    if voice_file and voice_file.filename:
        upload_dir_voice = upload_dir_base / "voices"
        os.makedirs(upload_dir_voice, exist_ok=True)
        safe_voice_name = "".join(c for c in voice_file.filename if c.isalnum() or c in "._-")
        if not safe_voice_name:
            safe_voice_name = "voice.wav"
        voice_file_path = str(upload_dir_voice / f"{job_id}_{safe_voice_name}")
        with open(voice_file_path, "wb") as buffer:
            import shutil
            shutil.copyfileobj(voice_file.file, buffer)

    # Arka planda Luma (ComfyUI) motorunu tetikle
    JOB_STATUS[job_id] = {"status": "starting", "message": "Görev sıraya alındı...", "video_url": None, "timestamp": time.time()}
    background_tasks.add_task(
        run_pipeline,
        job_id,
        prompt,
        duration,
        image_path,
        script_provider,
        voice_provider,
        voice_file_path,
        style,
        subtitle_style,
        storyboard,
        character_id,
        character_seed,
    )

    return JSONResponse({"job_id": job_id})


@app.get("/api/system-metrics")
async def system_metrics():
    try:
        from core.application.services.system_monitor import get_system_stats
        return JSONResponse(get_system_stats())
    except Exception as e:
        return JSONResponse({"cpu": "--", "ram": "--", "disk": "--", "gpu": "N/A"})

@app.get("/api/stats")
async def stats():
    try:
        # Just mock stats for now to prevent 404s
        return JSONResponse({
            "total_videos": 0,
            "avg_view_rate": "0%",
            "best_format": "N/A"
        })
    except Exception as e:
        return JSONResponse({"total_videos": 0, "avg_view_rate": "0%", "best_format": "N/A"})

@app.get("/api/status/{job_id}")

async def get_status(job_id: str):
    current_time = time.time()
    # Bellek sızıntısını önlemek için 10 dakikadan eski tamamlanmış veya hatalı işleri temizle
    stale_jobs = [
        jid for jid, info in JOB_STATUS.items()
        if info.get("status") in ("completed", "error") and current_time - info.get("timestamp", current_time) > 600
    ]
    for jid in stale_jobs:
        del JOB_STATUS[jid]
        VIDEO_ARTIFACTS.pop(jid, None)

    return JSONResponse(JOB_STATUS.get(job_id, {"status": "not_found", "message": "Bulunamadı"}))


@app.get("/api/artifacts/{job_id}/video", response_class=FileResponse)
async def get_video_artifact(job_id: str):
    """Serve only the MP4 registered for a completed generation job."""
    try:
        normalized_job_id = str(uuid.UUID(job_id))
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Video bulunamadı.") from error

    status = JOB_STATUS.get(normalized_job_id, {})
    artifact = VIDEO_ARTIFACTS.get(normalized_job_id)
    if status.get("status") != "completed" or artifact is None:
        raise HTTPException(status_code=404, detail="Video bulunamadı.")
    if artifact.suffix.lower() != ".mp4" or not artifact.is_file():
        raise HTTPException(status_code=404, detail="Video bulunamadı.")
    return FileResponse(artifact, media_type="video/mp4", filename=artifact.name)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=resolve_server_host(), port=7860)
