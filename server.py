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

# In-memory status tracker for the UI to poll
JOB_STATUS = {}


def _extract_topic(prompt: str) -> str:
    cleaned = " ".join((prompt or "").split()).strip()
    match = re.search(r"(?:bana\s+)?(.+?)\s+hakkında\b", cleaned, re.IGNORECASE)
    if match:
        return match.group(1).strip(" .,:;!?\"")
    return cleaned


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )

async def run_pipeline(job_id: str, prompt: str, image_path: Optional[str] = None):
    try:
        JOB_STATUS[job_id] = {"status": "generating", "message": "Senaryo ve görsel planlama başlatılıyor...", "video_url": None}
        settings = get_settings()

        # Luma tarzı I2V/T2V konfigürasyonu
        settings.video_generation_provider = "comfyui"
        settings.video_provider = "pexels"

        if image_path:
            settings.comfyui_mode = "i2v"
            settings.i2v_image_path = image_path
        else:
            settings.comfyui_mode = "t2v"

        settings.youtube_upload_enabled = False # Demo UI'da hızlı test için kapalı tutuyoruz, istenirse açılabilir
        settings.apply_cinematic_mastering = True

        run_id = job_id
        os.makedirs(PROJECT_ROOT / ".selma_runs", exist_ok=True)
        repo = LocalJsonRunRepository(PROJECT_ROOT / ".selma_runs")
        pipeline_run = PipelineRun(run_id=run_id)
        await repo.save(pipeline_run)

        output_dir = PROJECT_ROOT / settings.storage_root_dir / run_id

        orchestrator = build_orchestrator(
            repo,
            output_dir,
            target_duration_ms=10000, # Luma tarzı kısa 10s klipler
            enable_topic_pipeline=True,
            content_language="tr",
        )

        JOB_STATUS[job_id]["message"] = "Yapay Zeka filmi renderlıyor... Lütfen bekleyin."
        topic = _extract_topic(prompt)
        await orchestrator.run_topic_factory(
            run_id=run_id,
            topic=topic,
            language="tr",
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
            "video_url": expected_mp4 or "/static/dummy.mp4"
        }

    except Exception as e:
        JOB_STATUS[job_id] = {"status": "error", "message": str(e), "video_url": None}

@app.post("/api/generate")
async def generate(
    background_tasks: BackgroundTasks,
    prompt: str = Form(...),
    image: Optional[UploadFile] = File(None)
):
    job_id = str(uuid.uuid4())
    image_path = None

    if image and image.filename:
        import werkzeug.utils
        upload_dir = PROJECT_ROOT / "output" / "user_uploads" / "images"
        os.makedirs(upload_dir, exist_ok=True)
        # Safely extract the filename
        safe_filename = werkzeug.utils.secure_filename(image.filename)
        if not safe_filename:
            safe_filename = "upload.jpg"
        image_path = str(upload_dir / f"{job_id}_{safe_filename}")
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)

    # Arka planda Luma (ComfyUI) motorunu tetikle
    JOB_STATUS[job_id] = {"status": "starting", "message": "Görev sıraya alındı...", "video_url": None}
    background_tasks.add_task(run_pipeline, job_id, prompt, image_path)

    return JSONResponse({"job_id": job_id})

@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    return JSONResponse(JOB_STATUS.get(job_id, {"status": "not_found", "message": "Bulunamadı"}))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
