import gradio as gr
import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings
from scripts.run_factory import build_orchestrator
from core.domain.entities.pipeline_run import PipelineRun
from infrastructure.repositories.sqlite_video_repository import SQLiteVideoRepository
import uuid

async def generate_short(topic: str, language: str, music_theme: str, privacy: str):
    if not topic.strip():
        yield "Lütfen bir konu giriniz.", None, None
        return

    yield f"'{topic}' konulu video için yapay zeka senaryo yazımına başlıyor...", None, None

    settings = get_settings()
    # Force some settings for UI
    settings.youtube_upload_enabled = True
    settings.youtube_upload_privacy = privacy
    settings.vision_enabled = True
    settings.vision_provider = "openai" # Or nvidia, just to pass config test

    # Avoid crashing on missing API keys during UI initialization testing
    if not settings.pexels_api_key: settings.pexels_api_key = "mock"
    if not settings.elevenlabs_api_key: settings.elevenlabs_api_key = "mock"
    if not settings.nvidia_api_key: settings.nvidia_api_key = "mock"
    if not settings.openai_api_key: settings.openai_api_key = "mock"
    if not settings.anthropic_api_key: settings.anthropic_api_key = "mock"
    if not settings.youtube_data_api_key: settings.youtube_data_api_key = "mock"


    # Init repository
    run_id = str(uuid.uuid4())
    os.makedirs(settings.storage_root_dir, exist_ok=True)
    repo = SQLiteVideoRepository(str(Path(settings.storage_root_dir) / "runs.db"))

    # We will use the SQLite repository via RunExecutor in orchestrator
    # However, `build_orchestrator` expects `RunRepositoryPort` which `LocalJsonRunRepository` implements.
    # To keep it simple and safe for UI without full run injection, we can use the default CLI flow's repo.
    from infrastructure.repositories.local_json_run_repository import LocalJsonRunRepository
    os.makedirs(".selma_runs", exist_ok=True)
    json_repo = LocalJsonRunRepository(".selma_runs")
    pipeline_run = PipelineRun(run_id=run_id)
    await json_repo.save(pipeline_run)

    output_dir = Path(settings.storage_root_dir) / run_id

    orchestrator = build_orchestrator(
        json_repo,
        output_dir,
        target_duration_ms=25000,
        enable_topic_pipeline=True,
        content_language=language,
    )

    # Yielding progress updates
    yield "Senaryo, Fact-Check ve Voiceover aşamaları işleniyor... (Bu adım 1-2 dakika sürebilir)", None, None

    try:
        # Run the full topic factory
        result = await orchestrator.run_topic_factory(
            run_id,
            topic,
            target_duration_seconds=25,
            language=language,
            use_background_music=bool(music_theme.strip()),
            music_theme=music_theme if music_theme.strip() else None,
            music_track=None
        )

        final_video_path = result.get("final_output_path") or result.get("output_path")
        youtube_url = None
        if "youtube_upload" in result and "url" in result["youtube_upload"]:
            youtube_url = result["youtube_upload"]["url"]

        success_msg = "Video başarıyla tamamlandı! "
        if youtube_url:
            success_msg += f"YouTube'a yüklendi: {youtube_url}"

        yield success_msg, final_video_path, youtube_url
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        yield f"Hata Oluştu:\n{e}\n\n{err}", None, None



# UI Layout
with gr.Blocks(title="SELMA Labs - Shorts Fabrikası") as demo:
    gr.Markdown("# 🎬 SELMA Labs - Otonom Shorts Fabrikası")
    gr.Markdown("Bu kontrol paneli üzerinden belirlediğiniz konuda otomatik YouTube Shorts videoları üretebilir, yapay zeka ile senaryo/ses/görüntü eşleşmesini takip edebilir ve tek tıkla YouTube kanalınıza yükleyebilirsiniz.")

    with gr.Row():
        with gr.Column(scale=1):
            topic_input = gr.Textbox(label="Videonun Konusu (Prompt)", placeholder="Örn: Dünya'nın çekirdeği neden tersine dönüyor?", lines=3)
            language_input = gr.Dropdown(choices=["tr", "en", "es", "de"], value="tr", label="Seslendirme Dili")
            theme_input = gr.Dropdown(choices=["mysterious, dark ambient", "upbeat, tech, sci-fi", "cinematic, epic", ""], value="mysterious, dark ambient", label="Müzik Teması")
            privacy_input = gr.Dropdown(choices=["private", "unlisted", "public"], value="unlisted", label="YouTube Yükleme Gizliliği")

            generate_btn = gr.Button("🚀 Videoyu Üret ve Yayınla", variant="primary")
            status_output = gr.Textbox(label="Canlı Durum", interactive=False, lines=5)

        with gr.Column(scale=1):
            video_output = gr.Video(label="Render Edilen Video")
            youtube_link = gr.Textbox(label="YouTube Linki", interactive=False)

    generate_btn.click(
        fn=generate_short,
        inputs=[topic_input, language_input, theme_input, privacy_input],
        outputs=[status_output, video_output, youtube_link]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, theme=gr.themes.Base())
