# SELMA Labs — Aşama 1 Animasyon Öncesi Kapanış Raporu

> **Kapsam düzeltmesi (14 Eylül 2026):** Aşama 1'in kesin bitiş noktası
> animation orchestrator'ın view-pack, pose-pack ve keyframe onay kapılarının
> açılmasıdır. Wan worker ve episode package Aşama 2 kapsamındadır. Daraltılmış,
> ölçülmüş ve uygulanabilir plan için
> [`PHASE_1_ORCHESTRATOR_UNLOCK_ROADMAP_TR.md`](PHASE_1_ORCHESTRATOR_UNLOCK_ROADMAP_TR.md)
> esas alınmalıdır. Bu raporun P8'e uzanan bölümleri sonraki roadmap için bağlam
> olarak korunmuştur.

**Tarih:** 14 Eylül 2026  
**Kapsam:** Animasyon üretimine başlamadan önce sistemin ve ilk yapım paketinin tamamlaması gereken işler  
**Önerilen Aşama 1 çıktısı:** Onaylı tek bir 60–90 saniyelik pilot sekans için `AnimationReadyPackage`

## 1. Yönetici özeti

SELMA Labs'ın kod ve yerel üretim altyapısı Aşama 1'i kapatmaya yakındır; ancak
"bir karakteri farklı açılarda üretebiliyoruz" ile "bir bölüm animasyona hazır"
aynı durum değildir.

14 Eylül 2026 doğrulamasında:

- Python testleri **1165/1165 geçti**.
- Remotion/TypeScript type-check geçti.
- Yerel görsel readiness kontrolü **17 PASS / 4 FAIL** verdi.
- FLUX.2 Klein 4B, Kaito'yu yerel RTX 4060 8 GB üzerinde yaklaşık 23 saniyede
  kaynak-güdümlü farklı açıya çevirebildi.
- Kaito için altı açılı tanı paketi üretildi; genel kimlik, silüet, stil ve ana
  asimetri korundu.
- Kaito v7'nin onaylı `view-pack-approval.json` makbuzu vardır; fakat pose pack'i
  yoktur ve Kaito'nun Character Bible/cast kaydı eksiktir.
- Seri stili hâlâ `PROVISIONAL`; `style-approval.json` ve
  `production-style-lock.json` yoktur.
- Bölüm 1 senaryosu `DRAFT` durumundadır. Animatic, onaylı screenplay, shot list,
  bölüm ses planı, keyframe paketi ve animation-ready episode root henüz yoktur.
- Gerçek Wan animasyon worker'ı bilinçli olarak bağlı değildir.

**Karar:** Şu anda GPU kiralamak Aşama 1'i kapatmaz. Önce yerelde görsel, hikâye,
poz, arka plan, keyframe, ses ve paketleme kapıları kapatılmalıdır. Kiralık GPU,
onaylı Aşama 1 paketini hareketlendirecek Aşama 2 girdisidir.

## 2. Aşama 1'in kesin tanımı

Aşama 1, ilk hareketli videoyu üretmek değil; animasyon modelinin artık yaratıcı
karar vermek zorunda kalmayacağı eksiksiz ve kilitli girdiyi üretmektir.

Aşama 1 bittiğinde her pilot çekimi için şunlar hazır olmalıdır:

```text
packages/<shot-id>/
  shot-contract.json
  start-keyframe.png
  end-keyframe.png
  background-clean.png
  character-mask.png
  dialogue.wav
  effects-spec.json
```

Bölüm/pilot kökünde ayrıca şunlar bulunmalıdır:

```text
approved-screenplay.json
continuity-state.json
shot-list.json
animatic.mp4
audio-plan.json
wan-render-manifest.json
licenses-and-consents.json
dialogue/
characters/
backgrounds/
keyframes/
approvals/
```

Animasyon sistemi bu paketten sonra yalnız hareket üretir. Kimlik, kıyafet,
mekân, kadraj, kamera yönü, çekim süresi, başlangıç/bitiş pozu ve diyalog zamanı
önceden kararlaştırılmış olur.

## 3. Mevcut durum ve kapanmamış kapılar

| Alan | Bugünkü durum | Aşama 1 kapanış şartı |
|---|---|---|
| Kod tabanı | 1165 test geçti | Aynı testler ve Remotion kontrolü yeşil kalmalı |
| FLUX turnaround | Yerelde çalışıyor; tanı paketi başarılı | Tanı çıktısı değil, sürümlü production pack ve insan onayı |
| Kaito view pack | v7 onaylı | Yeni FLUX prompt sözleşmesi kullanılacaksa v8 üretip yeniden onaylamak |
| Kaito pose pack | Yok | Beş poz üretilmiş, QC geçmiş ve insan tarafından onaylanmış olmalı |
| Karakter kaydı | `canonical_cast` boş | Onaylı Character Bible oluşturulup cast'e kaydedilmeli |
| Seri stili | `PROVISIONAL` | Yaratıcı onay + teknik production lock + gerçek smoke receipt |
| Görsel model sözleşmesi | Turnaround FLUX; pose/keyframe hâlâ SDXL/OpenPose | Karma mimari açıkça onaylanmalı veya pose/keyframe FLUX'a taşınmalı |
| Pose template'leri | Altı nötr iskelet var | Beş gerçek aksiyon pozu ve FLUX/pose motoruyla canlı doğrulama |
| Hikâye | Bölüm 1 `DRAFT` | İnsan onaylı screenplay ve canon/continuity raporları |
| Bölüm oyuncuları | Akira, Mina, Elias, Lena, Sera, Ivo ve diğerleri | Pilot sekansında görünen her kişi için onaylı karakter paketi |
| Arka planlar | Factory kodu var | Pilot çekimlerinde kullanılan mekânlar için onaylı clean plate + depth kanıtı |
| Shot planı | Yok | Süre, yöntem, kadraj, başlangıç/bitiş kareleri ve seed içeren kilitli shot list |
| Keyframe'ler | Sistem kapısı var | Her çekim için insan onaylı start/end frame |
| Ses | Mimari hazır | Scratch dialogue, zamanlama, audio plan ve hak kayıtları |
| Animatic | Yok | 24 FPS bütün pilotu temsil eden izlenmiş ve insan kilitli animatic |
| Animation-ready paket | Yok | P8 paketleyicisinin eksiksiz ve hash kayıtlı çıktısı |
| Kiralık GPU worker | Yok | Aşama 2 başında gerçek instance bilgileriyle oluşturulmalı |

### Bugünkü dört görsel readiness hatası

1. Seri style durumu `PROVISIONAL`.
2. `style-approval.json` eksik.
3. `production-style-lock.json` eksik.
4. `canonical_cast` içinde kayıtlı karakter yok.

Bu dört hata kod arızası değil; eksik insan/üretim onayıdır.

## 4. Önce verilmesi gereken üç karar

### Karar A — Pilot kapsamı

Bölüm 1 taslağı 22 dakikalık, 10 sahneli, yaklaşık sekiz ayrı mekânlı ve en az
altı insan karakterli bir yapıdır. Bunu ilk Aşama 1 doğrulaması yapmak gereksiz
risk ve süre üretir.

Öneri: Önce **60–90 saniye, 8–16 çekim, 1–2 karakter ve tek mekân** içeren bir
pilot sekans seçilsin. Sistem bu paketi baştan sona kapattıktan sonra tam bölüme
ölçeklensin.

### Karar B — Ana karakter

Mevcut Bölüm 1 Akira merkezlidir; son canlı görsel çalışma Kaito üzerindedir.
Kaito mevcut senaryoda oyuncu değildir. Aşağıdakilerden biri yazılı olarak
seçilmelidir:

- Teknik pilot Kaito ile yapılır; hikâyeden bağımsız bir kalite demonstrasyonu olur.
- Bölüm pilotu Akira ile yapılır; aynı FLUX turnaround/pose akışı Akira'ya uygulanır.

Öneri: Önce Kaito ile 30–45 saniyelik teknik pilot, ardından Akira ile 60–90
saniyelik gerçek hikâye pilotu.

### Karar C — Pose ve keyframe motoru

FLUX.2 yalnız turnaround rolünde production sağlayıcısıdır. Mevcut pose ve
storyboard keyframe akışı Animagine/SDXL + IP-Adapter + OpenPose kullanır. Kaito
üzerinde kimliği koruyan beş aksiyon pozu henüz canlı doğrulanmamıştır.

Aşama 1 kapanmadan önce iki yöntem aynı Kaito girdisiyle karşılaştırılmalıdır:

1. FLUX.2 kaynak-güdümlü pose edit: görsel + kısa delta prompt.
2. Mevcut SDXL/OpenPose pose akışı: görsel kimlik + pose template.

Kimlik, el/anatomi, kıyafet, asimetri ve poza uyum ölçülür. Kazanan tek production
yolu olur; başarısız yöntem fallback adı altında sessizce kullanılmaz.

## 5. Önerilen çalışma planı

### İş Paketi 1 — Görsel sözleşmeyi kapat (0,5–1 gün)

- FLUX.2 model lock ve workflow hash'lerini production kaynaklarına bağla.
- `source-led-delta-edit-v1` prompt sözleşmesini ana generator olarak sabitle.
- Görsel requirement dosyasındaki eski model rolleri ile gerçek capability
  routing'ini uyumlu hale getir.
- Tam model SHA-256 readiness kontrolünü çalıştır.

**Bitti ölçütü:** Hangi görevde hangi modelin çalıştığı tek bir capability
tablosunda bellidir; eksik modelde fail-closed davranır.

### İş Paketi 2 — Kaito production turnaround v8 (0,5–1 gün)

- Onaylı kanonik Kaito'dan yedi görünüş üret: face close-up, front, iki profil,
  iki ¾ ve back.
- Çizilen her görünüşte üç seed adayını karşılaştır.
- Drift raporunu üret.
- Saç işareti, çanta/askı devamlılığı, taraf asimetrisi ve renk panellerini insan
  kontrol listesiyle imzala.
- Contact sheet'i ve `view-pack-approval.json` makbuzunu kilitle.

**Bitti ölçütü:** Production klasöründe sürümlü, hash doğrulanmış ve insan onaylı
yedi görünüş bulunur; diagnostic klasörü production girdisi sayılmaz.

### İş Paketi 3 — Character Bible ve cast (0,5 gün)

- Seçilen pilot karakteri için hikâye/visual Character Bible oluştur.
- Runtime referanslarını yalnız onaylı view pack'ten bağla.
- Rolü ile `selma-anime-v1.cast.json` içine kaydet.

**Bitti ölçütü:** `canonical_cast >= 1`; kayıtlı bütün referans hash'leri geçerli.

### İş Paketi 4 — Seri style lock (0,5–1 gün)

- `selma-anime-v1` ile `crimson-silence-visual-v1` arasındaki iki stil tanımından
  hangisinin üretim kanonu olduğuna karar ver.
- Yaratıcı style kriterlerini insan olarak onayla.
- Style'ı `APPROVED` durumuna yükselt.
- Production lock oluştur.
- Kilitli gerçek workflow ile tek smoke render al.
- Smoke receipt'i bağlayıp `PRODUCTION_COMPATIBLE` durumuna geçir.

**Bitti ölçütü:** Readiness'teki style ile ilgili üç FAIL kapanır.

### İş Paketi 5 — Beş pozluk pose pack (1–3 gün)

- Beş üretim pozu belirle: neutral front, ¾ neutral, strict profile, yürüyüş/koşu
  ve hikâye-özel aksiyon.
- Önce FLUX pose-edit ile küçük seed taraması yap.
- Gerekiyorsa aynı pozları mevcut OpenPose akışıyla A/B karşılaştır.
- Kimlik, outfit, anatomi, eller, aksesuar tarafı ve stil QC uygula.
- İnsan onayıyla `pose-pack-approval.json` üret.

**Bitti ölçütü:** Beş pozun tamamı onaylıdır ve view-pack/style-lock makbuzlarını
doğrulayarak üretilmiştir.

### İş Paketi 6 — Pilot hikâye ve shot planı (1–2 gün)

- Pilot sekansı kesinleştir.
- Senaryo metnini insan onaylı duruma getir.
- Canon, continuity ve karakter sesi kontrollerini kapat.
- Her çekime `shot_id`, süre, kadraj, kamera, karakter durumu, production method
  ve seed ata.

**Bitti ölçütü:** `approved-screenplay.json`, `continuity-state.json` ve
`shot-list.json` kilitlidir.

### İş Paketi 7 — Pilot arka planları (1–2 gün)

- Pilotun tek ana mekânı için Location Bible oluştur.
- Gerekli wide/medium/close/reverse clean plate'leri üret.
- Perspektif, geometri, ışık ve palet sürekliliğini kontrol et.
- Kullanılacak plate'leri insan olarak onayla.
- Parallax kullanılacaksa gerçek depth map üret; yoksa yöntemi `STATIC` olarak
  açıkça işaretle.

**Bitti ölçütü:** Her çekimin onaylı bir `background-clean.png` girdisi vardır.

### İş Paketi 8 — Start/end keyframe ve maskeler (2–4 gün)

- Her pilot çekimi için uygun karakter görünüşü/pozu seç.
- Start ve end keyframe üret.
- Karakter kimliği, mekân, lens, ekran yönü ve aks çizgisini QC'den geçir.
- İnsan onayı olmayan hiçbir kareyi animatic veya animation package'a alma.
- Karakter maskelerini üret ve doğrula.

**Bitti ölçütü:** 8–16 çekimin her birinde iki onaylı keyframe, clean background
ve character mask vardır.

### İş Paketi 9 — Scratch ses ve animatic (1–2 gün)

- Diyalogları scratch sesle zamanla.
- Müzik/SFX kararlarını audio plan'a yaz.
- Hak ve kaynak kayıtlarını ekle.
- 24 FPS animatic oluştur, baştan sona izle ve insan olarak kilitle.

**Bitti ölçütü:** Süre, ritim, diyalog boşlukları ve çekim sırası artık değişmeyecek
şekilde `animatic.mp4` onaylıdır.

### İş Paketi 10 — P8 paketleme ve prova (0,5–1 gün)

- Her shot için portable package oluştur.
- Tüm dosya ve hash'leri doğrula.
- Animation readiness kontrolünü episode root üzerinde çalıştır.
- Kiralık worker hariç hiçbir eksik bırakma.
- Wan render manifest ve retry/bütçe/fencing sözleşmesini ADR-009 ile doğrula.

**Bitti ölçütü:** Aşama 2'de worker bilgisi eklendiğinde paket değişmeden render
kuyruğuna girebilir.

## 6. Süre tahmini

### Önerilen teknik pilot: 60–90 saniye, 8–16 çekim

| İş | Tahmin |
|---|---:|
| Görsel sözleşme + production FLUX entegrasyonu | 0,5–1 gün |
| Kaito v8 turnaround + onay | 0,5–1 gün |
| Character Bible + cast + style lock | 1–1,5 gün |
| Pose motoru A/B testi + onaylı beş poz | 1–3 gün |
| Pilot senaryo + shot planı | 1–2 gün |
| Arka plan paketi | 1–2 gün |
| 8–16 start/end keyframe + maskeler | 2–4 gün |
| Scratch ses + animatic + insan revizyonu | 1–2 gün |
| P8 paketleme ve readiness prova | 0,5–1 gün |

**Toplam:** İşler ardışık yürütülürse **8–15 çalışma günü**. Bazı üretim ve
inceleme işleri paralel yapılırsa gerçekçi hedef **7–12 çalışma günü**dür.

Pose tutarlılığı FLUX ile ilk denemede kapanmazsa **3–5 gün Ar-Ge payı** eklenmelidir.
Bu durumda üst sınır yaklaşık **3 hafta** olur.

### Tam 22 dakikalık Bölüm 1

Mevcut taslak 10 sahne, yaklaşık sekiz mekân ve çok karakterli bir kadro içerir.
Kesin shot list olmadığı için doğru tahmin aralık olarak verilmelidir:

- Tek kişi, yerel üretim ve insan QC: **6–10 hafta pre-production**.
- İki–üç kişilik ekip ve paralel onay: **3–6 hafta pre-production**.
- Pose/keyframe motoru tekrar tasarlanırsa ek **1–2 hafta** risk payı.

Bu süre animasyon render süresi değildir; Aşama 1'in senaryo, tasarım, background,
keyframe, ses, animatic ve paketleme süresidir.

## 7. GPU kiralama kararı

Aşama 1'in çoğu yerel makinede tamamlanmalıdır:

- FLUX.2 4B turnaround yerelde çalışıyor.
- Prompt, QC, style lock, script, background seçimi, shot planı, ses ve animatic
  için 80 GB GPU gerekmez.
- Daha hızlı GPU, eksik onay veya yanlış pose sözleşmesini düzeltmez.

GPU yalnız şu durumda erken kiralanabilir:

- FLUX.2 4B, beş pozluk kimlik testinde hedefi tutturamaz ve 9B modelinin aynı
  girdide ölçülebilir kalite farkı yaratıp yaratmadığını görmek için 2–4 saatlik
  sınırlı benchmark yapılır.

Ana kiralama Aşama 2'de yapılmalıdır. Mevcut animation manifesti Wan2.2 I2V A14B
için en az **80 GB VRAM** ister. Worker dosyası gerçek instance, sabit container
image ve model revision bilgileri bilinmeden oluşturulmamalıdır.

## 8. Aşama 1 kapanış checklist'i

- [ ] Pilot kapsamı ve ana karakter yazılı olarak seçildi.
- [ ] Tek production visual style seçildi ve çelişkili style tanımları kapatıldı.
- [ ] FLUX/model capability sözleşmesi ve model hash'leri doğrulandı.
- [ ] Ana karakterin production view pack'i onaylandı.
- [ ] Character Bible oluşturuldu ve canonical cast'e kaydedildi.
- [ ] Production style lock gerçek smoke render ile kapatıldı.
- [ ] Beş pozluk pose pack onaylandı.
- [ ] Pilot screenplay ve continuity onaylandı.
- [ ] Shot list kilitlendi.
- [ ] Gerekli background clean plate'leri onaylandı.
- [ ] Her shot için start/end keyframe onaylandı.
- [ ] Character mask ve effects spec mevcut.
- [ ] Dialogue/scratch audio ve audio plan hazır.
- [ ] Lisanslar ve izinler hash kanıtıyla kaydedildi.
- [ ] 24 FPS animatic izlendi ve insan tarafından kilitlendi.
- [ ] P8 animation-ready package üretildi.
- [ ] Python testleri ve Remotion type-check yeşil.
- [ ] Visual readiness `READY`.
- [ ] Episode animation readiness worker dışında eksiksiz.
- [ ] Aşama 2 GPU bütçesi, retry sınırı ve maksimum render denemesi onaylandı.

## 9. Önerilen hemen sonraki adım

İlk yapılacak iş GPU kiralamak değil, **İş Paketi 5 için Kaito üzerinde beş
gerçek pose üretmek** olmalıdır. Bu test, FLUX turnaround başarısının animasyon
keyframe üretimine taşınıp taşınamadığını gösterecek son büyük teknik belirsizliktir.

Pose testi geçerse Aşama 1 planı 7–12 günlük pilot takviminde yürür. Geçmezse
FLUX.2 9B için kısa kiralık GPU benchmark'ı yapılır; sürekli kiralama kararı ancak
aynı prompt, seed ve pose setindeki kalite farkı ölçüldükten sonra verilir.

## 10. Kanıt ve kaynak dosyaları

- `docs/ANIME_PREPRODUCTION_P1_P8.md`
- `docs/operations/pre-animation-layer.md`
- `docs/ANIME_VISUAL_ANIMATION_REQUIREMENTS.md`
- `config/production/anime-visual-requirements.json`
- `config/production/anime-animation-requirements.json`
- `docs/project/status.md`
- `docs/project/roadmap.md`
- `output/diagnostics/flux2-kaito-turnaround-v2/pack-manifest.json`
- `output/production/characters/kaito/v7/view-pack-approval.json`
