from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import edge_tts
from mutagen.mp3 import MP3


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "visuals" / "venus" / "nasa"
PUBLIC = ROOT / "motion" / "public" / "venus-v2"
OUTPUT = ROOT / "output" / "venus_day_year_v2"

SENTENCES = [
    "Venüs, bir gününü bitiremeden koskoca bir yılı tamamlıyor.",
    "Çünkü kendi ekseninde o kadar yavaş dönüyor ki, tek turu 243 Dünya günü sürüyor.",
    "Buna yıldız günü deniyor.",
    "Oysa Güneş'in çevresindeki bir turunu 225 günde tamamlıyor.",
    "Yani Venüs'ün günü, yılından 18 Dünya günü daha uzun.",
    "Üstelik çoğu gezegenin tersine, doğudan batıya dönüyor.",
    "Ama burada küçük bir ayrıntı var.",
    "Venüs yüzeyinde, bir gün doğumundan diğerine kadar geçen güneş günü yaklaşık 117 Dünya günü sürüyor.",
]
SCRIPT = " ".join(SENTENCES)


async def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    audio_path = PUBLIC / "narration.mp3"
    sentence_tracks: list[tuple[Path, list[dict[str, int | str]]]] = []
    for index, sentence in enumerate(SENTENCES):
        sentence_path = PUBLIC / f"_sentence_{index:02d}.mp3"
        sentence_words: list[dict[str, int | str]] = []
        communicator = edge_tts.Communicate(
            text=sentence,
            voice="tr-TR-AhmetNeural",
            rate="+5%",
            pitch="-2Hz",
            volume="+0%",
            boundary="WordBoundary",
        )
        with sentence_path.open("wb") as audio_file:
            async for event in communicator.stream():
                event_type = event.get("type")
                if event_type == "audio":
                    audio_file.write(event["data"])
                elif event_type == "WordBoundary":
                    start_ms = round(int(event["offset"]) / 10_000)
                    duration_ms = max(60, round(int(event["duration"]) / 10_000))
                    sentence_words.append(
                        {
                            "text": str(event["text"]),
                            "startMs": start_ms,
                            "endMs": start_ms + duration_ms,
                        }
                    )
        sentence_tracks.append((sentence_path, sentence_words))

    ffmpeg_command = ["ffmpeg", "-y"]
    filter_parts: list[str] = []
    words: list[dict[str, int | str]] = []
    cursor_ms = 0
    gap_ms = 220
    for index, (sentence_path, sentence_words) in enumerate(sentence_tracks):
        ffmpeg_command.extend(["-i", str(sentence_path)])
        first_ms = int(sentence_words[0]["startMs"])
        last_ms = int(sentence_words[-1]["endMs"])
        filter_parts.append(
            f"[{index}:a]atrim=start={first_ms / 1000:.3f}:end={(last_ms + 70) / 1000:.3f},"
            f"asetpts=PTS-STARTPTS,apad=pad_dur={gap_ms / 1000:.3f}[s{index}]"
        )
        for word in sentence_words:
            words.append(
                {
                    "text": word["text"],
                    "startMs": cursor_ms + int(word["startMs"]) - first_ms,
                    "endMs": cursor_ms + int(word["endMs"]) - first_ms,
                }
            )
        cursor_ms += last_ms - first_ms + 70 + gap_ms

    filter_parts.append(
        "".join(f"[s{index}]" for index in range(len(sentence_tracks)))
        + f"concat=n={len(sentence_tracks)}:v=0:a=1[out]"
    )
    ffmpeg_command.extend(
        [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[out]",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(audio_path),
        ]
    )
    subprocess.run(ffmpeg_command, check=True, capture_output=True)
    for sentence_path, _ in sentence_tracks:
        sentence_path.unlink(missing_ok=True)

    duration_ms = round(MP3(audio_path).info.length * 1_000)
    data = {
        "script": SCRIPT,
        "durationMs": duration_ms,
        "words": words,
        "sources": [
            {
                "name": "Venus from Mariner 10",
                "credit": "NASA/JPL-Caltech",
                "url": "https://science.nasa.gov/photojournal/venus-from-mariner-10/",
            },
            {
                "name": "Magellan global views of Venus",
                "credit": "NASA/JPL",
                "url": "https://science.nasa.gov/photojournal/venus-computer-simulated-global-view-centered-at-0-degrees-east-longitude/",
            },
            {
                "name": "Evolution of Venus Animations",
                "credit": "NASA Goddard Space Flight Center Conceptual Image Lab",
                "url": "https://svs.gsfc.nasa.gov/20308/",
            },
        ],
    }
    (PUBLIC / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT / "narration_script.txt").write_text(SCRIPT, encoding="utf-8")
    (OUTPUT / "sources.json").write_text(
        json.dumps(data["sources"], ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for name in ("mariner_venus.jpg", "magellan_north.jpg", "magellan_global.jpg", "venus_evolution.mp4"):
        shutil.copy2(SOURCE / name, PUBLIC / name)
    shutil.copy2(ROOT / "assets" / "music" / "space-curiosity-bed.mp3", PUBLIC / "music.mp3")
    shutil.copy2(audio_path, OUTPUT / "narration_tr_natural.mp3")

    print(json.dumps({"duration_ms": duration_ms, "words": len(words), "audio": str(audio_path)}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
