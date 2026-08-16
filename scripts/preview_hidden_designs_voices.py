from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from infrastructure.providers.voice.elevenlabs_provider import ElevenLabsVoiceProvider

OUTPUT = ROOT / "output" / "hidden-designs-45" / "voice-previews"
SAMPLE = (
    "Etrafınıza dikkatlice bakın. Her gün kullandığınız nesnelerin üzerinde, "
    "bugüne kadar fark etmediğiniz küçük sırlar var. Şimdi kırk beş tanesini hızlıca çözüyoruz."
)


async def main() -> None:
    load_dotenv(ROOT / ".env")
    api_key = os.environ["ELEVENLABS_API_KEY"]
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": api_key})
        response.raise_for_status()
        voices = response.json().get("voices", [])
    preferred_names = ["Brian", "Liam", "Adam", "Daniel"]
    chosen = []
    for name in preferred_names:
        voice = next((item for item in voices if item.get("name", "").casefold() == name.casefold()), None)
        if voice:
            chosen.append(voice)
    if len(chosen) < 3:
        for voice in voices:
            labels = voice.get("labels") or {}
            if labels.get("gender") == "male" and voice not in chosen:
                chosen.append(voice)
            if len(chosen) >= 3:
                break
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for voice in chosen[:3]:
        provider = ElevenLabsVoiceProvider(
            api_key=api_key,
            model_id="eleven_multilingual_v2",
            stability=0.32,
            similarity_boost=0.82,
            style=0.62,
            speed=1.15,
            use_speaker_boost=True,
        )
        generated = await provider.generate_voice(SAMPLE, voice["voice_id"])
        slug = voice["name"].lower().replace(" ", "-")
        path = OUTPUT / f"{slug}.mp3"
        path.write_bytes(generated.audio_bytes)
        manifest.append(f"{voice['name']}\t{voice['voice_id']}\t{generated.duration_seconds:.2f}\t{path.name}")
        print(manifest[-1])
    (OUTPUT / "manifest.tsv").write_text("\n".join(manifest), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
