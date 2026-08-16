from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import edge_tts
from mutagen.mp3 import MP3


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "motion" / "public" / "hidden-designs-45"
OUTPUT = ROOT / "output" / "hidden-designs-45"


ITEMS = [
    ("Diş fırçasındaki mavi kıllar", "🪥", "Rengi solduğunda değişim zamanı", ["Bazı diş fırçalarındaki mavi gösterge kılları kullandıkça renk kaybeder.", "Renk belirgin biçimde solduğunda üretici size fırçayı yenileme zamanının yaklaştığını anlatır."]),
    ("Alışveriş arabasındaki halkalar", "🛒", "Hassas ürünleri ezilmekten korur", ["Alışveriş arabasının üst kenarındaki küçük halkalar süs değildir.", "Ekmek veya yumurta gibi ezilmesini istemediğiniz poşetleri buraya asarak ağır ürünlerden uzak tutabilirsiniz."]),
    ("Kutu içecek açacağı", "🥤", "Pipeti yerinde tutabilir", ["İçecek kutusunun açma halkasını deliğin üzerine çevirdiğinizde ikinci delik pipet için küçük bir yuva olur.", "Bu her kutuda kusursuz çalışmaz ama pipetin yüzmesini ciddi biçimde azaltabilir."]),
    ("Mezuranın metal ucundaki yarık", "📏", "Çiviye tutunur", ["Mezuranın ucundaki yarık bir çiviye veya vida başına takılmak için tasarlanmıştır.", "Böylece tek başınızayken şeridi sabitleyip daha rahat ölçüm yapabilirsiniz."]),
    ("Şişeyi açmanın acil yolu", "🍾", "Her sert kenar güvenli değildir", ["Referans videoda şişe kapağını sert bir kenarla açma yöntemi gösteriliyor.", "Fakat camı kırma ve yaralanma riski nedeniyle en güvenli çözüm hâlâ gerçek bir şişe açacağı kullanmak."]),
    ("Alüminyum folyo ve makas", "✂️", "Geçici iyileşme, gerçek bileme değil", ["Katlanmış alüminyum folyo kesmek makas ağzındaki küçük çapakları bir miktar düzeltebilir.", "Ama bu gerçek bir bileme işlemi değildir; çok körelmiş makasın doğru şekilde bilenmesi gerekir."]),
    ("Madeni paraların tırtıklı kenarı", "🪙", "Değerli metalin törpülenmesini belli ederdi", ["Eski altın ve gümüş paralardan kenar boyunca metal kazımak ciddi bir sahtekârlıktı.", "Tırtıklı kenarlar paranın çevresinin bozulduğunu hemen görünür hâle getirdi; bugünse gelenek ve ayırt etme işlevi taşıyor."]),
    ("Bozuk parayla lastik kontrolü", "🚗", "Yalnızca hızlı bir ön kontroldür", ["Bazı ülkelerde belirli bir bozuk parayla lastik diş derinliği kabaca kontrol edilir.", "Para birimi ve ölçü değiştiği için bunu kesin test saymayın; yasal sınır için bir diş derinliği ölçer kullanın."]),
    ("Yeni kıyafetin kumaş parçası", "👕", "Yama değil, yıkama deneyi", ["Yeni kıyafetle gelen küçük kumaş parçası çoğu zaman yama olsun diye verilmez.", "Deterjanın rengi soldurup soldurmadığını veya kumaşın çekip çekmediğini önce bu parçada deneyebilirsiniz."]),
    ("Spor ayakkabının yan delikleri", "👟", "Ek bağcık noktası ve havalandırma", ["Bazı kanvas spor ayakkabılardaki yan delikler hem hava dolaşımına yardım eder hem de bağcık geçirilebilir.", "Bağcığı buradan geçirmek ayağı daha sıkı tutabilir; fakat her ayak için daha rahat olacağı garanti değil."]),
    ("Kâğıttaki kenar boşlukları", "📄", "Yazıyı kenardan korur", ["Kenar boşluklarının farelerden kalan tarihî bir alışkanlık olduğu sık anlatılır, fakat bu hikâye kesin kanıtlanmış değil.", "Bugünkü gerçek yararı daha açık: metni kesilme, ciltleme ve not alanından uzak tutmak."]),
    ("Mavi ve kırmızı silgi", "🧽", "İki farklı sertlik", ["Çift renkli silginin kırmızı tarafı normal kâğıttaki kurşun kalem izleri için daha yumuşaktır.", "Mavi taraf daha aşındırıcıdır; kalın kâğıtta inatçı izi yüzeyden kazır ama ince sayfayı da yırtabilir."]),
    ("Sos kabındaki kıvrımlar", "🍟", "Açılınca genişler", ["Fast food restoranlarındaki kıvrımlı küçük sos kabını kenarlara doğru açabilirsiniz.", "Kâğıt kap yayılıp geniş bir tabağa dönüşür ve patatesi sosa batırmak çok daha kolay olur."]),
    ("Paket servis kutusu", "🥡", "Katları açılınca tabak olur", ["Klasik Amerikan tipi paket servis kutularının yapıştırılmamış modelleri açılarak düz bir tabağa dönüşebilir.", "Ama tel saplı veya sızdırmaz biçimde yapıştırılmış kutuları zorlamak masayı bir anda yemeğe boyayabilir."]),
    ("Maket bıçağının arka kapağı", "🔪", "Körelmiş ucu güvenli kırma aparatı", ["Bazı maket bıçaklarının arka kapağı çıkar ve körelmiş bölümü tutan bir aparata dönüşür.", "Bıçağın çizgili ucunu burada kırınca sıradaki keskin parça ortaya çıkar; gözlük ve üretici talimatı şart."]),
    ("Kalem kapağındaki delik", "🖊️", "Kazara yutulmaya karşı hava geçişi", ["Birçok kalem kapağının tepesindeki delik mürekkebi kurutmak için değildir.", "Kapak kazara boğaza kaçarsa hava geçişine yardım etmek üzere eklenmiştir; riski yok etmez ama güvenliği artırır."]),
    ("Gömleğin arkasındaki halka", "👔", "Askısız asmak için", ["Gömlek yakasının arkasındaki küçük halkaya locker loop denir.", "Denizcilerin ve öğrencilerin gömleği askı olmadan kancaya asmasına yarıyordu; bugün çoğunlukla tasarım geleneği."]),
    ("Zımbanın dönen metal tablası", "📎", "Geçici zımba yapabilir", ["Bazı zımbaların altındaki metal plakayı yüz seksen derece çevirebilirsiniz.", "Diğer konumda zımba ayakları dışa doğru kıvrılır ve kâğıttan daha kolay sökülen geçici bir bağlantı oluşur."]),
    ("Paket bardak kapağı", "☕", "Bardak altlığına dönüşür", ["Plastik içecek kapağının ortasındaki halka çoğu zaman bardağın tabanına uyacak ölçüdedir.", "Kapağı masaya koyup bardağı üstüne oturtursanız damlayan yoğuşmayı yakalayan küçük bir altlık elde edersiniz."]),
    ("Tava sapındaki delik", "🍳", "Kaşığı tutabilir", ["Tava sapındaki büyük delik yalnızca tavayı duvara asmak için kullanılmaz.", "Karıştırma kaşığının sapını buraya yerleştirince kaşığın kirli ucu tavanın üzerinde kalır ve tezgâh daha temiz olur."]),
    ("Makarna kaşığındaki delik", "🍝", "Bazı modellerde bir porsiyon ölçüsü", ["Bazı spagetti kaşıklarının ortasındaki delik yaklaşık tek kişilik kuru makarna ölçmek üzere boyutlandırılır.", "Fakat standart değildir; iştahınız ve kaşığın üreticisi sonucu epey değiştirebilir."]),
    ("Buzdolabının yön değiştiren kapısı", "🧊", "Menteşe diğer tarafa alınabilir", ["Birçok buzdolabının üst ve alt köşelerindeki plastik kapaklar kullanılmayan menteşe yuvalarını saklar.", "Model destekliyorsa kapının açılma yönü mutfağın düzenine göre tersine çevrilebilir."]),
    ("Otomobil koltuk başlığı", "💺", "Her araçta cam kırma aracı değildir", ["Çıkarılabilen başlığın metal ayaklarıyla yan cam kırılabileceği sık söylenir.", "Bu yöntem her araçta ve lamine camda çalışmaz; kemer kesicili gerçek bir acil durum çekici çok daha güvenilirdir."]),
    ("Telefon kamerasının yanındaki nokta", "📱", "Ek mikrofon", ["Bazı telefonlarda kamera ve flaşın yanındaki minicik nokta üçüncü mikrofondur.", "Video kaydında sesi iyileştirmek ve görüşme sırasında çevre gürültüsünü azaltmak için diğer mikrofonlarla birlikte çalışır."]),
    ("Asma kilidin altındaki delik", "🔒", "Su tahliyesi ve bakım noktası", ["Asma kilidin altındaki küçücük delik yağmur suyunun içeride birikmeden dışarı çıkmasını sağlar.", "Bazı modellerde kilit mekanizmasına uygun yağlayıcıyı uygulamak için de aynı açıklık kullanılır."]),
    ("Yakıt göstergesindeki ok", "⛽", "Depo kapağının tarafını gösterir", ["Gösterge panelindeki pompa simgesinin yanında küçük bir üçgen varsa yönüne bakın.", "Üçgen hangi tarafı gösteriyorsa yakıt kapağı genellikle o taraftadır; kiralık araçta utanç turunu önler."]),
    ("Bidonun üç sapı", "🛢️", "Bir veya iki kişi için dengeli taşıma", ["Klasik askerî tip yakıt bidonlarındaki üç paralel sap bilinçli bir tasarımdır.", "Ortadaki sap tek kişi içindir; iki kişi yan saplardan tutabilir, boş bidonlar da yan yana daha rahat taşınır."]),
    ("Sıvı bidonundaki hava deliği", "🫗", "Kesik kesik akışı azaltır", ["Bazı sıvı bidonlarında ana ağızdan ayrı küçük bir havalandırma kapağı bulunur.", "Açıldığında içeri hava girer, sıvı glug glug diye sıçramak yerine daha düzenli akar."]),
    ("Sedir ağacından askı", "🧥", "Koku ve güveye karşı doğal destek", ["Kaliteli ahşap askılarda sedir kullanılmasının nedeni yalnızca güzel görünmesi değil.", "Sedirin kokulu yağları bazı böcekleri uzaklaştırmaya yardımcı olur; etkisi azaldığında yüzeyi hafifçe zımparalamak kokuyu yenileyebilir."]),
    ("Kadın giysilerindeki ters düğmeler", "🧵", "Tarihî giydirme geleneği", ["Kadın ve erkek giysilerinde düğmelerin farklı tarafta olması için tek ve kesin bir kanıt yok.", "En yaygın açıklama, varlıklı kadınları sağ elini kullanan hizmetçilerin giydirmesine uygun tasarımın zamanla geleneğe dönüşmesi."]),
    ("F ve J tuşlarındaki kabartı", "⌨️", "İşaret parmaklarının pusulası", ["Klavyedeki F ve J tuşlarına bakmadan dokunduğunuzda küçük kabartıları hissedersiniz.", "Sol ve sağ işaret parmağını ana sıraya yerleştirir; diğer parmaklar da doğru tuşları otomatik bulur."]),
    ("Heinz şişesindeki 57", "🍅", "Şişenin vurulacak noktası", ["Klasik cam Heinz şişesinin boynundaki kabartmalı elli yedi yalnızca marka süsü değildir.", "Şişeyi ters tutup tam bu noktaya hafifçe vurmak koyu ketçabın akışını başlatabilir."]),
    ("Ketçap paketindeki küçük sayı", "🔢", "Üretim hattını izler", ["Tek kullanımlık sos paketlerinin köşesindeki küçük sayı gizli bir lezzet kodu değildir.", "Üreticinin hangi dolum veya paketleme hattının ürünü hazırladığını takip etmesine yarayan kalite kontrol işaretidir."]),
    ("Diş macunu tüpündeki renkli blok", "🎨", "Kesme ve katlama işareti", ["Diş macunu tüpünün ucundaki renkli dikdörtgen içeriğin doğal veya kimyasal olduğunu anlatmaz.", "Paketleme makinesinin tüpü nerede keseceğini ve katlayacağını optik sensörle görmesini sağlayan kayıt işaretidir."]),
    ("Toblerone üçgenleri", "🍫", "İçe doğru bastırarak kırılır", ["Toblerone parçasını dışarı çekerek koparmaya çalışmak gereksiz güç ister.", "Uçtaki üçgeni yanındaki parçaya doğru bastırınca dar taban kolayca kırılır ve tek parça temiz biçimde ayrılır."]),
    ("Üç renkli diş macunu", "🦷", "İşlevden çok görsel anlatım", ["Kırmızı, beyaz ve mavi şeritler çoğu zaman ayrı ayrı çalışmaya başlamaz.", "Üretici aynı macundaki özellikleri gözle görünür kılmak için renkleri ayırır; tek renkli ürün de benzer bileşenler taşıyabilir."]),
    ("Diş macunuyla metal parlatma", "🥄", "Hafif aşındırıcı yüzeyi temizler", ["Jel olmayan beyaz diş macunundaki hafif aşındırıcılar bazı metal yüzeylerdeki matlığı azaltabilir.", "Önce görünmeyen yerde deneyin; kaplamalı, antika veya değerli parçalarda profesyonel ürün kullanmak daha güvenli."]),
    ("Meyve suyu kutusunun kanatları", "🧃", "Küçük eller için tutacak", ["Meyve suyu kutusunun üstündeki katlı yan kanatları dışarı açabilirsiniz.", "Çocuk kutuyu gövdesinden sıkmak yerine bu kulaklardan tutarsa pipetten istemsiz meyve suyu fışkırma ihtimali azalır."]),
    ("Fırının alt çekmecesi", "♨️", "Modeline göre ısıtıcı veya depolama", ["Fırının altındaki çekmece her cihazda aynı işe sahip değildir.", "Bazı modellerde yemekleri sıcak tutan ısıtma çekmecesi, bazılarında broyler, bazılarındaysa yalnızca depodur; doğru cevap kullanım kılavuzunda."]),
    ("Tic Tac kapağındaki çıkıntı", "🍬", "Tek şekerlik mini hazne", ["Tic Tac kutusunun kapağındaki küçük şekilli oyuk bir taneyi yakalayacak büyüklüktedir.", "Kutuyu ters çevirip yavaşça açarsanız avucunuza bir avuç değil, kapağa tek bir şeker düşer."]),
    ("Birleşen Birleşik Krallık paraları", "🇬🇧", "Arka yüzler tek bir kalkan oluşturur", ["Birleşik Krallık'ın iki bin sekiz tasarımlı bazı madeni paralarını doğru düzende yan yana koyun.", "Bir penny'den elli pence'e kadar arka yüzlerdeki parçalar birleşerek Kraliyet Arması'nın büyük kalkanını oluşturur."]),
    ("Maşayla limon sıkmak", "🍋", "Kaldıraç gücü", ["Mutfak maşasının iki sapı limon sıkacağı gibi kullanılabilir.", "Yarım limonu sapların arasına koyup kontrollü sıktığınızda kaldıraç etkisi elinizden daha fazla meyve suyu çıkarır."]),
    ("Tel tokayı doğru takmak", "💇", "Dalgalı taraf saç derisine bakar", ["Tel tokanın dalgalı yüzü dekor olsun diye yapılmaz ve çoğu kişi onu dışarı çevirir.", "Dalgalı taraf saç derisine baktığında saçı kavrar; düz yüzey dışta kalır ve toka daha az kayar."]),
    ("McFlurry kaşığındaki kare boşluk", "🍨", "Karıştırma makinesine bağlanır", ["McFlurry kaşığının kalın ve kare biçimli sapı pipet değildir.", "Servis hazırlanırken makinenin miline takılır; kaşık karıştırıcı uç görevi görür ve ardından doğrudan müşteriye verilir."]),
    ("Mezuranın hareketli metal ucu", "📐", "İç ve dış ölçü farkını dengeler", ["Mezuranın metal ucunun hafifçe oynaması arıza değildir.", "Kancayla dıştan çekerken veya bir yüzeye içten iterken kendi kalınlığı kadar yer değiştirerek iki ölçümü de doğru tutar."]),
]


CHAPTERS = [
    {"id": "intro", "title": "Günlük nesnelerin 45 gizli amacı", "icon": "✨", "fact": "Gördüğün hiçbir ayrıntı tesadüf olmayabilir", "sentences": ["Etrafınıza bakın; evinizde bile fark etmediğiniz onlarca küçük tasarım sırrı var.", "Şimdi kırk beş günlük nesneyi, hızlı ve açık biçimde çözüyoruz; sonuncuya kadar kaç tanesini bildiğinizi sayın."]},
    *[
        {"id": f"item-{index + 1:02d}", "title": title, "icon": icon, "fact": fact, "sentences": sentences}
        for index, (title, icon, fact, sentences) in enumerate(ITEMS)
    ],
    {"id": "outro", "title": "Kaç tanesini biliyordun?", "icon": "💬", "fact": "Yorumlara sayını yaz", "sentences": ["Kırk beş nesnenin sonuna geldik.", "Kaç tanesini önceden biliyordunuz ve ikinci bölümde hangi günlük eşyayı inceleyelim? Yorumlara yazın."]},
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
                rate="+14%",
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
    words: list[dict[str, int | str]] = []
    ranges = [{**chapter, "startMs": None, "endMs": None} for chapter in CHAPTERS]
    cursor_ms = 0
    gap_ms = 120
    for index, (path, boundaries, chapter_index) in enumerate(tracks):
        command.extend(["-i", str(path)])
        first_ms = int(boundaries[0]["startMs"])
        last_ms = int(boundaries[-1]["endMs"])
        filters.append(f"[{index}:a]atrim=start={first_ms / 1000:.3f}:end={(last_ms + 90) / 1000:.3f},asetpts=PTS-STARTPTS,apad=pad_dur={gap_ms / 1000:.3f}[s{index}]")
        if ranges[chapter_index]["startMs"] is None:
            ranges[chapter_index]["startMs"] = cursor_ms
        for word in boundaries:
            words.append({"text": word["text"], "startMs": cursor_ms + int(word["startMs"]) - first_ms, "endMs": cursor_ms + int(word["endMs"]) - first_ms})
        cursor_ms += last_ms - first_ms + 90 + gap_ms
        ranges[chapter_index]["endMs"] = cursor_ms
    filters.append("".join(f"[s{i}]" for i in range(len(tracks))) + f"concat=n={len(tracks)}:v=0:a=1[out]")
    narration = PUBLIC / "narration.mp3"
    command.extend(["-filter_complex", ";".join(filters), "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k", str(narration)])
    subprocess.run(command, check=True, capture_output=True)
    for path, _, _ in tracks:
        path.unlink(missing_ok=True)

    duration_ms = round(MP3(narration).info.length * 1000)
    data = {"durationMs": duration_ms, "chapters": ranges, "words": words}
    (PUBLIC / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    full_script = "\n\n".join(f"{chapter['title']}\n" + " ".join(chapter["sentences"]) for chapter in CHAPTERS)
    (OUTPUT / "narration_script.txt").write_text(full_script, encoding="utf-8")
    shutil.copy2(narration, OUTPUT / "narration_tr.mp3")
    print(json.dumps({"durationMs": duration_ms, "minutes": round(duration_ms / 60000, 2), "chapters": len(CHAPTERS), "items": len(ITEMS), "words": len(words)}))


if __name__ == "__main__":
    asyncio.run(main())
