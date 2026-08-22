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

async def generate_short(topic: str, language: str, music_theme: str, privacy: str, generation_engine: str):
    if not topic.strip():
        yield "Lütfen bir konu giriniz.", None, None
        return

    yield f"'{topic}' konulu video için yapay zeka senaryo yazımına başlıyor...", None, None

    settings = get_settings()
    # Force some settings for UI
    settings.youtube_upload_enabled = True
    settings.youtube_upload_privacy = privacy
    # Map UI engine to backend providers
    if generation_engine == "Kişisel Havuzdan Seç (Sadece Benim Yüklediklerim)":
        settings.video_provider = "user_uploads"
        settings.video_generation_provider = "none"
    elif generation_engine == "Pexels (Stok Video)":
        settings.video_provider = "pexels"
        settings.video_generation_provider = "none"
    elif generation_engine == "ComfyUI (T2V - Üret)":
        settings.video_provider = "pexels" # fallback search
        settings.video_generation_provider = "comfyui"
    elif generation_engine == "ComfyUI (V2V - Videomu Dönüştür)":
        settings.video_provider = "user_uploads" # Use local
        settings.video_generation_provider = "comfyui"
        settings.comfyui_mode = "v2v"

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

    from infrastructure.repositories.local_json_run_repository import LocalJsonRunRepository
    os.makedirs(".selma_runs", exist_ok=True)
    repo = LocalJsonRunRepository(".selma_runs")
    pipeline_run = PipelineRun(run_id=run_id)
    await repo.save(pipeline_run)

    output_dir = Path(settings.storage_root_dir) / run_id

    orchestrator = build_orchestrator(
        repo,
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
with gr.Blocks(title="SELMA Labs - Yönetmen Stüdyosu") as demo:
    gr.Markdown("# 🎬 SELMA Labs - Yönetmen Stüdyosu (V2)")
    gr.Markdown("Kendi medyanızı yükleyin, yapay zekayı yönlendirin ve benzersiz kalitede YouTube Shorts'lar yaratın.")

    with gr.Tabs():
        # Sekme 1: Yönetmen Masası (Üretim)
        with gr.Tab("🎬 Yönetmen Masası"):
            with gr.Row():
                with gr.Column(scale=1):
                    topic_input = gr.Textbox(label="Video Konusu / Fikriniz", placeholder="Örn: Evrenin en karanlık sırrı nedir?", lines=3)
                    language_input = gr.Dropdown(choices=["en", "tr", "es", "de", "fr"], value="tr", label="Yayın Dili")
                    theme_input = gr.Dropdown(choices=["mystery", "epic", "sci-fi", "documentary", "chill"], value="mystery", label="Müzik / Atmosfer")
                    privacy_input = gr.Radio(choices=["public", "unlisted", "private"], value="unlisted", label="YouTube Gizlilik")

                    gr.Markdown("### Yapay Zeka Video Motoru")
                    generation_engine = gr.Radio(
                        choices=["Kişisel Havuzdan Seç (Sadece Benim Yüklediklerim)", "Pexels (Stok Video)", "ComfyUI (T2V - Üret)", "ComfyUI (V2V - Videomu Dönüştür)"],
                        value="Pexels (Stok Video)",
                        label="Görsel Kaynağı Seçimi"
                    )

                    generate_btn = gr.Button("🚀 Yapay Zeka ile Videoyu Üret ve Yayınla", variant="primary", size="lg")

                with gr.Column(scale=1):
                    status_output = gr.Textbox(label="Durum Konsolu", lines=6, interactive=False)
                    video_output = gr.Video(label="Üretilen Video Sonucu")
                    youtube_link = gr.Textbox(label="YouTube Linki", interactive=False)

        # Sekme 2: Medya Havuzu (Kullanıcı Yüklemeleri)
        with gr.Tab("📁 Medya Havuzu (Kişisel)"):
            gr.Markdown("### Kendi Videolarınızı ve Seslerinizi Buraya Yükleyin")
            gr.Markdown("Bu alana yüklediğiniz medya dosyaları, yapay zeka tarafından (eğer 'Kişisel Havuzdan Seç' ayarı açıksa) doğrudan kullanılır veya V2V (Video-to-Video) işleminde baz alınır.")

            with gr.Row():
                with gr.Column():
                    user_videos = gr.File(label="Ham Videoları Yükle (.mp4, .mov)", file_count="multiple", file_types=["video"])
                    video_gallery = gr.Gallery(label="Yüklenen Videolar (Önizleme)", columns=3)

                with gr.Column():
                    user_audio = gr.File(label="Ses / Müzik Dosyaları Yükle (.mp3, .wav)", file_count="multiple", file_types=["audio"])
                    audio_gallery = gr.Dataframe(headers=["Dosya Adı", "Boyut"], label="Yüklenen Sesler")

        # Sekme 3: Yapay Zeka Ayarları (LLM & ComfyUI)
        with gr.Tab("⚙️ Yapay Zeka Ayarları"):
            gr.Markdown("### Mevcut Yapay Zeka Entegrasyonları")
            with gr.Row():
                with gr.Column():
                    script_llm = gr.Dropdown(choices=["selmagpt", "ollama", "nvidia", "claude"], value="selmagpt", label="Senaryo Yazarı (LLM)")
                    llm_endpoint = gr.Textbox(label="Local LLM API URL (Ollama/SelmaGPT)", value="http://localhost:11434/api/generate")
                with gr.Column():
                    comfy_endpoint = gr.Textbox(label="ComfyUI API URL", value="http://127.0.0.1:8188")
                    comfy_workflow = gr.Dropdown(choices=["Text-to-Video (T2V)", "Video-to-Video (V2V)", "Image-to-Video (I2V)"], value="Text-to-Video (T2V)", label="Aktif ComfyUI Workflow")

            save_settings_btn = gr.Button("Ayarları Kaydet ve Uygula")

        # Dummy functions for the new UI logic (to be connected to backend later)
    def update_video_gallery(files):
        if not files: return []
        import shutil
        upload_dir = "output/user_uploads/videos"
        os.makedirs(upload_dir, exist_ok=True)
        paths = []
        for f in files:
            file_path = f.name if hasattr(f, 'name') else f
            dest = os.path.join(upload_dir, os.path.basename(file_path))
            shutil.copy(file_path, dest)
            paths.append(dest)
        return paths

    def update_audio_gallery(files):
        if not files: return []
        import shutil
        upload_dir = "output/user_uploads/audio"
        os.makedirs(upload_dir, exist_ok=True)
        res = []
        for f in files:
            file_path = f.name if hasattr(f, 'name') else f
            dest = os.path.join(upload_dir, os.path.basename(file_path))
            shutil.copy(file_path, dest)
            res.append([os.path.basename(file_path), f"{os.path.getsize(dest)/1024:.1f} KB"])
        return res

    user_videos.change(fn=update_video_gallery, inputs=user_videos, outputs=video_gallery)
    user_audio.change(fn=update_audio_gallery, inputs=user_audio, outputs=audio_gallery)

    generate_btn.click(
        fn=generate_short,
        inputs=[topic_input, language_input, theme_input, privacy_input, generation_engine],
        outputs=[status_output, video_output, youtube_link]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, theme=gr.themes.Base())
