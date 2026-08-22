from __future__ import annotations

import gradio as gr

import shutil
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings
from core.domain.entities.pipeline_run import PipelineRun
from infrastructure.repositories.local_json_run_repository import LocalJsonRunRepository
from scripts.run_factory import build_orchestrator

UPLOAD_DIR = PROJECT_ROOT / "output" / "user_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _paths(value: str | list[str] | None) -> list[Path]:
    if not value:
        return []
    values = value if isinstance(value, list) else [value]
    return [Path(item) for item in values if item]


def save_uploads(files: str | list[str] | None) -> tuple[str, str | None]:
    saved = []
    for source in _paths(files):
        if source.is_file():
            target = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{source.name}"
            shutil.copy2(source, target)
            saved.append(target.name)
    message = f"{len(saved)} dosya havuza eklendi." if saved else "Dosya seçilmedi."
    return message, str(UPLOAD_DIR / saved[0]) if saved else None


def list_uploaded_assets() -> str:
    files = sorted(path.name for path in UPLOAD_DIR.iterdir() if path.is_file())
    return "\n".join(files) if files else "Havuz boş."


async def generate_short(
    topic: str,
    language: str,
    music_theme: str,
    privacy: str,
    visual_source: str,
    video_mode: str,
    input_video: str | None,
    input_image: str | None,
):
    if not topic.strip():
        yield "Lütfen bir konu giriniz.", None, None
        return

    yield "Üretim hazırlanıyor...", None, None
    settings = get_settings()
    settings.youtube_upload_enabled = False
    settings.youtube_upload_privacy = privacy
    settings.vision_enabled = True
    settings.vision_provider = "openai"
    settings.video_provider = "user_uploads" if visual_source == "Kişisel havuz" else "pexels"
    settings.user_uploads_dir = str(UPLOAD_DIR)
    if settings.video_provider == "pexels" and not settings.pexels_api_key:
        yield "Pexels API anahtarı eksik. Kişisel havuz seçin veya .env dosyasını ayarlayın.", None, None
        return

    run_id = str(uuid.uuid4())
    repository = LocalJsonRunRepository(str(PROJECT_ROOT / ".selma_runs"))
    await repository.save(PipelineRun(run_id=run_id))
    orchestrator = build_orchestrator(
        repository,
        PROJECT_ROOT / "output" / run_id,
        target_duration_ms=25000,
        enable_topic_pipeline=True,
        content_language=language,
    )
    selected_input = input_video or input_image
    mode_suffix = f" ({video_mode}, giriş: {Path(selected_input).name})" if selected_input else f" ({video_mode})"
    yield f"Yönetmen masası çalışıyor{mode_suffix}...", None, None
    try:
        result = await orchestrator.run_topic_factory(
            run_id,
            topic,
            target_duration_seconds=25,
            language=language,
            use_background_music=bool(music_theme.strip()),
            music_theme=music_theme or None,
            music_track=None,
        )
        output_path = result.get("final_output_path") or result.get("output_path")
        yield "Video başarıyla tamamlandı.", output_path, None
    except Exception as exc:
        yield f"Üretim hatası: {exc}", None, None


with gr.Blocks(title="SELMA Director Studio") as demo:
    gr.Markdown("# SELMA Director Studio")
    gr.Markdown("Kişisel medya havuzunuzu yönetin, üretim motorunu seçin ve Shorts üretin.")
    with gr.Tabs():
        with gr.Tab("Medya Havuzu"):
            with gr.Row():
                video_files = gr.File(label="Video yükle", file_count="multiple", file_types=["video"], type="filepath")
                audio_files = gr.File(label="Ses yükle", file_count="multiple", file_types=["audio"], type="filepath")
            with gr.Row():
                video_preview = gr.Video(label="Video önizleme")
                audio_preview = gr.Audio(label="Ses önizleme", type="filepath")
            pool_status = gr.Textbox(label="Havuz durumu", interactive=False)
            pool_listing = gr.Textbox(label="Kişisel kütüphane", value=list_uploaded_assets, interactive=False, lines=5)
            video_files.change(save_uploads, inputs=video_files, outputs=[pool_status, video_preview]).then(list_uploaded_assets, outputs=pool_listing)
            audio_files.change(save_uploads, inputs=audio_files, outputs=[pool_status, audio_preview]).then(list_uploaded_assets, outputs=pool_listing)

        with gr.Tab("Yapay Zeka Ayarları"):
            visual_source = gr.Radio(["Kişisel havuz", "Pexels"], value="Kişisel havuz", label="Görsel kaynağı")
            video_mode = gr.Radio(["ComfyUI Text-to-Video", "ComfyUI Image-to-Video", "ComfyUI Video-to-Video"], value="ComfyUI Text-to-Video", label="ComfyUI modu")
            input_image = gr.Image(label="I2V giriş görseli", type="filepath")
            input_video = gr.Video(label="V2V giriş videosu")
            language_input = gr.Dropdown(["tr", "en", "es", "de"], value="tr", label="Seslendirme dili")
            theme_input = gr.Dropdown(["mysterious, dark ambient", "upbeat, tech, sci-fi", "cinematic, epic", ""], value="mysterious, dark ambient", label="Müzik teması")
            privacy_input = gr.Dropdown(["private", "unlisted", "public"], value="unlisted", label="YouTube gizliliği")

        with gr.Tab("Yönetmen Masası"):
            topic_input = gr.Textbox(label="Konu / yönetmen promptu", lines=3)
            generate_btn = gr.Button("Videoyu üret", variant="primary")
            status_output = gr.Textbox(label="Canlı durum", lines=5, interactive=False)
            video_output = gr.Video(label="Render edilen video")
            youtube_link = gr.Textbox(label="YouTube linki", interactive=False)
            generate_btn.click(
                generate_short,
                inputs=[topic_input, language_input, theme_input, privacy_input, visual_source, video_mode, input_video, input_image],
                outputs=[status_output, video_output, youtube_link],
            )


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
import sys
from pathlib import Path

# Add project root to sys path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings
