from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import edge_tts
from mutagen.mp3 import MP3


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "motion" / "public" / "microwave-mesh"
OUTPUT = ROOT / "output" / "microwave_mesh"

SENTENCES = [
    "Bu siyah ağ olmasaydı, mikrodalganın dalgaları kapaktan dışarı çıkabilirdi.",
    "Ama gördüğün noktalar boya değil; ince bir metal ekran.",
    "Fırının içindeki magnetron, yaklaşık 2,45 gigahertzlik mikrodalgalar üretir.",
    "Bu dalgaların boyu yaklaşık 12 santimetredir.",
    "Ağdaki delikler ise yalnızca birkaç milimetre.",
    "Bu yüzden mikrodalgalar metalden geri yansır; çok daha kısa görünür ışık deliklerden geçer.",
    "Yani sen yemeği görürsün, mikrodalgalar içeride kalır.",
    "Küçük delikler, büyük bir güvenlik görevi yapıyor.",
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
            rate="+7%",
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
    gap_ms = 150
    for index, (sentence_path, sentence_words) in enumerate(sentence_tracks):
        ffmpeg_command.extend(["-i", str(sentence_path)])
        first_ms = int(sentence_words[0]["startMs"])
        last_ms = int(sentence_words[-1]["endMs"])
        filter_parts.append(
            f"[{index}:a]atrim=start={first_ms / 1000:.3f}:end={(last_ms + 60) / 1000:.3f},"
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
        cursor_ms += last_ms - first_ms + 60 + gap_ms

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
            "160k",
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
                "name": "Microwave Ovens",
                "credit": "U.S. Food and Drug Administration",
                "url": "https://www.fda.gov/radiation-emitting-products/resources-you-radiation-emitting-products/microwave-ovens",
            },
            {
                "name": "Grandma's Microwave Oven",
                "credit": "University of Illinois Physics Van",
                "url": "https://van.physics.illinois.edu/ask/listing/12217",
            },
        ],
        "visuals": {
            "credit": "OpenAI ImageGen ile konuya özel üretildi",
        },
    }
    (PUBLIC / "data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT / "narration_script.txt").write_text(SCRIPT, encoding="utf-8")
    (OUTPUT / "sources.json").write_text(
        json.dumps(data["sources"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    shutil.copy2(ROOT / "assets" / "music" / "space-curiosity-bed.mp3", PUBLIC / "music.mp3")
    shutil.copy2(audio_path, OUTPUT / "narration_tr.mp3")

    print(
        json.dumps(
            {"duration_ms": duration_ms, "words": len(words), "audio": str(audio_path)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
