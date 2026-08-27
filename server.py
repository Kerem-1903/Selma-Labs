import asyncio
import os
import re
import uuid
import shutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

from config.settings import get_settings
from scripts.run_factory import build_orchestrator
from core.domain.entities.pipeline_run import PipelineRun
from infrastructure.repositories.local_json_run_repository import LocalJsonRunRepository

PROJECT_ROOT = Path(__file__).resolve().parent
app = FastAPI(title="SELMA Labs - Luma Edition")

# Serve static files (CSS, JS, Images, Videos)
os.makedirs(PROJECT_ROOT / "output", exist_ok=True)
os.makedirs(PROJECT_ROOT / "web" / "static", exist_ok=True)
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "web" / "static"), name="static")
app.mount("/output", StaticFiles(directory=PROJECT_ROOT / "output"), name="output")

templates = Jinja2Templates(directory=PROJECT_ROOT / "web" / "templates")

import time
# In-memory status tracker for the UI to poll
JOB_STATUS = {}


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


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )

async def run_pipeline(job_id: str, prompt: str, duration: int, image_path: Optional[str] = None, script_provider: Optional[str] = None, voice_provider: Optional[str] = None, voice_file_path: Optional[str] = None):
    try:
        JOB_STATUS[job_id] = {"status": "generating", "message": "Senaryo ve görsel planlama başlatılıyor...", "video_url": None, "timestamp": time.time()}
        request_settings = get_settings().model_copy()

        topic, duration_ms, lang = parse_user_prompt(prompt)
        duration_ms = duration * 1000 # Override with explicit UI duration if available

        if script_provider:
            request_settings.script_provider = script_provider
            request_settings.scene_planning_provider = script_provider
            request_settings.fact_check_provider = script_provider
            request_settings.translation_provider = script_provider

        if voice_provider:
            request_settings.voice_provider = voice_provider
            if voice_file_path and voice_provider == "local_xtts":
                # Assuming setting property or handle logic here
                pass


        # Luma tarzı I2V/T2V konfigürasyonu
        request_settings.video_generation_provider = "comfyui"
        request_settings.video_provider = "pexels"

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
            for f in os.listdir(output_dir):
                if f.endswith(".mp4"):
                    expected_mp4 = f"/output/{run_id}/{f}"
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


@app.get("/workspace/{job_id}", response_class=HTMLResponse)
async def workspace(request: Request, job_id: str):
    return templates.TemplateResponse(
        request=request,
        name="workspace.html",
        context={"job_id": job_id},
    )

@app.post("/api/generate")
async def generate(
    background_tasks: BackgroundTasks,
    prompt: str = Form(...),
    duration: int = Form(20),
    image: Optional[UploadFile] = File(None),
    script_provider: Optional[str] = Form(None),
    voice_provider: Optional[str] = Form(None),
    voice_file: Optional[UploadFile] = File(None)
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
    background_tasks.add_task(run_pipeline, job_id, prompt, duration, image_path, script_provider, voice_provider, voice_file_path)

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

    return JSONResponse(JOB_STATUS.get(job_id, {"status": "not_found", "message": "Bulunamadı"}))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
