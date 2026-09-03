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

async def generate_short(topic: str, language: str, music_theme: str, privacy: str, generation_engine: str, voice_provider: str, apply_mastering: bool = True, i2v_image: str = None):
    settings = get_settings()

    if not topic.strip():
        yield "Konu girilmedi. İnternetteki bugünün trend konusu aranıyor...", None, None
        from scripts.discover_trending_topic import get_trending_topic
        try:
            topic = await get_trending_topic(settings)
            yield f"Trend konu bulundu: '{topic}'. Yapay zeka senaryo yazımına başlıyor...", None, None
        except Exception as e:
            yield f"Trend bulunamadı: {e}. Lütfen elle bir konu girin.", None, None
            return
    else:
        yield f"'{topic}' konulu video için yapay zeka senaryo yazımına başlıyor...", None, None


    settings = get_settings()
    # Force some settings for UI
    settings.youtube_upload_enabled = True
    settings.youtube_upload_privacy = privacy
    # Map UI engine to backend providers
    settings.apply_cinematic_mastering = apply_mastering
    # Map UI engine to backend providers
    if voice_provider == "Local Ses Klonlama (Kendi Sesim)":
        settings.voice_provider = "local_xtts"
    else:
        settings.voice_provider = "elevenlabs"

    # Map UI engine to backend providers
    settings.apply_cinematic_mastering = apply_mastering
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
    elif generation_engine == "ComfyUI (Image-to-Video)":
        settings.video_provider = "pexels" # fallback search
        settings.video_generation_provider = "comfyui"
        settings.comfyui_mode = "i2v"
        if i2v_image:
            import shutil
            os.makedirs("output/user_uploads/images", exist_ok=True)
            dest = os.path.join("output/user_uploads/images", os.path.basename(i2v_image))
            shutil.copy(i2v_image, dest)
            settings.i2v_image_path = dest
    elif generation_engine == "ComfyUI (Video-to-Video)":
        settings.video_provider = "user_uploads" # Use local
        settings.video_generation_provider = "comfyui"
        settings.comfyui_mode = "v2v"

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
custom_theme = gr.themes.Soft(primary_hue="indigo", secondary_hue="blue", neutral_hue="slate")
with gr.Blocks(title="SELMA Labs - Yönetmen Stüdyosu") as demo:
    gr.Markdown("# 🎬 SELMA Labs - Yönetmen Stüdyosu (V2)")
    gr.Markdown("Kendi medyanızı yükleyin, yapay zekayı yönlendirin ve benzersiz kalitede YouTube Shorts'lar yaratın.")

    with gr.Tabs():
        # Sekme 1: Yönetmen Masası (Üretim)
        with gr.Tab("🎬 Yönetmen Masası"):
            with gr.Row():
                with gr.Column(scale=1):
                    with gr.Group():
                        topic_input = gr.Textbox(label="Video Konusu / Luma Promptu", placeholder="Boş bırakırsanız sistem bugünün en popüler Trend konusunu kendisi bulur!", lines=3)
                        enhance_btn = gr.Button("✨ Sihirli Değnek (Promptu Sinematik Yap)", size="sm")

                    with gr.Accordion("🖼️ Başlangıç Karesi (Image-to-Video)", open=False):
                        gr.Markdown("Luma'daki gibi hareketi bir görselden başlatmak için buraya ilk kareyi (Keyframe) yükleyin.")
                        i2v_image_input = gr.Image(type="filepath", label="İlk Kareyi Yükle (İsteğe Bağlı)")

                    language_input = gr.Dropdown(choices=["en", "tr", "es", "de", "fr"], value="tr", label="Yayın Dili")
                    theme_input = gr.Dropdown(choices=["mystery", "epic", "sci-fi", "documentary", "chill"], value="mystery", label="Müzik / Atmosfer")
                    privacy_input = gr.Radio(choices=["public", "unlisted", "private"], value="unlisted", label="YouTube Gizlilik")

                    gr.Markdown("### Yapay Zeka Video Motoru")
                    generation_engine = gr.Radio(
                        choices=["Kişisel Havuzdan Seç (Sadece Benim Yüklediklerim)", "Pexels (Stok Video)", "ComfyUI (T2V - Üret)", "ComfyUI (Image-to-Video)", "ComfyUI (Video-to-Video)"],
                        value="Pexels (Stok Video)",
                        label="Görsel Kaynağı Seçimi"
                    )

                    gr.Markdown("### Ekstra Kalite (Post-Processing)")
                    mastering_checkbox = gr.Checkbox(label="✨ Sinematik Mastering (Renk & Ses İyileştirme)", value=True)
                    generate_btn = gr.Button("🚀 Yapay Zeka ile Videoyu Üret ve Yayınla", variant="primary", size="lg")

                with gr.Column(scale=1):
                    status_output = gr.Textbox(label="Durum Konsolu", lines=6, interactive=False)
                    video_output = gr.Video(label="Üretilen Video Sonucu")
                    youtube_link = gr.Textbox(label="YouTube Linki", interactive=False)

        # Sekme 6: Yapay Zeka Beyni
        with gr.Tab("🧠 Yapay Zeka Beyni"):
            gr.Markdown("### YouTube Optimizasyon ve Öğrenme Merkezi")
            gr.Markdown("Sistem, ürettiği her videonun izlenme oranını (AVD) ve kitleyi tutma başarısını analiz ederek kendini eğitir. Sonuçlar senaryo yazarına (SelmaGPT) yönlendirme olarak iletilir.")

            with gr.Row():
                with gr.Column():
                    gr.Markdown("#### Anlık Öğrenme İstatistikleri")
                    total_vid_out = gr.Textbox(label="Analiz Edilen Toplam Video")
                    avg_view_out = gr.Textbox(label="Ortalama İzlenme Oranı (AVD)")
                    best_format_out = gr.Textbox(label="Kanalınızın En Başarılı Formatı")
                    refresh_stats_btn = gr.Button("🔄 Verileri Güncelle")

                with gr.Column():
                    gr.Markdown("#### SelmaGPT Aktif Öğrenme Stratejisi")
                    strategy_out = gr.Textbox(label="Senaryo Yazarına Verilen Gizli Talimat", lines=6, interactive=False)

        # Sekme 5: Sistem Monitörü
        with gr.Tab("📊 Sistem Monitörü"):
            gr.Markdown("### Canlı Kaynak Tüketimi (Real-Time Monitor)")
            gr.Markdown("Sunucunuzun / Bilgisayarınızın kaynak kullanımını buradan canlı olarak takip edebilirsiniz.")

            with gr.Row():
                with gr.Column():
                    cpu_out = gr.Textbox(label="💻 CPU Kullanımı", interactive=False)
                    ram_out = gr.Textbox(label="🧠 RAM Kullanımı", interactive=False)
                with gr.Column():
                    gpu_out = gr.Textbox(label="🎮 GPU Durumu (VRAM)", interactive=False, lines=2)
                    disk_out = gr.Textbox(label="💾 Disk Doluluğu", interactive=False)

            gr.Markdown("### Canlı Uygulama Logları")
            log_out = gr.Textbox(label="Terminal", lines=10, interactive=False)

        # Sekme 4: Otonom Fabrika (Scheduler)
        with gr.Tab("🤖 Otonom Fabrika (7/24)"):
            gr.Markdown("### Siz uyurken kanalınız büyüsün!")
            gr.Markdown("Bu botu başlattığınızda, ayarladığınız saat aralığında bir uyanıp internetteki trendleri bulur, senaryoyu kendi yazar, videoyu kendi renderlar ve YouTube kanalınıza otomatik yükler.")

            with gr.Row():
                with gr.Column():
                    interval_input = gr.Slider(minimum=1, maximum=72, step=1, value=24, label="Üretim Sıklığı (Kaç saatte bir?)")
                    sched_lang_input = gr.Dropdown(choices=["en", "tr", "es", "de"], value="tr", label="Yayın Dili")
                    sched_privacy = gr.Radio(choices=["public", "unlisted", "private"], value="private", label="YouTube Gizliliği")

                    with gr.Row():
                        start_bot_btn = gr.Button("🟢 Otonom Botu Başlat", variant="primary")
                        stop_bot_btn = gr.Button("🔴 Botu Durdur", variant="stop")

                with gr.Column():
                    bot_status = gr.Textbox(label="Bot Durumu", value="Bot şu an: UYUYOR (Kapalı)", interactive=False, lines=3)

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
                    voice_provider = gr.Radio(choices=["ElevenLabs (Ücretli API)", "Local Ses Klonlama (Kendi Sesim)"], value="ElevenLabs (Ücretli API)", label="Seslendirme Motoru (TTS)")

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
        upload_dir = "output/user_uploads"
        os.makedirs(upload_dir, exist_ok=True)
        res = []
        for f in files:
            file_path = f.name if hasattr(f, 'name') else f
            # Always save as voice_reference.wav so the backend can easily pick it up for cloning
            dest = os.path.join(upload_dir, "voice_reference.wav")
            shutil.copy(file_path, dest)
            res.append(["voice_reference.wav (Ses Klonlama Referansı)", f"{os.path.getsize(dest)/1024:.1f} KB"])
            break # Sadece ilk yüklenen dosyayı referans kabul et
        return res

    user_videos.change(fn=update_video_gallery, inputs=user_videos, outputs=video_gallery)
    user_audio.change(fn=update_audio_gallery, inputs=user_audio, outputs=audio_gallery)





    # Enhancer Logic
    from core.application.services.prompt_enhancer_service import prompt_enhancer_service
    async def enhance_prompt(prompt, endpoint, llm_choice):
        # Determine model name based on UI choice
        model_name = "llama3" if llm_choice == "ollama" else "SelmaGPT-v1"
        enhanced = await prompt_enhancer_service.enhance(prompt, endpoint, model_name)
        return enhanced

    enhance_btn.click(fn=enhance_prompt, inputs=[topic_input, llm_endpoint, script_llm], outputs=topic_input)

    # AI Brain Logic
    from core.application.services.analytics_strategy_service import analytics_strategy_service

    async def load_brain_stats():
        stats = await analytics_strategy_service.get_dashboard_stats()
        strategy = await analytics_strategy_service.get_current_strategy()
        return stats["total_videos"], stats["avg_view_rate"], stats["best_format"], strategy

    refresh_stats_btn.click(fn=load_brain_stats, inputs=None, outputs=[total_vid_out, avg_view_out, best_format_out, strategy_out])

    # Real-Time Monitor Logic
    from core.application.services.system_monitor import get_system_stats


    # Logging capture setup
    import logging
    log_file = "output/system.log"
    os.makedirs("output", exist_ok=True)
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logging.getLogger().addHandler(file_handler)
    logging.getLogger().setLevel(logging.INFO)

    def refresh_monitor():
        stats = get_system_stats()
        logs = ""
        try:
            with open(log_file, "r", encoding="utf-8") as lf:
                lines = lf.readlines()
                logs = "".join(lines[-15:]) # Son 15 log
        except:
            pass
        return stats["cpu_percent"], stats["ram_percent"], stats["gpu_info"], stats["disk_percent"], logs

    timer = gr.Timer(2.0)
    timer.tick(fn=refresh_monitor, inputs=None, outputs=[cpu_out, ram_out, gpu_out, disk_out, log_out])


    # Scheduler Logic Connections
    from core.application.services.scheduler_bot import scheduler_bot_instance

    def start_scheduler(interval, lang, priv):
        scheduler_bot_instance.start(interval, lang, priv)
        return f"Bot şu an: ÇALIŞIYOR (Her {interval} saatte bir içerik üretecek)"

    def stop_scheduler():
        scheduler_bot_instance.stop()
        return "Bot şu an: UYUYOR (Durduruldu)"

    start_bot_btn.click(fn=start_scheduler, inputs=[interval_input, sched_lang_input, sched_privacy], outputs=bot_status)
    stop_bot_btn.click(fn=stop_scheduler, inputs=[], outputs=bot_status)

    generate_btn.click(
        fn=generate_short,
        inputs=[topic_input, language_input, theme_input, privacy_input, generation_engine, voice_provider, mastering_checkbox, i2v_image_input],
        outputs=[status_output, video_output, youtube_link]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, theme=gr.themes.Base())
