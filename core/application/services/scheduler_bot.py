import asyncio
import logging
from datetime import datetime
from scripts.run_factory import build_orchestrator
from config.settings import get_settings
from infrastructure.repositories.sqlite_video_repository import SQLiteVideoRepository
from core.domain.entities.pipeline_run import PipelineRun
from pathlib import Path
import uuid
from scripts.discover_trending_topic import get_trending_topic

logger = logging.getLogger(__name__)

class SchedulerBot:
    def __init__(self):
        self.is_running = False
        self._task = None
        self.interval_hours = 24

    def start(self, interval_hours: int, language: str = "tr", privacy: str = "private"):
        if self.is_running:
            logger.warning("Scheduler Bot is already running.")
            return

        self.interval_hours = interval_hours
        self.is_running = True
        self._task = asyncio.create_task(self._run_loop(language, privacy))
        logger.info(f"Otonom Fabrika Başlatıldı! Her {interval_hours} saatte bir video üretilecek.")

    def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
        logger.info("Otonom Fabrika Durduruldu.")

    async def _run_loop(self, language: str, privacy: str):
        settings = get_settings()

        while self.is_running:
            logger.info(f"Otonom Bot tetiklendi. Zaman: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            try:
                # 1. Trend Bul (Eğer konu yoksa)
                logger.info("İnternetten bugünün trend konusu aranıyor...")
                topic = await get_trending_topic(settings)
                logger.info(f"Trend bulundu: {topic}")

                # 2. Pipeline'ı Tetikle
                from infrastructure.repositories.local_json_run_repository import LocalJsonRunRepository
                import os
                run_id = str(uuid.uuid4())

                os.makedirs(".selma_runs", exist_ok=True)
                repo = LocalJsonRunRepository(".selma_runs")
                pipeline_run = PipelineRun(run_id=run_id)
                await repo.save(pipeline_run)

                output_dir = Path(settings.storage_root_dir) / run_id

                orchestrator = build_orchestrator(
                    repo,
                    output_dir,
                    target_duration_ms=30000,
                    enable_topic_pipeline=True,
                    content_language=language,
                )

                settings.youtube_upload_privacy = privacy
                settings.youtube_upload_enabled = True

                await orchestrator.execute(pipeline_run, topic=topic)
                logger.info(f"Otonom üretim tamamlandı ve yüklendi! Run ID: {run_id}")

            except Exception as e:
                logger.error(f"Otonom üretim sırasında kritik hata: {e}")

            # Uyku modu
            logger.info(f"Bir sonraki üretim için {self.interval_hours} saat bekleniyor...")
            await asyncio.sleep(self.interval_hours * 3600)

scheduler_bot_instance = SchedulerBot()
