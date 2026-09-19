# Kaito v1 — Üretim Öncesi Kabul Listesi

Kaito için kaynak brief kilitlidir. Brief değişirse hash kilidi eşleşmez ve CLI üretimi başlatmaz.

> Bu doküman operatör talimatıdır; makine tarafındaki tek doğru kaynak
> [`config/character_acceptance/kaito-v1.json`](../config/character_acceptance/kaito-v1.json)
> dosyasıdır. İkisi arasındaki madde listesi bir testle eşitlenir
> (`tests/unit/test_character_acceptance.py`), böylece biri güncellenip diğeri
> unutulamaz.

## Sabit kimlik ayrıntıları

- Tek karakter, tek beden ve tek kafa.
- Kısa siyah saçta tam olarak bir adet `#0047AB` kobalt çizgi.
- Çizgi karakterin solundadır; ön görünüşte izleyicinin sağına düşer.
- Çanta karakterin sağ kalçasındadır; askı karakterin sol omzundan geçer.
- Asimetrik ayrıntılar sağ/sol görünüşlerde aynalanmaz.

## İnsan onayı

Yedi görünüş temas sayfasında birlikte incelenir. Aşağıdaki on iki maddenin
tamamı imzalanmadan `approve-view-pack` çalıştırılmaz.

| # | Madde id | Ne onaylanır |
|---|---|---|
| 1 | `same_facial_identity` | Yedi görünüşte aynı yüz kimliği |
| 2 | `hair_black_single_cobalt_streak` | Kısa siyah saçta tam olarak bir dar kobalt çizgi |
| 3 | `streak_character_left_never_mirrored` | Çizgi karakterin solunda kalır, asla aynalanmaz |
| 4 | `bag_character_right_never_mirrored` | Çanta karakterin sağ kalçasında kalır, asla aynalanmaz |
| 5 | `outfit_layers_consistent` | Kömür ceket, mavi biye, siyah pantolon ve botlar tutarlı |
| 6 | `body_proportions_consistent` | Vücut oranı ve giysi katmanları tutarlı |
| 7 | `style_line_and_shading_consistent` | Temiz anime çizgi ve ölçülü iki kademeli gölge yedi görünüşte tutarlı |
| 8 | `palette_and_materials_consistent` | Kömür/siyah/kırık gri ve sınırlı kobalt paleti tutarlı |
| 9 | `neutral_studio_background_consistent` | Yumuşak mavi-gri gradyanlı nötr stüdyo arka planı ve nötr ışık tutarlı; sokak veya dramatik ışık yok |
| 10 | `single_person_no_collage_no_text` | Fazladan kişi, çift beden, kolaj, yazı veya filigran yok |
| 11 | `back_view_no_face` | Arka görünüşte görünür yüz veya arkaya bakış yok |
| 12 | `profile_views_are_true_side_views` | İki profil de gerçek yan görünüş (tek göz hattı, burun siluette, uzak yanak görünmez); üç-çeyrek değil |

## İmzalı kabul (zorunlu)

`approve-view-pack` kabul listesini **zorunlu** uygular:

1. Kabul dosyası bulunmadan onay reddedilir.
2. Kabul dosyası **tek bir karakter sürümünü** yönetir: `character_version`
   incelenen paketin sürümüyle birebir eşleşmelidir. Varsayılan dosya adı
   `<character>-v<version>.json`; uyuşmazlıkta hata iki sürümü de adıyla söyler.
3. Kabul dosyasının `brief_hash` değeri görünüş paketinin brief hash'iyle
   eşleşmelidir.
4. Listedeki **her insan maddesi** ayrı bir `--check <id>` bayrağıyla açıkça
   imzalanmalıdır; eksik madde onayı reddeder.
5. `required_evidence` listesindeki kanıt dosyaları (kök altında) mevcut
   olmalıdır.

Kullanım:

```bash
python -m cli.main character approve-view-pack \
  --character kaito --version v1 --approved-by LOQ \
  --acceptance config/character_acceptance/kaito-v1.json \
  --check same_facial_identity \
  --check hair_black_single_cobalt_streak \
  --check streak_character_left_never_mirrored \
  --check bag_character_right_never_mirrored \
  --check outfit_layers_consistent \
  --check body_proportions_consistent \
  --check style_line_and_shading_consistent \
  --check palette_and_materials_consistent \
  --check neutral_studio_background_consistent \
  --check single_person_no_collage_no_text \
  --check back_view_no_face \
  --check profile_views_are_true_side_views
```

Onay makbuzu (`view-pack-approval.json`) görünüş hash'lerine ek olarak şunları içerir:

- `acceptance_sha256` — onayda kullanılan kabul dosyasının birebir SHA-256 özeti
- `human_checks` — imzalanan her maddenin `id` + `label` çifti
- `verified_evidence` — doğrulanmış kanıt dosyası yolları

## Zorunlu kanıt dosyaları

`approve-view-pack` aşağıdaki dosyaların tamamını kök altında arar; biri eksikse
onay reddedilir:

| Kanıt | Ne kanıtlar |
|---|---|
| `canonical-approval.json` | Kilitlenen kanonik görselin insan imzası |
| `drift-report.json` | Kaynaktan sapmanın ölçülmüş, yeniden üretilebilir kaydı |
| `face_anchor.png` | Yüz kimliği anchor'ı |
| `fullbody_anchor.png` | Tam vücut anchor'ı |
| `view-pack.json` | Yedi görünüşlük paket manifesti ve QC kanıtı |
| `contact-sheets/views.png` | Yedi görünüşün birlikte temas sayfası |
| `view-pack-approval.json` | Yazan onay makbuzunun kendisi |
| `manifest.json` | Üretim satır bilgisi; her görselin seed ve hash kaydı |

## `drift-report.json` — zorunlu kanıt

Paket üretilirken kaynak görüntü ile her görünüş arasındaki fark ölçülür ve
`drift-report.json` kilitli varlık olarak yazılır. Rapor **danışma niteliğindedir**;
hiçbir görünüşü tek başına onaylamaz veya reddetmez. Amacı insanı tek bir ölçülebilir
farklılığa yönlendirmektir: aksesuar ölçeği/rengi ve imza çizgisinin kaybolması ya da
aynalanması.

Rapor hangi eşik bandının kullanıldığını ve bandın hangi byte'lardan geldiğini
(`threshold_source.path` + `threshold_source.sha256`) kaydeder. Kalibre edilmiş bant
`config/character_acceptance/kaito-drift-thresholds-v1.json` dosyasındadır ve yol
ayarlarla verilir; dosya eksik veya bozuksa üretim varsayılanlara sessizce düşmez,
fail-closed durur. İşaret eşikleri bilinçli olarak kalibre edilmemiştir — referans
paket çizginin kaybedildiği yerdir, oradan kalibre etmek kusuru sabitlerdi.

Rapor **yalnızca çizilen görünüşleri** ölçer. `front.png` ve `face-closeup.png`
onaylı varlıkların sözleşme kopyalarıdır, model çıktısı değildir: front kaynağın
birebir kendisidir (kendisiyle karşılaştırmak ölçüm değildir) ve face-closeup bir
kafa kırpmasıdır (kırpılmış bir kafayı tam gövde kaynakla karşılaştırmak elmayla
armut). İkisini ölçmek, byte'ların destekleyemediği bir alarm üretir; v6 paketi
tam olarak bunu yaşadı — onaylı `face_anchor.png` kendi byte'ları üzerinden
`signature_mark_missing_or_hidden` diye işaretlendi.

Her görünüş kaydı bir de `mark_measurable` alanı taşır. `false` ise işaret
metrikleri **hiç uygulanmadı**: kaynağın kafa bölgesinde oranın anlam taşıyacağı
kadar aksan pikseli yok, gürültü baskın. Kaito'nun kanonik görselinde ölçülen kafa
aksan yoğunluğu `4,1e-05` — yani 3. kabul maddesi (çizginin karakterin solunda
kalması) bu çözünürlükte **otomatik olarak doğrulanamaz** ve insan kararı olarak
kalır. "Ölçüldü ve temiz" ile "ölçülmedi" ayrımı raporda görünür durumdadır.

## Tuval politikası

Kaynak-güdümlü (FLUX.2) diyalektin sözleşmesi "yalnızca bakış açısını değiştir"
dir. Üretim bu yüzden tuvali kaynağın kendi en-boy oranından türetir
(`edit_canvas_for`, ~1 MP, 16'nın katına yuvarlanır) ve her istek
`canvas_policy: source_aspect` kaydeder. Kare bir kaynağı sabit 768×1152 portre
tuvale basmak sessizce ikinci bir değişiklik — yeniden çerçeveleme — ekler ve
yeniden çerçeveleme özne kutusunu, palet histogramını ve arka plan gradyanını
birlikte kaydırır; bu tam olarak turnuvada kaçınmaya çalıştığımız sürüklenmedir.
Poz-güdümlü (IP-Adapter) diyalekt kalibre edildiği portre tuvalde kalır.

## Geçiş koşulu

Poz üretimine yalnızca `canonical-approval.json`, iki anchor, QC geçmişi, temas
sayfası, `drift-report.json` ve `view-pack-approval.json` mevcutsa geçilir.
Poz üretimi bu onayı **kod tarafından** doğrular: `pose-pack generate` üretim
modunda görünüş paketi onay muhafızını çağırır ve makbuz yoksa render başlamaz.
Başarısız çıktılar üretim klasörüne alınmaz; kendi çalışma kimliği altındaki
karantinada kalır.

Otomatik maddeler (`automatic_checks`) üretim anında QC/framing kapılarınca
uygulanır; makbuz bunları görünüş paketinin QC kanıtı ve `manifest.json` satır
bilgisi üzerinden kayda geçirir.

## Sürüm bağı neden önemli

Kilitli bir görünüş zaten başka byte'lara yazılamaz: `save_locked_asset` mevcut
kilitli varlığın üzerine yazmayı reddeder. Yeni bir diyalektle (örneğin FLUX.2)
paketi yeniden üretmek bu yüzden **sürüm artışı** gerektirir; kabul listesi de o
sürüme bağlı olarak yazılır.
