import logging
from infrastructure.repositories.sqlite_youtube_performance_repository import SQLiteYoutubePerformanceRepository

logger = logging.getLogger(__name__)

class AnalyticsStrategyService:
    """
    Sistemin beyni: Geçmiş performans verilerini analiz eder,
    hangi konseptlerin/formatların daha iyi çalıştığını öğrenir
    ve yeni üretilecek videolar için LLM'e (SelmaGPT) yönlendirme (strategy prompt) çıkarır.
    """

    def __init__(self, db_path: str = "data/youtube_performance.sqlite"):
        self.db_path = db_path
        self.repository = SQLiteYoutubePerformanceRepository(db_path)

    async def get_current_strategy(self) -> str:
        """
        Geçmiş videoları analiz edip senaryo yazarı için stratejik bir prompt döndürür.
        Eğer yeterli veri yoksa standart bir strateji döner.
        """
        try:
            records = await self.repository.list_records()
        except Exception as e:
            logger.warning(f"Could not load performance records: {e}")
            return "Genel, ilgi çekici ve yüksek tempolu bir Shorts kurgula."

        if not records:
            return "Genel, ilgi çekici ve yüksek tempolu bir Shorts kurgula."

        # Basit bir Zeka Algoritması (Rule-Based AI):
        # AVD (Ortalama İzlenme Süresi) ve Hook Performansı bazlı analiz.

        # Son 20 videoyu değerlendir
        recent_records = sorted(records, key=lambda x: x.published_at, reverse=True)[:20]

        best_formats = {}
        best_hooks = {}

        for r in recent_records:
            score = (r.average_percentage_viewed * 0.7) + ((r.first_3_second_retention_percentage or 0) * 0.3)

            # Format Skoru
            if r.content_format not in best_formats:
                best_formats[r.content_format] = []
            best_formats[r.content_format].append(score)

            # Hook (Kanca) Skoru
            if r.hook_type not in best_hooks:
                best_hooks[r.hook_type] = []
            best_hooks[r.hook_type].append(score)

        # Ortalamaları al
        avg_formats = {k: sum(v)/len(v) for k, v in best_formats.items()}
        avg_hooks = {k: sum(v)/len(v) for k, v in best_hooks.items()}

        if not avg_formats or not avg_hooks:
            return "Genel, ilgi çekici ve yüksek tempolu bir Shorts kurgula."

        top_format = max(avg_formats.items(), key=lambda x: x[1])[0]
        top_hook = max(avg_hooks.items(), key=lambda x: x[1])[0]

        strategy_prompt = (
            f"Kanalın geçmiş istatistiksel zeka analizine göre:\n"
            f"1. En başarılı içerik formatı: '{top_format}' olmuştur. Hikayeyi bu formata uygun (örneğin bilgi verici, şaşırtıcı vs.) tasarla.\n"
            f"2. En çok izleyici tutan kanca (hook) tekniği: '{top_hook}'. Videonun ilk 3 saniyesini kesinlikle bu kanca stiliyle başlat.\n"
            f"Bu kurallara harfiyen uyarak seyirciyi sonuna kadar videoda tutacak bir metin yaz."
        )

        logger.info(f"AI Strategy Generated: {strategy_prompt}")
        return strategy_prompt

    async def get_dashboard_stats(self) -> dict:
        """UI Dashboard'una beyin istatistiklerini göndermek için."""
        try:
            records = await self.repository.list_records()
            if not records:
                return {"total_videos": 0, "avg_view_rate": "0%", "best_format": "Veri Yok"}

            total = len(records)
            avg_view = sum([r.average_percentage_viewed for r in records]) / total

            formats = {}
            for r in records:
                formats[r.content_format] = formats.get(r.content_format, 0) + 1
            best_format = max(formats.items(), key=lambda x: x[1])[0]

            return {
                "total_videos": total,
                "avg_view_rate": f"{avg_view:.1f}%",
                "best_format": best_format
            }
        except Exception:
            return {"total_videos": 0, "avg_view_rate": "0%", "best_format": "Veri Yok"}

analytics_strategy_service = AnalyticsStrategyService()
