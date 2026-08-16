from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import edge_tts
from mutagen.mp3 import MP3


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "motion" / "public" / "hidden-designs"
OUTPUT = ROOT / "output" / "hidden-designs"

CHAPTERS = [
    {
        "id": "hook",
        "kicker": "GÖRDÜN. AMA FARK ETMEDİN.",
        "title": "Bunların hiçbiri süs değil",
        "image": "fuel-gauge.jpg",
        "sentences": [
            "Arabanızdaki bu küçük ok, benzinliğe yanlış taraftan girmenizi engelleyebilir.",
            "Kalem kapağındaki delik süs değil.",
            "Yürüyen merdivendeki fırça da ayakkabınızı temizlemiyor.",
            "Her gün gördüğünüz sekiz küçük tasarım detayı var; ama gerçek amaçları gözünüzün önünde saklanıyor.",
            "Sonuncusunu öğrendiğinizde mezuraya bir daha aynı gözle bakmayacaksınız.",
        ],
    },
    {
        "id": "fuel",
        "kicker": "1 / 8 — ARABADAKİ KÜÇÜK OK",
        "title": "Depo kapağı hangi tarafta?",
        "image": "fuel-gauge.jpg",
        "sentences": [
            "Birinci detay, yakıt göstergesinin yanındaki minicik ok.",
            "Kiralık bir arabayla benzinliğe girdiniz ve depo kapağının hangi tarafta olduğunu unuttunuz diyelim.",
            "Camdan sarkmaya gerek yok.",
            "Ok hangi yönü gösteriyorsa yakıt kapağı o tarafta.",
            "Küçücük bir işaret, istasyonda arabanın çevresinde atacağınız utanç turunu önlüyor.",
        ],
    },
    {
        "id": "pen",
        "kicker": "2 / 8 — KALEM KAPAĞINDAKİ DELİK",
        "title": "Mürekkep kurusun diye değil",
        "image": "pen-caps.jpg",
        "sentences": [
            "İkinci detay, tükenmez kalem kapağının tepesindeki delik.",
            "Çoğu kişi bunun mürekkebi havalandırdığını sanıyor.",
            "Asıl fikir güvenlik.",
            "Kapak yanlışlıkla boğaza kaçarsa, bu açıklık bir miktar hava geçişine yardımcı olabiliyor.",
            "Elbette boğulma riskini ortadan kaldırmıyor; ama ufacık bir delik kritik birkaç saniye kazandırabilir.",
        ],
    },
    {
        "id": "keyboard",
        "kicker": "3 / 8 — F VE J TUŞLARI",
        "title": "Parmaklarınızın pusulası",
        "image": "keyboard.jpg",
        "sentences": [
            "Şimdi klavyenizde F ve J tuşlarına dokunun.",
            "İkisinde de küçük bir kabartı var.",
            "Bunlar, klavyeye bakmadan ellerinizi ana sıraya yerleştirmeniz için yapılmış dokunsal işaretler.",
            "Sol işaret parmağı F'yi, sağ işaret parmağı J'yi bulduğunda diğer parmaklar da doğru konuma geliyor.",
            "Yani o iki çizgi, parmaklarınızın pusulası.",
        ],
    },
    {
        "id": "escalator",
        "kicker": "4 / 8 — YÜRÜYEN MERDİVEN FIRÇASI",
        "title": "Ayakkabı temizlemiyor",
        "image": "escalator.jpg",
        "sentences": [
            "Yürüyen merdivenin kenarındaki uzun fırçaya ayakkabınızı sürttünüz mü?",
            "Kötü haber: o bir ayakkabı fırçası değil.",
            "Basamağın hareketli kısmıyla sabit yan panel arasında dar bir boşluk bulunuyor.",
            "Bazı modellerde bulunan kenar fırçaları ayağınızı, bağcığınızı ve kıyafetinizi bu boşluktan uzak tutan dokunsal bir uyarı oluşturuyor.",
            "Kısacası böyle bir fırçaya değdiğinizde mesaj şu: biraz ortaya geç.",
        ],
    },
    {
        "id": "airplane",
        "kicker": "5 / 8 — UÇAK CAMINDAKİ DELİK",
        "title": "Basıncın görünmez bekçisi",
        "image": "airplane-window.jpg",
        "sentences": [
            "Uçak camının alt kısmındaki o iğne ucu kadar deliğe gelelim.",
            "Pencere aslında birden fazla katmandan oluşuyor.",
            "Bu küçük açıklık, katmanlar arasındaki basıncın kontrollü biçimde dengelenmesini sağlıyor; böylece kabin basıncının asıl yükünü dış katman taşıyor.",
            "Ayrıca katmanlar arasındaki nemin kaçmasına yardım ederek buğulanmayı azaltıyor.",
            "Gökyüzünde görmek isteyeceğiniz delik tam olarak bu.",
        ],
    },
    {
        "id": "microwave",
        "kicker": "6 / 8 — MİKRODALGA KAPAĞINDAKİ AĞ",
        "title": "Işığı geçirir, dalgayı tutar",
        "image": "microwave-door.jpg",
        "sentences": [
            "Mikrodalga kapağındaki siyah noktalı metal ağ neden var?",
            "Delikler görünür ışığın dalga boyuna göre yeterince büyük; bu yüzden yemeği görebiliyorsunuz.",
            "Mikrodalgaların dalga boyuysa bu deliklerden çok daha büyük.",
            "Metal ağ, fırının içini küçük bir Faraday kafesi gibi çevreleyerek enerjinin dışarı kaçmasını engelliyor.",
            "Yani o desen görüşünüzü biraz bozuyor ama mutfağın görünmez güvenlik duvarı olarak çalışıyor.",
        ],
    },
    {
        "id": "knife",
        "kicker": "7 / 8 — MAKET BIÇAĞINDAKİ ÇİZGİLER",
        "title": "Bıçak körelmedi; sıradaki hazır",
        "image": "knife.jpg",
        "sentences": [
            "Maket bıçağının üzerindeki çapraz çizgiler süs ya da ölçü işareti değil.",
            "Her çizgi, bıçağın güvenli biçimde kırılabileceği zayıflatılmış bir bölüm.",
            "Uç köreldiğinde yalnızca en öndeki parçayı uygun bir aparatta kırıyorsunuz ve alttan yeni, keskin bir uç çıkıyor.",
            "Tek bıçak gövdesinin içinde sıraya girmiş birçok yedek uç var.",
            "Ama penseyle gelişigüzel denemeyin; kopan parça beklenmedik şekilde fırlayabilir.",
        ],
    },
    {
        "id": "tape",
        "kicker": "8 / 8 — MEZURADAKİ SİYAH ELMAS",
        "title": "Her 48,8 santimetrede bir gizli işaret",
        "image": "tape.jpg",
        "sentences": [
            "Ve mezuralarda tekrar eden siyah elmaslar.",
            "Bunlar rastgele basılmış logolar değil.",
            "Amerikan tipi yapılarda kirişleri eşit aralıklarla yerleştirmek için her on dokuz nokta iki inçte, yani yaklaşık kırk sekiz virgül sekiz santimetrede bir görünürler.",
            "Bu aralık sayesinde iki yüz kırk dört santimetrelik standart bir levhanın altına beş eşit bölüm yerleştirilebilir.",
            "Bir dahaki sefere mezurayı açtığınızda yalnızca sayıları değil, marangozların gizli kısa yolunu da göreceksiniz.",
        ],
    },
    {
        "id": "outro",
        "kicker": "ŞİMDİ SIRA SENDE",
        "title": "Hangisini ilk kez duydun?",
        "image": "airplane-window.jpg",
        "sentences": [
            "Günlük tasarımın en güzel tarafı bu: iyi çalıştığında varlığını fark etmiyoruz.",
            "Bu sekiz detaydan hangisini ilk kez duydunuz?",
            "Yorumlara numarasını yazın; devam videosunda evinizde saklanan sekiz ayrıntıya daha bakalım.",
        ],
    },
]


async def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    sentence_tracks: list[tuple[Path, list[dict[str, int | str]], int, int]] = []
    sentence_index = 0
    for chapter_index, chapter in enumerate(CHAPTERS):
        for sentence in chapter["sentences"]:
            sentence_path = PUBLIC / f"_sentence_{sentence_index:03d}.mp3"
            sentence_words: list[dict[str, int | str]] = []
            communicator = edge_tts.Communicate(
                text=sentence,
                voice="tr-TR-AhmetNeural",
                rate="+3%",
                pitch="+1Hz",
                volume="+0%",
                boundary="WordBoundary",
            )
            with sentence_path.open("wb") as audio_file:
                async for event in communicator.stream():
                    if event.get("type") == "audio":
                        audio_file.write(event["data"])
                    elif event.get("type") == "WordBoundary":
                        start_ms = round(int(event["offset"]) / 10_000)
                        duration_ms = max(70, round(int(event["duration"]) / 10_000))
                        sentence_words.append(
                            {
                                "text": str(event["text"]),
                                "startMs": start_ms,
                                "endMs": start_ms + duration_ms,
                            }
                        )
            sentence_tracks.append((sentence_path, sentence_words, chapter_index, sentence_index))
            sentence_index += 1

    ffmpeg_command = ["ffmpeg", "-y"]
    filters: list[str] = []
    words: list[dict[str, int | str]] = []
    chapter_ranges = [
        {**chapter, "sentences": chapter["sentences"], "startMs": None, "endMs": None}
        for chapter in CHAPTERS
    ]
    cursor_ms = 0
    gap_ms = 145
    for index, (sentence_path, sentence_words, chapter_index, _) in enumerate(sentence_tracks):
        ffmpeg_command.extend(["-i", str(sentence_path)])
        first_ms = int(sentence_words[0]["startMs"])
        last_ms = int(sentence_words[-1]["endMs"])
        filters.append(
            f"[{index}:a]atrim=start={first_ms / 1000:.3f}:end={(last_ms + 80) / 1000:.3f},"
            f"asetpts=PTS-STARTPTS,apad=pad_dur={gap_ms / 1000:.3f}[s{index}]"
        )
        if chapter_ranges[chapter_index]["startMs"] is None:
            chapter_ranges[chapter_index]["startMs"] = cursor_ms
        for word in sentence_words:
            words.append(
                {
                    "text": word["text"],
                    "startMs": cursor_ms + int(word["startMs"]) - first_ms,
                    "endMs": cursor_ms + int(word["endMs"]) - first_ms,
                }
            )
        cursor_ms += last_ms - first_ms + 80 + gap_ms
        chapter_ranges[chapter_index]["endMs"] = cursor_ms

    filters.append(
        "".join(f"[s{i}]" for i in range(len(sentence_tracks)))
        + f"concat=n={len(sentence_tracks)}:v=0:a=1[out]"
    )
    narration_path = PUBLIC / "narration.mp3"
    ffmpeg_command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[out]",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "192k",
            str(narration_path),
        ]
    )
    subprocess.run(ffmpeg_command, check=True, capture_output=True)
    for sentence_path, _, _, _ in sentence_tracks:
        sentence_path.unlink(missing_ok=True)

    duration_ms = round(MP3(narration_path).info.length * 1_000)
    data = {
        "durationMs": duration_ms,
        "chapters": chapter_ranges,
        "words": words,
    }
    (PUBLIC / "data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    full_script = "\n\n".join(
        f"{chapter['title']}\n" + " ".join(chapter["sentences"]) for chapter in CHAPTERS
    )
    (OUTPUT / "narration_script.txt").write_text(full_script, encoding="utf-8")
    shutil.copy2(narration_path, OUTPUT / "narration_tr.mp3")
    print(json.dumps({"durationMs": duration_ms, "chapters": len(CHAPTERS), "words": len(words)}))


if __name__ == "__main__":
    asyncio.run(main())
