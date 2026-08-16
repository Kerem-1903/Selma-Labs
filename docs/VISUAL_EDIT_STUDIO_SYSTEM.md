# Strange Things Lab Visual Edit Studio

Durum: ücretsiz çekirdek etkin, otomatik kalite eşiği 90/100.

## Sistem artık ne yapıyor?

Her zaman kodlu anlatı bölümü için ayrı bir görsel kurgu kararı üretir:

- İzleyiciye verilen söz, yönlendirme, açıklama, kanıt ve ödül işlevi
- Kadraj ölçeği ve kamera hareketi
- Sert kesme veya sınırlı semantik geçiş
- Diyagram, çağrı etiketi, düzen değişimi ve final kartı gibi desen kırıcılar
- Dikey mobil kadraj ve altyazı/arayüz güvenli bölgesi
- Bir sonraki sahneyle kadraj ve hareket tekrarının önlenmesi

Efekt bütçesi kesmelerin en fazla yüzde 25'idir. İki efektli geçiş arka arkaya
gelemez. Varsayılan geçiş sert kesmedir; geçiş yalnızca anlatı işlevi değiştiğinde
kullanılır.

## Üretim zinciri

1. `VISUAL_EDIT_PLAN_V1`: Semantik sahne planını uygulanabilir kurgu gramerine çevirir.
2. `VISION_SEARCH`: Her beat için kaynak, lisans, çözünürlük ve görsel uygunluk kanıtı toplar.
3. `EDITORIAL_RHYTHM_V1`: Kesme zamanlarını, düşük hareketli beklemeleri ve açıklama istisnalarını denetler.
4. `RENDER`: Planlanan kadraj ve hareketi FFmpeg veya Remotion ile uygular.
5. `VISUAL_QUALITY_V1`: Plan dosyasını değil, çıkan MP4'ü de ölçer.
6. `UPLOAD_PACKAGE`: Görsel kalite 90/90 otomatik puana ulaşmadan yayın paketi oluşturmaz.

## 90 otomatik puan

| Kontrol | Puan | Engelleyici |
|---|---:|:---:|
| Storyboard ve kaynak kapsamı | 8 | Evet |
| İlk 1,3 saniyede görsel söz | 10 | Evet |
| Semantik görsel görevleri | 10 | Evet |
| Lisans, kaynak ve atıf kanıtı | 8 | Evet |
| Yerel kaynak çözünürlüğü | 8 | Evet |
| Kaynak ve algısal çeşitlilik | 10 | Evet |
| Bilgi değişimi ritmi | 10 | Evet |
| Renderda ölçülen kesme/durağanlık | 12 | Evet |
| Kadraj, hareket ve geçiş grameri | 8 | Hayır |
| Açıklama grafiği ve mobil güvenli bölge | 6 | Evet |

Kalan 10 puan insan estetik incelemesidir: kadrajın gerçekten güzel olması,
görsel metaforun yaratıcı olması, duygusal akış ve kanal zevki. Otomasyon 90/100
olmadan geçemez; “stüdyo onayı” için insan estetik notunun en az 8/10 olması gerekir.

## Render sonrası gerçek ölçümler

- Açılışta siyah kare
- Toplam siyah kare süresi
- Donmuş görüntü
- Algılanan sahne değişim zamanları
- Ortalama plan süresi
- En uzun görsel durağanlık
- Planlanan kesme sayısı ile ölçülen değişimlerin karşılaştırılması
- Ses ve görüntü teknik teslim ayarları

Birbirine çok benzeyen iki görüntü arasındaki sert kesme sahne algılayıcı tarafından
kaçırılabilir. Bu nedenle kesme sayısı, durağanlık ve bağımsız donmuş-kare taraması
birlikte değerlendirilir; tek bir zayıf sinyale güvenilmez.

## Şu anda ücretsiz ve etkin

- FFmpeg: tek geçişli 1080x1920 kurgu, hareketli crop, altyazı/etiket ve post-render analiz
- Remotion: semantik sahne sözleşmesi, diyagram, çağrı etiketi, marka ve hareket katmanları
- Pexels: lisans ve kaynak URL'si saklanan ücretsiz video havuzu
- Yerel onaylı görsel manifesti: internet servisi olmadan lisanslı kaynakla üretim
- Algısal hash: aynı veya kozmetik olarak kırpılmış görüntüyü yeniden kullanmayı engelleme

Pexels lisansı ücretsiz kişisel ve ticari kullanıma, düzenlemeye ve YouTube kullanımına
izin verir. Sistem yine de her varlık için lisans, atıf ve kaynak URL'si kaydeder.

## Ücretsiz fakat henüz adaptörü olmayan seçenekler

- Pixabay ve Unsplash: lisansları klip bazında doğrulanarak ikinci kaynak havuzu olabilir.
- Wikimedia Commons ve NASA arşivleri: yalnızca varlık sayfasındaki özgül lisans/atıf
  koşulları kayda alınırsa kullanılmalıdır.
- Blender: özel 3B açıklama ve ürün/mekanizma animasyonları için yerel üretim.
- OpenStreetMap/MapLibre: atıf şartı korunarak harita ve rota anlatımları.

Bu kaynaklar otomatik olarak “telifsiz” kabul edilmez; sağlayıcı adaptörü ve lisans
kanıt zinciri tamamlanmadan yayın yoluna eklenmez.

## Ücretli gelecek planı — şu anda kapalı

14 Ağustos 2026 itibarıyla değerlendirilen öncelik sırası:

1. Envato Core: yıllık faturalamada ayda 16,50 USD veya aylık 39 USD. Stok video,
   motion template, grafik, font, müzik ve SFX'i tek lisans akışında topladığı için ilk
   ücretli yatırım adayıdır. Her proje için varlık kaydı tutulmalıdır.
2. Canva Pro: yıllık 144 USD. Kapak, hızlı infografik, marka kiti ve ekip içi görsel
   üretim için uygundur; ana video kurgu motorunun yerine geçmez.
3. Adobe Stock: ayda 29,99 USD başlangıç planında bir video/ay eşdeğeri. Nadir ve çok
   spesifik “hero shot” gerektiğinde sınırlı satın alma için uygundur.
4. Storyblocks/Artgrid: daha yüksek hacimli stok ihtiyacı oluştuğunda katalog ve
   kanal/yayın lisansı satın alma gününde yeniden karşılaştırılmalıdır.
5. Ücretli üretken video: yalnızca stokta bulunmayan bilimsel/soyut sahnelerde,
   tutarlılık ve ticari kullanım şartları klip bazında kanıtlanarak eklenmelidir.

Ücretli sağlayıcıların hiçbiri şu anda çağrılmaz; API anahtarı, abonelik veya deneme
başlatılmaz.

## Referans kanıtı

- Video: `output/visual_edit_reference.mp4`
- Kare inceleme sayfası: `output/visual_edit_reference_contact_sheet.jpg`
- Makine raporu: `output/visual_edit_reference_report.json`
- Tekrar üretme: `.venv/Scripts/python.exe scripts/build_visual_edit_reference.py`

Referans sonuç: 9 planlı kesmenin 9'u algılandı, en uzun algılanan görsel durağanlık
4,2666 saniye, otomatik görsel kalite 90/90 ve yayın kapısı geçti.
