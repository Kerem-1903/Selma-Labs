import json
import asyncio
import os
import sqlite3
from typing import List, Dict

# Projeden Youtube Performance Repository'yi ve SQLite altyapısını dahil edelim
from infrastructure.repositories.sqlite_youtube_performance_repository import SQLiteYoutubePerformanceRepository

async def build_dataset():
    print("=== SELMAGPT: Veri Seti Oluşturucu (Dataset Builder) Başlatıldı ===")

    # 1. Performance kayıtlarını SQLite üzerinden çek
    db_path = "data/youtube_performance.sqlite"
    if not os.path.exists("data"):
        os.makedirs("data")

    # Eğer database boşsa, sistemi kandırmak (simüle etmek) için dummy (sahte) veriler ekleyeceğiz
    # Gerçek kullanımda burası YouTube Performance Repository'den gerçek verilerle dolar
    repo = SQLiteYoutubePerformanceRepository(db_path=db_path)
    records = await repo.list_records()

    dataset: List[Dict[str, str]] = []

    if not records:
        print("Mevcut veri bulunamadı. SelmaGPT eğitimi için örnek (dummy) yüksek performanslı veriler yükleniyor...")
        # Örnek dummy viral Shorts senaryoları (Eğitim (Fine-Tuning) formatında Instruction-Response yapısı)
        dummy_data = [
            {
                "topic": "Quantum entanglement explained simply",
                "narration": "What if two particles could communicate instantly across the universe? Welcome to quantum entanglement. Even Einstein called it spooky action at a distance. If you spin one particle here, its twin spins exactly the same way on Mars. Zero delay. It breaks the speed of light. And the craziest part? We're building quantum computers right now that use this to solve impossible problems. Subscribe for more space secrets."
            },
            {
                "topic": "The mystery of the Bermuda Triangle",
                "narration": "Hundreds of ships. Dozens of planes. All vanished without a single trace. The Bermuda Triangle remains our planet's greatest unsolved mystery. Some say it's alien abductions, others say magnetic anomalies that destroy compasses. In 1945, Flight 19 disappeared perfectly on a clear day, and the rescue plane sent to find them vanished too. Will we ever know the truth? Follow for daily mysteries."
            },
            {
                "topic": "Scariest deep sea creatures",
                "narration": "You are terrified of space, but the real monsters live right here on Earth. Down in the Mariana Trench, there's no light, crushing pressure, and nightmares. Meet the Goblin Shark. It thrusts its entire jaw out of its mouth to catch prey. Or the Anglerfish, luring victims with a glowing trap in pitch black darkness. We've only explored 5 percent of our oceans. What else is down there? Like and subscribe."
            }
        ]

        for item in dummy_data:
            dataset.append({
                "system": "You are SelmaGPT, a highly specialized AI designed to write viral, engaging, and high-retention YouTube Shorts scripts.",
                "user": f"Write a 30-second engaging YouTube Shorts script about: '{item['topic']}'. Only output the raw spoken narration text. No stage directions.",
                "assistant": item["narration"]
            })
    else:
        # Gerçek veriler SQLite'a işlendiyse, AVD (Average View Duration) yüksek olanları seçip eğitime katıyoruz
        print(f"{len(records)} adet gerçek YouTube performansı bulundu. Sadece 'Viral' (> 70% AVD) olanlar filtreleniyor...")
        from config.settings import get_settings
        from infrastructure.repositories.local_json_run_repository import LocalJsonRunRepository
        settings = get_settings()
        run_repo = LocalJsonRunRepository(settings.storage_root_dir)

        for record in records:
            if record.average_percentage_viewed >= 70.0:
                try:
                    pipeline_run = await run_repo.get_by_id(record.run_id)
                    # Pipeline run üzerinden script ve konuyu çekiyoruz (örnek yapıya göre)
                    script_text = pipeline_run.get_artifact_manifest().get("narrative_script")
                    topic = pipeline_run.get_artifact_manifest().get("topic", "Trending Topic")
                    if script_text:
                        dataset.append({
                            "system": "You are SelmaGPT, a highly specialized AI designed to write viral, engaging, and high-retention YouTube Shorts scripts.",
                            "user": f"Write a 30-second engaging YouTube Shorts script about: '{topic}'. Only output the raw spoken narration text. No stage directions.",
                            "assistant": script_text
                        })
                except Exception as e:
                    print(f"Skipping run {record.run_id} due to error: {e}")

    # JSONL formatında kaydet (HuggingFace, Unsloth, Llama-Factory uyumlu)
    output_file = "data/selmagpt_training_dataset.jsonl"
    with open(output_file, "w", encoding="utf-8") as f:
        for entry in dataset:
            f.write(json.dumps(entry) + "\n")

    print(f"Başarılı! Eğitim veriseti ({len(dataset)} kayıt) JSONL formatında '{output_file}' konumuna oluşturuldu.")
    print("Bu veri setini Unsloth veya Llama-Factory ile kullanarak kendi SelmaGPT modelinizi eğitebilirsiniz.")

if __name__ == "__main__":
    asyncio.run(build_dataset())
