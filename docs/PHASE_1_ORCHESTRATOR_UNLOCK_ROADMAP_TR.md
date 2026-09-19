# Aşama 1 Roadmap — Animation Orchestrator Kilidini Açma

**Tarih:** 14 Eylül 2026  
**Bitiş noktası:** `AnimationOrchestratorService` için onaylı view pack, pose pack
ve keyframe çifti hazır; visual readiness sıfır FAIL.  
**Kapsam dışı:** Wan 2.2 kiralık GPU, `wan2.2-worker.json`, episode package ve
animasyon render zinciri. Bunlar Aşama 2'dir.

## Ölçülen başlangıç durumu

| Kontrol | Sonuç |
|---|---|
| Python test paketi | 1165/1165 PASS |
| Remotion type-check | PASS |
| Kaito v7 view pack | APPROVED; 8 otomatik + 12 insan kontrolü |
| Visual readiness | 17 PASS / 4 FAIL |
| ComfyUI 8188 | Kapalı |
| `config/series/selma-anime-v1/` | Henüz yok |
| `assets/character_bibles/kaito.json` | Henüz yok |
| Kaito pose-pack approval | Henüz yok |
| Model rolleri ve SDXL workflow düğümleri | PASS |

Visual readiness'in dört hatası:

1. `approved_style`
2. `style_approval_receipt`
3. `production_style_lock`
4. `canonical_cast`

Animation readiness'teki worker ve episode package hataları bu roadmap'in
kapsamı dışında ve Aşama 2 için beklenen durumlardır.

## Sabit mimari sınır

Capability routing şu anda göreve göre iki motor kullanır:

| Görev | Motor |
|---|---|
| Character turnaround | FLUX.2 Klein 4B source-led edit |
| Pose pack | SDXL/Animagine + IP-Adapter + ControlNet OpenPose |
| Storyboard/keyframe | SDXL/Animagine + IP-Adapter + ControlNet OpenPose |
| Style smoke | SDXL production workflow |

FLUX.2 edit provider `pose_storage_key` girdisini reddeder. Bu nedenle mevcut
production pose yolunu yalnız ayar değiştirerek FLUX'a çevirmek mümkün değildir.
İki motor arasındaki kimlik ve çizim dokusu farkı pose/keyframe insan onayında
ölçülmelidir.

## Aşama 0 — Oturum hazırlığı

**Tahmin:** 5–10 dakika, GPU render yok.

- ComfyUI-runtime'ı extra model path dosyasıyla başlat.
- `127.0.0.1:8188` durumunu doğrula.
- Serbest RAM'in preflight eşiğini geçtiğini doğrula.
- Visual readiness ve test baseline'ını kaydet.

**DoD:** 8188 dinliyor, testler yeşil ve readiness başlangıç durumu tekrar
üretilebilir.

## Aşama 1 — Kaito Character Bible

**Tahmin:** 30–60 dakika, GPU yok.

`character init` doğrudan yaratıcı `kaito.json` şemasını kabul etmez. Önce fabrika
şemasında `assets/character_bibles/kaito.brief.json` hazırlanmalıdır:

- `character_id`, `display_name`
- `visual.eye_color`, `hair`, `facial_geometry`, `body_proportions`
- `visual.silhouette`, `outfit`, `base_style`
- `narrative.motivation`, `backstory`

Ardından:

```powershell
python -m cli.main character init `
  --brief assets/character_bibles/kaito.brief.json `
  --output assets/character_bibles/kaito.json
```

Fabrika çıktısı başlangıçta `narrative_profile.locked: false` üretir. Production
kullanımından önce narrative alanı insan tarafından tamamlanıp kilitlenmeli;
kobalt saç işareti structured mark olarak ve çanta tarafı değişmez kimlik kuralı
olarak kaydedilmelidir. Runtime reference pack yalnız v7 onaylı varlıklardan
bağlanmalıdır.

**DoD:** Bible parse edilir, narrative kilitlidir, Kaito'ya ait onaylı referans
hash'lerini taşır ve `character show` komutu başarılıdır.

## Aşama 2 — Canonical cast kaydı

**Tahmin:** 1–5 dakika, GPU yok.

```powershell
python -m cli.main series register-character `
  --project config/series/selma-anime-v1.json `
  --bible assets/character_bibles/kaito.json `
  --role protagonist --version 1 --status CANONICAL
```

`--status` verilmezse varsayılan `DRAFT` olur. Visual readiness yalnız
`CANONICAL` üyeleri sayar. Bu davranış dokümana ve regresyon testine bağlanmıştır.

**DoD:** Cast bir canonical üye taşır; `canonical_cast` ve
`character_bible:kaito:v1` PASS olur.

## Aşama 3 — Series style lock

**Tahmin:** 10–20 dakika; son adım tek GPU smoke render içerir.

Sıra değiştirilemez:

1. `series approve-style`
2. `series promote-style`
3. Style approval makbuzunun SHA-256'sını hesapla.
4. `series create-production-lock`
5. `series smoke-production-lock`
6. `series mark-production-compatible`

Smoke testi model/workflow byte'larını doğrular ve kilitli SDXL ayarlarıyla gerçek
bir kare üretir. Fake provider'dan gelen makbuz kabul edilmez.

**İnsan kapısı:** Style kriteri ve smoke karesi kullanıcı tarafından görülmeden
`approved-by` imzası atılmaz.

**DoD:** Style `APPROVED`, lock `PRODUCTION_COMPATIBLE`,
`production_eligible: true`; style kaynaklı üç readiness hatası kapanır.

## Aşama 4 — Beş pozluk Kaito pose pack

**Tahmin:** Render için yaklaşık 10–20 dakika; inceleme/tuning için 15–60 dakika.

> **Durum (15 Eylül 2026): üretildi, 5/5 ölçülebilir QC geçti, imza bekliyor.**
> Beş render ile beş poz ve contact sheet yazıldı (`v7/pose-pack/`), manifest
> `PENDING_HUMAN_REVIEW`, `production_eligible: true`.
>
> **Asıl kusur kabul politikasındaydı, üreticide değil.** Deneme döngüsü ilk
> yapısal olarak geçerli render'ı QC ne derse desin kilitliyordu; kadraj dışı ya
> da ters yöne bakan bir seed paketin içine giriyor ve insan onay listesinin
> kapsamak zorunda kaldığı bir kusura dönüşüyordu. Artık ölçülebilir bir QC hatası
> karantinaya alınıp sonraki seed harcanıyor; hepsi başarısız olursa paket
> `BLOCKED` durur ve bilinen kötü bir render'ı kilitlemez.
>
> Aynı ayarlarla ölçülen sonuç: **5/5 poz geçti** ve hiçbir poz üç seed'den fazla
> harcamadı. Karantina kaydı neyin elendiğini isimleriyle tutuyor:
>
> | Poz | Elenen seed'ler | Kabul edilen |
> |---|---|---|
> | `FRONT_NEUTRAL` | 1: ayaklar kadraj dışı | `front`, ayaklar içeride |
> | `THREE_QUARTER_LEFT` | 1: kişi tespit edilemedi + kadraj | `three_quarter_left` |
> | `PROFILE_LEFT` | 1: ters taraf + ayaklar · 2: öne dönmüş | `three_quarter_left` (aynı taraf) |
> | `THREE_QUARTER_RIGHT` | 1: ayaklar kadraj dışı | `three_quarter_right` |
> | `BACK_FULL_BODY` | 1, 2: üç-çeyrek + yüz görünür | `back`, yüz yok |
>
> **Yön rehberi çalışıyor; eski hat onu hiç zorlamıyordu.** Bu, önceki
> "OpenPose rehberi kimlik koşullanması tarafından eziliyor" teşhisini düzeltir:
> aynı rehber ve aynı ağırlıklarla doğru render alınabiliyor, sadece başarısız
> seed seçilmiyordu.
>
> Bu aşamaya gelinmesi üç gerçek blocker'ın düzeltilmesini gerektirdi; üçü de
> poz diyalektinin gerçek sağlayıcıyla hiç çalışmamış olmasından geliyordu:
> (1) istek, iki adapter'lı workflow'a karşı üç referans bildiriyor ve zincirini
> `reference_views` ile adlandırmıyordu; (2) `identity_mode`
> `identity_only_with_style_seed` sağlayıcının tanımadığı bir moddu, ayrıca
> conditioning referanslarının `asset_id` değerleri kendi
> `reference_asset_ids` haritasıyla eşleşmiyordu; (3) her poz artık kendi eşleşen
> onaylı görünüşüyle koşullanıyor ve zincirini adlandırıyor.
>
> **Ölçülemeyen tek şey: profil ile üç-çeyrek ayrımı.** `PROFILE_LEFT` pozu
> `three_quarter_left` okundu ve QC kapısı bunu aynı taraf olduğu için danışma
> olarak kabul ediyor. Bu ayrımın gerçekten ölçülemez olduğu doğrulandı: onaylı
> altı görünüş yer gerçeği olarak alındı ve üç sensör de (yüz keypoint'leri,
> normalize ofsetler, yüz dedektörü kutusu) profili üç-çeyrekten ayıramadı.
> Dördüncü sensör — gövde öngörünüm kısalması — ölçülebilir tek yaw ekseni olarak
> bulundu ve artık her görünüş/poz için danışma kanıtı olarak kaydediliyor
> (`torso_foreshortening`), fakat etiketli örneklem temiz ayrışmadığı için kapı
> yapılmadı. Kanıt: yeni `PROFILE_LEFT` pozu 0,296 (onaylı profil 0,276 ile
> uyumlu), `THREE_QUARTER_LEFT` pozu 0,549 (onaylı üç-çeyrek 0,427) — yani
> sonuncusunun gövdesi neredeyse önden; insan incelemesinin bakacağı yer burası.

Pozlar:

- `FRONT_NEUTRAL`
- `THREE_QUARTER_LEFT`
- `PROFILE_LEFT`
- `THREE_QUARTER_RIGHT`
- `BACK_FULL_BODY`

Üretim v7 view-pack onayı ve aktif production style lock olmadan başlamaz.

```powershell
python -m cli.main character pose-pack generate `
  --brief assets/character_creation_briefs/kaito.json `
  --approval output/production/characters/kaito/v7/canonical-approval.json `
  --active-series config/series/selma-anime-v1.json `
  --manifest output/production/characters/kaito/v7/pose-pack.json
```

İnsan kontrolleri:

- `identity_consistent`
- `outfit_consistent`
- `all_five_poses_present`
- `style_consistent`
- `anatomy_and_artifacts_pass`

Özellikle tek kobalt işaretin tarafı, çanta tarafı, yüz, ceket panelleri ve iki
motor arasındaki çizim dokusu incelenir.

**DoD:** 5/5 poz QC geçmiş ve `pose-pack-approval.json` insan imzalıdır.

## Aşama 5 — Onaylı keyframe çifti

**Tahmin:** Render için yaklaşık 10–20 dakika; inceleme/tuning için 15–60 dakika.

Komutta `--character-id kaito` açıkça verilmelidir; varsayılan karaktere
güvenilmez. Başlangıç ve bitiş pozu Aşama 4'te oluşan gerçek storage key'lerinden
seçilir.

İnsan kontrolleri:

- `identity_consistent`
- `outfit_consistent`
- `start_pose_matches`
- `end_pose_matches`
- `start_end_continuity`

**DoD:** Keyframe çifti onaylıdır ve shot plan `keyframe_approved: true` taşır.

## Aşama 6 — Kapanış doğrulaması

**Tahmin:** 15–30 dakika.

- `check_anime_readiness.py --stage visual` → `READY`, sıfır FAIL.
- `series status` → `production_ready: true`.
- View-pack, pose-pack ve keyframe approval hash'leri yeniden doğrulanır.
- `docs/project/status.md`, `docs/project/roadmap.md`, bu runbook ve changelog
  gerçek sonuçlarla güncellenir.
- Python ve Remotion testleri yeniden çalıştırılır.

**DoD:** Animation orchestrator'ın view, pose ve keyframe onay kapıları
karşılanmıştır. Sonraki iş Aşama 2 Wan/episode roadmap'idir.

## Zaman tahmini

| Senaryo | Süre |
|---|---:|
| Teknik alt sınır; ilk renderlar geçer, onaylar beklemez | 1–1,5 saat |
| Gerçekçi; görsel inceleme ve tek ayar turu | 2–4 saat |
| Pose/keyframe kimliği başarısız, birkaç tuning turu gerekir | 1 çalışma günü |

1–1,5 saat yalnız **happy path** tahminidir. Aşama 1 taahhüdü olarak 2–4 saat
ayrılmalı; görsel insan onayı nedeniyle otomatik olarak “tamamlandı” denmemelidir.

## Bloklamayan kararlar

### Palette drift

v7'nin beş çizilen görünüşünde advisory palette drift vardır. Paket insan onaylı
olduğu için bu tek başına bloklayıcı değildir. Aynı kayma pose pack'te görülürse
prompt/reference ağırlığı için bir tuning turu açılır.

### İki motor

View pack FLUX, pose/keyframe SDXL'dir. Onay kriterleri farkı yakalamak zorundadır.
Kimlik farkı kabul sınırını aşarsa production onayı verilmez.

### Kilitli byte'lar

v7 üzerine yazılmaz. View pack değişirse yeni sürüm ve yeni acceptance dosyası
gerekir. Bu roadmap v7'yi değiştirmeden pose ve keyframe kapılarını kapatmayı
hedefler.

## İnsan imzaları

- Senaryo (`ep01` "Birinci Taslak"): 1 imza tamamlandı — kanon 0 ihlal, üç hakem
geçti, `LOCKED`, `approved_by: LOQ`.
- View-pack: 12 imza tamamlandı.
- Style: 1 yaratıcı onay tamamlandı (`style-approval.json`, `approved_by: LOQ`).
- Pose-pack: 5 imza bekliyor.
- Keyframe pair: 5 imza bekliyor.

Toplam kalan: **10 insan kararı**. Komutlar `--approved-by LOQ` ile ancak ilgili
görsel kullanıcı tarafından görüldükten ve açıkça kabul edildikten sonra
çalıştırılır.

## Kapanış checklist'i

- [x] ComfyUI 8188 hazır (PID 20000, ComfyUI-runtime + `extra_model_paths`).
- [x] Baseline testler yeşil (1166 → 1167 after the new regression test).
- [x] Kaito Character Bible hazır ve narrative kilitli.
- [x] Kaito cast içinde `CANONICAL` (`canonical_cast` + `character_bible:kaito:v1` PASS).
- [x] Style yaratıcı onayı kayıtlı (4 kriter, `approved_by: LOQ`).
- [x] Production style lock gerçek smoke render ile uyumlu (`PRODUCTION_COMPATIBLE`,
      768×1152, 56,3 sn, `comfyui:keyframe`).
- [ ] Beş Kaito pozu insan onaylı — **5/5 ölçülebilir QC geçti, imza bekliyor**.
- [x] `ep01` senaryosu `LOCKED` (kanon 0 ihlal, üç hakem geçti, insan imzası) ve
      çekim hiyerarşisi üretildi (3 sequence, 10 sahne, 25 çekim, 82,0 sn).
- [ ] Çok karakterli bölümde kimlik seçimi: kırılım tek bible'ı her çekime
      yazdığı için 25 çekimin 6'sı sahnede olmayan karakterle etiketlendi.
- [ ] Keyframe çifti QC geçmiş ve insan onaylı.
- [x] Visual readiness sıfır FAIL (`READY`).
- [ ] Animation orchestrator üç approval guard'ı geçiyor.
- [x] Status, roadmap, runbook ve changelog senkron.

