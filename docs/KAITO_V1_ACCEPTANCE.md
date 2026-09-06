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

## Geçiş koşulu

Poz üretimine yalnızca `canonical-approval.json`, iki anchor, QC geçmişi, temas sayfası ve `view-pack-approval.json` mevcutsa geçilir. Başarısız çıktılar üretim klasörüne alınmaz; kendi çalışma kimliği altındaki karantinada kalır.
