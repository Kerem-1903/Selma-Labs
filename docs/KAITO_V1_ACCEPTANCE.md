# Kaito v1 — Üretim Öncesi Kabul Listesi

Kaito için kaynak brief kilitlidir. Brief değişirse hash kilidi eşleşmez ve CLI üretimi başlatmaz.

## Sabit kimlik ayrıntıları

- Tek karakter, tek beden ve tek kafa.
- Kısa siyah saçta tam olarak bir adet `#0047AB` kobalt çizgi.
- Çizgi karakterin solundadır; ön görünüşte izleyicinin sağına düşer.
- Çanta karakterin sağ kalçasındadır; askı karakterin sol omzundan geçer.
- Asimetrik ayrıntılar sağ/sol görünüşlerde aynalanmaz.

## İnsan onayı

Yedi görünüş temas sayfasında birlikte incelenir. Yüz, saç, renk, kıyafet, vücut oranı, çanta tarafı ve arka görünüş kabul edilmeden `approve-view-pack` çalıştırılmaz. Makine tarafından kullanılan tam liste [kaito-v1.json](../config/character_acceptance/kaito-v1.json) dosyasındadır.

## İmzalı kabul (zorunlu)

`approve-view-pack` artık kabul listesini **zorunlu** uygular:

1. Kabul dosyası (`config/character_acceptance/kaito-v1.json`) bulunmadan onay reddedilir.
2. Kabul dosyasının `character_id`/`character_version` değerleri istekle, `brief_hash` değeri görünüş paketinin brief hash'iyle eşleşmelidir.
3. Listedeki **her insan maddesi** ayrı bir `--check <id>` bayrağıyla açıkça imzalanmalıdır; eksik madde onayı reddeder.
4. `required_evidence` listesindeki kanıt dosyaları (kök altında) mevcut olmalıdır.

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
  --check single_person_no_collage_no_text \
  --check back_view_no_face
```

Onay makbuzu (`view-pack-approval.json`) görünüş hash'lerine ek olarak şunları içerir:

- `acceptance_sha256` — onayda kullanılan kabul dosyasının birebir SHA-256 özeti
- `human_checks` — imzalanan her maddenin `id` + `label` çifti
- `verified_evidence` — doğrulanmış kanıt dosyası yolları

## Geçiş koşulu

Poz üretimine yalnızca `canonical-approval.json`, iki anchor, QC geçmişi, temas sayfası ve `view-pack-approval.json` mevcutsa geçilir. Başarısız çıktılar üretim klasörüne alınmaz; kendi çalışma kimliği altındaki karantinada kalır.

Otomatik maddeler (`automatic_checks`) üretim anında QC/framing kapılarınca uygulanır; makbuz bunları görünüş paketinin QC kanıtı ve `manifest.json` satır bilgisi üzerinden kayda geçirir.
