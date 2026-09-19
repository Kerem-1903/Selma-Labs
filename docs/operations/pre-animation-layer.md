# Pre-animation layer — operating order

Bu doküman animasyon katmanına geçmeden önce kapatılması gereken üç kapıyı ve
sırasını tanımlar. Sıra keyfi değil: her adım bir sonrakinin ön koşulunu üretir.

```
0. Senaryo kapısı              → LOCKED episode-script.json (insan imzası)
1. Karakter turnaround onayı   → view-pack-approval.json
2. Seri style lock             → PRODUCTION_COMPATIBLE kilit + cast kaydı
3. Beş pozluk pose pack        → pose-pack-approval.json
        ↓
   animation orchestrator (keyframe onayı + pose-pack makbuzu ister)
```

**Sıra neden önemli.** §1–§3 karakteri üretir; **hangi karakterlerin
üretileceğini ise §0 belirler.** Kaito'nun hattını uçtan uca doğrulayıp
`ep01`'in senaryosunu dondurmamak, doğrulanmış işi bölüme bağlamaz: `ep01`'in
planı Kaito'yu hiç kullanmıyor. Aşağı akışta çalışıp yukarı akışı kilitlememek
Kaito tuzağıdır ve her karakterde tekrarlanır.

Hazır mıyız sorusunun tek cevabı:

```bash
python scripts/check_anime_readiness.py --stage visual
```

`NOT READY` çıktısındaki her `[FAIL]` satırı bu dokümandaki bir adıma karşılık gelir.

---

## 0. Ön kontrol

```bash
# ComfyUI ayakta mı; FLUX.2 üçlüsü ve SDXL yığını yerinde mi
python -m cli.main series status
python scripts/check_anime_readiness.py --stage visual --json
```

**Bellek notu.** Üretim preflight'ı **4,0 GiB** boş RAM ister. ComfyUI bir
render'dan sonra checkpoint'i RAM önbelleğinde tutar (SDXL yüklemesi ~6 GB),
bu yüzden bir GPU işi bittiğinde makinede boş alan eşiğin altına düşebilir ve
sıradaki koşum `BLOCKED_PREFLIGHT: ram_free` ile durur. Bu bir arıza değil:
paket `BLOCKED` durumdan kaldığı yerden devam eder. İki iş arasında önbelleği
açıkça boşaltmak eşiği güvenli tarafa çeker:

```bash
python -c "import asyncio; from infrastructure.providers.keyframe.comfyui_memory_releaser import ComfyUiMemoryReleaser as R; asyncio.run(R('http://127.0.0.1:8188').release())"
```

---

## 0.5 Senaryo kapısı ve çekim hiyerarşisi

Senaryo zincirin kaynağıdır: `episode plan` ve `preproduction plan` ondan
türer, dolayısıyla imzasız bir taslak üzerine harcanan her render boşa gider.
Kapı iki aşamalıdır ve **ikisi de zorunludur**:

```bash
# 1. İnceleme — kanon doğrulayıcı + üç hakem (continuity, character-voice, final-editor)
python -m cli.main story review \
  --input assets/preproduction/episodes/ep01/episode-script.json \
  --output output/preproduction/ep01-story-review.json

# 2. İnsan imzası — yalnız incelemeden geçmiş bir senaryoyu kilitler
python -m cli.main story approve \
  --input assets/preproduction/episodes/ep01/episode-script.json \
  --approved-by <isim> \
  --output assets/preproduction/episodes/ep01/episode-script.locked.json
```

`story approve` imzayı kör atmaz: kendi içinde yeniden inceler ve yalnız
`ready_for_approval` olan bir sonucu kilitler. Bloke koşumda `--output` yoluna
**hiçbir şey yazılmaz** — orada kilitli senaryo bekleyen bir çağıran tuzaktan
korunur.

Kilitli senaryodan çekim hiyerarşisi:

```bash
python -m cli.main preproduction plan \
  --input assets/preproduction/episodes/ep01/episode-script.locked.json \
  --character-id akira \
  --output output/preproduction/ep01-plan-locked.json
```

**`--character-id` neden zorunlu.** Kırılım servisi somut bir Character Bible
ister ve container her komut için bir kez kurulur, bu yüzden kimlik burada
açıkça seçilir. Varsayılan bir kimlik, her çekimi sessizce yanlış karakter
durumuyla etiketlerdi.

> **Dikkat — tek-bible sınırı.** `ScriptBreakdownService` gördüğü tek bible'ın
> kimlik parçalarını *her* çekime yazar. Çok karakterli bir bölümde bu, sahnede
> bulunmayan karakteri çekime etiketler: `ep01`'de 25 çekimin 6'sı (%24) böyle
> çıktı (`ep01-sc01` kadrosu Elias+Lena, `ep01-sc05` kadrosu Ivo+Sera). Plan bu
> yüzden çok karakterli bölümlerde henüz tek karakterli bölümlerde olduğu kadar
> güvenilir değildir.

---

## 1. Karakter turnaround (yedi görünüş)

Ön koşullar: kilitli kanonik görsel (`canonical-approval.json`) ve iki anchor.

```bash
# Sürüm artışı zorunlu olabilir: kilitli varlıkların üzerine yazılmaz
python -m cli.main character approve-design \
  --brief assets/character_creation_briefs/kaito.json \
  --manifest <design manifest> --candidate-key <key> \
  --approved-by <operator> --version 6 --output <canonical-approval.json>

python -m cli.main character turnaround \
  --brief assets/character_creation_briefs/kaito.json \
  --approval <canonical-approval.json> \
  --manifest <view-pack.json> \
  --seeds 3
```

Notlar:

- **Brief doğru olmalı.** `kaito.json` (hash `7a398fec…`) onaylı soyun bağlı olduğu
  brief'tir; `kaito-quality-benchmark-v1.json` başka bir hash üretir ve soyu
  eşleştirmez. `character turnaround` brief ile approval hash'ini karşılaştırır ve
  uyuşmazsa hiç başlamaz.
- **`--seeds N`** görünüş başına N aday render eder ve en az kayanı saklar. Kopya
  olan görünüşler (FRONT, FACE_CLOSEUP) süpürmeye girmez — orada seçilecek bir şey
  yok, süpürmek GPU'yu çöpe harcamak olurdu. Sıralama, karakterin **kendi** imza
  rengiyle yapılır (bkz. §4).
- **Tek görünüş yeniden üretme.** `--view VIEW` (tekrarlanabilir) yalnız adı geçen
  görünüşleri çizer, diğerlerini bayt bayt korur; yerini bırakan kare
  `superseded_by_targeted_rerender` gerekçesiyle karantinaya alınır ve bu kayıt
  deneme sayacını ilerlettiği için yeni kare hiç çizilmemiş bir seed bloğundan
  gelir. Ölçülen kazanç: 2 dk 43 sn (tam koşum 6 dk 14 sn).
- **Yeniden üretim geri alınabilir: `--restore-superseded`.** Bir seed saf bir
  fonksiyon olduğu için aynı komutu tekrar koşmak insanın baktığı kareyi geri
  getirmez; tek kopya arşivdeki bayt'lardır. Bu bayrak `--view` ile adı geçen
  görünüşleri arşivden geri koyar ve yerinden ettiği kareyi
  `superseded_by_restored_render` gerekçesiyle dosyalar; hiçbir şey çizilmez,
  GPU hiç çalışmaz.

```bash
python -m cli.main character turnaround \
  --brief assets/character_creation_briefs/akira.json \
  --approval output/production/characters/akira/v6/canonical-approval.json \
  --manifest <view-pack.json> \
  --restore-superseded --view THREE_QUARTER_RIGHT --view PROFILE_RIGHT \
  --restored-by <operator> --reason "<hangi ayrıntı arşivde doğru>"
```

  **Arşiv bir geri-alma yığınıdır.** Geri getirme, yerine geçtiği kareyi de
  dosyaladığı için komutu tekrarlamak yerine koyduğunuz kareyi geri getirir —
  insan yakından bakıp kararını döndürdüğünde tek yol budur. Bir kontrolü
  düşürmüş kare asla aday değildir; olsaydı "geri getir" reddedilmiş bir kareyi
  içeri sokmanın yolu olurdu. Reddedilenler: onaysız insan adı, boş görünüş
  listesi, hiçbir şeyin yerinden etmediği görünüş, kopya görünüşler (FRONT,
  FACE_CLOSEUP), **onaylanmış** veya **reddedilmiş** paket (imza artık var olmayan
  kanıtı işaret edemez), arşivdeki hash'iyle eşleşmeyen bayt'lar ve arşivlenmiş
  kare artık QC kapısından geçmiyorsa. Geri
  getirilen kare için manifest'e yeni bir provenance kaydı yazılır — yazılmasaydı
  paket `provenance_hashes` yüzünden bir daha onaylanamazdı. Karar ayrıca
  `<root>/view-pack-restore.json` makbuzuna geçer (kim, ne zaman, hangi seed'ler,
  hangi gerekçe).

<details><summary>Akira v6'da gerçek koşum (2026-09-16) — karar bir kez döndü</summary>

```
20:00:34Z  THREE_QUARTER_RIGHT  1921057500 → 1921055399   2cae2b2e… → 480cbf99…
           PROFILE_RIGHT        1921066399 → 1921065500   891b8de6… → 1962d10c…
20:10:30Z  THREE_QUARTER_RIGHT  1921055399 → 1921057500   480cbf99… → 2cae2b2e…
           PROFILE_RIGHT        1921065500 → 1921066399   1962d10c… → 891b8de6…
```

İlk gerekçe: arşivdeki karede bacağa kayışla bağlanan cep kanonik kaynakla
uyuşuyor, yerini bırakan karede kayboluyor. İkinci gerekçe: 3× kalça/bacak
kırpmaları gösterildiğinde karar tersine döndü ve yerini bırakan kare tercih
edildi. İki kare de diskte; `view-pack-restore.json` zinciri iki kararı da,
kullanıcıyı, zamanı ve seed'leri taşıyor. Her iki yönde de doğrulandı: sekiz
otomatik kabul kontrolü (provenance ve consistency dahil) geçiyor ve
`load_approved_view_pack` paketi okuyabiliyor.

</details>
- Paketle birlikte `drift-report.json` yazılır (bkz. §4) ve pack kabul listesinin
  `required_evidence` girdisi olduğu için onaysız kalamaz.
- Onay: `docs/KAITO_V1_ACCEPTANCE.md` içindeki on iki maddenin tamamı `--check`
  ile imzalanır.

```bash
python -m cli.main character approve-view-pack \
  --character kaito --version v7 --approved-by <operator> \
  --acceptance config/character_acceptance/kaito-v7.json --check ... (×12)
```

> **Durum: v7 onaylandı.** `output/production/characters/kaito/v7/view-pack-approval.json`
> mevcut; sekiz otomatik kontrol doğrulandı, on iki insan maddesi imzalandı ve yedi
> görünüş hash'i kilitlendi. `pose-pack generate` artık bu makbuz olmadan
> başlamıyor (`require_view_pack_approval`). v6 haklı olarak reddediliyor.
>
> **Onayın v5'ten beri neden imkânsız olduğu:** `provenance_hashes` otomatik
> kontrolü *her* görünüşten model/prompt/workflow hash'i istiyordu. `FRONT` ve
> `FACE_CLOSEUP` onaylı varlıkların kopyası olduğu için ikisinde de model
> çalışmadı ve bu alanlar yapısal olarak boş kaldı. Kapı bu yüzden hiçbir sürümde
> geçilemedi. Artık bir görünüş kopya olduğunu ancak byte'ları kopyaladığı onaylı
> varlıkla birebir eşleşiyorsa iddia edebiliyor; diğer görünüşler tam üretim
> kanıtı vermeye devam ediyor.

---

## 2. Seri style lock (teknik kilit)

Zincir dört adımdır ve **son adımı bir koşum kanıtı ister**:

```bash
PROJECT=config/series/selma-anime-v1.json

# 2.1 Yaratıcı onay: insan, stiller listesini gözden geçirdiğini imzalar
python -m cli.main series approve-style --project $PROJECT \
  --approved-by <operator> --check <creative criterion>

# 2.2 Persisted creative receipt'i aktif APPROVED durumuna yükseltir
python -m cli.main series promote-style --project $PROJECT

# 2.3 Teknik kilidi, yaratıcı makbuzun SHA-256'sına bağlayarak oluşturur
RECEIPT_SHA=$(python -c "import hashlib;print(hashlib.sha256(open('config/series/selma-anime-v1/style-approval.json','rb').read()).hexdigest())")
python -m cli.main series create-production-lock --project $PROJECT \
  --workflow assets/comfyui_keyframe_workflow.json \
  --receipt-sha256 $RECEIPT_SHA \
  --width 768 --height 1152 --sampler euler --steps 24 --cfg 5.0 --denoise 0.65

# 2.4 Gerçek bir koşumla kilitli boru hattının çalıştığını kanıtla
python -m cli.main series smoke-production-lock --project $PROJECT \
  --workflow assets/comfyui_keyframe_workflow.json \
  --receipt config/series/selma-anime-v1/smoke-receipt.json

# 2.5 Makbuzu kilide bağla ve üretimi aç
python -m cli.main series mark-production-compatible --project $PROJECT \
  --smoke-receipt config/series/selma-anime-v1/smoke-receipt.json

# 2.6 Karakteri cast'e kaydet (canonical_cast boş kalırsa readiness FAIL)
python -m cli.main series register-character --project $PROJECT \
  --bible assets/character_bibles/kaito.json --role protagonist \
  --version 1 --status CANONICAL
```

`--status` verilmezse kayıt `DRAFT` olur. Visual readiness yalnız
`CANONICAL` üyeleri `canonical_cast` kapısında sayar; bu nedenle üretim kaydında
durum açıkça yazılmalıdır.

`smoke-production-lock` ne yapar:

1. Bekleyen kilidin `model_lock_sha256`, `workflow_sha256` ve `model_hashes`
   değerlerini **diskteki byte'larla** karşılaştırır. Uyuşmazlık → `STYLE_LOCK_TAMPERED`.
2. Her kilitli ağırlık dosyasını doğrular: varsayılan olarak boyut, `--full-model-hash`
   ile SHA-256.
3. Kilitli sampler ayarlarıyla (`steps`, `cfg`, `sampler_name`, `denoise`) ve kilitli
   çözünürlükte **tek kare** gerçek render alır. Kare, makbuzun yanına yazılır.
4. Makbuzu koşumdan **türetir**: `production_lock_digest` bekleyen kilidin digest'i,
   `render.content_hash` üretilen karenin hash'i. Hiçbir alan elle yazılmaz.

Makbuzsuz, yanlış digest'li veya offline (`fake:`) bir motorla alınmış bir makbuz
kabul edilmez; kilit `PENDING_SMOKE_TEST` kalır ve `pose-pack` üretim modu açılmaz.
Tamamlanmış bir kilide ikinci kez makbuz yazılamaz.

---

## 3. Beş pozluk pose pack

Ön koşullar: kanonik onay **ve** onaylı yedi görünüşlük paket **ve** seri production
style lock. Üçünden biri eksikse render başlamaz.

> **Ölçülebilir QC, sonra insan.** Bir seed ölçülebilir bir kriteri ihlal ederse
> (çerçeveleme, bakan taraf, kişi sayısı, arka görünüşte yüz) karantinaya alınır ve
> sonraki seed harcanır; denemeler tükenirse paket `BLOCKED` durur ve bilinen
> kötü bir render kilitlenmez. Beş poz da geçtiğinde manifest
> `PENDING_HUMAN_REVIEW` olur — DoD **hem** 5/5 QC **hem** insan imzasıdır.
>
> **Ölçülemeyen ayrım açıkça kaydedilir.** Profil ile üç-çeyrek bu çizim tarzında
> ayırt edilemiyor (yüz keypoint'leri ve yüz dedektörü ikisi de profili üç-çeyrek
> okur), bu yüzden `PROFILE_LEFT` aynı taraf olduğunda `three_quarter_left`
> olarak kabul edilir. Gövde öngörünüm kısalması (`torso_foreshortening`) her
> görünüş/poz için danışma kanıtı olarak yazılır; eşik olarak kullanılmaz.
>
> Ayrıca `generate_pack` tamamlanmış pozları atlayarak devam eder: prompt veya
> referans değişikliğinden sonra yeniden üretmek istiyorsanız paket dizini ve
> manifest kaldırılmalı ya da yeni karakter sürümü kullanılmalıdır.

```bash
python -m cli.main character pose-pack generate \
  --brief assets/character_creation_briefs/kaito.json \
  --approval <canonical-approval.json> \
  --manifest <pose-pack.json>

python -m cli.main character pose-pack approve \
  --manifest <pose-pack.json> --approved-by <operator> \
  --check identity_consistent --check outfit_consistent \
  --check all_three_poses_present --check style_consistent \
  --check anatomy_and_artifacts_pass
```

---

## 4. Drift raporu — danışma kanıtı

```bash
python -m cli.main character drift-report \
  --source output/production/characters/kaito/v7/canonical_source.png \
  --pack output/production/characters/kaito/v7
```

- Varsayılan bant, ayarlardaki kalibre dosyadır
  (`character_drift_thresholds_path`). Yol verilmiş ama dosya yok/bozuksa üretim
  sessizce gevşek varsayılanlara düşmez; fail-closed durur.
- **Aksan rengi ve işaret tarafı karakterden gelir.** Paket üretimi brief'in
  `signature_marks[].colour` ve `.character_side` alanlarını okur, çünkü ayarlardaki
  tek renk dağıtım geneli bir varsayılandır ve başka renkteki bir karakteri yanlış
  ölçer: Akira'nın kızıl tutamı (`#C04838`) kobalt ayarıyla ölçüldüğünde
  `accent_fraction = 0,0` çıkıyor ve **çizilen beş görünüşün tamamı** `palette_drift`
  işaretleniyordu — bayt'ların desteklemediği bir alarm, ki gerçek bir bayrağın
  görmezden gelinmesinin yolu budur. Brief işaret bildirmiyorsa yapılandırılmış
  değer geçerli kalır; bant, tolerans ve eşik kaynağı her durumda taşınır, böylece
  verdict önceki raporlarla karşılaştırılabilir kalır.
- Tekil `character drift-report` komutu için `--accent-colour ""` veya
  `--mark-side ""` ile kontrol açıkça kapatılabilir. Kapatmak, işaret
  kontrollerini atlamak demektir — temiz rapor değil, ölçülmemiş rapor üretir.
- Çıkış kodu 2 "insan ilgisi gerekli" demektir, "reddedildi" değil. Rapor hiçbir
  görünüşü tek başına onaylamaz veya reddetmez.
- İşaret eşikleri bilinçli olarak kalibre edilmemiştir: referans paket, çizginin
  kaybedildiği pakettir.
- Rapor **yalnızca çizilen görünüşleri** ölçer; `front.png` ve `face-closeup.png`
  onaylı varlıkların kopyaları olduğu için atlanır.
- Her görünüş kaydındaki `mark_measurable: false`, işaret metriklerinin hiç
  uygulanmadığı anlamına gelir: kaynağın kafasında oranın anlam taşıyacağı kadar
  aksan pikseli yok. Bu bir geçiş değil, atlanmış bir kontrol olarak okunmalıdır;
  `output/production/characters/kaito/v7/drift-report.json` dosyasını kontrol edin:

```bash
python -c "import json;r=json.load(open('output/production/characters/kaito/v7/drift-report.json'));print(r['source_metrics']['mark_measurable'],[(v['view'],v['mark_measurable']) for v in r['views']])"
```

- Kaito kanonik görselinin ölçülen kafa aksan yoğunluğu `4,1e-05`; yani
  çizginin kaybolması/aynalanması **bu çözünürlükte otomatik olarak
  doğrulanamaz** ve 3. kabul maddesi insan kararı olarak kalır.
- **Tuval kaynağa uyar.** Kaynak-güdümlü diyalekt tuvali kaynağın en-boy
  oranından türetir (~1 MP, 16'nın katı) ve isteğe `canvas_policy: source_aspect`
  yazar. v7 paketi bu tuvali kullanır: beş çizilen görünüş **992×992**, kopya
  olan FRONT ve FACE_CLOSEUP ise kanonik/anchor boyutunda **1024×1024** kalır ve
  süpürmeye hiç girmez. Sonuç: `summary.canvas_comparable: true`.

- v7 ölçümü tek ve eyleme dönüştürülebilir bir kusur gösterir: **`palette_drift`
  beş görünüşün tamamında**, `palette_distance` 0,119–0,280 bandında. Üç
  görünüşte (PROFILE_LEFT, PROFILE_RIGHT, THREE_QUARTER_LEFT) tek neden budur;
  BACK ve THREE_QUARTER_RIGHT ayrıca `subject_height_drift` ve
  `line_density_drift` taşır. v6'da ise her görünüşte beş-altı neden vardı ve
  bunların arasında byte-identical onaylı anchor'ın kendisi bulunuyordu — yani
  sinyal yoktu. Eski rapor karşılaştırma için
  `output/production/characters/kaito/v6/drift-report.json` altında duruyor.

---

## 5. Animasyon katmanına geçiş

Animasyon orchestrator'ı üç şey ister ve üçü de yukarıdaki adımlardan çıkar:

| Kapı | Nereden gelir |
|---|---|
| `keyframe_approved` | İnsan keyframe onayı (ayrı bir kapı) |
| Pose-pack makbuzu | §3 `pose-pack-approval.json` |
| View-pack onayı | §1 `view-pack-approval.json` |

Bunların üstünde bir de **kilitli senaryo** vardır: `preproduction plan`,
`ScriptBreakdownService.parse_episode` üzerinden `LOCKED` olmayan senaryoyu
reddeder (§0.5).

Animasyon üretiminin kendisi hâlâ ADR-009 (Wan execution contract) nedeniyle
fake/sınır katmanındadır; bu doküman o sözleşmeyi açmaz, yalnız ön koşullarını
tamamlar.
