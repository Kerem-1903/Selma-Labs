from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import edge_tts
from mutagen.mp3 import MP3


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "motion" / "public" / "earth-stop"
OUTPUT = ROOT / "output" / "earth-stop"

CHAPTERS = [
    {
        "id": "hook",
        "title": "Dünya sadece beş saniye dursa?",
        "sentences": [
            "Şu kırmızı düğmenin Dünya'yı yalnızca beş saniyeliğine durdurduğunu düşünün.",
            "Beş saniye kısa geliyor, değil mi? Ama daha ilk saniye bitmeden şehirlerin üzerinde sesten hızlı bir felaket başlayabilir.",
            "Çünkü Dünya dursa bile siz, hava ve okyanuslar durmayacaksınız.",
            "Önce oyunun kuralını netleştirelim: Gezegenin kendi ekseni etrafındaki dönüşü aniden duruyor, yer çekimi ve Güneş çevresindeki yörüngesi devam ediyor; beş saniye sonra dönüş yine aniden başlıyor.",
        ],
    },
    {
        "id": "speed",
        "title": "Şu anda ne kadar hızlı gidiyoruz?",
        "sentences": [
            "Hareketsiz oturuyor gibi görünseniz de Dünya sizi sürekli doğuya taşıyor.",
            "Ekvatorun çevresi yaklaşık kırk bin kilometre ve gezegen bunu bir günde tamamlıyor.",
            "Bu nedenle ekvatordaki bir insan saatte yaklaşık bin altı yüz yetmiş kilometre hızla hareket ediyor.",
            "Bu, deniz seviyesinde ses hızından daha yüksek.",
            "En ilginç kısmıysa bu hızın her yerde aynı olmaması. Ekvatora yakınken en yüksek, kutuplara gittikçe daha düşük; tam kutup noktasında neredeyse sıfır.",
            "Türkiye'nin enlemlerinde yüzey hızı kabaca saatte bin iki yüz ile bin üç yüz kilometre arasında.",
            "Bunu hissetmiyoruz, çünkü eviniz, atmosfer ve elinizdeki bardak sizinle aynı hızda hareket ediyor. Tıpkı sabit hızla giden bir uçağın içinde oturmak gibi.",
        ],
    },
    {
        "id": "first-second",
        "title": "İlk saniye",
        "sentences": [
            "Şimdi düğmeye basılıyor ve katı Dünya bir anda duruyor.",
            "Newton'un eylemsizlik ilkesi devreye giriyor: sabitlenmemiş her şey eski doğu yönündeki hızını korumaya çalışıyor.",
            "Siz uzaya fırlamazsınız; çünkü bu hız Dünya'nın kaçış hızından çok daha düşük ve yer çekimi hâlâ çalışıyor.",
            "Fakat yüzeye paralel biçimde doğuya savrulursunuz.",
            "Ekvator yakınında bu, sesten hızlı giden bir araçtan aniden dışarı atılmaya benzer.",
            "Binalar temelleriyle zemine bağlı oldukları için ilk darbeyi alır. Üst katlar hareketini sürdürmek isterken temel durur; yapılar dev bir depremdeymiş gibi zorlanır.",
            "Ağaçlar, araçlar, insanlar ve sabitlenmemiş nesneler doğuya doğru hareket eder. Ama sonuç yalnızca savrulmak değildir; asıl görünmeyen duvar birkaç saniye sonra gelir.",
        ],
    },
    {
        "id": "atmosphere",
        "title": "Atmosfer durmuyor",
        "sentences": [
            "Katı yüzey durduğunda atmosfer eski hızını korur.",
            "Ekvator çevresinde yere göre saatte binlerce kilometreye yaklaşan rüzgârlar ortaya çıkar.",
            "Bu, normal bir kasırgadan çok daha hızlı ve ses hızının üzerinde olabilir.",
            "Hava bir anda binalara, tepelere ve ormanlara çarpar. Basınç darbeleri camları parçalar, gevşek malzemeleri mermiye dönüştürür ve yüzeydeki enkazı doğuya taşır.",
            "Türkiye gibi orta enlemlerde hız ekvatordan düşük olsa bile hâlâ son derece yıkıcıdır.",
            "Dağların arkasında veya derin yer altında olmak ilk rüzgâr darbesini azaltabilir; fakat girişler, havalandırma sistemleri ve uçuşan enkaz yeni tehlikeler yaratır.",
            "Uçakta olmak da sihirli çözüm değildir. Uçak atmosferle birlikte hareket eder ama aniden değişen rüzgâr, basınç ve yerdeki kaos güvenli bir uçuş bırakmaz.",
        ],
    },
    {
        "id": "oceans",
        "title": "Okyanuslar hareket etmeye devam ediyor",
        "sentences": [
            "Okyanuslar da gezegenle birlikte doğuya hareket ediyordu ve katı kabuk durunca suyun momentumu kaybolmaz.",
            "Burada klasik bir deprem tsunamisinden daha karmaşık, küresel ölçekte bir su hareketi düşünmeliyiz.",
            "Su kıtalara ve okyanus havzalarının kenarlarına doğru yığılır; kıyılarda güçlü akıntılar ve ani su seviyesi değişimleri oluşur.",
            "Beş saniye, bütün okyanusun yeni bir dengeye ulaşması için yetmez. Ama ilk şok dalgalarını ve devasa akıntıları başlatmak için fazlasıyla yeterlidir.",
            "Üstelik atmosferin basınç darbesi su yüzeyini ayrıca iter.",
            "Kıyıya yakınsanız tek tehlike filmlerdeki kıvrılan dev dalga değildir. Gerçek tsunamiler çoğu zaman çok hızlı yükselen bir gelgit gibi karaya girer; güçlü akıntı ve taşıdığı enkaz büyük hasar verir.",
            "Açık denizdeki gemiler ilk anda kıyıdakilerden daha iyi durumda görünebilir, fakat okyanus havzasında başlayan düzensizlik ve hava koşulları onları da hızla yakalar.",
        ],
    },
    {
        "id": "latitude",
        "title": "Nerede olmak daha güvenli?",
        "sentences": [
            "Bu felaketin şiddeti enleme bağlıdır.",
            "Ekvator üzerinde bir nokta en büyük çemberi çizdiği için en hızlıdır. Altmış derece kuzey veya güneyde aynı noktanın günlük yolu yarıya iner; yüzey hızı da yaklaşık yarıya düşer.",
            "Tam coğrafi kutupta dönme ekseninin üzerindesiniz. Yatay hız neredeyse sıfır olduğu için savrulma etkisi en az orada olur.",
            "Bu, kutupların tamamen güvenli olduğu anlamına gelmez. Atmosfer ve okyanustaki küresel bozulma, iletişimin çökmesi ve ikmal sorunları devam eder.",
            "Yine de ilk beş saniyeyi yalnızca mekanik etki açısından değerlendirdiğimizde, kutba yakın sağlam ve yer altındaki bir yapı en iyi ihtimallerden biridir.",
            "Ekvatora yakın, kıyıda ve yüksek yapıların arasında olmaksa listenin en kötü tarafında.",
        ],
    },
    {
        "id": "weight-space",
        "title": "Yer çekimi ve uydular",
        "sentences": [
            "Dünya'nın dönmesi sizi uzaya savurmuyor; fakat merkezkaç etkisi ekvatorda ağırlığınızı çok az azaltıyor.",
            "Dönüş durduğunda yer çekimi kaybolmaz. Tam tersine, ekvatorda tartı üzerinde çok küçük bir miktar daha ağır görünürsünüz.",
            "Elbette etrafınızdaki yıkım düşünüldüğünde yarım kilodan bile küçük bu değişim listenin en önemsiz sorunu.",
            "Peki uydular? Çoğu uydu, Dünya'nın kendi ekseni etrafındaki dönüşünden bağımsız olarak yörüngesinde kalır.",
            "Ancak yer istasyonları, yönlendirme sistemleri ve iletişim altyapısı ağır hasar görür.",
            "Jeostasyoner uydular uzayda yaklaşık aynı yörüngede devam ederken altlarındaki yüzey bir süre durduğu için artık aynı noktanın üzerinde görünmezler.",
            "Navigasyonun ve iletişimin en çok gerektiği anda, sistemlerin yerdeki kısmı çalışmayabilir.",
        ],
    },
    {
        "id": "restart",
        "title": "Beşinci saniye: İkinci darbe",
        "sentences": [
            "Sayaç sıfıra geliyor. Hayatta kalanlar için iyi haber burada bitiyor; çünkü Dünya şimdi eski dönüş hızına aniden geri dönüyor.",
            "Bu kez zemin doğuya doğru hızlanırken, ilk darbede hareket eden hava, su ve enkazın hızı artık her yerde yüzeyle uyuşmuyor.",
            "Bir otomobilin duvara çarpıp ardından aynı şiddetle ters yönden darbe alması gibi, yapılar ikinci kez zorlanır.",
            "Atmosferin yeni yüzey hızıyla tekrar dengelenmesi zaman alır. Rüzgâr bir düğmeye basılmış gibi bir anda sakinleşmez.",
            "Okyanuslarda başlayan dalgalar da gezegen yeniden döndü diye kaybolmaz; havzalar boyunca yolculuk etmeyi sürdürür.",
            "Elektrik şebekeleri, limanlar, yollar, veri merkezleri ve yakıt hatları aynı anda hasar gördüğü için felaket beş saniyede bitmez.",
            "Düğme yalnızca beş saniye açık kalmıştır, ama etkileri günler, aylar ve bazı bölgelerde yıllar boyunca devam eder.",
        ],
    },
    {
        "id": "survival",
        "title": "Hayatta kalmak mümkün mü?",
        "sentences": [
            "Eğer bu imkânsız senaryoda bir yer seçme şansınız olsaydı, birkaç özellik arardınız.",
            "Kutuplara yakın, kıyıdan uzak, alçak nüfuslu ve sağlam kaya içine kurulmuş bir yer altı tesisi.",
            "Girişlerin doğrudan rüzgâra bakmaması, kendi elektriği, filtreli havası, suyu ve uzun süreli gıda stoğu olması gerekir.",
            "Metro tüneli ilk bakışta iyi fikir gibi görünür; ancak su baskını, elektrik kesintisi, yangın ve çöken girişler onu tuzağa çevirebilir.",
            "Denizaltı da yüzey rüzgârından korunur ama ani akıntılar, kıyı altyapısının kaybı ve iletişim kesintisiyle baş başa kalır.",
            "Kısacası tamamen güvenli bir yer yok. Sadece ilk şoktan kurtulma olasılığı diğerlerinden daha yüksek yerler var.",
        ],
    },
    {
        "id": "outro",
        "title": "Sonuç",
        "sentences": [
            "Beş saniye bize kısa gelir, çünkü insan ölçeğinde düşünürüz.",
            "Fakat kırk bin kilometrelik bir gezegenin dönüşünü aniden durdurduğunuzda, o beş saniyenin içine sesten hızlı rüzgârları, küresel su hareketini ve iki ayrı darbeyi sığdırırsınız.",
            "Neyse ki Dünya'nın dönüşünü böyle durdurabilecek gerçekçi bir düğme yok.",
            "Maskotumuz da düğmeyi kilitleyip anahtarı teslim ediyor.",
            "Peki sıradaki deney ne olsun: Ay bir anda yok olsun mu, yoksa Güneş beş saniyeliğine sönsün mü? Yorumlara yazın.",
        ],
    },
]


async def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    tracks: list[tuple[Path, list[dict[str, int | str]], int]] = []
    sentence_index = 0
    for chapter_index, chapter in enumerate(CHAPTERS):
        for sentence in chapter["sentences"]:
            path = PUBLIC / f"_sentence_{sentence_index:03d}.mp3"
            boundaries: list[dict[str, int | str]] = []
            communicator = edge_tts.Communicate(
                text=sentence,
                voice="tr-TR-EmelNeural",
                rate="+9%",
                pitch="+2Hz",
                volume="+0%",
                boundary="WordBoundary",
            )
            with path.open("wb") as audio_file:
                async for event in communicator.stream():
                    if event.get("type") == "audio":
                        audio_file.write(event["data"])
                    elif event.get("type") == "WordBoundary":
                        start_ms = round(int(event["offset"]) / 10_000)
                        duration_ms = max(70, round(int(event["duration"]) / 10_000))
                        boundaries.append({"text": str(event["text"]), "startMs": start_ms, "endMs": start_ms + duration_ms})
            tracks.append((path, boundaries, chapter_index))
            sentence_index += 1

    command = ["ffmpeg", "-y"]
    filters: list[str] = []
    captions: list[dict[str, int | float | str | None]] = []
    words: list[dict[str, int | str]] = []
    ranges = [{**chapter, "startMs": None, "endMs": None} for chapter in CHAPTERS]
    cursor_ms = 0
    gap_ms = 125
    for index, (path, boundaries, chapter_index) in enumerate(tracks):
        command.extend(["-i", str(path)])
        first_ms = int(boundaries[0]["startMs"])
        last_ms = int(boundaries[-1]["endMs"])
        filters.append(f"[{index}:a]atrim=start={first_ms/1000:.3f}:end={(last_ms+90)/1000:.3f},asetpts=PTS-STARTPTS,apad=pad_dur={gap_ms/1000:.3f}[s{index}]")
        if ranges[chapter_index]["startMs"] is None:
            ranges[chapter_index]["startMs"] = cursor_ms
        for word in boundaries:
            start = cursor_ms + int(word["startMs"]) - first_ms
            end = cursor_ms + int(word["endMs"]) - first_ms
            words.append({"text": word["text"], "startMs": start, "endMs": end})
            captions.append({"text": " " + str(word["text"]), "startMs": start, "endMs": end, "timestampMs": None, "confidence": None})
        cursor_ms += last_ms - first_ms + 90 + gap_ms
        ranges[chapter_index]["endMs"] = cursor_ms
    filters.append("".join(f"[s{i}]" for i in range(len(tracks))) + f"concat=n={len(tracks)}:v=0:a=1[out]")
    narration = PUBLIC / "narration.mp3"
    command.extend(["-filter_complex", ";".join(filters), "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k", str(narration)])
    subprocess.run(command, check=True, capture_output=True)
    for path, _, _ in tracks:
        path.unlink(missing_ok=True)
    duration_ms = round(MP3(narration).info.length * 1000)
    (PUBLIC / "data.json").write_text(json.dumps({"durationMs": duration_ms, "chapters": ranges, "words": words}, ensure_ascii=False, indent=2), encoding="utf-8")
    (PUBLIC / "captions.json").write_text(json.dumps(captions, ensure_ascii=False, indent=2), encoding="utf-8")
    script = "\n\n".join(f"{chapter['title']}\n" + " ".join(chapter["sentences"]) for chapter in CHAPTERS)
    (OUTPUT / "narration_script.txt").write_text(script, encoding="utf-8")
    shutil.copy2(narration, OUTPUT / "narration_emel.mp3")
    print(json.dumps({"durationMs": duration_ms, "minutes": round(duration_ms/60000, 2), "chapters": len(CHAPTERS), "words": len(words)}))


if __name__ == "__main__":
    asyncio.run(main())
