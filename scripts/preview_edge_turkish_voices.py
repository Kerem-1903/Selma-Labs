from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "hidden-designs-45" / "voice-previews"
TEXT = (
    "Etrafınıza dikkatlice bakın. Her gün kullandığınız nesnelerin üzerinde, "
    "bugüne kadar fark etmediğiniz küçük sırlar var. Şimdi kırk beş tanesini hızlıca çözüyoruz."
)


async def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, voice, pitch in [
        ("emel-tempolu", "tr-TR-EmelNeural", "+2Hz"),
        ("ahmet-tempolu", "tr-TR-AhmetNeural", "+2Hz"),
    ]:
        await edge_tts.Communicate(
            text=TEXT,
            voice=voice,
            rate="+14%",
            pitch=pitch,
            volume="+0%",
        ).save(str(OUTPUT / f"{name}.mp3"))
        print(OUTPUT / f"{name}.mp3")


if __name__ == "__main__":
    asyncio.run(main())
