from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import edge_tts
from mutagen.mp3 import MP3


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "motion" / "public" / "perseid-short"
OUTPUT = ROOT / "output" / "perseid-short"

SCRIPT = (
    "Bu gece gökyüzünde kayan ışıklar görebilirsin. Ama onlar yıldız değil. "
    "Bunlar, Swift Tuttle kuyruklu yıldızının geride bıraktığı küçücük parçalar. "
    "Dünya bu toz bulutunun içinden geçerken parçalar atmosfere yaklaşık saniyede elli dokuz kilometre hızla giriyor. "
    "Havayı sıkıştırıp ısıttıkları için bir anlığına parlıyorlar. Çoğu kum tanesi kadar küçük. "
    "Perseidlerin zirvesi on iki, on üç Ağustos gecesiydi; ama karanlık bir yerde birkaç gece daha meteor yakalama şansın var. "
    "Şehir ışıklarından uzaklaş, gökyüzünün geniş bir bölümünü izle ve gözlerinin karanlığa alışması için yirmi dakika bekle. Teleskop gerekmiyor."
)


async def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    narration = PUBLIC / "narration.mp3"
    boundaries: list[dict[str, int | str]] = []
    communicator = edge_tts.Communicate(
        text=SCRIPT,
        voice="tr-TR-EmelNeural",
        rate="+15%",
        pitch="+2Hz",
        volume="+0%",
        boundary="WordBoundary",
    )
    with narration.open("wb") as handle:
        async for event in communicator.stream():
            if event.get("type") == "audio":
                handle.write(event["data"])
            elif event.get("type") == "WordBoundary":
                start_ms = round(int(event["offset"]) / 10_000)
                duration_ms = max(70, round(int(event["duration"]) / 10_000))
                boundaries.append({
                    "text": str(event["text"]),
                    "startMs": start_ms,
                    "endMs": start_ms + duration_ms,
                })
    duration_ms = round(MP3(narration).info.length * 1000)
    captions = [
        {"text": " " + str(word["text"]), "startMs": word["startMs"], "endMs": word["endMs"], "timestampMs": None, "confidence": None}
        for word in boundaries
    ]
    (PUBLIC / "data.json").write_text(json.dumps({"durationMs": duration_ms, "words": boundaries}, ensure_ascii=False, indent=2), encoding="utf-8")
    (PUBLIC / "captions.json").write_text(json.dumps(captions, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT / "script.txt").write_text(SCRIPT, encoding="utf-8")
    shutil.copy2(narration, OUTPUT / "narration_emel.mp3")
    print(json.dumps({"durationMs": duration_ms, "words": len(boundaries)}))


if __name__ == "__main__":
    asyncio.run(main())
