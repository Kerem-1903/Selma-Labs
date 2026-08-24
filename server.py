import asyncio
import os
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

app = FastAPI(title="SELMA Labs - Luma Edition")

# Serve static files (CSS, JS, Images, Videos)
os.makedirs("output", exist_ok=True)
os.makedirs("web/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="web/static"), name="static")
app.mount("/output", StaticFiles(directory="output"), name="output")

templates = Jinja2Templates(directory="web/templates")

# In-memory status tracker for the UI to poll
JOB_STATUS = {}

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

async def run_pipeline(job_id: str, prompt: str, image_path: Optional[str] = None, llm_provider: str = "nvidia"):
    try:
        from core.application.services.prompt_enhancer_service import prompt_enhancer_service
        settings = get_settings()

        # Determine endpoint based on provider selection
        llm_endpoint = "http://localhost:11434/api/generate" if llm_provider == "ollama" else settings.selmagpt_api_url if llm_provider == "selmagpt" else None
        model_name = "llama3" if llm_provider == "ollama" else "SelmaGPT-v1"

        JOB_STATUS[job_id] = {"status": "enhancing", "message": "Prompt Enhancer: Senaryo sinematik dile çevriliyor...", "video_url": None, "enhanced_prompt": None}

        # 1. Enhance Prompt dynamically
        enhanced_prompt = prompt
        if llm_endpoint:
            try:
                enhanced_prompt = await prompt_enhancer_service.enhance(prompt, llm_endpoint, model_name)
                JOB_STATUS[job_id]["enhanced_prompt"] = enhanced_prompt
            except Exception as e:
                JOB_STATUS[job_id]["message"] = f"Prompt geliştirilemedi, orijinal metin kullanılıyor: {e}"
        else:
            # If using API providers like NVIDIA or Claude, we skip local enhance for now or implement their specific clients
            JOB_STATUS[job_id]["enhanced_prompt"] = f"(Using default script pipeline for {llm_provider}): {prompt}"

        JOB_STATUS[job_id]["message"] = "Gelişmiş senaryo hazırlandı. Planlama başlatılıyor..."

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
        os.makedirs(".selma_runs", exist_ok=True)
        repo = LocalJsonRunRepository(".selma_runs")
        pipeline_run = PipelineRun(run_id=run_id)
        await repo.save(pipeline_run)

        output_dir = Path(settings.storage_root_dir) / run_id

        orchestrator = build_orchestrator(
            repo,
            output_dir,
            target_duration_ms=10000, # Luma tarzı kısa 10s klipler
            enable_topic_pipeline=True,
            content_language="tr",
        )

        JOB_STATUS[job_id]["message"] = "Yapay Zeka (Orchestrator) aktif. Video renderlanıyor... Lütfen bekleyin."
        await orchestrator.run_topic_factory(run_id=run_id, topic=enhanced_prompt)

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
    llm_provider: str = Form("nvidia"),
    image: Optional[UploadFile] = File(None)
):
    job_id = str(uuid.uuid4())
    image_path = None

    settings = get_settings()
    settings.script_provider = llm_provider
    if llm_provider == "selmagpt":
        # Override to ensure it hits the local model on alternate port if needed
        # Fallback to .env defaults if set, otherwise assume 8001
        settings.selmagpt_api_url = os.getenv("SELMAGPT_API_URL", "http://127.0.0.1:8001/v1/chat/completions")

    if image and image.filename:
        import werkzeug.utils
        upload_dir = "output/user_uploads/images"
        os.makedirs(upload_dir, exist_ok=True)
        # Safely extract the filename
        safe_filename = werkzeug.utils.secure_filename(image.filename)
        if not safe_filename:
            safe_filename = "upload.jpg"
        image_path = os.path.join(upload_dir, f"{job_id}_{safe_filename}")
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)

    # Arka planda Luma (ComfyUI) motorunu tetikle
    JOB_STATUS[job_id] = {"status": "starting", "message": "Görev sıraya alındı...", "video_url": None, "enhanced_prompt": None}
    background_tasks.add_task(run_pipeline, job_id, prompt, image_path, llm_provider)

    return JSONResponse({"job_id": job_id})

@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    return JSONResponse(JOB_STATUS.get(job_id, {"status": "not_found", "message": "Bulunamadı"}))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
